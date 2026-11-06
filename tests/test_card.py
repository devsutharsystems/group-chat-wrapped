from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

import conftest
from gcw import card
from gcw.dataset import verify_dataset
from gcw.parser import parse_chat
from gcw.stats import compute_stats
from test_stats import COLUMNS, FROZEN, ROWS, frame, raw_messages

ROOT = Path(__file__).resolve().parent.parent
FROZEN_PATH = ROOT / "synthetic" / "frozen" / "chat_synthetic.txt"


# ---------------------------------------------------------------- helpers
# the session `browser` fixture and its BROWSER_CREATED flag live in tests/conftest.py (shared with tests/test_card_ai.py)


def assert_no_session_browser() -> None:
    """The subprocess render tests start their own Chromium, so they must run BEFORE the session browser exists."""
    assert not conftest.BROWSER_CREATED, ("one-browser rule broken: the session browser already exists, so a second Chromium would start. "
                                 "Keep the subprocess render tests above every test that uses the `browser` fixture (or run them alone).")


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip, self.tags, self.attrs = [], 0, [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [k for k, _ in attrs]
        self.skip += tag in ("style", "title")

    def handle_endtag(self, tag):
        self.skip -= tag in ("style", "title")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def parsed(html: str) -> _Text:
    p = _Text()
    p.feed(html)
    return p


def visible_text(html: str) -> str:
    """Visible text with numbers' thousands separators removed and whitespace normalised."""
    text = " ".join(" ".join(parsed(html).parts).split())
    return re.sub(r"(?<=\d),(?=\d{3})", "", text)


ROW = re.compile(r'<div class="row"><span class="rk">(\d)</span><span class="nm[^"]*">(.*?)<span class="bar"[^>]*></span></span>'
                 r'<span class="num( lead)?">([\d,]+)</span><span class="num( lead)?">([\d,]+)</span></div>')


def leaderboard(html: str) -> list[dict]:
    return [{"rank": int(r), "name": n, "messages": int(m.replace(",", "")), "words": int(w.replace(",", "")), "lead_msg": bool(lm), "lead_words": bool(lw)}
            for r, n, lm, m, lw, w in ROW.findall(html)]


def png_size(png: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(png)).size


def busy_frame(names: list[str], year: int = 2026) -> pd.DataFrame:
    """Every sender talks in morning, noon and night blocks on two days, so every tile and the leaderboard are populated."""
    rows, n = [], 0
    for day in ("03-02", "03-03"):
        for start_h, count in ((5, 40), (12, 40), (22, 40)):
            for k in range(count):
                n += 1
                total = start_h * 60 + k
                text = "see https://example.com/x" if k == 3 else ("lol \U0001F602" if k == 5 else f"message {k}")
                rows.append((n, f"{day} {total // 60:02d}:{total % 60:02d}", names[k % len(names)], text, ""))
    return frame(rows, year)


def render_case(browser, stats: dict, **kw) -> dict:
    html = card.build_card_html(stats, **kw)
    res = card.render_png(html, browser=browser, measure=True)
    return {"html": html, **res}


def assert_clean(res: dict) -> None:
    ov = res["overflow"]
    assert ov["bad"] == [], ov["bad"][:5]
    assert ov["root"] == [1080, 1080, 1350, 1350] and ov["card"] == [1080, 1350]
    assert ov["zone2"] == [984, card.ZONE2_HEIGHT] and card.ZONE2_HEIGHT == 460  # the reserved AI block, same size in every mode
    assert png_size(res["png"]) == (1080, 1350)


# ---------------------------------------------------------------- subprocess tests FIRST
# These start their own Chromium in a child process. They sit above every test that uses the session-scoped
# `browser` fixture so that only one browser exists at a time (the fixture is created lazily at first use).
# ---------------------------------------------------------------- stats-only path: no anthropic, end to end
def _env() -> dict:
    import os

    return {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / ".cache" / "ms-playwright")}


def test_cli_and_card_never_import_anthropic():
    code = "import sys, gcw.cli, gcw.card; bad = [m for m in ('anthropic', 'gcw.llm', 'gcw.cost') if m in sys.modules]; sys.exit(1 if bad else 0)"
    r = subprocess.run([sys.executable, "-c", code], env=_env(), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_cli_end_to_end_makes_a_png_without_anthropic(tmp_path):
    assert_no_session_browser()
    lines = [f"3/{2 + (n // 20)}/26, 9:{n % 20:02d} PM - {['Sam', 'Alex'][n % 2]}: message {n}" for n in range(40)]
    chat = tmp_path / "chat.txt"
    chat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = tmp_path / "card.png"
    code = (f"import sys; from gcw.cli import main; rc = main(['stats-card', {str(chat)!r}, '--out', {str(out)!r}]); "
            "sys.exit(rc or (3 if 'anthropic' in sys.modules else 0))")
    r = subprocess.run(["nice", "-n", "10", sys.executable, "-c", code], env=_env(), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert "no API calls made" in r.stdout and png_size(out.read_bytes()) == (1080, 1350)
    assert "AMBIGUOUS" in r.stderr  # a 2-day chat with 12h headers: day/month order is ambiguous and the CLI says so


def test_cli_rejects_missing_file_and_bad_aliases(tmp_path):
    from gcw.cli import main

    assert main(["stats-card", str(tmp_path / "nope.txt")]) == 2
    chat = tmp_path / "c.txt"
    chat.write_text("3/2/26, 9:00 PM - Sam: hi\n", encoding="utf-8")
    bad = tmp_path / "a.json"
    bad.write_text("[1]")
    assert main(["stats-card", str(chat), "--aliases", str(bad)]) == 2
    chat.write_text("nothing parseable here\n", encoding="utf-8")
    assert main(["stats-card", str(chat), "--out", str(tmp_path / "o.png")]) == 3


def test_one_browser_guard_fires_when_a_session_browser_exists(monkeypatch):
    assert_no_session_browser()  # passes now: nothing has created the session browser yet in this ordering
    monkeypatch.setattr(conftest, "BROWSER_CREATED", True)
    with pytest.raises(AssertionError, match="one-browser rule broken"):
        assert_no_session_browser()


def test_python_m_gcw_works_from_a_non_editable_install(tmp_path):
    """Cannot skip: install the project (no deps) into a scratch target, then run `python -m gcw --help` with PYTHONPATH set
    ONLY to that target (no src), from another directory."""
    import os

    target = ROOT / ".cache" / "tmp" / "site"
    shutil.rmtree(target, ignore_errors=True)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PIP_CACHE_DIR"] = str(ROOT / ".cache" / "pip")
    inst = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(ROOT)], env=env, capture_output=True, text=True)
    assert inst.returncode == 0, inst.stderr[-500:]
    env["PYTHONPATH"] = str(target)  # only the installed copy: no src
    r = subprocess.run([sys.executable, "-m", "gcw", "--help"], env=env, cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0 and "stats-card" in r.stdout, r.stderr[-300:]
    where = subprocess.run([sys.executable, "-c", "import gcw; print(gcw.__file__)"], env=env, cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    assert where.startswith(str(target)), where  # really the installed copy, not src
    # the packaged keyword list must load from the installed copy (importlib.resources), with no src and no repo config directory
    code = ("from gcw.privacy import sensitive_screen, load_keywords; import gcw.privacy as p; "
            "assert sensitive_screen('I need a doctor') and not sensitive_screen('Sounds fine.'); "
            "assert 'fined' in load_keywords()['legal']; print(p.__file__)")
    r = subprocess.run([sys.executable, "-c", code], env=env, cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip().startswith(str(target)), r.stderr[-400:]
    assert (target / "gcw" / "data" / "sensitive_keywords.json").is_file()


def test_chromium_is_launched_with_disable_gpu_scale_1_and_closed():
    """Runs in a subprocess (Playwright's sync API cannot nest) under nice, and before the session browser exists."""
    assert_no_session_browser()
    assert card.CHROMIUM_ARGS == ["--disable-gpu"]
    code = ("import sys; from gcw import card\n"
            "with card.chromium() as b:\n"
            "    assert b.is_connected()\n"
            "    r = card.render_png('<!doctype html><p>x</p>', browser=b, measure=True, probe='window.devicePixelRatio')\n"
            "    assert r['probe'] == 1, r['probe']\n"
            "    assert b.contexts == [], b.contexts\n"
            "assert not b.is_connected()\n")
    r = subprocess.run(["nice", "-n", "10", sys.executable, "-c", code], env=_env(), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------- pure helpers (no browser)
def test_clean_name_strips_bidi_and_truncates_to_30():
    assert card.clean_name("Sam‮‎ x") == "Sam x"
    assert card.clean_name("a" * 30) == "a" * 30
    n = card.clean_name("b" * 31)
    assert len(n) == 30 and n.endswith("…")
    assert card.clean_name("  ‮ ") == "?"
    assert "\U0001F468‍\U0001F469" in card.clean_name("x \U0001F468‍\U0001F469 y")  # ZWJ sequences survive in names


def test_duration_and_response_formats():
    assert card.fmt_duration(14 * 24 + 21 + 56 / 60) == "14d 21h 56m"  # 14 days, 21 hours, 56 minutes
    assert card.fmt_duration(0.999) == "1h 0m" and card.fmt_duration(0.0) == "0m"  # 59.94 minutes rounds up to a full hour (int() would say 59m)
    assert card.fmt_duration(13.5) == "13h 30m" and card.fmt_duration(6.0) == "6h 0m" and card.fmt_duration(0.5) == "30m"
    assert card.fmt_response(0) == "under 1 min" and card.fmt_response(59) == "under 1 min"
    assert card.fmt_response(60) == "1 min" and card.fmt_response(90) == "1.5 min"


def test_aliases_load_and_validate(tmp_path):
    assert card.load_aliases(ROOT / "aliases.example.json")  # the committed example parses
    good = tmp_path / "a.json"
    good.write_text('{"Zed": "Z"}')
    assert card.load_aliases(good) == {"Zed": "Z"}
    for bad in ('["x"]', '{"a": 1}', '{"a": {"b": "c"}}'):
        f = tmp_path / "b.json"
        f.write_text(bad)
        with pytest.raises(ValueError):
            card.load_aliases(f)


def test_aliases_change_display_only():
    stats = compute_stats(frame([(1, "03-02 10:00", "Zed", "x", ""), (2, "03-02 10:01", "Amy", "y", ""), (3, "03-02 10:02", "Zed", "z", "")]))
    text = visible_text(card.build_card_html(stats, {"Zed": "Display <Z>", "Amy": "Display A"}))
    assert "Display <Z>" in text and "Display A" in text and "Zed" not in text and "Amy" not in text
    assert [t["sender"] for t in stats["top_talkers"]["by_messages"]] == ["Zed", "Amy"]  # stats keep the export names
    assert "&lt;Z&gt;" in card.build_card_html(stats, {"Zed": "Display <Z>"})


def test_example_aliases_file_is_committed_and_real_one_is_ignored():
    assert (ROOT / "aliases.example.json").is_file()
    assert "aliases.json" in (ROOT / ".gitignore").read_text().split()


# ---------------------------------------------------------------- fastest responder rule (20 samples)
def alternating(pairs: int) -> pd.DataFrame:
    rows = []
    for i in range(pairs):  # A speaks, then B replies one minute later: B gets `pairs` samples, A gets `pairs - 1`
        rows.append((2 * i + 1, f"03-02 {(i * 2) // 60 + 8:02d}:{(i * 2) % 60:02d}", "A", "q", ""))
        rows.append((2 * i + 2, f"03-02 {(i * 2 + 1) // 60 + 8:02d}:{(i * 2 + 1) % 60:02d}", "B", "a", ""))
    return frame(rows)


def test_fastest_responder_needs_20_samples():
    s20 = compute_stats(alternating(20))
    assert (s20["response_time"]["A"]["n"], s20["response_time"]["B"]["n"]) == (19, 20)
    assert card.fastest_responder(s20) == {"sender": "B", "median_seconds": 60.0, "n": 20}  # B has exactly 20; A has 19
    s19 = compute_stats(alternating(19))
    assert (s19["response_time"]["A"]["n"], s19["response_time"]["B"]["n"]) == (18, 19)
    assert card.fastest_responder(s19) is None


def test_fastest_responder_hand_table_nobody_qualifies():
    stats = compute_stats(frame())
    assert {s: v["n"] for s, v in stats["response_time"].items()} == {"Sam": 2, "Alex": 2, "Maya": 4}
    assert card.fastest_responder(stats) is None
    t = visible_text(card.build_card_html(stats))
    assert "Fastest responder" not in t and "Busiest slot Monday 08:00 4 messages" in t  # hand table: Monday 08:00 has rows 2-5


def test_fastest_responder_tie_goes_to_earlier_name():
    stats = {"response_time": {"Zed": {"median_seconds": 60.0, "n": 30}, "Amy": {"median_seconds": 60.0, "n": 25}, "Bob": {"median_seconds": 30.0, "n": 5}}}
    assert card.fastest_responder(stats, min_gap=0)["sender"] == "Amy"  # Bob is faster but has only 5 samples; gap rule switched off here
    assert card.fastest_responder(stats) is None  # tie = 0 s gap, under the 120 s rule


def synthetic_response_stats(gap: float) -> dict:
    return {"response_time": {"Ann": {"median_seconds": 0.0, "n": 50}, "Ben": {"median_seconds": gap, "n": 50}}}


def test_fastest_responder_needs_a_120s_gap():
    assert card.fastest_responder(synthetic_response_stats(119.0)) is None
    assert card.fastest_responder(synthetic_response_stats(60.0)) is None  # the frozen chat: exactly 60 s
    assert card.fastest_responder(synthetic_response_stats(120.0)) == {"sender": "Ann", "median_seconds": 0.0, "n": 50}


def test_fastest_responder_tile_shows_with_a_120s_gap_and_is_replaced_otherwise(frozen_card):
    stats, html = frozen_card
    base = {**stats, "response_time": synthetic_response_stats(120.0)["response_time"]}
    t = visible_text(card.build_card_html(base))
    assert "Fastest responder Ann 50 replies" in t and "Busiest slot" not in t
    close = {**stats, "response_time": synthetic_response_stats(60.0)["response_time"]}
    t = visible_text(card.build_card_html(close))
    assert "Fastest responder" not in t and "Busiest slot Saturday 22:00 285 messages" in t


# ---------------------------------------------------------------- frozen chat values on the card
@pytest.fixture(scope="module")
def frozen_card():
    verify_dataset()  # fail loudly if the data is not the frozen version
    df, report = parse_chat(FROZEN_PATH)
    stats = compute_stats(df)
    return stats, card.build_card_html(stats)


def test_frozen_card_text_has_the_counted_values(frozen_card):
    _, html = frozen_card
    t = visible_text(html)
    board = {r["name"]: r for r in leaderboard(html)}
    assert board["Riley"]["messages"] == 1316 and board["Maya"]["words"] == 22872  # same values, now read from the top-talkers table
    assert [r["name"] for r in leaderboard(html) if r["lead_msg"]] == ["Riley"] and [r["name"] for r in leaderboard(html) if r["lead_words"]] == ["Maya"]  # two different leaders
    for want in ["14d 21h 56m", "2026-02-07" + " 201 messages", "1121 emoji", "2 links", "136 media",
                 "Night owl Maya", "Early bird Jordan", "By the numbers", "From the chat", "AI sections off (stats-only mode)", "Counted locally. No AI used."]:
        assert want in t, want
    assert "+1 more" in t  # 6 senders: top 5 shown plus one more


def test_frozen_fastest_responder_and_top_starter_from_plain_loops(frozen_card):
    stats, html = frozen_card
    raw = raw_messages()
    delays, starts = {}, {}
    for a, b in zip(raw, raw[1:]):
        gap = (b[0] - a[0]).total_seconds()
        if gap >= 6 * 3600:
            starts[b[1]] = starts.get(b[1], 0) + 1
        if a[1] != b[1] and 0 <= gap <= 3600:
            delays.setdefault(b[1], []).append(gap)

    def median(v):
        v = sorted(v)
        return v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2

    qual = sorted((median(v), s) for s, v in delays.items() if len(v) >= 20)
    best = max(starts.values())
    tied = sorted(s for s, v in starts.items() if v == best)
    t = visible_text(html)
    assert qual[0][1] == "Riley" and qual[1][0] - qual[0][0] == 60  # first place leads by exactly 60 s: under the 120 s rule
    assert card.fastest_responder(stats) is None and "Fastest responder" not in t and "Busiest slot Saturday 22:00 285 messages" in t
    assert tied == ["Maya", "Riley"] and f"Top starter {tied[0]} {best} starts, tied with {tied[1]}" in t


def test_png_size(frozen_card, browser):
    _, html = frozen_card
    res = card.render_png(html, browser=browser, measure=True)
    assert browser.contexts == []  # the page's context is closed right after the render
    assert png_size(res["png"]) == (1080, 1350)
    assert res["png"][:8] == b"\x89PNG\r\n\x1a\n"
    assert res["overflow"]["bad"] == [], res["overflow"]["bad"][:5]


# ---------------------------------------------------------------- layout robustness (measured overflow must be 0)
LONG30 = "Alexandria Bartholomew-Smythe!"  # 30 characters
assert len(LONG30) == 30


@pytest.mark.parametrize("label, names", [
    ("30-character names", [LONG30, "W" * 30, "M" * 30]),
    ("2-person chat", ["Sam", "Alex"]),
    ("single sender", ["Sam"]),
    ("12 members", [f"Member {i:02d}" for i in range(1, 13)]),
])
def test_layout_cases_have_no_overflow(browser, label, names):
    res = render_case(browser, compute_stats(busy_frame(names)))
    assert_clean(res)
    text = visible_text(res["html"])
    if label == "12 members":
        assert "+7 more" in text and "Member 06" not in text.split("Top talkers")[1].split("Night owl")[0]  # 5 shown, 7 hidden
    if label == "30-character names":
        assert LONG30 in text and "W" * 30 in text


def test_words_leader_outside_top_five_is_named_in_the_more_row(browser):
    names = [f"Member {i:02d}" for i in range(1, 13)]
    df = busy_frame(names)
    df.loc[df["sender"] == "Member 12", "text"] = "a very long message with many many words in it " * 3
    res = render_case(browser, compute_stats(df))
    assert_clean(res)
    t = visible_text(res["html"])
    assert "+7 more · most words: Member 12" in t
    assert not [r for r in leaderboard(res["html"]) if r["lead_words"]]  # the words leader is not among the 5 rows shown


def test_layout_empty_window(browser):
    res = render_case(browser, compute_stats(frame([])))
    assert_clean(res)
    t = visible_text(res["html"])
    assert "No messages in this window" in t and "Counted locally. No AI used." in t


def test_layout_name_longer_than_30_is_truncated_not_overflowing(browser):
    res = render_case(browser, compute_stats(busy_frame(["X" * 45, "Sam"])))
    assert_clean(res)
    assert "X" * 45 not in res["html"] and "X" * 29 + "…" in res["html"]


def test_layout_ambiguous_date_note(browser):
    res = render_case(browser, compute_stats(busy_frame(["Sam", "Alex"])), date_note="Dates read as m/d (assumed)")
    assert_clean(res)
    assert "Dates read as m/d (assumed)" in visible_text(res["html"])


# ---------------------------------------------------------------- the renderer blocks the network
def test_network_requests_are_blocked(browser):
    html = '<!doctype html><html><body><p>hi</p><img src="http://example.invalid/x.png"><link rel="stylesheet" href="https://example.invalid/s.css"></body></html>'
    log: list = []
    res = card.render_png(html, browser=browser, request_log=log)
    assert png_size(res["png"]) == (1080, 1350)
    urls = {u for k, u in log if k == "aborted"}
    assert "http://example.invalid/x.png" in urls and "https://example.invalid/s.css" in urls  # both were routed and aborted
    assert {u for k, u in log if k == "failed"} >= urls  # and the browser reports them as failed
    assert not [u for k, u in log if k == "response"]  # no request got any response
    # the failure came from the route abort (ERR_FAILED), not merely from the offline flag (ERR_INTERNET_DISCONNECTED)
    reasons = [u for k, u in log if k == "reason"]
    assert reasons and all("ERR_FAILED" in r and "DISCONNECTED" not in r for r in reasons), reasons


def test_context_is_offline_and_page_has_a_locked_down_csp(browser, frozen_card):
    _, html = frozen_card
    assert "Content-Security-Policy" in html and "default-src 'none'" in html and "<script" not in html.lower()
    res = card.render_png(html, browser=browser, measure=True, probe="({online: navigator.onLine, dpr: window.devicePixelRatio, w: innerWidth, h: innerHeight})")
    assert res["probe"] == {"online": False, "dpr": 1, "w": 1080, "h": 1350}


# ---------------------------------------------------------------- untrusted names are escaped
def test_hostile_names_are_escaped_text_not_markup(browser):
    evil1 = "<b onclick=x>Sam</b>"
    evil2 = '<img src=x onerror="window.__pwned=1">'
    rows = [(i, f"03-02 10:{i:02d}", [evil1, evil2, "Amy"][i % 3], "hello", "") for i in range(1, 10)]
    stats = compute_stats(frame(rows))
    html = card.build_card_html(stats)
    assert "&lt;b onclick=x&gt;Sam&lt;/b&gt;" in html and "<b onclick" not in html and "<img" not in html
    p = parsed(html)
    assert "b" not in p.tags and "img" not in p.tags and not {"onclick", "onerror"} & set(p.attrs)
    assert evil1 in visible_text(html)  # shown literally as text
    res = card.render_png(html, browser=browser, measure=True,
                          probe="({pwned: typeof window.__pwned, onclick: document.querySelectorAll('[onclick]').length, onerror: document.querySelectorAll('[onerror]').length, b: document.querySelectorAll('.card b').length})")
    assert res["probe"] == {"pwned": "undefined", "onclick": 0, "onerror": 0, "b": 0}
    assert res["overflow"]["bad"] == []


def test_emoji_in_names_and_emoji_stats_are_escaped_safely():
    stats = compute_stats(frame([(1, "03-02 10:00", "Sam <3 \U0001F602", "lol \U0001F602 <script>x</script>", "")]))
    html = card.build_card_html(stats)
    assert "<script>" not in html and "Sam &lt;3 \U0001F602" in html
