from __future__ import annotations

import pytest

from gcw.textnorm import normalise_for_match as n

ZWJ, LRM, RLM, NN = "‍", "‎", "‏", " "


@pytest.mark.parametrize("raw, want", [
    ("a​b", "ab"),                                  # zero-width space
    (f"x{ZWJ}y", "xy"),                                  # ZWJ
    (f"{LRM}hi{RLM}", "hi"),                              # bidi marks
    ("‪Hello‬", "Hello"),                       # bidi embedding
    ("‭A‮", "A"),
    ("⁠w⁠", "w"),                               # word joiner
    ("﻿abc", "abc"),                                 # BOM / ZWNBSP
    (f"9:18{NN}PM", "9:18 PM"),                           # U+202F -> space
    ("é", "é"),                                # NFD -> NFC
    ("  a \n\t b  ", "a b"),                              # whitespace collapse + strip
    (f"⁠{LRM}{RLM}", ""),                            # only invisibles
    (f"\U0001f468{ZWJ}\U0001f469{ZWJ}\U0001f467", "\U0001f468\U0001f469\U0001f467"),  # ZWJ family falls apart
    ("same", "same"),
])
def test_normalise(raw, want):
    assert n(raw) == want


def test_idempotent_and_both_sides_match():
    a = f"Hey{NN}there{ZWJ}!  ​"
    assert n(n(a)) == n(a) == "Hey there!"
    assert n("école") == n("école")
