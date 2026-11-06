from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from gcw.dataset import verify_dataset
from gcw.parser import parse_chat

FIX = Path("tests/fixtures/android_us_12h.txt")
FROZEN = Path("synthetic/frozen/chat_synthetic.txt")
NN, ZWJ = " ", "‍"


def j(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def ts(df, i):
    return df["ts"].iloc[i].to_pydatetime()


# ---------------------------------------------------------------- the real-export fixture (VERIFIED format)
def test_fixture_counts_by_hand():
    df, r = parse_chat(FIX)
    # hand count of the 14-line file: 4 system lines + 10 sender lines, all "Sam"
    assert (r.n_messages, r.n_system, r.n_unparsed) == (10, 4, 0)
    assert int(df["is_media"].sum()) == 1 and int(df["is_deleted"].sum()) == 1 and int(df["is_edited"].sum()) == 1
    assert r.per_sender == {"Sam": 10}
    assert set(df.loc[~df["is_system"], "sender"]) == {"Sam"}
    assert r.format == "android_12h" and r.format_verified is True
    # single-day file: both date orders fit -> ambiguous, assumed m/d because the headers have AM/PM
    assert r.ambiguous is True and r.date_order == "mdy" and r.date_order_source == "assumed"
    assert any("AMBIGUOUS" in w for w in r.warnings)
    assert {d.date() for d in df["ts"]} == {datetime(2026, 11, 5).date()}
    assert (r.first_ts, r.last_ts) == (datetime(2026, 11, 5, 21, 18), datetime(2026, 11, 5, 21, 21))


def test_fixture_rows_by_hand():
    df, _ = parse_chat(FIX)
    assert df["id"].tolist() == [f"m{i:06d}" for i in range(1, 15)]
    assert df["is_system"].tolist() == [True] * 4 + [False] * 10
    assert df["sender"].iloc[:4].isna().all()
    media = df[df["is_media"]]
    assert media["text"].tolist() == ["<Media omitted>"]
    dele = df[df["is_deleted"]]
    assert dele["text"].tolist() == ["You deleted this message"]
    ed = df[df["is_edited"]]
    assert ed["text"].tolist() == ["I am learning Whatsapp Features! ✨"]  # suffix stripped
    assert df["text"].iloc[6] == "https://www.google.com?utm_source=chatgpt.com"  # query string kept
    assert "You created this group" in df["text"].tolist()[:4]


def test_plain_space_variant_same_result():
    text = FIX.read_text(encoding="utf-8").replace(NN, " ")
    assert NN not in text
    df, r = parse_chat(text)
    assert (r.n_messages, r.n_system, r.n_unparsed) == (10, 4, 0)
    assert int(df["is_media"].sum()) == 1 and r.last_ts == datetime(2026, 11, 5, 21, 21)


def test_str_path_bom_and_crlf_variants():
    base = parse_chat(FIX)[1].n_messages
    assert parse_chat(str(FIX))[1].n_messages == base == 10
    text = FIX.read_text(encoding="utf-8")
    assert parse_chat("﻿" + text)[1].n_messages == 10
    df, r = parse_chat(text.replace("\n", "\r\n"))
    assert r.n_messages == 10 and not any("\r" in t for t in df["text"])


# ---------------------------------------------------------------- date order
def test_dmy_by_component_over_12_and_12h_clock_edges():
    df, r = parse_chat(j(
        "13/05/26, 12:05 AM - Sam: midnight",
        "14/05/26, 12:30 PM - Alex: noon",
        "15/05/26, 11:30 PM - Sam: late",
    ))
    assert (r.date_order, r.ambiguous, r.date_order_source) == ("dmy", False, "component>12")
    assert [ts(df, i) for i in range(3)] == [datetime(2026, 5, 13, 0, 5), datetime(2026, 5, 14, 12, 30), datetime(2026, 5, 15, 23, 30)]


def test_mdy_by_component_over_12():
    df, r = parse_chat(j("5/13/26, 9:15 AM - Sam: a", "5/14/26, 9:16 AM - Sam: b"))
    assert (r.date_order, r.ambiguous) == ("mdy", False) and ts(df, 0) == datetime(2026, 5, 13, 9, 15)


def test_rule2_monotone_picks_mdy():
    # m/d reading: Feb 5, Mar 4, Apr 5 (increasing); d/m reading: 2 May, 3 Apr (goes back) -> only m/d fits
    df, r = parse_chat(j("02/05/26, 9:00 AM - A: x", "03/04/26, 9:00 AM - A: y", "04/05/26, 9:00 AM - A: z"))
    assert (r.date_order, r.ambiguous, r.date_order_source) == ("mdy", False, "monotone")
    assert ts(df, 1) == datetime(2026, 3, 4, 9, 0)


def test_rule2_monotone_picks_dmy():
    # d/m reading: 5 Feb, 4 Mar, 5 Apr (increasing); m/d reading: May 2, Apr 3 (goes back) -> only d/m fits
    df, r = parse_chat(j("05/02/26, 9:00 AM - A: x", "04/03/26, 9:00 AM - A: y", "05/04/26, 9:00 AM - A: z"))
    assert (r.date_order, r.ambiguous, r.date_order_source) == ("dmy", False, "monotone")
    assert ts(df, 1) == datetime(2026, 3, 4, 9, 0)


def test_override_and_invalid_override():
    text = j("05/11/26, 21:18 - Sam: hi", "05/11/26, 21:20 - Alex: yo")
    df, r = parse_chat(text)  # 24h, single day, ambiguous: d/m assumed (UNVERIFIED format)
    assert r.ambiguous and r.date_order == "dmy" and ts(df, 0) == datetime(2026, 11, 5, 21, 18)
    df, r = parse_chat(text, date_order="mdy")
    assert (r.ambiguous, r.date_order, r.date_order_source) == (False, "mdy", "override") and ts(df, 0) == datetime(2026, 5, 11, 21, 18)
    assert parse_chat(text, date_order="m/d")[1].date_order == "mdy"
    with pytest.raises(ValueError):
        parse_chat(text, date_order="ymd")


# ---------------------------------------------------------------- other formats (UNVERIFIED: no real samples)
def test_android_24h_unverified():
    df, r = parse_chat(j("25/12/26, 08:05 - Sam: x", "26/12/26, 23:59 - Alex: y"))
    assert r.format == "android_24h" and r.format_verified is False
    assert any("UNVERIFIED" in w for w in r.warnings)
    assert (r.date_order, r.ambiguous) == ("dmy", False)
    assert [ts(df, 0), ts(df, 1)] == [datetime(2026, 12, 25, 8, 5), datetime(2026, 12, 26, 23, 59)]


def test_ios_12h_with_lrm_and_system_unverified():
    lrm = "‎"
    df, r = parse_chat(j(
        f"{lrm}[13/05/26, 9:15:00{NN}PM] {lrm}Messages and calls are end-to-end encrypted. No one outside of this chat can read them.",
        f"[13/05/26, 9:15:02{NN}PM] Sam: hello",
        "[14/05/26, 9:16:30 PM] Alex: hi again",
    ))
    assert r.format == "ios" and not r.format_verified
    assert (r.n_messages, r.n_system, r.n_unparsed) == (2, 1, 0)
    assert r.date_order == "dmy" and ts(df, 1) == datetime(2026, 5, 13, 21, 15, 2)
    assert df["sender"].tolist()[1:] == ["Sam", "Alex"]


def test_ios_24h_four_digit_year_unverified():
    df, r = parse_chat(j("[14/05/2026, 21:15:02] Sam: x", "[15/05/2026, 07:01:09] Alex: y"))
    assert r.format == "ios" and r.date_order == "dmy"
    assert [ts(df, 0), ts(df, 1)] == [datetime(2026, 5, 14, 21, 15, 2), datetime(2026, 5, 15, 7, 1, 9)]


# ---------------------------------------------------------------- message body rules
def test_colon_inside_text_splits_at_first_colon_space():
    df, r = parse_chat(j("5/11/26, 9:19 PM - Sam: ratio is 3: 1 and note: yes"))
    assert df["sender"].iloc[0] == "Sam" and df["text"].iloc[0] == "ratio is 3: 1 and note: yes" and r.n_system == 0


def test_zwj_emoji_kept_intact():
    fam = f"\U0001f468{ZWJ}\U0001f469{ZWJ}\U0001f467"
    df, r = parse_chat(j(f"5/11/26, 9:19 PM - Sam: family {fam} here"))
    assert df["text"].iloc[0] == f"family {fam} here" and r.n_messages == 1


def test_system_patterns_are_anchored_and_cannot_eat_messages():
    df, r = parse_chat(j(
        "5/11/26, 9:18 PM - Sam: I changed my mind",
        "5/11/26, 9:18 PM - Sam: Alex was added",
        "5/11/26, 9:18 PM - Sam: You removed Alex",
        "5/11/26, 9:19 PM - Sam changed the group description",
        "5/11/26, 9:19 PM - Alex left",
        "5/11/26, 9:19 PM - Kai joined using this group's invite link",
        "5/11/26, 9:19 PM - Your security code with Maya changed. Tap to learn more.",
        "5/11/26, 9:19 PM - Something odd happened",  # no 'Sender: ' -> treated as system
    ))
    assert df["is_system"].tolist() == [False, False, False, True, True, True, True, True]
    assert (r.n_messages, r.n_system) == (3, 5)


def test_deleted_and_media_flags_and_custom_patterns():
    text = j("5/11/26, 9:19 PM - Sam: You deleted this message", "5/11/26, 9:19 PM - Alex: This message was deleted",
             "5/11/26, 9:19 PM - Sam: <Media omitted>", "5/11/26, 9:19 PM - Sam: gone", "5/11/26, 9:19 PM - Sam: ping")
    df, r = parse_chat(text)
    assert df["is_deleted"].tolist() == [True, True, False, False, False]  # 2nd pattern is UNVERIFIED but on by default
    assert df["is_media"].tolist() == [False, False, True, False, False]
    assert r.n_messages == 5  # deleted and media still count as messages
    df, r = parse_chat(text, system_patterns=(r"Sam: ping",), deleted_patterns=("gone",), media_patterns=("<img>",))
    assert df["is_deleted"].tolist() == [False, False, False, True, False]
    assert df["is_media"].sum() == 0 and df["is_system"].tolist() == [False] * 4 + [True]


def test_edited_suffix_stripped_only_at_end():
    df, _ = parse_chat(j("5/11/26, 9:19 PM - Sam: hi <This message was edited> there", "5/11/26, 9:20 PM - Sam: bye <This message was edited>"))
    assert df["is_edited"].tolist() == [False, True] and df["text"].tolist() == ["hi <This message was edited> there", "bye"]


# ---------------------------------------------------------------- multi-line (UNVERIFIED against a real export)
def test_multiline_appends_with_newline_and_keeps_inner_blank():
    df, r = parse_chat(j("5/11/26, 9:19 PM - Sam: line one", "line two", "", "line four", "5/11/26, 9:20 PM - Alex: ok"))
    assert df["text"].tolist() == ["line one\nline two\n\nline four", "ok"]
    assert (r.n_messages, r.n_unparsed) == (2, 0)


def test_multiline_edited_and_trailing_blank_lines():
    df, _ = parse_chat("5/11/26, 9:19 PM - Sam: first\nsecond <This message was edited>\n\n\n")
    assert df["text"].tolist() == ["first\nsecond"] and df["is_edited"].tolist() == [True]


def test_unicode_line_separator_does_not_split_a_message():
    df, r = parse_chat(j("5/11/26, 9:19 PM - Sam: a b", "5/11/26, 9:20 PM - Alex: c\u0085d"))
    assert df["text"].tolist() == ["a b", "c\u0085d"] and r.n_unparsed == 0


# ---------------------------------------------------------------- unparsed / degenerate input
def test_leading_junk_and_impossible_date_count_as_unparsed():
    df, r = parse_chat(j("junk line", "28/02/26, 9:00 AM - Sam: ok", "31/02/26, 9:00 AM - Sam: impossible", "still junk after it"))
    assert (r.n_messages, r.n_unparsed) == (1, 3)  # leading junk, impossible date, and the line that followed it
    assert df["text"].tolist() == ["ok"]


def test_no_header_format_recognised():
    df, r = parse_chat("hello world\nsecond line\n")
    assert df.empty and r.n_unparsed == 2 and r.format is None and r.warnings


# ---------------------------------------------------------------- the frozen synthetic chat (5144 / 9 / ...)
def test_frozen_chat_counts():
    verify_dataset()  # fail loudly if the data is not the frozen version
    df, r = parse_chat(FROZEN)
    assert (r.n_messages, r.n_system, r.n_unparsed) == (5144, 9, 0)
    assert int(df["is_media"].sum()) == 136
    assert int(df["is_deleted"].sum()) == 8
    assert int(df["is_edited"].sum()) == 142
    assert int(df["text"].str.contains("\n").sum()) == 32  # multi-line messages
    assert FROZEN.read_bytes().count(b"\n") == 5185  # raw file lines, not parser output
    assert r.per_sender == {"Riley": 1316, "Kai": 1158, "Maya": 1010, "Sam": 899, "Jordan": 527, "Alex": 234}
    assert (r.date_order, r.ambiguous, r.format) == ("mdy", False, "android_12h")
    assert len(df) == 5153 and df["id"].is_unique


def test_system_patterns_never_match_a_sender_line_even_when_the_text_fits_them():
    # each text WOULD match a system pattern if the "Sam: " prefix were allowed inside the name part
    lines = ["Sam: I changed the group description yesterday", "Sam: they changed their phone number", "Sam: Alex added the file",
             "Sam: Kai left", "Sam: Kai joined", "Sam: Alex created group chat rules", "Sam: Kai was added"]
    df, r = parse_chat(j(*[f"5/11/26, 9:19 PM - {x}" for x in lines]))
    assert df["is_system"].tolist() == [False] * 7 and (r.n_messages, r.n_system) == (7, 0)
    assert df["sender"].tolist() == ["Sam"] * 7


def test_messages_and_message_timestamps_on_fixture():
    from gcw.parser import messages

    df, r = parse_chat(FIX)
    # hand: first sender line is 9:19 PM (the four system lines are 9:18 PM), last line 9:21 PM, all on 2026-11-05
    assert r.first_msg_ts == datetime(2026, 11, 5, 21, 19) and r.last_msg_ts == datetime(2026, 11, 5, 21, 21)
    assert (r.first_ts, r.last_ts) == (datetime(2026, 11, 5, 21, 18), datetime(2026, 11, 5, 21, 21))  # unchanged: all rows
    m = messages(df)
    assert len(m) == 9  # 10 sender rows minus the 1 deleted
    assert not m["is_system"].any() and not m["is_deleted"].any()
    assert "You deleted this message" not in m["text"].tolist() and int(m["is_media"].sum()) == 1  # media stays
    assert len(df) == 14  # the raw frame is untouched


def test_messages_helper_on_empty_and_no_sender_rows():
    from gcw.parser import messages

    df, r = parse_chat("5/11/26, 9:18 PM - You created this group\n")
    assert len(messages(df)) == 0 and r.first_msg_ts is None and r.last_msg_ts is None and r.first_ts is not None
    df, r = parse_chat("nothing here")
    assert len(messages(df)) == 0 and r.first_msg_ts is None
