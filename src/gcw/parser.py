"""Parse WhatsApp exports into a DataFrame. See docs/PRD.md section 8 (Parser format facts).

Formats:
  android_12h  VERIFIED   M/D/YY, h:mm<U+202F or space>AM|PM - Sender: text
  android_24h  UNVERIFIED d/m/yy, HH:MM - Sender: text            (no real sample yet)
  ios          UNVERIFIED [d/m/yy, h:mm:ss AM] Sender: text       (12h or 24h, no real sample yet)
Multi-line messages (continuation lines without a header) are UNVERIFIED against a real export.
Not supported: date separators other than "/", non-English AM/PM markers.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

SP = "[  ]"  # plain space or narrow no-break space
_DATE = r"(\d{1,2})/(\d{1,2})/(\d{2,4})"
HEADERS: dict[str, re.Pattern[str]] = {
    "android_12h": re.compile(rf"^‎?{_DATE},{SP}(\d{{1,2}}):(\d{{2}}){SP}?([AaPp][Mm]){SP}-{SP}(.*)$"),
    "android_24h": re.compile(rf"^‎?{_DATE},{SP}(\d{{1,2}}):(\d{{2}}){SP}-{SP}(.*)$"),
    "ios": re.compile(rf"^‎?\[{_DATE},{SP}(\d{{1,2}}):(\d{{2}}):(\d{{2}})(?:{SP}?([AaPp][Mm]))?\]{SP}(.*)$"),
}
VERIFIED_FORMATS = {"android_12h"}

# System lines: matched (re.fullmatch, first line of the body) BEFORE splitting "Sender: text".
# The name part is [^:]+? so a message like "Sam: I changed my mind" can never match.
DEFAULT_SYSTEM_PATTERNS: tuple[str, ...] = (
    r"Messages and calls are end-to-end encrypted\b.*",
    r"[^:]+? created (?:this |the )?group\b.*",
    r"[^:]+? (?:was|were) added",
    r"[^:]+? added [^:]+",
    r"[^:]+? removed [^:]+",
    r"[^:]+? left",
    r"[^:]+? joined\b.*",
    r"[^:]+? changed (?:the |this group's |their )?(?:group )?(?:subject|description|icon|settings|phone number|name)\b.*",
    r"Your security code with .+ changed\b.*",
)
# Deleted messages (exact text after "Sender: "). "You deleted this message" is VERIFIED; others' deletions are UNVERIFIED.
DEFAULT_DELETED_PATTERNS: tuple[str, ...] = ("You deleted this message", "This message was deleted")
DEFAULT_MEDIA_PATTERNS: tuple[str, ...] = ("<Media omitted>",)
EDITED_SUFFIX = " <This message was edited>"
_NEWLINE = re.compile(r"\r\n|\n|\r")  # NOT str.splitlines(): it also splits on U+2028, U+0085, \x0b, \x0c

COLUMNS = ["id", "ts", "sender", "text", "is_media", "is_deleted", "is_edited", "is_system"]


@dataclass
class ParseReport:
    n_messages: int = 0  # sender lines only; deleted and media included
    n_system: int = 0
    n_unparsed: int = 0
    first_ts: pd.Timestamp | None = None  # over all rows, system lines included
    last_ts: pd.Timestamp | None = None
    first_msg_ts: pd.Timestamp | None = None  # sender rows only (deleted and media included, system lines excluded)
    last_msg_ts: pd.Timestamp | None = None
    date_order: str | None = None  # "mdy" or "dmy"
    ambiguous: bool = False
    per_sender: dict[str, int] = field(default_factory=dict)
    format: str | None = None
    format_verified: bool = False
    date_order_source: str = ""  # "override" | "component>12" | "monotone" | "assumed"
    warnings: list[str] = field(default_factory=list)


def _read(path_or_text: str | Path) -> str:
    if isinstance(path_or_text, Path):
        text = path_or_text.read_text(encoding="utf-8")
    else:
        text = path_or_text
        if "\n" not in text and "\r" not in text and len(text) < 4096:
            try:
                p = Path(text)
                if p.is_file():
                    text = p.read_text(encoding="utf-8")
            except OSError:
                pass
    return text[1:] if text.startswith("﻿") else text


def _norm_order(order: str | None) -> str | None:
    if order is None:
        return None
    o = order.lower().replace("/", "").replace("-", "")
    if o in ("mdy", "md", "m"):
        return "mdy"
    if o in ("dmy", "dm", "d"):
        return "dmy"
    raise ValueError(f"date_order must be 'mdy' or 'dmy' (or 'm/d', 'd/m'), got {order!r}")


def _ts(order: str, rec: tuple) -> datetime | None:
    a, b, y, h, mi, s, ap = rec
    month, day = (a, b) if order == "mdy" else (b, a)
    year = y + 2000 if y < 100 else y
    if ap:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if ap.lower() == "pm" else 0)
    elif not 0 <= h <= 23:
        return None
    try:
        return datetime(year, month, day, h, mi, s)
    except ValueError:
        return None


def _detect_format(lines: list[str]) -> str | None:
    counts = {name: sum(1 for ln in lines if rx.match(ln)) for name, rx in HEADERS.items()}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] else None


def _choose_order(recs: list[tuple], fmt: str, override: str | None, report: ParseReport) -> str:
    if override:
        report.date_order_source, report.ambiguous = "override", False
        return override
    d_evidence = any(r[0] > 12 for r in recs)  # first component can only be a day
    m_evidence = any(r[1] > 12 for r in recs)  # second component can only be a day
    if d_evidence != m_evidence:
        report.date_order_source = "component>12"
        return "dmy" if d_evidence else "mdy"
    if d_evidence and m_evidence:
        report.warnings.append("date components > 12 in both positions: dates are inconsistent")
    survivors = []
    for order in ("mdy", "dmy"):
        stamps = [_ts(order, r) for r in recs]
        if all(s is not None for s in stamps) and all(x <= y for x, y in zip(stamps, stamps[1:])):  # type: ignore[operator]
            survivors.append(order)
    if len(survivors) == 1:
        report.date_order_source = "monotone"
        return survivors[0]
    has_ampm = any(r[6] for r in recs)
    order = "mdy" if has_ampm else "dmy"
    report.ambiguous, report.date_order_source = True, "assumed"
    report.warnings.append(
        f"date order is AMBIGUOUS ({'both orders fit' if survivors else 'neither order fits'}); assumed {'m/d' if order == 'mdy' else 'd/m'} "
        f"for {'12h AM/PM' if has_ampm else '24h'} headers. Pass date_order to override."
    )
    return order


def parse_chat(
    path_or_text: str | Path,
    date_order: str | None = None,
    *,
    system_patterns: Iterable[str] = DEFAULT_SYSTEM_PATTERNS,
    deleted_patterns: Iterable[str] = DEFAULT_DELETED_PATTERNS,
    media_patterns: Iterable[str] = DEFAULT_MEDIA_PATTERNS,
) -> tuple[pd.DataFrame, ParseReport]:
    """Parse an export. date_order: None to infer, or 'mdy' / 'dmy' to override."""
    override = _norm_order(date_order)
    lines = _NEWLINE.split(_read(path_or_text))
    if lines and lines[-1] == "":
        lines.pop()  # file ends with a newline
    report = ParseReport()
    fmt = _detect_format(lines)
    if fmt is None:
        report.n_unparsed = sum(1 for ln in lines if ln.strip())
        report.warnings.append("no WhatsApp header format recognised")
        return pd.DataFrame({c: [] for c in COLUMNS}), report
    report.format, report.format_verified = fmt, fmt in VERIFIED_FORMATS
    if not report.format_verified:
        report.warnings.append(f"format {fmt} is UNVERIFIED (no real sample); treat results with care")
    rx = HEADERS[fmt]

    # pass 1: headers
    parsed: list[tuple[int, tuple, str] | None] = []  # per line: (line index, rec, body) or None
    recs: list[tuple] = []
    for i, ln in enumerate(lines):
        m = rx.match(ln)
        if not m:
            parsed.append(None)
            continue
        g = m.groups()
        if fmt == "android_12h":
            rec = (int(g[0]), int(g[1]), int(g[2]), int(g[3]), int(g[4]), 0, g[5])
        elif fmt == "android_24h":
            rec = (int(g[0]), int(g[1]), int(g[2]), int(g[3]), int(g[4]), 0, None)
        else:
            rec = (int(g[0]), int(g[1]), int(g[2]), int(g[3]), int(g[4]), int(g[5]), g[6])
        body = g[-1].lstrip("‎") if fmt == "ios" else g[-1]
        parsed.append((i, rec, body))
        recs.append(rec)

    order = _choose_order(recs, fmt, override, report)
    report.date_order = order

    # pass 2: messages; continuation lines append to the previous message
    rows: list[dict] = []
    cur: dict | None = None
    for ln, p in zip(lines, parsed):
        if p is None:
            if cur is not None:
                cur["body"] += "\n" + ln
            elif ln.strip():
                report.n_unparsed += 1
            continue
        _, rec, body = p
        ts = _ts(order, rec)
        if ts is None:
            report.n_unparsed += 1  # header-looking line with an impossible date
            cur = None
            continue
        cur = {"ts": ts, "body": body}
        rows.append(cur)
    if report.n_unparsed:
        report.warnings.append(f"{report.n_unparsed} line(s) could not be parsed")

    sys_rx = [re.compile(p) for p in system_patterns]
    deleted = set(deleted_patterns)
    media = set(media_patterns)
    out = []
    for n, r in enumerate(rows, 1):
        body = r["body"].rstrip("\n")
        first = body.split("\n", 1)[0]
        sender, text, is_system = None, body, False
        if any(p.fullmatch(first) for p in sys_rx):
            is_system = True
        else:
            k = first.find(": ")
            if k < 0:
                is_system = True  # WhatsApp sender lines always have "Sender: "
            else:
                sender, text = body[:k], body[k + 2 :]
        is_edited = False
        if not is_system and text.endswith(EDITED_SUFFIX):
            text, is_edited = text[: -len(EDITED_SUFFIX)], True
        out.append({
            "id": f"m{n:06d}", "ts": r["ts"], "sender": sender, "text": text,
            "is_media": (not is_system) and text in media,
            "is_deleted": (not is_system) and text in deleted,
            "is_edited": is_edited, "is_system": is_system,
        })
    df = pd.DataFrame(out, columns=COLUMNS)
    if df.empty:
        return df, report
    df["ts"] = pd.to_datetime(df["ts"])
    sender_rows = df[~df["is_system"]]
    report.n_messages = int(len(sender_rows))
    report.n_system = int(df["is_system"].sum())
    report.per_sender = dict(Counter(sender_rows["sender"]))
    report.first_ts, report.last_ts = df["ts"].min(), df["ts"].max()
    if len(sender_rows):
        report.first_msg_ts, report.last_msg_ts = sender_rows["ts"].min(), sender_rows["ts"].max()
    return df, report


def messages(df: pd.DataFrame) -> pd.DataFrame:
    """The rows stats and the AI layer may use: no system lines and no deleted messages.
    (Media rows stay; callers that count words or send text drop them via is_media.)
    Stats and the AI layer must read this, never the raw parse_chat DataFrame."""
    return df[~df["is_system"] & ~df["is_deleted"]]
