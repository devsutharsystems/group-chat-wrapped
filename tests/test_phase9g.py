"""Phase 9g: a file-name-plus-"(file attached)" message is media (stats count it, the payload shows [media] with no file name). Synthetic lines only.
The frozen-chat digests below were taken BEFORE the parser change: neither frozen chat contains such lines, so stats and payload are byte-identical."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gcw.parser import messages, parse_chat
from gcw.privacy import build_payload
from gcw.stats import compute_stats

ROOT = Path(__file__).resolve().parents[1]
ATT = " (file attached)"


def chat(*bodies: str) -> str:
    # lines are built from parts so no export-looking line sits in the source
    return "\n".join("[" + "11/10/2026, 10:0" + str(i) + ":00] " + b for i, b in enumerate(bodies))


def test_file_attached_lines_count_as_media_and_omitted_still_does():
    df, _ = parse_chat(chat("Ann: hello there everyone", "Ben: <Media omitted>", "Ann: IMG-" + "0001-WA0057.jpg" + ATT, "Ben: STK-" + "0002-WA0059.webp" + ATT, "Ann: ok then"))
    assert list(df["is_media"]) == [False, True, True, True, False]
    assert compute_stats(df)["media"]["total"] == 3


def test_payload_shows_media_without_the_file_name_and_keeps_every_line():
    df, _ = parse_chat(chat("Ann: hello there everyone", "Ben: <Media omitted>", "Ann: IMG-" + "0001-WA0057.jpg" + ATT, "Ben: STK-" + "0002-WA0059.webp" + ATT, "Ann: ok then"))
    payload, counts, _ = build_payload(df)
    lines = payload.splitlines()
    assert len(lines) == 5 and [l.split(" | ", 3)[3] for l in lines].count("[media]") == 3
    assert "WA00" not in payload and "file attached" not in payload and ".jpg" not in payload and ".webp" not in payload


def test_only_a_whole_file_name_plus_marker_message_is_media():
    df, _ = parse_chat(chat("Ann: see the notes" + ATT, "Ann: IMG-" + "0001-WA0057.jpg" + ATT + "\na caption"))
    assert not df["is_media"].any()


@pytest.mark.parametrize("path,stats,payload", [
    ("synthetic/frozen/chat_synthetic.txt", "c9835fcfacf4f491f080778436f1f4403f763f13b976434c708fb122148bae2b", "36d12d813bd65ccc7d70324751f47cdc37461d3de4351f37e587fd072e910f1b"),
    ("synthetic/frozen_large/chat_synthetic_large.txt", "67d1dde5f2e7f9c4f3142bdd023333bd652af43b90ce700a327d3b2219ab1d61", "e244e886b414a7fc55b0935800c8a6d3f70e1d8c6cabd8addb127f1c618f8ea3"),
])
def test_frozen_chats_are_unchanged(path, stats, payload):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert "(file attached)" not in text
    df, _ = parse_chat(text)
    s = json.dumps(compute_stats(df), sort_keys=True, default=str)
    assert hashlib.sha256(s.encode()).hexdigest() == stats
    assert hashlib.sha256(build_payload(df)[0].encode()).hexdigest() == payload
