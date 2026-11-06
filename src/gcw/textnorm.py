"""Text normalisation used when matching quotes against the chat (verify.py, later).

The parser keeps raw text; this is for MATCHING only. It removes invisible and bidi characters,
which includes U+200D (ZWJ), so ZWJ emoji sequences fall apart into their parts on both sides.
"""
from __future__ import annotations

import re
import unicodedata

# U+200B-200F (zero-width and bidi marks), U+202A-202E (bidi embeddings), U+2060 (word joiner), U+FEFF (BOM / ZWNBSP)
_INVISIBLE = re.compile("[​-‏‪-‮⁠﻿]")
_SPACES = re.compile(r"\s+")


def normalise_for_match(text: str) -> str:
    """NFC, strip invisible/bidi characters, U+202F -> space, collapse whitespace, strip ends."""
    t = unicodedata.normalize("NFC", text)
    t = _INVISIBLE.sub("", t)
    t = t.replace(" ", " ")
    return _SPACES.sub(" ", t).strip()
