"""Compute the stats defined in docs/PRD.md section 3. Pure pandas/regex: no network, no LLM.

Population: gcw.parser.messages(df) (no system lines, no deleted messages). Media rows stay (they are
messages) except for word counts. Window: [last_msg_ts - 365 days, last_msg_ts], both ends inclusive.
This module must never import anthropic (stats-only mode makes zero API calls).
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

import pandas as pd
import regex

from gcw.parser import messages

WINDOW_DAYS = 365
MIN_BAND_MESSAGES = 30
STARTER_GAP_S = 6 * 3600
RESPONSE_MAX_S = 3600
NIGHT_HOURS = frozenset({22, 23, 0, 1, 2, 3})  # 22:00-03:59
EARLY_HOURS = frozenset({4, 5, 6, 7, 8})  # 04:00-08:59
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TOP_EMOJIS = 10
VS16 = chr(0xFE0F)  # variation selector-16 (emoji presentation); never write it as a raw character in this file

LAUGH = re.compile(r"\b(ha){2,}\b|\b(?:lol+|lmao+|rofl+(?:mao+)?)\b|😂|🤣", re.IGNORECASE)  # PRD: lol/lmao/rofl are whole words (stretched letters ok)
URL = re.compile(r"https?://", re.IGNORECASE)

_GRAPHEME = regex.compile(r"\X")
_PICTO = regex.compile(r"\p{Extended_Pictographic}")
_FLAG = regex.compile(r"\p{Regional_Indicator}{2}")
_KEYCAP = regex.compile(r"[0-9#*]\uFE0F?\u20E3")


NEEDS_VS16 = frozenset(map(chr, (0xA9, 0xAE, 0x2122)))  # (c), (r), TM: count as emoji only with U+FE0F


def emoji_clusters(text: str) -> list[str]:
    """One entry per emoji grapheme cluster: a cluster containing an Extended_Pictographic character
    (so a heart with U+FE0F, a ZWJ family and a skin-toned thumb each count once), a flag, or a keycap.
    Bare text-style symbols such as a heart or sun without U+FE0F count; (c), (r) and TM count only with U+FE0F."""
    out = []
    for c in _GRAPHEME.findall(text):
        core = c if VS16 in c else "".join(ch for ch in c if ch not in NEEDS_VS16)
        if _PICTO.search(core) or _FLAG.fullmatch(c) or _KEYCAP.fullmatch(c):
            out.append(c)
    return out


def _bound(x: Any, *, end: bool) -> pd.Timestamp | None:
    """datetime/Timestamp: as given. date (or 'YYYY-MM-DD'): start of that day, or end of that day (inclusive) for `until`."""
    if x is None:
        return None
    if isinstance(x, str):
        x = date.fromisoformat(x) if len(x) == 10 else pd.Timestamp(x)
    if isinstance(x, datetime):  # includes pd.Timestamp
        return pd.Timestamp(x)
    if isinstance(x, date):
        t = pd.Timestamp(x)
        return t + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1) if end else t
    raise TypeError(f"since/until must be a date, datetime, Timestamp or ISO string, got {type(x).__name__}")


def _iso(t: pd.Timestamp | None) -> str | None:
    return None if t is None else t.isoformat()


def _empty_hours() -> list[int]:
    return [0] * 24


def _busiest_hour(counts: list[int]) -> int | None:
    return min(range(24), key=lambda h: (-counts[h], h)) if any(counts) else None


def _busiest_weekday(counts: dict[str, int]) -> str | None:
    return min(WEEKDAYS, key=lambda d: (-counts[d], WEEKDAYS.index(d))) if any(counts.values()) else None


def compute_stats(df: pd.DataFrame, since: Any = None, until: Any = None, *, min_messages_for_bands: int = MIN_BAND_MESSAGES) -> dict:
    """Return the stats dict (JSON-serialisable). Defaults: the 365 days ending at the last non-deleted message."""
    pop = messages(df)
    lo, hi = _bound(since, end=False), _bound(until, end=True)
    if len(pop):
        last = pop["ts"].max()
        hi = hi if hi is not None else last
        lo = lo if lo is not None else hi - pd.Timedelta(days=WINDOW_DAYS)
        w = pop[(pop["ts"] >= lo) & (pop["ts"] <= hi)]
    else:
        w = pop
    w = w.sort_values("ts", kind="stable")
    ts = list(w["ts"])
    senders_col = list(w["sender"])
    texts = list(w["text"])
    media = list(w["is_media"])

    msg_n: Counter = Counter(senders_col)
    senders = sorted(msg_n, key=lambda s: (-msg_n[s], s))

    words: Counter = Counter({s: 0 for s in senders})
    laughs: Counter = Counter({s: 0 for s in senders})
    medias: Counter = Counter({s: 0 for s in senders})
    links: Counter = Counter({s: 0 for s in senders})
    emoji_per: Counter = Counter({s: 0 for s in senders})
    hours = {s: _empty_hours() for s in senders}
    hours_all = _empty_hours()
    wd = {s: {d: 0 for d in WEEKDAYS} for s in senders}
    wd_all = {d: 0 for d in WEEKDAYS}
    night: Counter = Counter({s: 0 for s in senders})
    early: Counter = Counter({s: 0 for s in senders})
    variants: dict[str, Counter] = defaultdict(Counter)
    first_seen: dict[str, int] = {}
    emoji_group: Counter = Counter()
    per_date: Counter = Counter()

    for i, (t, s, text, is_media) in enumerate(zip(ts, senders_col, texts, media)):
        h, d = int(t.hour), WEEKDAYS[int(t.weekday())]
        hours[s][h] += 1
        hours_all[h] += 1
        wd[s][d] += 1
        wd_all[d] += 1
        per_date[t.date()] += 1
        night[s] += h in NIGHT_HOURS
        early[s] += h in EARLY_HOURS
        if is_media:
            medias[s] += 1
            continue  # a media placeholder has no words, laughs, links or emoji
        words[s] += len(text.split())
        laughs[s] += bool(LAUGH.search(text))
        links[s] += len(URL.findall(text))
        for c in emoji_clusters(text):
            key = c.replace(VS16, "")
            emoji_per[s] += 1
            emoji_group[key] += 1
            variants[key][c] += 1
            first_seen.setdefault(key, len(first_seen))

    top_emojis = []
    for key in sorted(emoji_group, key=lambda k: (-emoji_group[k], first_seen[k]))[:TOP_EMOJIS]:
        shown = max(variants[key].items(), key=lambda kv: (kv[1], VS16 in kv[0]))[0]
        top_emojis.append({"emoji": shown, "count": int(emoji_group[key])})

    bands: dict[str, dict] = {}
    for s in senders:
        n = msg_n[s]
        ns, es = night[s] / n, early[s] / n
        bands[s] = {"messages": int(n), "night_share": ns, "early_share": es, "qualifies": n >= min_messages_for_bands,
                    "leaning": "night" if ns > es else "early" if es > ns else "tie"}
    qual = [s for s in senders if bands[s]["qualifies"]]
    owl = min(qual, key=lambda s: (-bands[s]["night_share"], -bands[s]["messages"], s)) if qual else None
    bird = min(qual, key=lambda s: (-bands[s]["early_share"], -bands[s]["messages"], s)) if qual else None

    silence = None
    starters: Counter = Counter({s: 0 for s in senders})
    delays: dict[str, list[float]] = {s: [] for s in senders}
    best = -1.0
    for i in range(1, len(ts)):
        gap = (ts[i] - ts[i - 1]).total_seconds()
        if gap > best:  # strict: ties keep the earlier gap
            best, silence = gap, {"start": _iso(ts[i - 1]), "end": _iso(ts[i]), "hours": gap / 3600}
        if gap >= STARTER_GAP_S:
            starters[senders_col[i]] += 1
        if senders_col[i] != senders_col[i - 1] and 0 <= gap <= RESPONSE_MAX_S:
            delays[senders_col[i]].append(gap)

    busiest_date = None
    if per_date:
        d0 = min(per_date, key=lambda d: (-per_date[d], d))
        busiest_date = {"date": d0.isoformat(), "messages": int(per_date[d0])}

    def per_sender(c: Counter) -> dict[str, int]:
        return {s: int(c[s]) for s in senders}

    return {
        "window": {"since": _iso(lo) if len(pop) else _iso(lo), "until": _iso(hi), "days": WINDOW_DAYS, "inclusive": "both", "n_messages": len(w)},
        "senders": senders,
        "top_talkers": {
            "by_messages": [{"sender": s, "messages": int(msg_n[s])} for s in senders],
            "by_words": [{"sender": s, "words": int(words[s])} for s in sorted(senders, key=lambda s: (-words[s], s))],
        },
        "busiest": {
            "hour": {"overall": _busiest_hour(hours_all), "per_sender": {s: _busiest_hour(hours[s]) for s in senders}},
            "weekday": {"overall": _busiest_weekday(wd_all), "per_sender": {s: _busiest_weekday(wd[s]) for s in senders}},
            "hour_counts": {"overall": hours_all, "per_sender": hours},
            "weekday_counts": {"overall": wd_all, "per_sender": wd},
        },
        "night_early": {"min_messages": min_messages_for_bands, "per_sender": bands, "night_owl": owl, "early_bird": bird},
        "longest_silence": silence,
        "starters": per_sender(starters),
        "response_time": {s: {"median_seconds": (float(statistics.median(delays[s])) if delays[s] else None), "n": len(delays[s])} for s in senders},
        "laughs": {"total": int(sum(laughs.values())), "per_sender": per_sender(laughs)},
        "emojis": {"total": int(sum(emoji_per.values())), "per_sender": per_sender(emoji_per), "top": top_emojis},
        "media": {"total": int(sum(medias.values())), "per_sender": per_sender(medias)},
        "links": {"total": int(sum(links.values())), "per_sender": per_sender(links)},
        "busiest_date": busiest_date,
    }
