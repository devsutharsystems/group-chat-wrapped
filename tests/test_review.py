"""review.py: stable ids, statuses, apply, file round trip, the review CLI, and the synthetic auto-approve gate. No API, no render."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from gcw import dataset, review
from test_privacy import ROOT, FROZEN


def ev(pid="m000001", quote="a quote that is long enough"):
    return {"message_id": pid, "quote": quote}


def item(title="Cheese protocol", first="m000001", **k):
    return {"title": title, "summary": "s", "evidence": [ev(first), ev("m000002")], **k}


REPORT = {"running_jokes": [item("Cheese protocol", "m000001")], "moments": [item("Cake disaster", "m000010")],
          "awards": [{"award": "Best planner", "member": "Member 4", "summary": "s", "evidence": [ev("m000020")]}]}


def test_item_id_is_stable_and_depends_on_type_title_and_first_evidence():
    base = review.item_id("moments", item("Cake", "m000010"))
    assert base == review.item_id("moments", item("Cake", "m000010")) and len(base) == 12 and int(base, 16) >= 0
    assert base != review.item_id("running_jokes", item("Cake", "m000010"))  # type
    assert base != review.item_id("moments", item("Cake!", "m000010"))  # title
    assert base != review.item_id("moments", item("Cake", "m000011"))  # first evidence id
    other = item("Cake", "m000010")
    other["evidence"] = [ev("m000010"), ev("m000099")]
    other["summary"] = "different"
    assert base == review.item_id("moments", other)  # later evidence and the summary do not matter
    assert review.item_id("awards", {"award": "Best planner", "evidence": [ev("m000020")]}) == review.item_id("awards", {"award": "Best planner", "evidence": [ev("m000020")], "member": "x"})


def test_new_review_is_all_pending_and_nothing_renders():
    rv = review.new_review(REPORT, "run1")
    assert rv["version"] == 1 and rv["run"] == "run1" and len(rv["items"]) == 3 and {v["status"] for v in rv["items"].values()} == {"pending"}
    assert review.apply(REPORT, rv) == {"running_jokes": [], "moments": [], "awards": []}
    assert review.apply(REPORT, None) == {"running_jokes": [], "moments": [], "awards": []}
    assert review.counts(REPORT, rv) == {"pending": 3, "approved": 0, "rejected": 0}


def test_apply_keeps_only_approved_items_in_order():
    rv = review.new_review(REPORT)
    ids = {v["title"]: i for i, v in rv["items"].items()}
    assert review.set_status(rv, [ids["Cake disaster"], ids["Best planner"]], "approved") == []
    review.set_status(rv, [ids["Cheese protocol"]], "rejected")
    out = review.apply(REPORT, rv)
    assert out == {"running_jokes": [], "moments": REPORT["moments"], "awards": REPORT["awards"]}
    assert review.counts(REPORT, rv) == {"pending": 0, "approved": 2, "rejected": 1}


def test_unknown_ids_and_items_missing_from_the_review():
    rv = review.new_review(REPORT)
    assert review.set_status(rv, ["nope", "alsono"], "approved") == ["nope", "alsono"]
    with pytest.raises(review.ReviewError):
        review.set_status(rv, [], "maybe")
    rv["items"]["zzzzzzzzzzzz"] = {"type": "moments", "title": "ghost", "status": "approved"}  # an id that is in no report: ignored
    longer = {**REPORT, "moments": REPORT["moments"] + [item("New item", "m000030")]}
    assert review.apply(longer, rv) == {"running_jokes": [], "moments": [], "awards": []}  # the new item is not in the review: pending
    assert review.counts(longer, rv)["pending"] == 4
    merged = review.merge(rv, longer)
    assert len(merged["items"]) == 5 and merged["items"][review.item_id("moments", longer["moments"][1])]["status"] == "pending"


def test_save_load_round_trip_and_atomic_write(tmp_path):
    rv = review.new_review(REPORT, "r")
    review.set_status(rv, [next(iter(rv["items"]))], "approved")
    path = tmp_path / "deep" / "dir" / "r.json"
    review.save_review(path, rv)
    assert review.load_review(path) == rv and not list(path.parent.glob("*.tmp"))
    review.save_review(path, review.new_review(REPORT, "r2"))
    assert review.load_review(path)["run"] == "r2"


@pytest.mark.parametrize("content", ["not json", "[]", '{"items": []}', '{"items": {"a": {"status": "maybe"}}}', '{"items": {"a": 5}}'])
def test_malformed_review_files_are_refused(tmp_path, content):
    f = tmp_path / "r.json"
    f.write_text(content)
    with pytest.raises(review.ReviewError):
        review.load_review(f)
    with pytest.raises(review.ReviewError):
        review.load_review(tmp_path / "missing.json")


def test_auto_approve_gate_only_accepts_the_frozen_chat(tmp_path):
    assert dataset.is_frozen_chat(FROZEN)
    copy = tmp_path / "chat.txt"
    shutil.copy(FROZEN, copy)
    assert dataset.is_frozen_chat(copy)  # same bytes, any path
    copy.write_bytes(copy.read_bytes() + b"\n")  # one byte more
    assert not dataset.is_frozen_chat(copy)
    assert not dataset.is_frozen_chat(tmp_path / "missing.txt") and not dataset.is_frozen_chat(tmp_path)


def _env():
    return {**os.environ, "PYTHONPATH": str(ROOT / "src"), "GCW_TEST_NO_NETWORK": "1"}


def _run(args, cwd):
    return subprocess.run([sys.executable, "-m", "gcw", *args], env=_env(), capture_output=True, text=True, cwd=cwd)


def test_review_cli_lists_approves_rejects_and_reports_unknown_ids(tmp_path):
    run = tmp_path / "20260101T000000-A.json"
    run.write_text(json.dumps({"config": "A", "messages": 1}))
    (tmp_path / "20260101T000000-A.report.json").write_text(json.dumps(REPORT))
    rf = tmp_path / "rv.json"
    r = _run(["review", str(run), "--file", str(rf)], tmp_path)
    assert r.returncode == 0 and "Cheese protocol" in r.stdout and "pending" in r.stdout and "{'pending': 3, 'approved': 0, 'rejected': 0}" in r.stdout
    rv = json.loads(rf.read_text())
    ids = {v["title"]: i for i, v in rv["items"].items()}
    r = _run(["review", str(run), "--file", str(rf), "--approve", ids["Cake disaster"], "--reject", ids["Cheese protocol"]], tmp_path)
    assert r.returncode == 0 and "{'pending': 1, 'approved': 1, 'rejected': 1}" in r.stdout
    r = _run(["review", str(run), "--file", str(rf), "--approve", "bogus"], tmp_path)
    assert r.returncode == 2 and "unknown item ids: bogus" in r.stderr
    assert json.loads(rf.read_text())["items"][ids["Cake disaster"]]["status"] == "approved"  # the failed call changed nothing
    r = _run(["review", str(tmp_path / "nope.json")], tmp_path)
    assert r.returncode == 3
    (tmp_path / "x.json").write_text("{}")
    r = _run(["review", str(tmp_path / "x.json")], tmp_path)
    assert r.returncode == 3 and "without --save-response" in r.stderr


def test_merge_keeps_existing_statuses_and_adds_new_items_as_pending():
    rv = review.new_review(REPORT)
    ids = {v["title"]: i for i, v in rv["items"].items()}
    review.set_status(rv, [ids["Cake disaster"]], "approved")
    review.set_status(rv, [ids["Cheese protocol"]], "rejected")
    longer = {**REPORT, "moments": REPORT["moments"] + [item("New item", "m000030")]}
    merged = review.merge(rv, longer)
    assert merged["items"][ids["Cake disaster"]]["status"] == "approved" and merged["items"][ids["Cheese protocol"]]["status"] == "rejected"
    assert merged["items"][ids["Best planner"]]["status"] == "pending" and len(merged["items"]) == 4


def _three_moments():
    return {"running_jokes": [], "awards": [], "moments": [item("First", "m000001"), item("Second", "m000002"), item("Third", "m000003")]}


def test_default_order_is_the_models_order_and_rank_reorders():
    rep = _three_moments()
    rv = review.approve_all(rep)
    assert [m["title"] for m in review.apply(rep, rv)["moments"]] == ["First", "Second", "Third"]  # no ranks: model order, no cherry-picking
    ids = {v["title"]: i for i, v in rv["items"].items()}
    assert review.set_rank(rv, ids["Third"], 0) is True
    assert [m["title"] for m in review.apply(rep, rv)["moments"]] == ["First", "Third", "Second"]  # rank 0 ties with First's default rank (its position 0): model order breaks the tie
    review.set_rank(rv, ids["Third"], -1)
    assert [m["title"] for m in review.apply(rep, rv)["moments"]] == ["Third", "First", "Second"]  # the model's position is the default rank
    review.set_rank(rv, ids["Second"], -5)
    assert [m["title"] for m in review.apply(rep, rv)["moments"]] == ["Second", "Third", "First"]
    review.set_rank(rv, ids["Third"], None)  # clearing returns the item to its model position
    assert [m["title"] for m in review.apply(rep, rv)["moments"]] == ["Second", "First", "Third"]


def test_equal_ranks_fall_back_to_model_order_and_unapproved_items_never_appear():
    rep = _three_moments()
    rv = review.approve_all(rep)
    ids = {v["title"]: i for i, v in rv["items"].items()}
    for t in ("First", "Second", "Third"):
        review.set_rank(rv, ids[t], 7)
    assert [m["title"] for m in review.apply(rep, rv)["moments"]] == ["First", "Second", "Third"]
    review.set_status(rv, [ids["Second"]], "rejected")
    review.set_rank(rv, ids["Second"], -100)  # a rejected item with the best rank still never shows
    assert [m["title"] for m in review.apply(rep, rv)["moments"]] == ["First", "Third"]


def test_rank_validation_and_file_round_trip(tmp_path):
    rv = review.new_review(_three_moments())
    i = next(iter(rv["items"]))
    assert review.set_rank(rv, "nope", 1) is False
    for bad in ("1", 1.5, True):
        with pytest.raises(review.ReviewError):
            review.set_rank(rv, i, bad)
    review.set_rank(rv, i, 3)
    review.save_review(tmp_path / "r.json", rv)
    assert review.load_review(tmp_path / "r.json")["items"][i]["rank"] == 3
    data = json.loads((tmp_path / "r.json").read_text())
    data["items"][i]["rank"] = "high"
    (tmp_path / "bad.json").write_text(json.dumps(data))
    with pytest.raises(review.ReviewError):
        review.load_review(tmp_path / "bad.json")


def test_rank_flag_in_the_review_cli(tmp_path):
    run = tmp_path / "20260101T000000-A.json"
    run.write_text(json.dumps({"config": "A", "messages": 1}))
    (tmp_path / "20260101T000000-A.report.json").write_text(json.dumps(_three_moments()))
    rf = tmp_path / "rv.json"
    assert _run(["review", str(run), "--file", str(rf)], tmp_path).returncode == 0
    ids = {v["title"]: i for i, v in json.loads(rf.read_text())["items"].items()}
    r = _run(["review", str(run), "--file", str(rf), "--approve", *ids.values(), "--rank", f"{ids['Third']}=0"], tmp_path)
    assert r.returncode == 0 and "rank 0" in r.stdout
    assert json.loads(rf.read_text())["items"][ids["Third"]]["rank"] == 0
    assert _run(["review", str(run), "--file", str(rf), "--rank", "bogus=1"], tmp_path).returncode == 2
    assert _run(["review", str(run), "--file", str(rf), "--rank", f"{ids['First']}=x"], tmp_path).returncode == 2


def test_apply_ignores_a_boolean_rank_even_in_a_hand_built_review():
    rep = _three_moments()
    rv = review.approve_all(rep)
    ids = {v["title"]: i for i, v in rv["items"].items()}
    review.set_rank(rv, ids["Second"], 2)  # ties with Third's default rank (its position, 2): model order puts Second first
    rv["items"][ids["Third"]]["rank"] = True  # True == 1 in Python; treated as rank 1 it would jump ahead of Second
    assert [m["title"] for m in review.apply(rep, rv)["moments"]] == ["First", "Second", "Third"]
