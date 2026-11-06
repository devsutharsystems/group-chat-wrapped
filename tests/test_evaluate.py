"""evaluate.py: classification of dropped evidence, grounding vs rule-compliant rates, dev/held-out split. Hand-built chats, no API."""
from __future__ import annotations

import pandas as pd
import pytest

from gcw import evaluate, privacy, verify
from test_privacy import al
from test_stats import frame

ROWS = [
    (1, "03-02 09:00", "Sam", "the stapler has opinions again", ""),
    (2, "03-02 09:01", "Alex", "totally different message about cheese", ""),
    (3, "03-02 09:02", "Maya", "it’s a lighthouse kind of day", ""),  # curly apostrophe
    (4, "03-02 09:03", "Sam", "I need a doctor tomorrow", ""),
    (5, "03-02 09:04", "Alex", "<Media omitted>", "media"),
    (6, "03-02 09:05", "Maya", "I <3 pizza always and forever", ""),
    (7, "03-02 09:06", "Sam", "short one", ""),
]


@pytest.fixture(scope="module")
def index():
    rows, _, _ = privacy.build_payload_rows(frame(ROWS), al("Sam", "Alex", "Maya"))
    return verify.make_index(rows)


def rep(*evs):
    return {"running_jokes": [], "awards": [], "moments": [{"title": "t", "summary": "s", "evidence": list(evs)}]}


def ev(pid, quote):
    return {"message_id": pid, "quote": quote}


def status(index, pid, quote):
    return evaluate.classify_evidence(rep(ev(pid, quote)), index)[0]


@pytest.mark.parametrize("pid, quote, want", [
    ("m000001", "the stapler has opinions again", "verified"),
    ("m000099", "the stapler has opinions again", "id_missing"),
    ("m000004", "I need a doctor tomorrow", "withheld"),
    ("m000005", "<Media omitted>", "media"),
    ("m000001", "the stapler", "too_short"),
    ("m000002", "the stapler has opinions again", "other_message"),
    ("m000001", "the stapler has opinions today", "not_found"),
    ("m000003", "it's a lighthouse kind of day", "normalisation_only"),  # straight apostrophe where the chat has a curly one
    ("m000003", "IT’S a LIGHTHOUSE kind of day", "normalisation_only"),  # case only
    ("m000006", "I <3 pizza always and forever", "normalisation_only"),  # the model turned the fullwidth bracket back into '<'
    ("m000006", "I " + chr(0xFF1C) + "3 pizza always and forever", "verified"),
])
def test_status_of_each_kind_of_evidence(index, pid, quote, want):
    assert status(index, pid, quote)["status"] == want


def test_other_message_reports_the_real_id_and_the_distance(index):
    r = status(index, "m000007", "the stapler has opinions again")
    assert r["status"] == "other_message" and r["real_ids"] == ["m000001"] and r["distance"] == 6 and not r["grounded"]


def test_too_short_reports_whether_it_was_grounded(index):
    assert status(index, "m000001", "the stapler")["grounded"] is True
    assert status(index, "m000002", "the stapler")["grounded"] is False


def test_duplicate_and_caps(index):
    recs = evaluate.classify_evidence(rep(ev("m000001", "the stapler has opinions"), ev("m000001", "stapler has opinions again")), index)
    assert [r["status"] for r in recs] == ["verified", "duplicate"]
    many = {"running_jokes": [], "awards": [], "moments": [{"title": "t", "summary": "s", "evidence": [ev("m000001", "the stapler has opinions")] * 13}]}
    assert [r["status"] for r in evaluate.classify_evidence(many, index)][-1] == "over_cap"
    assert evaluate.classify_evidence({"running_jokes": "nope", "moments": [None, {"evidence": [5]}], "awards": []}, index)[0]["status"] == "bad_shape"


def test_rates_and_counts_agree_with_verify(index):
    report = rep(ev("m000001", "the stapler has opinions again"), ev("m000001", "the stapler"), ev("m000002", "the stapler has opinions again"),
                 ev("m000003", "it's a lighthouse kind of day"), ev("m000099", "x" * 20), ev("m000001", "stapler has opinions again"))
    recs = evaluate.classify_evidence(report, index)
    summ = evaluate.summarise_classification(recs)
    _, stats = verify.verify_report(report, index, valid_members={"Member 1", "Member 2", "Member 3"})
    assert summ["evidence_total"] == stats["evidence_total"] == 6
    assert summ["status_counts"]["verified"] == stats["evidence_verified"] == 1
    assert summ["rule_compliant_rate"] == pytest.approx(1 / 6)
    assert summ["grounding_rate"] == pytest.approx(3 / 6)  # verified + the short grounded one + the duplicate; the curly-apostrophe and wrong-id ones are not grounded
    assert summ["too_short_but_grounded"] == 1 and summ["other_message_distances"] == [1]


def test_strong_fold():
    assert evaluate.strong_fold("It’s  A… " + chr(0xFF1C) + "3") == "it's a... <3"


def test_dev_held_out_split_is_derived_from_the_truth_items():
    truth = [{"kind": "joke", "id": "j1", "timestamp": "2026-01-05T10:00:00"}, {"kind": "joke", "id": "j1", "timestamp": "2026-03-05T10:00:00"},
             {"kind": "joke", "id": "j3", "timestamp": "2026-04-01T10:00:00"}, {"kind": "moment", "id": "m1", "timestamp": "2026-02-08T23:59:00"},
             {"kind": "moment", "id": "m2", "timestamp": "2026-02-09T00:00:00"}, {"kind": "pii", "id": "p", "timestamp": "2026-01-01T00:00:00"}]
    res = evaluate.dev_held_out(truth, "2025-11-01", "2026-02-08")
    assert {k: v["status"] for k, v in res.items()} == {"j1": "dev", "j3": "held-out", "m1": "dev", "m2": "held-out"}
    assert res["j1"]["occurrences"] == 2 and res["j1"]["in_dev"] == 1


def test_frozen_dev_and_held_out_items_match_the_prd_table():
    import json

    from test_privacy import TRUTH

    res = evaluate.dev_held_out(json.loads(TRUTH.read_text(encoding="utf-8"))["items"], "2025-11-01", "2026-02-08")
    assert sorted(k for k, v in res.items() if v["status"] == "dev") == ["j1", "j2", "jL", "m1"]
    assert sorted(k for k, v in res.items() if v["status"] == "held-out") == ["j3", "j4", "j5", "j6", "m2", "m3"]
    assert res["jL"]["occurrences"] == 12 and res["jL"]["in_dev"] == 4
