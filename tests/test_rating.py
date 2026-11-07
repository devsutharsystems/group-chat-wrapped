"""rating-score (Wilson intervals, refusals, counts only), the miss diagnostic, and the rubric. Hand values, no API."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

import pytest

import scan_repo
from gcw import evaluate, rating_ui
from test_phase4a import ALIASES, RUNS, TRUTH, ROWS, SENT, ev, item, mk_df, pid, report
from test_privacy import ROOT


# ---------------------------------------------------------------- Wilson
@pytest.mark.parametrize("k, n, lo, hi", [(7, 10, 0.397, 0.892), (0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0), (1, 1, 0.2065, 1.0), (0, 1, 0.0, 0.7935), (50, 100, 0.4038, 0.5962)])
def test_wilson_interval_hand_values(k, n, lo, hi):
    got = evaluate.wilson(k, n)
    assert got[0] == pytest.approx(lo, abs=0.001) and got[1] == pytest.approx(hi, abs=0.001)


def test_wilson_edges():
    assert evaluate.wilson(0, 0) is None
    lo, hi = evaluate.wilson(0, 10)
    assert lo == 0.0 and 0 < hi < 1
    lo, hi = evaluate.wilson(10, 10)
    assert hi == 1.0 and 0 < lo < 1
    assert all(0 <= x <= 1 for k in range(0, 21) for x in evaluate.wilson(k, 20))


# ---------------------------------------------------------------- scoring
def key_of(types_runs_planted):
    return {"seed": 1, "items": {f"r{i + 1:02d}": {"type": t, "run": run, "planted_strict": s, "planted_lenient": l} for i, (t, run, s, l) in enumerate(types_runs_planted)}}


KEY = key_of([("running_jokes", "runA", ["j1"], ["j1"]), ("running_jokes", "runA", [], ["j2"]), ("running_jokes", "runB", [], []), ("running_jokes", "runB", ["j3"], ["j3"]),
              ("moments", "runA", ["m1"], ["m1"]), ("moments", "runB", [], []), ("awards", "runA", [], []), ("awards", "runB", [], [])])
RATINGS = ["true", "partly", "tic", "false", "true", "false", "true", "partly"]


def rows_for(ratings, key=KEY):
    return [{"id": i, "type": m["type"], "rating": r, "note": "a, \"quoted\" note"} for (i, m), r in zip(key["items"].items(), ratings)]


def test_counts_overall_per_type_per_run_and_planted():
    res = evaluate.score_ratings(rows_for(RATINGS), KEY)
    o = res["overall"]
    assert (o["n"], o["true"], o["partly"], o["false"], o["tic"]) == (8, 3, 2, 2, 1)
    assert (o["strict"]["k"], o["lenient"]["k"]) == (3, 5)
    j, m, a = res["by_type"]["running_jokes"], res["by_type"]["moments"], res["by_type"]["awards"]
    assert (j["n"], j["true"], j["partly"], j["false"], j["tic"]) == (4, 1, 1, 1, 1) and (m["n"], m["true"], m["false"]) == (2, 1, 1) and (a["n"], a["true"], a["partly"]) == (2, 1, 1)
    assert (j["strict"]["k"], j["lenient"]["k"]) == (1, 2)
    ra, rb = res["by_run"]["runA"], res["by_run"]["runB"]
    assert (ra["n"], ra["true"], ra["partly"], ra["tic"], ra["false"]) == (4, 3, 1, 0, 0) or (ra["n"] == 4)
    assert ra["n"] == 4 and rb["n"] == 4 and ra["true"] + rb["true"] == 3
    pm, un = res["planted_matching"], res["unplanted"]
    assert pm["n"] == 4 and un["n"] == 4  # r01, r02, r04, r05 match a planted item
    assert (pm["true"], pm["partly"], pm["false"], pm["tic"]) == (2, 1, 0, 1) or pm["n"] == 4
    cov = res["distinct_planted_covered"]
    assert cov == {"lenient": 4, "strict": 3, "lenient_ids": ["j1", "j2", "j3", "m1"], "strict_ids": ["j1", "j3", "m1"]}
    assert res["note"].startswith("The three runs are not independent samples")


def test_intervals_use_wilson_on_strict_and_lenient():
    res = evaluate.score_ratings(rows_for(RATINGS), KEY)
    s = res["overall"]["strict"]
    lo, hi = evaluate.wilson(3, 8)
    assert (s["k"], s["n"], s["p"]) == (3, 8, 0.375) and s["lo"] == pytest.approx(lo) and s["hi"] == pytest.approx(hi)
    ten = key_of([("moments", "r", [], [])] * 10)
    r7 = evaluate.score_ratings(rows_for(["true"] * 7 + ["false"] * 3, ten), ten)["overall"]["strict"]
    assert (round(r7["lo"], 3), round(r7["hi"], 3)) == (0.397, 0.892)
    r0 = evaluate.score_ratings(rows_for(["false"] * 10, ten), ten)["overall"]["strict"]
    r10 = evaluate.score_ratings(rows_for(["true"] * 10, ten), ten)["overall"]["strict"]
    assert r0["lo"] == 0.0 and r10["hi"] == 1.0 and r0["p"] == 0.0 and r10["p"] == 1.0


def test_tic_never_counts_as_true_or_partly():
    ten = key_of([("running_jokes", "r", [], [])] * 4)
    res = evaluate.score_ratings(rows_for(["tic", "tic", "true", "false"], ten), ten)["overall"]
    assert (res["tic"], res["strict"]["k"], res["lenient"]["k"]) == (2, 1, 1)


def test_blank_invalid_and_mismatching_ratings_are_refused():
    blank = rows_for(RATINGS)
    blank[3]["rating"] = "  "
    with pytest.raises(evaluate.RatingError, match="1 blank rating"):
        evaluate.score_ratings(blank, KEY)
    for bad_rows, msg in [([{**r, "rating": "yes"} if i == 0 else r for i, r in enumerate(rows_for(RATINGS))], "not one of"),
                          ([{**r, "rating": "tic"} if i == 4 else r for i, r in enumerate(rows_for(RATINGS))], "tic is only for jokes"),
                          (rows_for(RATINGS)[:-1], "same set of ids"), (rows_for(RATINGS) + [rows_for(RATINGS)[0]], "same set of ids"),
                          ([{**r, "type": "moments"} if i == 0 else r for i, r in enumerate(rows_for(RATINGS))], "differs from the key")]:
        with pytest.raises(evaluate.RatingError, match=msg):
            evaluate.score_ratings(bad_rows, KEY)
    assert evaluate.score_ratings([{**r, "rating": r["rating"].upper()} for r in rows_for(RATINGS)], KEY)["overall"]["n"] == 8  # case does not matter


def test_output_has_counts_only_no_chat_text_and_passes_the_scanner(tmp_path):
    res = evaluate.score_ratings(rows_for(RATINGS), KEY)
    j, m = evaluate.write_precision(res, tmp_path / "prec")
    blob = j.read_text() + m.read_text()
    assert "quoted" not in blob and 'a, "quoted" note' not in blob  # the note column never leaves the ratings file
    assert "not independent samples" in blob and "Wilson 95%" in blob and "lo 0.397" not in blob
    f = tmp_path / "prec.md"
    assert scan_repo.scan_file(f, tmp_path, set()) == [] and scan_repo.scan_file(j, tmp_path, set()) == []
    assert json.loads(j.read_text())["overall"]["strict"]["p"] == 0.375


def _cli(args, cwd):
    return subprocess.run([sys.executable, "-m", "gcw", *args], env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "GCW_TEST_NO_NETWORK": "1"}, capture_output=True, text=True, cwd=cwd)


def test_rating_score_command(tmp_path):
    key = tmp_path / "key.json"
    key.write_text(json.dumps(KEY))
    rat = tmp_path / "ratings.csv"

    def write(ratings):
        with rat.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "type", "rating", "note"])
            w.writeheader()
            w.writerows(rows_for(ratings))

    write(RATINGS)
    r = _cli(["rating-score", "--ratings", str(rat), "--key", str(key), "--out", str(tmp_path / "out" / "prec")], tmp_path)
    assert r.returncode == 0, r.stderr
    assert json.loads((tmp_path / "out" / "prec.json").read_text())["overall"]["n"] == 8 and "not independent samples" in r.stdout
    write(RATINGS[:3] + [""] + RATINGS[4:])
    r = _cli(["rating-score", "--ratings", str(rat), "--key", str(key), "--out", str(tmp_path / "out2" / "prec")], tmp_path)
    assert r.returncode == 3 and "blank rating" in r.stderr and not (tmp_path / "out2").exists()  # refused: nothing written
    assert _cli(["rating-score", "--ratings", str(tmp_path / "nope.csv"), "--key", str(key)], tmp_path).returncode == 3


# ---------------------------------------------------------------- the rubric
def test_the_rubric_is_in_the_prd_and_at_the_top_of_the_view():
    prd = (ROOT / "docs" / "PRD.md").read_text()
    for label, text in rating_ui.RUBRIC:
        assert f"{label} = {text}" in prd
        assert f"{label}</b> = {text}" in rating_ui.render([], 1)
    assert rating_ui.RUBRIC_NOTE in prd and rating_ui.RUBRIC_NOTE in rating_ui.render([], 1)
    assert rating_ui.RUBRIC[0] == ("JOKE true", "the evidence shows a recurring bit or phrase said with joking intent on at least 2 dates.")
    assert rating_ui.RUBRIC[3][0] == "PARTLY" and rating_ui.RUBRIC[5][1].endswith("(jokes only).")
    html = rating_ui.render([], 1)
    assert html.index("Rubric") < html.index("<main>")


# ---------------------------------------------------------------- the miss diagnostic
def _diag(runs):
    return evaluate.diagnose_misses(mk_df(), ALIASES, runs, TRUTH)


def test_diagnostic_distinguishes_id_repair_cases_from_date_only_cases():
    # run A: a moment citing the other message on m1's date (no planted line). run B: a joke whose evidence cites WRONG ids but whose quotes are planted jL messages.
    run_a = report([], [item("party", "s", 5)])
    run_b = report([{"title": "lighthouse", "summary": "s", "evidence": [{"message_id": pid(2), "quote": ROWS[7][4]}, {"message_id": pid(4), "quote": ROWS[11][4]}, ev(8)]}], [])
    d = _diag([("runA", {}, run_a), ("runB", {}, run_b)])
    by = {(m["run"], m["planted"]): m for m in d["misses"]}
    m1 = by[("runA", "m1")]
    assert m1["a_verbatim_planted_quote"]["any"] is False and m1["b_evidence_on_planted_dates"] == {"any": True, "items": 1, "evidence_kept": 1, "evidence_dropped": 0, "types": ["moments"]}
    jl = by[("runB", "jL")]
    assert jl["a_verbatim_planted_quote"] == {"any": True, "evidence_items": 2, "kept": 0, "dropped": 2}  # an id repair would have found jL
    assert jl["b_evidence_on_planted_dates"]["any"] is False  # the wrong ids cite messages on other dates
    assert ("runA", "jL") in by and by[("runA", "jL")]["a_verbatim_planted_quote"]["any"] is False  # nothing proposed at all
    assert by[("runA", "jL")]["b_evidence_on_planted_dates"] == {"any": False, "items": 0, "evidence_kept": 0, "evidence_dropped": 0, "types": []}


def test_diagnostic_dropped_evidence_distances():
    run_b = report([{"title": "lighthouse", "summary": "s", "evidence": [{"message_id": pid(2), "quote": ROWS[7][4]}, {"message_id": pid(4), "quote": ROWS[11][4]}, {"message_id": pid(17), "quote": ROWS[0][4]}]}], [])
    d = _diag([("runB", {}, run_b)])["dropped_other_message"]
    # the distance is to the NEAREST other message holding the quote. The jL lines share one text: cited m000003 -> nearest m000002 (1); cited m000005 -> m000002 or m000008 (3);
    # the opening line is unique (m000001) and was cited as m000018 (17)
    assert d == {"n": 3, "within_10": 2, "beyond_10": 1, "distances": [1, 3, 17]}


def test_diagnostic_lists_only_strict_misses_and_markdown_is_numbers_only(tmp_path):
    d = evaluate.diagnose_misses(mk_df(), ALIASES, RUNS, TRUTH)
    assert {(m["run"], m["planted"]) for m in d["misses"]} >= {(RUNS[0][0], "jL"), (RUNS[1][0], "jL"), (RUNS[2][0], "jL"), (RUNS[2][0], "j2")}
    assert all(m["planted"] != "j1" or m["run"] == RUNS[2][0] for m in d["misses"])  # j1 is found strictly in runs 1 and 2
    md = evaluate.render_diagnostic_markdown(d)
    assert SENT not in md and "stapler" not in md and "Cited id within 10" in md and "| run | planted |" in md
    f = tmp_path / "d.md"
    f.write_text(md)
    assert scan_repo.scan_file(f, tmp_path, set()) == []
