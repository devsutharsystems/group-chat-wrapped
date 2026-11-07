"""The large frozen dataset (Phase 5a): its hashes, structure, the payload leak test and quote verification on the large payload, and the committed
results file. No API."""
from __future__ import annotations

import json
import re

import pytest
import regex

import scan_repo
from gcw import dataset, privacy, verify
from gcw.parser import parse_chat
from test_privacy import NAMES6, PLANTED_PII, ROOT

LARGE = ROOT / "synthetic" / "frozen_large"
CHAT = LARGE / dataset.LARGE_CHAT_FILE


@pytest.fixture(scope="module")
def payload():
    dataset.verify_large_dataset()
    df, _ = parse_chat(CHAT)
    rows, counts, mapping = privacy.build_payload_rows(df, privacy.load_aliases(ROOT / "aliases.example.json"))
    return rows, counts, mapping


def test_large_dataset_is_frozen_separate_and_small_enough_to_commit():
    assert dataset.verify_large_dataset() and dataset.verify_dataset() and dataset.which_frozen(CHAT) == "large"
    assert dataset.is_frozen_large_chat(CHAT) and not dataset.is_frozen_chat(CHAT)
    assert CHAT.stat().st_size < 3 * 1024 * 1024
    man = json.loads((LARGE / "manifest.json").read_text())
    assert man["chat_sha256"] == dataset.LARGE_CHAT_SHA256 and man["ground_truth_sha256"] == dataset.LARGE_GROUND_TRUTH_SHA256 and man["chat_bytes"] == CHAT.stat().st_size
    assert dataset.LARGE_CHAT_SHA256 != dataset.CHAT_SHA256 and (ROOT / "synthetic" / "frozen" / "chat_synthetic.txt").is_file()


def test_large_ground_truth_has_the_same_planted_structure():
    items = json.loads((LARGE / "ground_truth.json").read_text())["items"]
    kinds = {k: len({i["id"] for i in items if i["kind"] == k}) for k in ("joke", "long_joke", "moment")}
    assert kinds == {"joke": 6, "long_joke": 1, "moment": 3}
    assert sum(i["kind"] == "sensitive" for i in items) == 4 and sum(i["kind"] == "pii" for i in items) == 5 and sum(i["kind"] == "injection" for i in items) == 1
    assert {i["id"] for i in items if i["kind"] == "joke"} == {"j1", "j2", "j3", "j4", "j5", "j6"}


def test_large_payload_size_and_withheld_planted_lines(payload):
    rows, counts, mapping = payload
    assert counts["messages"] == len(rows) == 17097 and counts["withheld"] == 101 and len(mapping) == 6
    text = privacy.rows_text(rows)
    assert 2_000_000 < len(text.encode()) < 2_200_000
    items = json.loads((LARGE / "ground_truth.json").read_text())["items"]
    sens = [i for i in items if i["kind"] == "sensitive"]
    for it in sens:
        stamp = it["timestamp"].replace("T", " ")[:16]
        assert any(r["withheld"] and f"{r['ts']:%Y-%m-%d %H:%M}" == stamp for r in rows), it["timestamp"]


def test_large_payload_leak_test(payload):
    rows, counts, _ = payload
    text = privacy.rows_text(rows)
    for n in NAMES6 + ["Sammy", "Mayz"]:
        assert not regex.search(r"(?i)(?<!\p{L})" + n + r"(?!\p{L})", text), n
    for p in PLANTED_PII + ["maya.test", "example.com"]:
        assert p not in text
    assert "http" not in text.lower() and not re.search(r"@[^\W\d_]", text)
    assert counts["replacements"]["link"] >= 1 and counts["replacements"]["email"] >= 1 and counts["replacements"]["phone"] >= 1


def test_quote_verification_on_the_large_payload(payload):
    rows, _, _ = payload
    index = verify.make_index(rows)
    long_rows = [r for r in rows if not r["withheld"] and not r["media"] and len(r["body"]) >= 40]
    a, b = long_rows[10], long_rows[5000]
    members = {r["sender"] for r in rows}
    good = {"running_jokes": [], "awards": [], "moments": [{"title": "t", "summary": "s", "evidence": [{"message_id": a["pid"], "quote": a["body"][:30]}]}]}
    out, st = verify.verify_report(good, index, valid_members=members)
    assert len(out["moments"]) == 1 and st["evidence_verified"] == 1
    wrong_id = {**good, "moments": [{"title": "t", "summary": "s", "evidence": [{"message_id": b["pid"], "quote": a["body"][:30]}]}]}
    out, st = verify.verify_report(wrong_id, index, valid_members=members)
    assert out["moments"] == [] and st["drop_reasons"]["quote_not_found"] == 1  # a quote cited under another message's id never verifies
    withheld = next(r for r in rows if r["withheld"])
    out, st = verify.verify_report({**good, "moments": [{"title": "t", "summary": "s", "evidence": [{"message_id": withheld["pid"], "quote": "I need a doctor tomorrow"}]}]}, index, valid_members=members)
    assert out["moments"] == [] and st["drop_reasons"]["withheld"] == 1


def test_the_committed_large_results_hold_counts_and_ids_only(tmp_path):
    base = ROOT / "docs" / "results" / "eval_large_A"
    j, m = json.loads(base.with_suffix(".json").read_text()), base.with_suffix(".md").read_text()
    assert j["dataset"] == "large" and j["n_runs"] == 1 and j["runs"][0]["input_tokens"] == 889497 and j["runs"][0]["stop_reason"] == "end_turn" and j["messages"] == 17097
    assert set(j["recall_by_third"]) == {"start", "middle", "end", "long-range"} and set(j["planted"]) == {"j1", "j2", "j3", "j4", "j5", "j6", "jL", "m1", "m2", "m3"}
    blob = base.with_suffix(".json").read_text() + m
    for forbidden in ("stapler", "cheese", "pigeon", "sock", "elevator", "Thursday", "surprise party", "Sam", "Alex", "Maya", "Jordan", "Riley", "Kai"):
        assert forbidden not in blob, forbidden
    assert "n = 1" in m and scan_repo.scan_file(base.with_suffix(".md"), ROOT, set()) == [] and scan_repo.scan_file(base.with_suffix(".json"), ROOT, set()) == []
