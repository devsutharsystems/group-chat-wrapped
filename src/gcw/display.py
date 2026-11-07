"""Display layer for AI items (pure, no I/O, no network). Verified text is never changed: everything here is for DISPLAY only.

- Member tokens become display names (one regex, longest token first, digit boundary: 'Member 12' is never clobbered by 'Member 1').
- The fullwidth '<' used to neutralise chat text goes back to '<'. Escaping is NOT done here: card.py escapes every string once.
- Fields are cut at a word boundary with an ellipsis (title 60, summary 140, quote 120, award summary 56).
- An item whose displayed text still contains an unmapped Member token is dropped and counted.
"""
from __future__ import annotations

import re
from typing import Any

LIMITS = {"title": 32, "summary": 110, "quote": 72, "award": 36, "award_summary": 72, "member": 20, "who": 14}
ELLIPSIS = "…"
FULLWIDTH_LT = chr(0xFF1C)
STOPWORDS = frozenset("the a an of for to and or in on with by at from".split())
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


def _last_word(t: str) -> str:
    w = t.rstrip(" ,;:-–—").rsplit(" ", 1)[-1]
    return w.strip(".,;:!?\"'()").lower()


def _no_stopword_end(cut: str, limit: int) -> str:
    """A truncated summary never ends on a stopword: prefer to end at a clause end (the last comma, if it keeps at least 40% of the limit), otherwise drop the
    trailing stopwords. The result is always a prefix of `cut`."""
    if _last_word(cut) not in STOPWORDS:
        return cut
    comma = cut.rfind(",")
    if comma >= 0.4 * limit:
        return cut[:comma]
    while cut and _last_word(cut) in STOPWORDS:
        sp = cut.rstrip(" ,;:-–—").rfind(" ")
        if sp <= 0:
            break
        cut = cut[:sp]
    return cut


def fit(text: str, limit: int, no_stopword_end: bool = False) -> str:
    """Whitespace-normalise, then cut at a word boundary with an ellipsis so the result is at most `limit` characters. With `no_stopword_end` the cut text never
    ends on a stopword (used for summaries)."""
    t = " ".join(str(text).split())
    if len(t) <= limit:
        return t
    cut = t[: limit - 1]
    if t[limit - 1] != " ":  # the cut falls inside a word: back up to the previous space
        sp = cut.rfind(" ")
        if sp > 0:
            cut = cut[:sp]
    if no_stopword_end:
        cut = _no_stopword_end(cut, limit)
    return cut.rstrip(" ,;:-–—") + ELLIPSIS


def fit_summary(text: str, limit: int) -> str:
    """Summaries (3 lines on the card): whole text if it fits; otherwise cut at the last SENTENCE END ('.', '!' or '?' followed by a space) that lies
    within the limit and keeps at least 40% of it; otherwise at a word boundary with an ellipsis (as fit). The result is always a prefix of the
    whitespace-normalised text."""
    t = " ".join(str(text).split())
    if len(t) <= limit:
        return t
    ends = [m.end() - 1 for m in re.finditer(r"[.!?](?= )", t[: limit + 1])]  # index of the punctuation mark
    best = max((i for i in ends if i + 1 <= limit), default=None)
    if best is not None and best + 1 >= 0.4 * limit:
        return t[: best + 1]
    return fit(t, limit, no_stopword_end=True)


def _quote_of(item: dict, index: dict[str, dict], names: dict[str, str]) -> dict | None:
    ev = item.get("evidence") or []
    if not ev:
        return None
    row = index.get(ev[0].get("message_id", ""))
    if row is None or row["sender"] not in names:
        return None
    return {"text": fit(detokenise(ev[0]["quote"], names), LIMITS["quote"]), "who": fit(names[row["sender"]], LIMITS["who"]), "date": row["ts"].date().isoformat(),
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
            card = {"title": fit(title, LIMITS["title"]), "summary": fit_summary(summary, LIMITS["summary"]), "quote": q["text"], "who": q["who"], "date": q["date"]}
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
        awards.append({"award": fit(name, LIMITS["award"]), "member": fit(member, LIMITS["member"]), "summary": fit(summary, LIMITS["award_summary"], no_stopword_end=True)})
    return {"joke": joke, "moment": moment, "awards": awards, "display_drops": drops}
