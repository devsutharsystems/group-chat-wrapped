from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from gcw.dataset import verify_dataset
from gcw.stats import compute_stats, emoji_clusters

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "synthetic" / "frozen" / "chat_synthetic.txt"
MEDIA = "<Media omitted>"
FAMILY = "\U0001F468‍\U0001F469‍\U0001F467"
THUMB = "\U0001F44D\U0001F3FD"
LAUGH_FACE = "\U0001F602"
HEART = "❤️"

# ---------------------------------------------------------------- the hand table (see the plan; values below are hand-computed)
ROWS = [
    # (n, "MM-DD HH:MM", sender, text, flag)
    (1, "03-02 07:55", None, "Alex was added", "system"),
    (2, "03-02 08:00", "Sam", "good morning all", ""),
    (3, "03-02 08:20", "Alex", "morning haha", ""),
    (4, "03-02 08:25", "Maya", MEDIA, "media"),
    (5, "03-02 08:25", "Sam", "https://example.com/a?x=1 look at this", ""),
    (6, "03-02 09:30", "Alex", f"lol {LAUGH_FACE}{LAUGH_FACE}", ""),
    (7, "03-02 10:00", "Maya", f"sure {HEART}", ""),
    (8, "03-02 10:05", "Sam", "You deleted this message", "deleted"),
    (9, "03-02 23:30", "Alex", f"night owl post {THUMB}", ""),
    (10, "03-02 23:50", "Maya", f"{FAMILY} family", ""),
    (11, "03-03 02:00", "Sam", "up late", ""),
    (12, "03-03 02:30", "Maya", f"hahaha {LAUGH_FACE * 3} same", ""),
    (13, "03-03 06:00", "Alex", "early bird here", ""),
    (14, "03-03 06:10", "Sam", "good morning again", ""),
    (15, "03-03 12:00", "Sam", "lunch?", ""),
    (16, "03-03 12:40", "Alex", "yes https://example.com/b and http://example.com/c", ""),
    (17, "03-03 18:40", "Sam", MEDIA, "media"),
]


COLUMNS = ["id", "ts", "sender", "text", "is_media", "is_deleted", "is_edited", "is_system"]


def frame(rows=ROWS, year=2026) -> pd.DataFrame:
    return pd.DataFrame([{
        "id": f"m{n:06d}", "ts": pd.Timestamp(f"{year}-{t}"), "sender": s, "text": text,
        "is_media": flag == "media", "is_deleted": flag == "deleted", "is_edited": False, "is_system": flag == "system",
    } for n, t, s, text, flag in rows], columns=COLUMNS)


@pytest.fixture(scope="module")
def st() -> dict:
    return compute_stats(frame())


def test_population_and_window(st):
    assert st["window"]["n_messages"] == 15  # 17 rows minus 1 system minus 1 deleted
    assert st["window"]["until"] == "2026-03-03T18:40:00" and st["window"]["since"] == "2025-03-03T18:40:00"
    assert st["senders"] == ["Sam", "Alex", "Maya"]


def test_top_talkers(st):
    assert st["top_talkers"]["by_messages"] == [{"sender": "Sam", "messages": 6}, {"sender": "Alex", "messages": 5}, {"sender": "Maya", "messages": 4}]
    assert st["top_talkers"]["by_words"] == [{"sender": "Alex", "words": 15}, {"sender": "Sam", "words": 13}, {"sender": "Maya", "words": 7}]


def test_busiest_hour_weekday_date(st):
    b = st["busiest"]
    counts = [0] * 24
    for h, n in {2: 2, 6: 2, 8: 4, 9: 1, 10: 1, 12: 2, 18: 1, 23: 2}.items():
        counts[h] = n
    assert b["hour_counts"]["overall"] == counts and b["hour"]["overall"] == 8
    assert b["hour"]["per_sender"] == {"Sam": 8, "Alex": 6, "Maya": 2}  # Alex and Maya tie: earliest hour
    assert b["weekday_counts"]["overall"]["Monday"] == 8 and b["weekday_counts"]["overall"]["Tuesday"] == 7
    assert b["weekday"]["overall"] == "Monday"
    assert b["weekday"]["per_sender"] == {"Sam": "Tuesday", "Alex": "Monday", "Maya": "Monday"}
    assert st["busiest_date"] == {"date": "2026-03-02", "messages": 8}


def test_night_owl_early_bird_bands(st):
    ne = st["night_early"]
    assert ne["min_messages"] == 30 and ne["night_owl"] is None and ne["early_bird"] is None  # nobody has 30 messages
    assert not any(v["qualifies"] for v in ne["per_sender"].values())
    sh = {s: (v["night_share"], v["early_share"], v["leaning"]) for s, v in ne["per_sender"].items()}
    assert sh == {"Sam": (1 / 6, 3 / 6, "early"), "Alex": (1 / 5, 2 / 5, "early"), "Maya": (2 / 4, 1 / 4, "night")}


def test_bands_winners_with_lower_minimum():
    ne = compute_stats(frame(), min_messages_for_bands=4)["night_early"]
    assert ne["night_owl"] == "Maya" and ne["early_bird"] == "Sam"
    assert all(v["qualifies"] for v in ne["per_sender"].values())
    ne5 = compute_stats(frame(), min_messages_for_bands=5)["night_early"]  # Maya (4 messages) drops out
    assert ne5["per_sender"]["Maya"]["qualifies"] is False and ne5["night_owl"] == "Alex" and ne5["early_bird"] == "Sam"


def test_longest_silence_ignores_deleted_message(st):
    s = st["longest_silence"]
    assert (s["start"], s["end"]) == ("2026-03-02T10:00:00", "2026-03-02T23:30:00") and s["hours"] == 13.5


def test_conversation_starters(st):
    # row 9 (13.5h gap) -> Alex; row 17 (gap of exactly 6h) -> Sam; the first message (row 2) is not a starter
    assert st["starters"] == {"Sam": 1, "Alex": 1, "Maya": 0}


def test_median_response_times(st):
    rt = st["response_time"]
    assert rt["Alex"] == {"median_seconds": 1800.0, "n": 2}  # 1200, 2400
    assert rt["Maya"] == {"median_seconds": 1500.0, "n": 4}  # 300, 1200, 1800, 1800
    assert rt["Sam"] == {"median_seconds": 300.0, "n": 2}  # 0, 600


def test_laughs_emojis_media_links(st):
    assert st["laughs"] == {"total": 3, "per_sender": {"Sam": 0, "Alex": 2, "Maya": 1}}
    assert st["emojis"]["total"] == 8 and st["emojis"]["per_sender"] == {"Sam": 0, "Alex": 3, "Maya": 5}
    assert st["emojis"]["top"] == [{"emoji": LAUGH_FACE, "count": 5}, {"emoji": HEART, "count": 1}, {"emoji": THUMB, "count": 1}, {"emoji": FAMILY, "count": 1}]
    assert st["media"] == {"total": 2, "per_sender": {"Sam": 1, "Alex": 0, "Maya": 1}}
    assert st["links"] == {"total": 3, "per_sender": {"Sam": 1, "Alex": 2, "Maya": 0}}


def test_json_serialisable_and_round_trips(st):
    assert json.loads(json.dumps(st)) == st


# ---------------------------------------------------------------- windows
def test_since_date_means_start_of_day():
    s = compute_stats(frame(), since=date(2026, 3, 3))
    assert s["window"]["n_messages"] == 7  # rows 11-17
    assert s["top_talkers"]["by_messages"] == [{"sender": "Sam", "messages": 4}, {"sender": "Alex", "messages": 2}, {"sender": "Maya", "messages": 1}]
    assert s["busiest_date"] == {"date": "2026-03-03", "messages": 7}
    assert s["starters"] == {"Sam": 1, "Alex": 0, "Maya": 0}  # row 11 is first in the window, so not a starter; row 17 is 6h after row 16
    assert s["longest_silence"]["hours"] == 6.0 and s["longest_silence"]["start"] == "2026-03-03T12:40:00"


def test_until_date_is_inclusive_end_of_day():
    s = compute_stats(frame(), until=date(2026, 3, 2))
    assert s["window"]["n_messages"] == 8  # rows 2-7, 9, 10
    assert s["window"]["until"] == "2026-03-02T23:59:59.999999"


def test_timestamp_bounds_are_inclusive():
    t = pd.Timestamp("2026-03-02T08:20")
    assert compute_stats(frame(), since=t)["window"]["n_messages"] == 14  # row 3 (08:20) is in, row 2 (08:00) is out
    assert compute_stats(frame(), until=t)["window"]["n_messages"] == 2  # rows 2 and 3
    assert compute_stats(frame(), since="2026-03-03")["window"]["n_messages"] == 7  # ISO date string


def test_default_window_is_365_days_before_last_message_inclusive():
    rows = ROWS + [(18, "03-03 18:40", "Sam", "boundary", "")]
    df = frame(rows)
    old = frame([(19, "01-01 12:00", "Sam", "too old", "")], year=2025)  # ~14 months before the last message
    edge = frame([(20, "03-03 18:40", "Sam", "exactly 365 days before", "")], year=2025)  # same clock time one year earlier = last message minus 365 days
    s = compute_stats(pd.concat([old, edge, df], ignore_index=True))
    assert s["window"]["n_messages"] == 15 + 1 + 1  # +1 boundary row at the last instant, +1 edge row; the old row is out
    assert s["window"]["since"] == "2025-03-03T18:40:00"


def test_last_message_is_taken_from_non_deleted_messages():
    rows = ROWS + [(18, "03-05 09:00", "Sam", "You deleted this message", "deleted")]
    assert compute_stats(frame(rows))["window"]["until"] == "2026-03-03T18:40:00"


# ---------------------------------------------------------------- ties and empty input
def test_ties_break_alphabetically_and_earlier():
    df = frame([(1, "03-02 10:00", "Zed", "aa", ""), (2, "03-02 10:10", "Amy", "bb", ""), (3, "03-02 11:00", "Zed", "cc dd", ""), (4, "03-02 11:10", "Amy", "ee", "")])
    s = compute_stats(df)
    assert [t["sender"] for t in s["top_talkers"]["by_messages"]] == ["Amy", "Zed"]  # 2 each: A-Z
    assert [t["sender"] for t in s["top_talkers"]["by_words"]] == ["Zed", "Amy"]  # 3 v 2 words
    assert s["busiest"]["hour"]["overall"] == 10  # hours 10 and 11 tie 2-2: earlier hour
    assert s["busiest_date"]["messages"] == 4


def test_longest_silence_tie_keeps_earlier_gap():
    df = frame([(1, "03-02 10:00", "A", "x", ""), (2, "03-02 12:00", "B", "y", ""), (3, "03-02 14:00", "A", "z", "")])
    s = compute_stats(df)["longest_silence"]
    assert (s["start"], s["end"], s["hours"]) == ("2026-03-02T10:00:00", "2026-03-02T12:00:00", 2.0)


def test_empty_and_all_system_frames_are_well_formed():
    for df in (frame([]), frame([(1, "03-02 10:00", None, "Alex was added", "system")])):
        s = compute_stats(df)
        assert s["window"]["n_messages"] == 0 and s["senders"] == [] and s["longest_silence"] is None and s["busiest_date"] is None
        assert s["emojis"] == {"total": 0, "per_sender": {}, "top": []} and s["night_early"]["night_owl"] is None
        assert json.loads(json.dumps(s)) == s


def test_bad_bound_type_raises():
    with pytest.raises(TypeError):
        compute_stats(frame(), since=12345)


# ---------------------------------------------------------------- emoji and laugh units (hand counts)
@pytest.mark.parametrize("text, want", [
    ("\U0001F600 \U0001F60D \U0001F973 ❤️ \U0001F525 ✨ \U0001F338 \U0001F389", 8),  # the verified emoji line
    (f"hahaha {LAUGH_FACE * 3}", 3),
    (HEART, 1), (FAMILY, 1), (THUMB, 1),
    ("\U0001F1EE\U0001F1F3", 1),  # flag
    ("1️⃣", 1),  # keycap
    ("✔ and ☀", 2),  # bare text-style symbols count (decision)
    ("(c) 2026 #1 plain text, digits 123", 0),
    ("a‍b", 0),
])
def test_emoji_clusters(text, want):
    assert len(emoji_clusters(text)) == want


def test_emoji_line_and_haha_line_through_compute_stats():
    df = frame([(1, "03-02 10:00", "Sam", "\U0001F600 \U0001F60D \U0001F973 ❤️ \U0001F525 ✨ \U0001F338 \U0001F389", ""),
                (2, "03-02 10:01", "Sam", f"hahaha {LAUGH_FACE * 3}", "")])
    s = compute_stats(df)
    assert s["emojis"]["total"] == 11 and s["laughs"]["total"] == 1  # 8 + 3 emojis; the second message is 1 laugh message


@pytest.mark.parametrize("text, laugh", [("hahaha", True), ("haha ok", True), ("HAHA", True), ("ha", False), ("hahah", False), ("lol", True), ("LMAO", True),
                                         ("rofl", True), ("lmaooo", True), (LAUGH_FACE, True), ("\U0001F923", True), ("nothing here", False)])
def test_laugh_regex(text, laugh):
    df = frame([(1, "03-02 10:00", "Sam", text, "")])
    assert compute_stats(df)["laughs"]["total"] == int(laugh)


def test_top_emojis_merge_variation_selector():
    df = frame([(1, "03-02 10:00", "Sam", "☀️ ☀️ ☀", "")])  # two with FE0F, one bare
    assert compute_stats(df)["emojis"]["top"] == [{"emoji": "☀️", "count": 3}]


# ---------------------------------------------------------------- stats-only mode makes zero API calls
def test_stats_never_imports_anthropic():
    code = "import sys, gcw.stats; bad = [m for m in ('anthropic', 'gcw.llm', 'gcw.cost') if m in sys.modules]; sys.exit(1 if bad else 0); "
    r = subprocess.run([sys.executable, "-c", code], env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------- known answers on the frozen chat, from plain Python over the raw file
HEADER = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}), (\d{1,2}):(\d{2}) ([AP]M) - (.*)$")


def raw_messages():
    """(ts, sender, text) for sender lines, own parsing, deleted lines dropped. Does not use gcw.parser or gcw.stats."""
    out, cur = [], None
    for ln in FROZEN.read_text(encoding="utf-8").split("\n"):
        m = HEADER.match(ln)
        if m:
            mo, d, y, h, mi, ap, body = m.groups()
            sm = re.match(r"^([^:]+): (.*)$", body)
            cur = None
            if sm:
                hour = int(h) % 12 + (12 if ap == "PM" else 0)
                cur = [datetime(2000 + int(y), int(mo), int(d), hour, int(mi)), sm.group(1), sm.group(2)]
                out.append(cur)
        elif cur is not None and ln:
            cur[2] += "\n" + ln
    suffix = " <This message was edited>"  # a trailing edit marker is not part of the message text
    return [(r[0], r[1], r[2][: -len(suffix)] if r[2].endswith(suffix) else r[2]) for r in out if r[2] != "You deleted this message"]


@pytest.fixture(scope="module")
def frozen():
    verify_dataset()  # fail loudly if the data is not the frozen version
    from gcw.parser import parse_chat

    df, _ = parse_chat(FROZEN)
    return compute_stats(df), raw_messages()


def test_frozen_population_and_top_talkers(frozen):
    s, raw = frozen
    assert len(raw) == 5136 and s["window"]["n_messages"] == 5136  # 5144 sender lines minus 8 deletions; the 365-day window holds everything
    assert [t["sender"] for t in s["top_talkers"]["by_messages"]] == ["Riley", "Kai", "Maya", "Sam", "Jordan", "Alex"]
    c = Counter(r[1] for r in raw)
    assert {t["sender"]: t["messages"] for t in s["top_talkers"]["by_messages"]} == dict(c) == {"Riley": 1316, "Kai": 1158, "Maya": 1010, "Sam": 891, "Jordan": 527, "Alex": 234}


def test_frozen_words(frozen):
    s, raw = frozen
    w = Counter()
    for _, sender, text in raw:
        if text != MEDIA:
            w[sender] += len(text.split())
    assert {t["sender"]: t["words"] for t in s["top_talkers"]["by_words"]} == dict(w)
    assert [t["sender"] for t in s["top_talkers"]["by_words"]] == ["Maya", "Kai", "Sam", "Riley", "Jordan", "Alex"]


def test_frozen_longest_silence_contains_the_generated_silence(frozen):
    s, raw = frozen
    gaps = [(b[0] - a[0], a[0], b[0]) for a, b in zip(raw, raw[1:])]
    gap, start, end = max(gaps, key=lambda g: (g[0], -g[1].timestamp()))  # longest, earliest on ties
    sil = s["longest_silence"]
    assert sil["start"] == start.isoformat() and sil["end"] == end.isoformat()
    assert sil["hours"] == pytest.approx(gap.total_seconds() / 3600) and sil["hours"] >= 9 * 24
    gt = json.loads((FROZEN.parent / "ground_truth.json").read_text())
    silence_days = [date.fromisoformat(d) for d in gt["meta"]["silence"]]
    cfg = json.loads((ROOT / "synthetic" / "config.json").read_text())
    assert len(silence_days) == cfg["silence_days"] == 10
    assert start.date() < silence_days[0] and end.date() > silence_days[-1]  # the reported gap contains every generated silent day
    assert not any(start < r[0] < end for r in raw)


def test_frozen_busiest_date_is_the_planted_200_message_burst(frozen):
    s, raw = frozen
    gt = json.loads((FROZEN.parent / "ground_truth.json").read_text())
    moment = [i for i in gt["items"] if i["kind"] == "moment" and i["burst_messages"] == 200][0]
    n = sum(1 for r in raw if r[0].date().isoformat() == moment["date"])
    assert s["busiest_date"] == {"date": moment["date"], "messages": n} and n >= 200


def test_frozen_night_owl_and_early_bird_match_member_profiles(frozen):
    s, raw = frozen
    cfg = json.loads((ROOT / "synthetic" / "config.json").read_text())
    owl = [m["name"] for m in cfg["members"] if "night owl" in m["profile"]]
    bird = [m["name"] for m in cfg["members"] if "early bird" in m["profile"]]
    assert (s["night_early"]["night_owl"], s["night_early"]["early_bird"]) == (owl[0], bird[0])
    for sender in s["senders"]:
        hs = [r[0].hour for r in raw if r[1] == sender]
        night = sum(h >= 22 or h <= 3 for h in hs) / len(hs)
        early = sum(4 <= h <= 8 for h in hs) / len(hs)
        b = s["night_early"]["per_sender"][sender]
        assert b["night_share"] == pytest.approx(night, abs=1e-9) and b["early_share"] == pytest.approx(early, abs=1e-9) and b["qualifies"]
        hc = Counter(hs)
        assert s["busiest"]["hour"]["per_sender"][sender] == min(range(24), key=lambda h: (-hc[h], h))


def test_frozen_emoji_link_media_laugh_counts(frozen):
    s, raw = frozen
    body = "\n".join(r[2] for r in raw)
    # precondition for comparing grapheme clusters with codepoints: no multi-codepoint sequences in this data
    assert not re.search("[‍\U0001F3FB-\U0001F3FF\U0001F1E6-\U0001F1FF⃣]", body)
    cp = re.findall("[\U0001F300-\U0001FAFF☀-➿⭐⭕⌀-⏿]", body)
    assert s["emojis"]["total"] == len(cp) == 1121
    top = Counter(cp).most_common(10)
    assert [(e["emoji"].replace("️", ""), e["count"]) for e in s["emojis"]["top"]] == top
    assert s["links"]["total"] == len(re.findall(r"https?://", body)) == 2
    assert s["media"]["total"] == sum(r[2] == MEDIA for r in raw) == 136
    laugh = re.compile(r"\b(ha){2,}\b|lol|lmao|rofl|\U0001F602|\U0001F923", re.I)
    for sender in s["senders"]:
        assert s["laughs"]["per_sender"][sender] == sum(bool(laugh.search(r[2])) for r in raw if r[1] == sender and r[2] != MEDIA)
        assert s["media"]["per_sender"][sender] == sum(r[2] == MEDIA for r in raw if r[1] == sender)


def test_frozen_starters_and_response_times_cross_check(frozen):
    s, raw = frozen
    starters, delays = Counter(), {}
    for i in range(1, len(raw)):
        gap = (raw[i][0] - raw[i - 1][0]).total_seconds()
        if gap >= 6 * 3600:
            starters[raw[i][1]] += 1
        if raw[i][1] != raw[i - 1][1] and gap <= 3600:
            delays.setdefault(raw[i][1], []).append(gap)
    for sender in s["senders"]:
        assert s["starters"][sender] == starters[sender]
        d = sorted(delays[sender])
        mid = len(d) // 2
        want = d[mid] if len(d) % 2 else (d[mid - 1] + d[mid]) / 2
        assert s["response_time"][sender] == {"median_seconds": want, "n": len(d)}


# ---------------------------------------------------------------- boundaries and tie rules (added after the mutation pass)
def test_response_delay_exactly_one_hour_counts_but_one_second_more_does_not():
    df = frame([(1, "03-02 10:00", "A", "x", ""), (2, "03-02 11:00", "B", "y", ""), (3, "03-02 12:00:01", "A", "z", "")])
    rt = compute_stats(df)["response_time"]
    assert rt["B"] == {"median_seconds": 3600.0, "n": 1}  # exactly 3600 s: counted
    assert rt["A"] == {"median_seconds": None, "n": 0}  # 3601 s: not counted


def test_night_and_early_band_edges_by_the_minute():
    times = ["21:59", "22:00", "23:59", "00:00", "03:59", "04:00", "08:59", "09:00"]
    df = frame([(i, f"03-02 {t}", "X", "word", "") for i, t in enumerate(times, 1)])
    b = compute_stats(df, min_messages_for_bands=1)["night_early"]["per_sender"]["X"]
    # night = 22:00-03:59 -> 22:00, 23:59, 00:00, 03:59 (4 of 8); early = 04:00-08:59 -> 04:00, 08:59 (2 of 8)
    assert (b["night_share"], b["early_share"]) == (4 / 8, 2 / 8)


def test_top_emoji_ties_keep_first_appearance_not_codepoint_order():
    df = frame([(1, "03-02 10:00", "Sam", "\U0001F600 \U0001F389", "")])  # grinning (U+1F600) first, party popper (U+1F389) second
    assert [e["emoji"] for e in compute_stats(df)["emojis"]["top"]] == ["\U0001F600", "\U0001F389"]


def test_night_owl_and_early_bird_ties_go_to_the_earlier_name():
    rows = [(1, "03-02 23:00", "Zed", "a", ""), (2, "03-02 23:10", "Amy", "a", ""), (3, "03-02 05:00", "Zed", "a", ""), (4, "03-02 05:10", "Amy", "a", "")]
    ne = compute_stats(frame(rows), min_messages_for_bands=1)["night_early"]
    assert (ne["night_owl"], ne["early_bird"]) == ("Amy", "Amy")


def test_busiest_date_tie_goes_to_the_earlier_date():
    rows = [(1, "03-03 10:00", "A", "a", ""), (2, "03-03 10:05", "A", "a", ""), (3, "03-02 10:00", "A", "a", ""), (4, "03-02 10:05", "A", "a", "")]
    assert compute_stats(frame(rows))["busiest_date"] == {"date": "2026-03-02", "messages": 2}
