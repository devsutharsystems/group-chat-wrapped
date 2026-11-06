"""Text normalisation used when matching quotes against the chat (verify.py, later).

The parser keeps raw text; this is for MATCHING only. It removes invisible and bidi characters,
which includes U+200D (ZWJ), so ZWJ emoji sequences fall apart into their parts on both sides.
"""
from __future__ import annotations

import re
import unicodedata

def _rng(lo: int, hi: int | None = None) -> str:
    return chr(lo) if hi is None else chr(lo) + "-" + chr(hi)


# built from code points (never raw characters in this file): U+200B-200F, U+202A-202E, U+2060, U+2066-2069 (bidi isolates, added in
# Phase 3a as a precaution: UNVERIFIED that exports wrap @mentions in them), U+FEFF
_INVISIBLE = re.compile("[" + _rng(0x200B, 0x200F) + _rng(0x202A, 0x202E) + _rng(0x2060) + _rng(0x2066, 0x2069) + _rng(0xFEFF) + "]")
_SPACES = re.compile(r"\s+")


def normalise_for_match(text: str) -> str:
    """NFC, strip invisible/bidi characters, U+202F -> space, collapse whitespace, strip ends."""
    t = unicodedata.normalize("NFC", text)
    t = _INVISIBLE.sub("", t)
    t = t.replace(" ", " ")
    return _SPACES.sub(" ", t).strip()
