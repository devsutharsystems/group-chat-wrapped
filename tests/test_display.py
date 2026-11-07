"""display.py: token mapping (longest first), unmapped drops, truncation, the prefix property, escaping. Pure functions, no render, no API."""
from __future__ import annotations

import random

import pandas as pd
import pytest

from gcw import card, display

NAMES12 = {f"Member {i}": f"Person{i:02d}" for i in range(1, 13)}


def test_member_12_is_not_clobbered_by_member_1():
    assert display.detokenise("Member 12 and Member 1, Member 11, Member 2.", NAMES12) == "Person12 and Person01, Person11, Person02."
    assert display.detokenise("Member 123 stays", NAMES12) == "Member 123 stays"  # a digit boundary: not Member 12 + '3'
    assert display.detokenise("xMember 1", NAMES12) == "xMember 1"  # not at a word start
    assert display.detokenise("Member 1's turn", NAMES12) == "Person01's turn"


def test_longest_token_first_even_when_the_dict_order_is_adversarial():
    names = {"Member 1": "A", "Member 10": "B", "Member 100": "C"}
    assert display.detokenise("Member 100 Member 10 Member 1", names) == "C B A"


def test_hash_prefix_tokens_are_mapped_too():
    names = {"Pdeadbeef_1": "Ann", "Pdeadbeef_12": "Bob"}
    assert display.detokenise("Pdeadbeef_12 and Pdeadbeef_1", names) == "Bob and Ann"
    assert display.has_unmapped_token("Pdeadbeef_7") and not display.has_unmapped_token("plain text")


def test_fullwidth_bracket_maps_back_for_display_only():
    s = "I " + chr(0xFF1C) + "3 pizza"
    assert display.detokenise(s, {}) == "I <3 pizza" and card.display_text(s) == "I &lt;3 pizza"


@pytest.mark.parametrize("text, unmapped", [("Member 9 did it", True), ("Person 3 here", True), ("Speaker 12!", True), ("Participant 1", True),
                                            ("Member of the year", False), ("Ann did it", False), ("members 3", False), ("", False)])
def test_has_unmapped_token(text, unmapped):
    assert display.has_unmapped_token(text) is unmapped


def test_fit_cuts_at_a_word_boundary_with_an_ellipsis():
    assert display.fit("short text", 20) == "short text"
    assert display.fit("exactly ten", 11) == "exactly ten"
    assert display.fit("one two three four five", 14) == "one two three…"  # "one two three" fits, "four" does not
    assert display.fit("one two three four five", 13) == "one two…"  # 12 characters of room: the cut lands inside "three"
    assert display.fit("abcdefghijklmnop", 8) == "abcdefg…"  # no space at all: hard cut
    assert display.fit("a  b\n c", 20) == "a b c"  # whitespace is normalised
    assert display.fit("end, with comma, trailing", 15) == "end, with…"  # the cut drops trailing punctuation before the ellipsis
    for limit in (5, 12, 40, 60):
        assert len(display.fit("word " * 50, limit)) <= limit


def test_every_field_limit():
    assert display.LIMITS == {"title": 32, "summary": 110, "quote": 72, "award": 36, "award_summary": 72, "member": 20, "who": 14}


def _row(sender, day="2026-01-05"):
    return {"sender": sender, "ts": pd.Timestamp(day + "T10:00"), "withheld": False, "media": False}


def _approved(**over):
    base = {"running_jokes": [{"title": "Cheese protocol", "summary": "They keep saying it.", "evidence": [{"message_id": "m000001", "quote": "reminder: cheese protocol is in effect"}]}],
            "moments": [{"title": "Cake disaster", "summary": "It sank.", "evidence": [{"message_id": "m000002", "quote": "Well, that cake was a disaster."}]}],
            "awards": [{"award": "Best planner", "member": "Member 2", "summary": "Always has a plan.", "evidence": [{"message_id": "m000002", "quote": "x" * 12}]},
                       {"award": "Most generous", "member": "Member 3", "summary": "Brings snacks.", "evidence": [{"message_id": "m000003", "quote": "y" * 12}]},
                       {"award": "Third award", "member": "Member 1", "summary": "Not shown.", "evidence": [{"message_id": "m000001", "quote": "z" * 12}]}]}
    base.update(over)
    return base


INDEX = {"m000001": _row("Member 1", "2025-12-06"), "m000002": _row("Member 2", "2026-01-05"), "m000003": _row("Member 3")}
NAMES = {"Member 1": "Sam", "Member 2": "Maya", "Member 3": "Kai"}


def test_zone2_picks_first_joke_first_moment_first_two_awards_with_sender_and_date_from_the_index():
    z = display.build_zone2(_approved(), INDEX, NAMES)
    assert z["joke"] == {"title": "Cheese protocol", "summary": "They keep saying it.", "quote": "reminder: cheese protocol is in effect", "who": "Sam", "date": "2025-12-06"}
    assert z["moment"]["who"] == "Maya" and z["moment"]["date"] == "2026-01-05" and z["moment"]["title"] == "Cake disaster"
    assert [(a["award"], a["member"]) for a in z["awards"]] == [("Best planner", "Maya"), ("Most generous", "Kai")] and z["display_drops"] == 0


def test_an_item_with_an_unmapped_token_is_dropped_counted_and_the_next_one_is_used():
    a = _approved()
    a["running_jokes"].insert(0, {"title": "Member 9 strikes again", "summary": "s", "evidence": [{"message_id": "m000001", "quote": "reminder: cheese protocol"}]})
    a["moments"].insert(0, {"title": "ok title", "summary": "talks about Member 7", "evidence": [{"message_id": "m000002", "quote": "q"}]})
    a["moments"].insert(0, {"title": "ok", "summary": "ok", "evidence": [{"message_id": "m000002", "quote": "Member 5 said so"}]})  # inside the quote
    a["awards"].insert(0, {"award": "Best", "member": "Member 8", "summary": "s", "evidence": []})  # the member token is unmapped
    z = display.build_zone2(a, INDEX, NAMES)
    assert z["joke"]["title"] == "Cheese protocol" and z["moment"]["title"] == "Cake disaster"
    assert [x["award"] for x in z["awards"]] == ["Best planner", "Most generous"] and z["display_drops"] == 4


def test_items_without_evidence_or_with_an_unknown_sender_are_dropped():
    a = _approved(running_jokes=[{"title": "t", "summary": "s", "evidence": []}], moments=[{"title": "t", "summary": "s", "evidence": [{"message_id": "m999999", "quote": "q" * 20}]}])
    z = display.build_zone2(a, INDEX, NAMES)
    assert z["joke"] is None and z["moment"] is None and z["display_drops"] == 2
    z = display.build_zone2(_approved(), {"m000001": _row("Member 77")}, NAMES)  # sender token not in names
    assert z["joke"] is None


def test_nothing_approved_gives_empty_zone2():
    z = display.build_zone2({"running_jokes": [], "moments": [], "awards": []}, INDEX, NAMES)
    assert z == {"joke": None, "moment": None, "awards": [], "display_drops": 0}


def test_displayed_texts_are_cut_to_their_limits_at_word_boundaries():
    long = " ".join(["wordy"] * 80)
    a = _approved(running_jokes=[{"title": long, "summary": long, "evidence": [{"message_id": "m000001", "quote": long}]}],
                  awards=[{"award": long, "member": "Member 2", "summary": long, "evidence": []}])
    z = display.build_zone2(a, INDEX, NAMES)
    assert len(z["joke"]["title"]) <= 32 and len(z["joke"]["summary"]) <= 110 and len(z["joke"]["quote"]) <= 72
    assert len(z["awards"][0]["award"]) <= 36 and len(z["awards"][0]["summary"]) <= 72
    for t in (z["joke"]["title"], z["joke"]["summary"], z["joke"]["quote"], z["awards"][0]["summary"]):
        assert t.endswith("…") and not t[:-1].endswith(" ") and t[:-1].split(" ")[-1] == "wordy"  # whole words only


def test_the_displayed_quote_is_a_prefix_of_the_verified_quote_after_detokenising():
    rng = random.Random(7)
    words = ["cheese", "Member 1", "Member 12", "protocol", "<3", chr(0xFF1C) + "b>", "x", "reminder:", "is", "in", "effect", "Member 2's", "ok"]
    for _ in range(300):
        quote = " ".join(rng.choice(words) for _ in range(rng.randint(3, 60)))
        names = {"Member 1": "Sam", "Member 12": "Mo", "Member 2": "Maya"}
        idx = {"m000001": _row("Member 1")}
        z = display.build_zone2(_approved(running_jokes=[{"title": "t", "summary": "s", "evidence": [{"message_id": "m000001", "quote": quote}]}]), idx, names)
        full = " ".join(display.detokenise(quote, names).split())
        shown = z["joke"]["quote"]
        assert shown.removesuffix("…") == full[: len(shown.removesuffix("…"))] and len(shown) <= 72
        assert shown == full or shown.endswith("…")


def test_escaping_happens_once_in_the_card_not_in_the_display_layer():
    z = display.build_zone2(_approved(running_jokes=[{"title": "<script>alert(1)</script>", "summary": 'a "q" & b', "evidence": [{"message_id": "m000001", "quote": "<img src=x onerror=1>"}]}]), INDEX, NAMES)
    assert z["joke"]["title"] == "<script>alert(1)</script>"  # raw here
    html = card.build_card_html({"window": {"n_messages": 0, "first_ts": None, "last_ts": None}, "top_talkers": {"by_messages": [], "by_words": []}, "night_early": {"night_owl": None, "early_bird": None, "per_sender": {}},
                                 "longest_silence": None, "busiest_date": None, "busiest": {"slot": None}, "emojis": {"total": 0, "top": []}, "laughs": {"total": 0}, "media": {"total": 0}, "links": {"total": 0},
                                 "starters": {}, "response_time": {}},
                                ai={"zone2": z, "approved": 1, "proposed": 1, "verified": 1, "synthetic": False})
    assert "<script" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "&lt;img src=x onerror=1&gt;" in html and "&amp; b" in html and "&quot;q&quot;" in html


def test_the_quote_shown_is_the_first_evidence_not_the_last():
    a = _approved(running_jokes=[{"title": "t", "summary": "s", "evidence": [{"message_id": "m000001", "quote": "first quote here"}, {"message_id": "m000003", "quote": "last quote here"}]}])
    z = display.build_zone2(a, INDEX, NAMES)
    assert z["joke"]["quote"] == "first quote here" and z["joke"]["who"] == "Sam" and z["joke"]["date"] == "2025-12-06"


def test_token_order_is_irrelevant_given_the_digit_boundary_brute_force():
    """Why the 'tokens shortest first' mutant is equivalent: with (?!\\d) after the alternation, a shorter token cannot match a longer one's prefix, so
    the regex engine backtracks to the longer alternative. Checked over every string of up to 5 symbols from a small alphabet, both orders."""
    import itertools
    import re

    toks = ["Member 1", "Member 12", "Member 123"]
    longest = display.token_pattern(toks)
    shortest = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(t) for t in sorted(toks, key=lambda t: (len(t), t))) + r")(?!\d)")
    alpha = ["Member ", "1", "2", "3", " ", "x"]
    n = 0
    for length in range(1, 6):
        for tup in itertools.product(alpha, repeat=length):
            s = "".join(tup)
            assert [m.group() for m in longest.finditer(s)] == [m.group() for m in shortest.finditer(s)], s
            n += 1
    assert n == sum(6 ** k for k in range(1, 6))


def test_sender_and_member_names_are_cut_for_display_only():
    long = "Alexandria Bartholomew-Smythe!"
    names = {"Member 1": long, "Member 2": "Maya", "Member 3": "Kai"}
    z = display.build_zone2(_approved(awards=[{"award": "Best", "member": "Member 1", "summary": "s", "evidence": []}]), INDEX, names)
    assert len(z["awards"][0]["member"]) <= 20 and z["awards"][0]["member"].endswith("\u2026")
    assert len(z["joke"]["who"]) <= 14 and z["joke"]["who"].endswith("\u2026")  # the quote's sender (Member 1) is long
    assert names["Member 1"] == long  # the mapping itself is untouched


SUMMARY = ("The group keeps invoking the cheese protocol in unrelated plans. It started on a Tuesday and returned every week after that, "
           "usually right when someone proposed lunch.")  # 3 sentences


def test_summary_longer_than_the_limit_is_a_prefix_of_the_verified_text_plus_an_ellipsis():
    long = " ".join(["wordy"] * 80)
    out = display.fit_summary(long, 110)
    assert out.endswith("\u2026") and len(out) <= 110 and " ".join(long.split()).startswith(out[:-1]) and not out[:-1].endswith(" ")
    z = display.build_zone2(_approved(running_jokes=[{"title": "t", "summary": long, "evidence": [{"message_id": "m000001", "quote": "reminder: cheese protocol"}]}]), INDEX, NAMES)
    assert z["joke"]["summary"] == out  # the card shows exactly this


def test_summary_is_cut_at_a_sentence_end_when_one_fits():
    out = display.fit_summary(SUMMARY, 110)
    assert out == "The group keeps invoking the cheese protocol in unrelated plans." and SUMMARY.startswith(out)  # no ellipsis: a complete sentence
    two = display.fit_summary(SUMMARY, 140)  # the second sentence ends at 125 characters
    assert two.endswith("returned every week after that,") is False and SUMMARY.startswith(two) and len(two) <= 140


def test_summary_sentence_end_must_keep_at_least_40_percent_of_the_limit():
    t = "Hi. " + "word " * 40  # the only sentence end is at 3 characters: far too short, so a word-boundary cut with an ellipsis is used
    out = display.fit_summary(t, 110)
    assert out.endswith("\u2026") and out.startswith("Hi. word") and len(out) <= 110


@pytest.mark.parametrize("text, limit, want", [
    ("short text.", 110, "short text."),
    ("one. two. three. four. five.", 20, "one. two. three."),
    ("no sentence end in this fairly long run of words that keeps on going", 30, "no sentence end in this\u2026"),
    ("Is it? Yes! " + "x " * 60, 40, "Is it? Yes!"),  # '?' and '!' count as sentence ends; 11 characters is under 40% of 40 (16), so see the next case
    ("Is it? Yes! No. " + "x " * 60, 40, "Is it? Yes! No."),  # 15 characters: still under 16, so a word cut applies
    ("Is it? Yes! No way. Really. " + "x " * 60, 40, "Is it? Yes! No way. Really."),  # 27 characters >= 16: the last sentence end within 40 is used
])
def test_fit_summary_cases(text, limit, want):
    out = display.fit_summary(text, limit)
    assert " ".join(text.split()).startswith(out.removesuffix("\u2026")) and len(out) <= limit
    if text == "Is it? Yes! " + "x " * 60 or text == "Is it? Yes! No. " + "x " * 60:
        assert out.endswith("\u2026")  # the only sentence ends are below 40% of the limit: a word-boundary cut with an ellipsis
    else:
        assert out == want


def test_summary_that_fits_is_untouched_apart_from_whitespace():
    assert display.fit_summary("  A  short\n summary. ", 110) == "A short summary."


def test_zone2_story_summaries_use_the_sentence_end_rule_but_award_summaries_do_not():
    a = _approved(running_jokes=[{"title": "t", "summary": SUMMARY, "evidence": [{"message_id": "m000001", "quote": "reminder: cheese protocol"}]}],
                  awards=[{"award": "Best", "member": "Member 2", "summary": SUMMARY, "evidence": []}])
    z = display.build_zone2(a, INDEX, NAMES)
    assert z["joke"]["summary"] == "The group keeps invoking the cheese protocol in unrelated plans."  # sentence end, no ellipsis
    assert z["awards"][0]["summary"].endswith("…") and len(z["awards"][0]["summary"]) <= 72  # awards: word boundary plus ellipsis
