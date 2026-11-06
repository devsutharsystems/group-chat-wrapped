"""Privacy layer tests. Expected values are written by hand (or recomputed with plain Python), never taken from privacy.py.
Digit strings are assembled from parts so scripts/scan_repo.py does not mistake them for real phone numbers."""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pandas as pd
import pytest
import regex

from gcw import privacy
from gcw.dataset import verify_dataset
from gcw.parser import parse_chat
from test_stats import COLUMNS, FROZEN, frame, raw_messages

ROOT = Path(__file__).resolve().parent.parent
TRUTH = ROOT / "synthetic" / "frozen" / "ground_truth.json"
NAMES6 = ["Sam", "Alex", "Maya", "Jordan", "Riley", "Kai"]
ISO = "-".join(["2026", "02", "07"])  # a date, built from parts
LRI, PDI, FSI = chr(0x2066), chr(0x2069), chr(0x2068)  # bidi isolates


def j(*parts: str, sep: str = " ") -> str:
    return sep.join(parts)


def red(text: str) -> str:
    return privacy.redact(text)[0]


def al(*members) -> privacy.Aliases:
    """members: str or (export_name, display, nicknames, case_sensitive)"""
    out = []
    for m in members:
        if isinstance(m, str):
            out.append({"export_name": m})
        else:
            out.append(dict(zip(("export_name", "display", "nicknames", "case_sensitive"), m)))
    return privacy.parse_aliases({"members": out})


def chat(rows: list[tuple], year: int = 2026) -> pd.DataFrame:
    """rows: (sender, text) or (sender, text, flag)"""
    full = [(i + 1, f"03-02 {9 + i // 60:02d}:{i % 60:02d}", r[0], r[1], r[2] if len(r) > 2 else "") for i, r in enumerate(rows)]
    return frame(full, year)


# ---------------------------------------------------------------- redaction: positives
@pytest.mark.parametrize("text, want", [
    ("see https://example.com/a?id=1&ref=chat now", "see [link] now"),
    ("see HTTP://Example.com/x#frag, ok", "see [link], ok"),
    ("go to www.example.com/page. Then", "go to [link]. Then"),
    ("short bit.ly/abc here", "short [link] here"),
    ("just example.com ok", "just [link] ok"),
    ("mail maya.test@example.com please", "mail [email] please"),
    ("mail a.b+c@example.com.", "mail [email]."),
    ("pay maya@okaxis now", "pay [handle] now"),
    ("pay " + j("98765", "43210", sep="") + "@ybl now", "pay [handle] now"),
    ("hi @someone_9 and @x.y", "hi [handle] and [handle]"),
    ("call " + j("+", "91", sep="") + " " + j("98765", "43210") + " now", "call [phone] now"),
    ("call " + j("98765", "43210", sep="") + " now", "call [phone] now"),
    ("call " + j("98765", "43210") + " now", "call [phone] now"),
    ("call " + j("987", "654", "3210", sep="-") + " now", "call [phone] now"),
    ("call " + "(" + j("044") + ") " + j("2345", "6789") + " now", "call [phone] now"),
    ("call " + j("+", "44", sep="") + " (" + j("0", sep="") + ")" + j("7700", "900123") + " now", "call [phone] now"),
    ("call +00 000 000 0000 now", "call [phone] now"),
    ("call +00 0000 000000 now", "call [phone] now"),
    ("call " + j("00", "44", "7700", "900123") + " now", "call [phone] now"),
    ("otp " + j("123", "456", sep="") + " ok", "otp [number] ok"),
    ("call +" + j("123", "4567", sep="") + " now", "call +[number] now"),  # plus sign but only 7 digits: not a phone, still a number
    ("ref " + j("12345", "67890", sep="") + " ok", "ref [number] ok"),  # 10 digits but not a mobile start (6-9)
    ("ref " + j("1234", "5678", "9012", sep="") + " ok", "ref [number] ok"),
    ("order " + j("48213", "75", sep="") + " shipped", "order [number] shipped"),  # 7 digits: the accepted over-redaction
])
def test_redact_positives(text, want):
    assert red(text) == want


# ---------------------------------------------------------------- redaction: negatives (must survive untouched)
@pytest.mark.parametrize("text", [
    "on " + ISO + " we met",
    "on " + ISO + " " + "21:19" + " exactly",
    "on " + j("11", "6", "25", sep="/") + " we met",
    "at 21:19 sharp",
    "at 9:05 PM sharp",
    "at 9:05pm sharp",
    "on " + j("12", "12", "2025", sep=".") + " too",
    "use version 2.0 please",
    "v1.2.3 is out",
    "order #48213 shipped",
    "I am still paying 4000 for it",
    "see you at 3 pm",
    "meet @ 5 pm",
    "e.g. this and i.e. that",
    "-".join(map(str, range(1, 8))).replace("-", " "),
    "room 12, floor 3",
    "price 99.99 only",
    "score 21-19 at the end",
    "12345 is five digits",
    "call +" + " ".join("1234567") + " now",  # plus sign, but only 7 digits (spread out): below the 8-digit minimum for an international number
])
def test_redact_negatives(text):
    assert red(text) == text


def test_redact_counts_by_category():
    text = "a https://example.com/x?y=1 b maya.test@example.com c +00 000 000 0000 d @hey e " + j("123", "456", sep="") + " f maya@okaxis"
    out, counts = privacy.redact(text)
    assert out == "a [link] b [email] c [phone] d [handle] e [number] f [handle]"
    assert counts == {"link": 1, "email": 1, "phone": 1, "handle": 2, "number": 1}


def test_redact_survives_hostile_sentinel_characters():
    text = "x" + chr(0xE000) + "a" + chr(0xE001) + " " + ISO
    assert red(text) == "xa " + ISO


def test_no_at_followed_by_letter_survives_any_redacted_text():
    for s in ["a@b", "x@example.com", "@@abc", "foo@@bar", "name@", "@" + chr(0xE9) + "cole", "(@maya)", "mail@example.com@example.com"]:
        assert not re.search(r"@[^\W\d_]", red(s)), (s, red(s))


# ---------------------------------------------------------------- names
def pn(aliases, rows):
    df, mapping = privacy.pseudonymise(chat(rows), aliases)
    return list(df["text"]), list(df["sender"]), mapping


def test_name_variants_become_the_same_token():
    texts, senders, mapping = pn(al("Sam", "Alex", "Maya"), [
        ("Maya", "MAYA said hi"), ("Sam", "maya! come on"), ("Alex", "it is Maya's turn"),
        ("Sam", "ping @" + FSI + "Maya" + PDI + " now"), ("Sam", "ping @Maya now"), ("Sam", "Maya, Maya; (maya)"),
    ])
    assert texts == ["Member 3 said hi", "Member 3! come on", "it is Member 3's turn", "ping Member 3 now", "ping Member 3 now", "Member 3, Member 3; (Member 3)"]
    assert senders == ["Member 3", "Member 1", "Member 2", "Member 1", "Member 1", "Member 1"]
    assert mapping == {"Member 1": "Sam", "Member 2": "Alex", "Member 3": "Maya"}


def test_curly_apostrophe_possessive_and_nfd_vs_nfc():
    e = chr(0xE9)
    name_nfc = "Zo" + e
    name_nfd = unicodedata.normalize("NFD", name_nfc)
    assert name_nfc != name_nfd
    texts, _, _ = pn(al(name_nfc, "Sam"), [("Sam", name_nfd + " and " + name_nfc.upper() + " and " + name_nfc + chr(0x2019) + "s hat")])
    assert texts == ["Member 1 and Member 1 and Member 1" + chr(0x2019) + "s hat"]
    texts, _, _ = pn(al(name_nfd, "Sam"), [("Sam", name_nfc)])  # alias file in NFD, chat in NFC
    assert texts == ["Member 1"]


def test_names_inside_longer_words_are_untouched():
    texts, _, _ = pn(al("Sam", "Alex"), [("Sam", "Alexander ate a samosa with Samuel, alexandra, Sams and Samantha")])
    assert texts == ["Alexander ate a samosa with Samuel, alexandra, Sams and Samantha"]
    texts, _, _ = pn(al("Sam", "Maya"), [("Sam", "Ramaya, Wesam, Dasam2 and xMaya are not people we know")])  # a letter BEFORE the name
    assert texts == ["Ramaya, Wesam, Dasam2 and xMaya are not people we know"]


def test_nickname_first_name_and_longest_first():
    texts, senders, mapping = pn(al(("Alex Kim", "Alex K.", ["Lexi"], False), ("Alex Lee", "Alex L.", ["Lexxy"], False), "Sam"), [
        ("Sam", "Alex Kim and alex lee and LEXI and lexxy and alex"),
    ])
    # "Alex" alone is a first name of both: it maps to the first member (Alex Kim = Member 1); the full names win over it
    assert texts == ["Member 1 and Member 2 and Member 1 and Member 2 and Member 1"]
    ps = privacy.Pseudonymiser(chat([("Sam", "x")]), al(("Alex Kim", "Alex K.", ["Lexi"], False), ("Alex Lee", "Alex L.", [], False)))
    assert any("Alex" in w for w in ps.warnings)


def test_case_sensitive_member():
    texts, _, _ = pn(al(("Will", "Will", [], True), "Sam"), [("Sam", "Will will go; WILL too")])
    assert texts == ["Member 1 will go; WILL too"]


def test_case_sensitive_full_name_must_not_swallow_a_case_insensitive_first_name_of_another_member():
    """Killed mutant: ignoring the case-sensitivity of 'Alex Kim' lets 'ALEX KIM' match as a whole, find no token for that exact text and leave it,
    although the other member 'Alex' (case-insensitive) must still be replaced inside it."""
    texts, _, _ = pn(al(("Alex Kim", "Alex Kim", [], True), "Alex"), [("Alex", "ALEX KIM and alex kim and Alex Kim")])
    assert texts == ["Member 2 KIM and Member 2 kim and Member 1"]


def test_last_resort_at_rule_is_unreachable_brute_force():
    """The final ANY_AT_LETTER rule never fires: every '@' followed by a letter is already taken by the handle rule. Checked over every string
    of length <= 5 from an 8-symbol alphabet (the 3a-fix run covered length <= 6: 299,592 strings, 0 differences)."""
    import itertools
    from collections import Counter

    never = regex.compile(r"(?!x)x")
    real = privacy.ANY_AT_LETTER
    alpha = ["@", "a", chr(0xC9), "1", ".", "_", " ", "/"]
    try:
        n = 0
        for length in range(1, 6):
            for tup in itertools.product(alpha, repeat=length):
                text = "".join(tup)
                privacy.ANY_AT_LETTER = real
                a = privacy._scrub(text, None, Counter())
                privacy.ANY_AT_LETTER = never
                assert a == privacy._scrub(text, None, Counter()), text
                n += 1
    finally:
        privacy.ANY_AT_LETTER = real
    assert n == sum(8 ** k for k in range(1, 6))


def test_unknown_senders_get_tokens_and_their_names_are_replaced_too():
    texts, senders, mapping = pn(al("Sam"), [("Priya Nair", "hi"), ("Sam", "thanks priya and Priya Nair")])
    assert senders == ["Member 2", "Member 1"]
    assert texts == ["hi", "thanks Member 2 and Member 2"]
    assert mapping == {"Member 1": "Sam", "Member 2": "Priya Nair"}


def test_nickname_equal_to_a_placeholder_word_cannot_corrupt_placeholders():
    out, counts = privacy.build_payload(chat([("Sam", "link: see www.example.com or the link")]), al(("Sam", "Sam", ["link"], False)))[:2]
    assert out.splitlines()[0].endswith("| Member 1 | Member 1: see [link] or the Member 1")
    assert counts["replacements"]["link"] == 1 and counts["replacements"]["name"] == 2


def test_sensitive_screen_looks_at_the_original_not_the_redacted_text():
    text, counts, _ = privacy.build_payload(chat([("Sam", "write to loan@example.com"), ("Sam", "write to bob@example.com")]), al("Sam"))
    first, second = text.splitlines()
    assert first.endswith("| [withheld: sensitive]") and second.endswith("| write to [email]")


def test_system_and_deleted_rows_never_reach_pseudonymise():
    df = chat([("Sam", "Sam joined", "system"), ("Sam", "you deleted Maya", "deleted"), ("Sam", "kept")])
    out, _ = privacy.pseudonymise(df, al("Sam", "Maya"))
    assert list(out["text"]) == ["kept"]


@pytest.mark.parametrize("colliders, prefix", [
    ([], "Member"),
    (["I am Member 7 today"], "Person"),
    (["I am Member 7 today", "Person 2 here"], "Speaker"),
    (["Member 1", "Person 1", "Speaker 1"], "Participant"),
])
def test_token_collision_check_picks_a_prefix_that_is_not_in_the_chat(colliders, prefix):
    rows = [("Sam", c) for c in colliders] + [("Sam", "plain"), ("Alex", "plain too")]
    text, counts, mapping = privacy.build_payload(chat(rows), al("Sam", "Alex"))
    assert counts["prefix"] == prefix
    assert all(tok.startswith(prefix + " ") for tok in mapping)
    assert f"| {prefix} 1 | " in text and f"| {prefix} 2 | " in text


def test_token_collision_when_every_prefix_is_taken_falls_back_to_a_hash_prefix_not_in_the_chat():
    rows = [("Sam", "Member 1"), ("Sam", "Person 1"), ("Sam", "Speaker 1"), ("Sam", "Participant 1"), ("Alex", "hello")]
    text, counts, mapping = privacy.build_payload(chat(rows), al("Sam", "Alex"))
    pre = counts["prefix"]
    assert re.fullmatch(r"P[0-9a-f]{8}", pre) and set(mapping) == {pre + "_1", pre + "_2"}
    blob = "\n".join(r[1] for r in rows)
    assert pre not in blob
    assert text.splitlines()[0].split(" | ")[2] == pre + "_1"


def test_mapping_never_appears_in_the_payload():
    text, counts, mapping = privacy.build_payload(chat([("Sam", "hi Alex"), ("Alex", "hi Sam")]), al("Sam", "Alex"))
    assert text.splitlines() == [f"m000001 | {'2026-03-02'} 09:00 | Member 1 | hi Member 2", f"m000002 | {'2026-03-02'} 09:01 | Member 2 | hi Member 1"]
    assert "Sam" not in text and "Alex" not in text and "->" not in text and "export" not in text
    assert "Sam" not in json.dumps(counts) and "Alex" not in json.dumps(counts)
    assert mapping == {"Member 1": "Sam", "Member 2": "Alex"}  # returned to the caller only


# ---------------------------------------------------------------- aliases schema
def test_aliases_example_file_has_the_six_synthetic_members_and_card_still_reads_it():
    a = privacy.load_aliases(ROOT / "aliases.example.json")
    assert [m.export_name for m in a.members] == NAMES6
    from gcw import card

    assert card.load_aliases(ROOT / "aliases.example.json") == {n: n for n in NAMES6}


def test_aliases_old_flat_form_still_loads_and_bad_forms_are_rejected():
    assert privacy.parse_aliases({"Sam": "Sammy B"}).display_map() == {"Sam": "Sammy B"}
    for bad in [[], {"members": {}}, {"members": [{}]}, {"members": [{"export_name": "A", "nicknames": ["x"]}]},
                {"members": [{"export_name": "A"}, {"export_name": "A"}]}, {"members": [{"export_name": "A", "nicknames": [1]}]},
                {"members": [{"export_name": "A", "case_sensitive": "yes"}]}, {"a": 1}]:
        with pytest.raises(ValueError):
            privacy.parse_aliases(bad)


def test_textnorm_strips_bidi_isolates():
    from gcw.textnorm import normalise_for_match

    assert normalise_for_match("a" + chr(0x2066) + "b" + chr(0x2067) + "c" + chr(0x2068) + "d" + chr(0x2069) + "e") == "abcde"


# ---------------------------------------------------------------- sensitive screen
def test_sensitive_screen_unit_cases():
    for t in ["I need a doctor", "my BLOOD   pressure", "the election", "Voting day", "my loan", "diabetes is hard", "kill myself", "prayers every day",
              "medicines", "Elections soon", "I went to the doctor " + chr(0x2019) + "s"]:
        assert privacy.sensitive_screen(t), t
    for t in ["loanword and doctorate and brokerage", "I like cheese", "unmedicated cats", "samosa time"]:
        assert not privacy.sensitive_screen(t), t  # whole-word / word-start matching only
    assert privacy.sensitive_hits("the doctor owes me a loan") == ["health", "money"]


def test_known_gaps_of_the_screen_are_gaps():
    """Documented limits (docs/privacy.md): inflections of non-stem terms, slang, euphemism and non-English text are NOT caught."""
    for t in ["praying a lot", "the thing with my knee", "mi medicina de la presion", "my chest hurts"]:
        assert not privacy.sensitive_screen(t), t


def frozen_truth():
    return json.loads(TRUTH.read_text(encoding="utf-8"))["items"]


def test_the_four_planted_sensitive_messages_are_all_withheld():
    planted = [i for i in frozen_truth() if i["kind"] == "sensitive"]
    assert len(planted) == 4
    for it in planted:
        assert privacy.sensitive_screen(it["text"]), it["text"]
    verify_dataset()
    df, _ = parse_chat(FROZEN)
    text, counts, _ = privacy.build_payload(df, al(*NAMES6))
    lines = text.splitlines()
    for it in planted:
        stamp = it["timestamp"].replace("T", " ")[:16]
        hit = [ln for ln in lines if f" | {stamp} | " in ln and ln.endswith("| " + privacy.WITHHELD)]
        assert hit, it


def own_keyword_matcher():
    """Plain-Python re-implementation of the screen, for the frozen Latin-script chat only."""
    cats = json.loads((ROOT / "src" / "gcw" / "data" / "sensitive_keywords.json").read_text(encoding="utf-8"))["categories"]
    pats = []
    for terms in cats.values():
        for t in terms:
            stem = t.endswith("*")
            body = r"\s+".join(re.escape(w) for w in t.rstrip("*").split())
            pats.append(re.compile(r"(?<![A-Za-z0-9])" + body + (r"[A-Za-z]*" if stem else "") + r"(?![A-Za-z0-9])", re.IGNORECASE))
    return lambda s: any(p.search(s) for p in pats)


def test_withheld_count_on_the_frozen_chat_matches_an_independent_count(capsys):
    verify_dataset()
    df, _ = parse_chat(FROZEN)
    _, counts, _ = privacy.build_payload(df, al(*NAMES6))
    hit = own_keyword_matcher()
    raw = [r for r in raw_messages() if "<Media omitted>" not in r[2]]
    mine = [r for r in raw if hit(r[2])]
    planted = {i["text"] for i in frozen_truth() if i["kind"] == "sensitive"}
    filler = [r for r in mine if r[2] not in planted]
    assert counts["withheld"] == len(mine) == len(filler) + 4
    rng = random.Random(0)
    examples = sorted(rng.sample([r[2] for r in filler], 10))
    with capsys.disabled():
        print(f"\n[screen] withheld on the frozen chat: {counts['withheld']} = 4 planted + {len(filler)} filler; by category {counts['withheld_by_category']}")
        print("[screen] 10 filler examples (false positives):")
        for e in examples:
            print("   -", e[:110])


# ---------------------------------------------------------------- build_payload, hand table
def test_build_payload_hand_table():
    d = "2026-03-02"
    rows = [
        ("Sam", "joined", "system"),
        ("Sam", "Hello Maya!"),
        ("Alex", "<Media omitted>", "media"),
        ("Maya", "I need a doctor tomorrow"),
        ("Sam", "you deleted this", "deleted"),
        ("Alex", "mail maya.test@example.com or see https://example.com/q?x=1\nthen call +00 000 000 0000"),
        ("Maya", "on " + ISO + " at 21:19 order #48213, ref " + j("123", "456", sep="")),
    ]
    text, counts, mapping = privacy.build_payload(chat(rows), al("Sam", "Alex", "Maya"))
    want = [
        f"m000001 | {d} 09:01 | Member 1 | Hello Member 3!",
        f"m000002 | {d} 09:02 | Member 2 | [media]",
        f"m000003 | {d} 09:03 | Member 3 | [withheld: sensitive]",
        f"m000004 | {d} 09:05 | Member 2 | mail [email] or see [link] then call [phone]",
        f"m000005 | {d} 09:06 | Member 3 | on {ISO} at 21:19 order #48213, ref [number]",
    ]
    assert text.splitlines() == want
    assert text.endswith("\n")
    assert counts["messages"] == 5 and counts["withheld"] == 1 and counts["withheld_by_category"] == {"health": 1}
    assert counts["replacements"] == {"link": 1, "email": 1, "phone": 1, "handle": 0, "number": 1, "name": 1}
    assert counts["estimated_tokens"] == -(-len(text.encode()) * 100 // 237)  # ceil(bytes / 2.37)
    assert "rough" in counts["estimated_tokens_note"] and counts["prefix"] == "Member"


def test_build_payload_ids_are_sequential_over_the_filtered_chat():
    rows = [("Sam", "a", "system"), ("Sam", "b"), ("Sam", "c", "deleted"), ("Sam", "d")]
    text, _, _ = privacy.build_payload(chat(rows), al("Sam"))
    assert [ln.split(" | ")[0] for ln in text.splitlines()] == ["m000001", "m000002"]


def test_build_payload_on_an_empty_chat():
    text, counts, mapping = privacy.build_payload(chat([("Sam", "x", "system")]), al("Sam"))
    assert text == "" and counts["messages"] == 0 and mapping == {"Member 1": "Sam"}  # alias members always get a token


def test_sensitive_screen_runs_on_the_original_text_before_redaction():
    # the keyword sits inside a URL-like or name-like context: the whole message is withheld, nothing of it is kept
    text, counts, _ = privacy.build_payload(chat([("Sam", "my doctor Maya at https://example.com/clinic?id=1")]), al("Sam", "Maya"))
    assert text.splitlines()[0].endswith("| [withheld: sensitive]") and counts["replacements"]["link"] == 0


# ---------------------------------------------------------------- planted PII and the frozen-chat leak test
PLANTED_PII = ["+00 000 000 0000", "+00 0000 000000", "maya.test@example.com",
               "https://example.com/flat?id=000&ref=chat", "https://example.com/menu?table=0&utm_source=share"]


def test_planted_fake_pii_comes_from_ground_truth_and_is_redacted():
    items = [i["text"] for i in frozen_truth() if i["kind"] == "pii"]
    assert len(items) == 5
    for p in PLANTED_PII:
        assert any(p in t for t in items), p
        assert p not in red(" ".join(items))
    assert red(items[0]) == "call me on [phone] if you get lost"
    assert red("here is the listing https://example.com/flat?id=000&ref=chat") == "here is the listing [link]"
    assert red("send it to maya.test@example.com when you can") == "send it to [email] when you can"


@pytest.fixture(scope="module")
def frozen_payload():
    verify_dataset()
    df, _ = parse_chat(FROZEN)
    text, counts, mapping = privacy.build_payload(df, privacy.load_aliases(ROOT / "aliases.example.json"))
    return text, counts, mapping


def test_frozen_leak_test(frozen_payload, capsys):
    text, counts, mapping = frozen_payload
    body = "\n".join(ln.split(" | ", 3)[3] for ln in text.splitlines())  # message text only
    everything = text
    for n in NAMES6 + ["Sammy", "Mayz"]:
        assert not regex.search(r"(?i)(?<!\p{L})" + n + r"(?!\p{L})", everything), n
    for p in PLANTED_PII:
        assert p not in everything
    for frag in ["maya.test", "example.com", "http", "www.", "flat?id", "utm_source", "+00"]:
        assert frag not in everything.lower(), frag
    assert not re.search(r"@[^\W\d_]", everything)
    assert counts["messages"] == 5136 and len(text.splitlines()) == 5136
    assert counts["replacements"]["link"] == 2 and counts["replacements"]["email"] == 1 and counts["replacements"]["phone"] == 2
    senders = {ln.split(" | ")[2] for ln in text.splitlines()}
    assert senders == {f"Member {i}" for i in range(1, 7)}
    assert set(mapping.values()) == set(NAMES6)
    sub = sum(len(re.findall(n, body, re.IGNORECASE)) for n in NAMES6)  # substrings inside other words (informational)
    with capsys.disabled():
        print(f"\n[leak] frozen payload: {counts['messages']} messages, replacements {counts['replacements']}, withheld {counts['withheld']}, "
              f"~{counts['estimated_tokens']} tokens (rough); name-substrings inside other words: {sub}")


# ---------------------------------------------------------------- fuzz
FUZZ_TEMPLATES = [
    "{n} are you coming", "ok so {n} said that", "thanks {n}, see you", "did {n} call", "{n}?", "({n}) is here", "hey {n}! hey {n}",
    "ask {n} about the {w}", "it was {n}'s idea", "{n}: yes", "love the {w} {n}", "\"{n}\" said no", "tell {n}; tell the {w}",
]
WORDS = ["cheese", "stapler", "lighthouse", "bus", "pizza", "walk", "plan", "snacks"]


def name_variants(n: str, nick: str | None) -> list[str]:
    base = [n, n.lower(), n.upper(), n.title(), "@" + n, "@" + FSI + n + PDI, n + "'s", n + chr(0x2019) + "s", unicodedata.normalize("NFD", n)]
    if nick:
        base += [nick, nick.lower(), "@" + nick]
    return base


def test_fuzz_500_sentences_no_name_survives():
    e = chr(0xE9)
    members = [("Sam", "Sam", ["Sammy"], False), ("Alex", "Alex", [], False), ("Maya", "Maya", ["Mayz"], False), ("Jordan", "Jordan", [], False),
               ("Riley", "Riley", [], False), ("Kai", "Kai", [], False), ("Zo" + e, "Zo" + e, ["Zozo"], False), ("Alex Kim", "Alex K.", [], False)]
    aliases = al(*members)
    forms = [("Sam", "Sammy"), ("Alex", None), ("Maya", "Mayz"), ("Jordan", None), ("Riley", None), ("Kai", None), ("Zo" + e, "Zozo")]
    rng = random.Random(2026)
    rows = []
    for i in range(500):
        n, nick = rng.choice(forms)
        v = rng.choice(name_variants(n, nick))
        t = rng.choice(FUZZ_TEMPLATES).format(n=v, w=rng.choice(WORDS))
        rows.append((rng.choice(["Sam", "Alex", "Maya"]), t))
    text, counts, mapping = privacy.build_payload(chat(rows), aliases)
    assert counts["withheld"] == 0 and counts["messages"] == 500
    out = "\n".join(ln.split(" | ", 3)[3] for ln in text.splitlines())
    bad = regex.findall(r"(?i)(?<!\p{L})(?:sam|alex|maya|jordan|riley|kai|zo" + e + r"|zoé|sammy|mayz|zozo)(?!\p{L})", unicodedata.normalize("NFC", out))
    assert bad == [], bad[:5]
    assert "@" not in out
    assert counts["replacements"]["name"] >= 500  # at least one name per sentence, two in "hey {n}! hey {n}"
    pytest.fuzz_total = counts["replacements"]["name"]


# ---------------------------------------------------------------- CLI
def _env():
    return {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def test_preview_cli_end_to_end_and_no_anthropic_import(tmp_path):
    out = tmp_path / "p.txt"
    r = subprocess.run([sys.executable, "-m", "gcw", "preview", str(FROZEN), "--aliases", str(ROOT / "aliases.example.json"), "--out", str(out)],
                       env=_env(), capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert '"messages": 5136' in r.stdout and '"withheld"' in r.stdout and "20 random payload lines (seed 0)" in r.stdout
    shown = [ln for ln in r.stdout.splitlines() if re.match(r"m\d{6} \| ", ln)]
    assert len(shown) == 20 and all(ln in out.read_text(encoding="utf-8") for ln in shown)
    r2 = subprocess.run([sys.executable, "-m", "gcw", "preview", str(FROZEN), "--aliases", str(ROOT / "aliases.example.json"), "--out", str(tmp_path / "q.txt")],
                        env=_env(), capture_output=True, text=True, cwd=tmp_path)
    assert [ln for ln in r2.stdout.splitlines() if re.match(r"m\d{6} \| ", ln)] == shown  # fixed seed: the same 20 lines
    assert not re.search(r"\bSam\b|\bMaya\b", "\n".join(shown + [out.read_text(encoding="utf-8")]))
    code = "import sys; import gcw.cli, gcw.privacy; assert not any(m == 'anthropic' or m.startswith('anthropic.') or m in ('gcw.llm', 'gcw.cost') for m in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], env=_env(), capture_output=True, text=True).returncode == 0


def test_preview_cli_errors(tmp_path):
    bad = tmp_path / "a.json"
    bad.write_text('{"members": [{"export_name": "A", "nicknames": ["x"]}]}')
    r = subprocess.run([sys.executable, "-m", "gcw", "preview", str(FROZEN), "--aliases", str(bad)], env=_env(), capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 2 and "shorter than 2" in r.stderr
    r = subprocess.run([sys.executable, "-m", "gcw", "preview", str(tmp_path / "nope.txt")], env=_env(), capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 2
    r = subprocess.run([sys.executable, "-m", "gcw", "preview", str(FROZEN), "--out", str(tmp_path / "n.txt")], env=_env(), capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0 and "no --aliases file" in r.stderr


# ---------------------------------------------------------------- keyword list: packaged resource, fails closed
def test_keyword_list_is_loaded_from_the_package_and_has_fined_not_fine():
    cats = privacy.load_keywords()
    assert "fined" in cats["legal"] and "fine" not in cats["legal"]
    assert not privacy.sensitive_screen("Sounds fine.") and privacy.sensitive_screen("I got fined yesterday")
    assert (ROOT / "src" / "gcw" / "data" / "sensitive_keywords.json").is_file() and not (ROOT / "config").exists()
    assert 'gcw = ["data/*.json"]' in (ROOT / "pyproject.toml").read_text()


def test_missing_keyword_file_fails_closed_with_a_clear_error(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError, match="sensitive keyword list not found"):
        privacy.sensitive_screen("hello", tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError, match="sensitive keyword list not found"):
        privacy.build_payload(chat([("Sam", "hello")]), al("Sam"), keywords=tmp_path / "nope.json")
    # the packaged resource missing (a broken install) must also refuse, not return "nothing sensitive"
    class _Gone:
        def joinpath(self, *a):
            return self

        def read_text(self, **k):
            raise FileNotFoundError("gone")

    monkeypatch.setattr(privacy.resources, "files", lambda pkg: _Gone())
    with pytest.raises(FileNotFoundError, match="missing from the installed package"):
        privacy.load_keywords()
    bad = tmp_path / "bad.json"
    bad.write_text('{"categories": {"x": [""]}}')
    with pytest.raises(ValueError):
        privacy.load_keywords(bad)


# ---------------------------------------------------------------- planted items must pass through the layer untouched
PLANTED_KINDS = ("joke", "long_joke", "moment")


def test_planted_jokes_long_joke_and_moments_are_not_withheld_or_altered():
    verify_dataset()
    df, _ = parse_chat(FROZEN)
    pop = privacy.messages(df).reset_index(drop=True)
    text, counts, _ = privacy.build_payload(df, privacy.load_aliases(ROOT / "aliases.example.json"))
    bodies = [ln.split(" | ", 3)[3] for ln in text.splitlines()]
    index = {}
    for i, (ts, s, t) in enumerate(zip(pop["ts"], pop["sender"], pop["text"])):
        index.setdefault((ts.isoformat()[:16], s), []).append(i)
    planted = [it for it in frozen_truth() if it["kind"] in PLANTED_KINDS]
    assert len(planted) == 57
    hit = []
    for it in planted:
        cands = [i for i in index[(it["timestamp"][:16], it["sender"])] if privacy.clean(pop["text"][i]) == privacy.clean(it["text"])]
        assert len(cands) == 1, it
        i = cands[0]
        if bodies[i] != privacy.clean(pop["text"][i]):
            hit.append((it["kind"], it["id"], privacy.sensitive_hits(it["text"]), bodies[i]))
    assert hit == [], hit


def test_party_alone_is_not_sensitive_but_political_party_is():
    for t in ["surprise party on Saturday", "Party time!", "hang on wait I have to find my old party speaker", "the party is at 8"]:
        assert not privacy.sensitive_screen(t), t
    for t in ["which political party will win", "Political   Party meeting", "I joined a political party", "bjp or congress?", "a democrat and a republican"]:
        assert privacy.sensitive_screen(t), t
    assert "political party" in privacy.load_keywords()["politics"] and "party" not in privacy.load_keywords()["politics"]
