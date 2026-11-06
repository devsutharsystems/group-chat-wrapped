"""Display layer for AI items (pure, no I/O, no network). Verified text is never changed: everything here is for DISPLAY only.

- Member tokens become display names (one regex, longest token first, digit boundary: 'Member 12' is never clobbered by 'Member 1').
- The fullwidth '<' used to neutralise chat text goes back to '<'. Escaping is NOT done here: card.py escapes every string once.
- Fields are cut at a word boundary with an ellipsis (title 60, summary 140, quote 120, award summary 56).
- An item whose displayed text still contains an unmapped Member token is dropped and counted.
"""
from __future__ import annotations

import re
from typing import Any

LIMITS = {"title": 60, "summary": 140, "quote": 120, "award": 36, "award_summary": 56}
ELLIPSIS = "…"
FULLWIDTH_LT = chr(0xFF1C)
_TOKEN_SHAPES = (r"(?:Member|Person|Speaker|Participant) \d+", r"P[0-9a-f]{8}_\d+")


def token_pattern(tokens: list[str] | set[str]) -> re.Pattern | None:
    ts = sorted(tokens, key=lambda t: (-len(t), t))
    if not ts:
        return None
    return re.compile(r"(?<![\w])(?:" + "|".join(re.escape(t) for t in ts) + r")(?!\d)")


def detokenise(text: str, names: dict[str, str]) -> str:
    """Replace Member tokens with display names and map the fullwidth '<' back. `names`: token -> already-cleaned display name."""
    pat = token_pattern(set(names))
    out = pat.sub(lambda m: names[m.group()], text) if pat else text
    return out.replace(FULLWIDTH_LT, "<")


def has_unmapped_token(text: str) -> bool:
    """True if the (already de-tokenised) text still looks like a pseudonym token."""
    return any(re.search(r"(?<![\w])" + shape + r"(?!\d)", text) for shape in _TOKEN_SHAPES)


def fit(text: str, limit: int) -> str:
    """Whitespace-normalise, then cut at a word boundary with an ellipsis so the result is at most `limit` characters."""
    t = " ".join(str(text).split())
    if len(t) <= limit:
        return t
    cut = t[: limit - 1]
    if t[limit - 1] != " ":  # the cut falls inside a word: back up to the previous space
        sp = cut.rfind(" ")
        if sp > 0:
            cut = cut[:sp]
    return cut.rstrip(" ,;:-–—") + ELLIPSIS


def _quote_of(item: dict, index: dict[str, dict], names: dict[str, str]) -> dict | None:
    ev = item.get("evidence") or []
    if not ev:
        return None
    row = index.get(ev[0].get("message_id", ""))
    if row is None or row["sender"] not in names:
        return None
    return {"text": fit(detokenise(ev[0]["quote"], names), LIMITS["quote"]), "who": names[row["sender"]], "date": row["ts"].date().isoformat(),
            "full": detokenise(ev[0]["quote"], names)}


def _texts_ok(*texts: str) -> bool:
    return not any(has_unmapped_token(t) for t in texts)


def build_zone2(approved: dict, index: dict[str, dict], names: dict[str, str]) -> dict[str, Any]:
    """Display model for Zone 2 from an APPROVED report: first running joke, first moment, first two awards (list order = the model's
    'strongest first'). Items that cannot be displayed completely (an unmapped token, a missing sender) are skipped and counted in display_drops."""
    drops = 0
    joke = moment = None
    awards: list[dict] = []
    for typ in ("running_jokes", "moments"):
        for it in approved.get(typ) or []:
            q = _quote_of(it, index, names)
            title, summary = detokenise(str(it.get("title", "")), names), detokenise(str(it.get("summary", "")), names)
            if q is None or not _texts_ok(title, summary, q["full"], q["who"]):
                drops += 1
                continue
            card = {"title": fit(title, LIMITS["title"]), "summary": fit(summary, LIMITS["summary"]), "quote": q["text"], "who": q["who"], "date": q["date"]}
            if typ == "running_jokes":
                joke = card
            else:
                moment = card
            break  # the first displayable approved item of this type
    for it in approved.get("awards") or []:
        if len(awards) == 2:
            break
        member = names.get(it.get("member", ""))
        name, summary = detokenise(str(it.get("award", "")), names), detokenise(str(it.get("summary", "")), names)
        if member is None or not _texts_ok(name, summary):
            drops += 1
            continue
        awards.append({"award": fit(name, LIMITS["award"]), "member": member, "summary": fit(summary, LIMITS["award_summary"])})
    return {"joke": joke, "moment": moment, "awards": awards, "display_drops": drops}
