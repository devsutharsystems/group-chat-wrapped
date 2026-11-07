"""Phase 5b tooling: diagnosing a saved run (nearest match, ambiguity, planted attribution, hypothetical re-pointing), planted density, slice scoring,
the four-row comparison, and the run guards. Hand-built fixtures and fake clients only; no API."""
from __future__ import annotations

import copy
import json
import sys

import pytest

import scan_repo
from gcw import analyze, chunked, cli, evaluate
from test_chunked import Fake
from test_phase4a import ALIASES, ROWS, SENT, TRUTH, ev, item, mk_df, pid, report
from test_privacy import ROOT

STAPLER = ROWS[2][4]


def dropped_report():
    wrong = {"message_id": pid(8), "quote": STAPLER}  # cites a cheese line, the quote is on three stapler lines (ambiguous; nearest is row 6)
    return report(
        jokes=[{"title": "t", "summary": "s", "evidence": [ev(2), ev(3), wrong]}],
        moments=[{"title": "u", "summary": "s", "evidence": [{"message_id": pid(4), "quote": ROWS[5][4]}, {"message_id": pid(0), "quote": "this quote exists nowhere in the chat"}]}],
    )


def test_diagnose_dropped_nearest_ambiguity_and_planted_attribution():
    d = evaluate.diagnose_dropped(mk_df(), ALIASES, dropped_report(), TRUTH)
    a = {(x["item"], x["evidence_index"]): x for x in d["dropped_evidence"]}
    j = a[("running_jokes[0]", 2)]
    assert (j["status"], j["cited"], j["nearest"], j["distance"], j["n_matches"], j["ambiguous"], j["exact"]) == ("other_message", pid(8), pid(6), 2, 3, True, True)
    assert j["nearest_planted"] == "j1" and j["planted_among_matches"] == ["j1"]
    m0 = a[("moments[0]", 0)]  # unique match, not planted, one message away, the quote is part of the message
    assert (m0["nearest"], m0["distance"], m0["ambiguous"], m0["nearest_planted"]) == (pid(5), 1, False, None)
    m1 = a[("moments[0]", 1)]
    assert m1["nearest"] is None and m1["distance"] is None and m1["n_matches"] == 0 and m1["status"] == "not_found"
    b = {x["item"]: x for x in d["per_proposed_item"]}
    assert b["running_jokes[0]"]["quoting_planted_lines"] == {"j1": 3} and b["moments[0]"]["quoting_planted_lines"] == {}
    c = d["planted_quoted_by_any_proposed_item"]
    assert c["j1"] == {"kept": 2, "dropped": 1, "items": 1} and c["j2"] == {"kept": 0, "dropped": 0, "items": 0}


def test_hypothetical_repointing_is_measured_not_applied_and_respects_ambiguity():
    rep = dropped_report()
    before = copy.deepcopy(rep)
    d = evaluate.diagnose_dropped(mk_df(), ALIASES, rep, TRUTH)
    assert rep == before  # the report is never changed
    assert d["baseline_strict_found"] == []  # two verified quotes are not enough for a joke
    allr, clear = d["hypothetical_repoint_all"], d["hypothetical_repoint_unambiguous_only"]
    assert allr["re_pointed"] == 2 and allr["strict_found"] == ["j1"] and allr["items_kept"]["running_jokes"] == 1
    assert clear["re_pointed"] == 1 and clear["strict_found"] == []  # the ambiguous stapler quote is left alone; the unique moment quote is re-pointed
    assert allr["evidence_verified"] == clear["evidence_verified"] + 1 and allr["evidence_total"] == 5


def test_diagnosis_results_hold_ids_and_numbers_only(tmp_path):
    d = evaluate.diagnose_dropped(mk_df(), ALIASES, dropped_report(), TRUTH)
    dens = {"original chat": evaluate.planted_density(mk_df(), TRUTH), "large chat": evaluate.planted_density(mk_df(), TRUTH)}
    md = evaluate.render_dropped_markdown(d, dens, {"repeated_over_3": 2, "top_3grams": [["a b c", 5]]})
    blob = md + json.dumps(d)
    assert SENT not in blob and "stapler" not in blob and "nowhere" not in blob
    p = tmp_path / "x.md"
    p.write_text(md)
    assert scan_repo.scan_file(p, tmp_path, set()) == []


def test_planted_density_counts_payload_lines_that_are_planted():
    dens = evaluate.planted_density(mk_df(), TRUTH)
    assert dens["payload_messages"] == len(ROWS)
    assert 0 < dens["planted_messages"] <= len(TRUTH) and dens["fraction"] == dens["planted_messages"] / dens["payload_messages"]
    cut = evaluate.planted_density(mk_df(), TRUTH, slice_end="02-01".join(["2026-", ""]))
    assert cut["payload_messages"] == 3 and cut["planted_messages"] == 3  # 01-01 (p1), 01-10 (jL) and 02-01 (j1) are all planted lines


def test_a_slice_scores_only_items_whose_whole_span_lies_inside_it():
    runs = [("r1", {"messages": 5, "slice": {"start": None, "end": "2026-02-09"}}, report(jokes=[item("t", "s", 2, 3, 6)]))]
    res = evaluate.evaluate_runs(mk_df(), ALIASES, runs, TRUTH, slice_end="2026-02-09")
    assert res["slice_end"] == "2026-02-09" and res["partial_items_not_scored"] == ["jL"]
    inside = {t for t, v in res["planted"].items() if v["in_scope"]}
    assert inside == {"j1", "m1"} and res["planted"]["j1"]["found_strict_runs"] == 1 and res["planted"]["jL"]["found_strict_runs"] == 0
    md = evaluate.render_markdown(res)
    assert "out of scope" in md and "are not scored" in md and "(jL)" in md


def test_pick_runs_separates_slice_runs_from_whole_chat_runs(tmp_path):
    for name, end in (("a", None), ("b", "2026-03-07")):
        (tmp_path / f"{name}-A.json").write_text(json.dumps({"phase": "5b", "config": "A", "mode": "single", "slice": {"start": None, "end": end}, "saved_response": True}))
        (tmp_path / f"{name}-A.response.txt").write_text("{}")
    names = lambda **k: [f.name for f in evaluate.pick_runs(tmp_path, "5b", "A", "single", **k)]  # noqa: E731
    assert names() == ["a-A.json"] and names(slice_end="2026-03-07") == ["b-A.json"]


def _res(n, tokens, cost, ids, found, ev_v, ev_t, unplanted=None):
    return {"n_runs": n, "messages": 100, "recall_by_type": {"running_jokes": {"items": ids, "strict_found_item_runs": found, "possible_item_runs": len(ids) * n}, "moments": {"items": [], "strict_found_item_runs": 0, "possible_item_runs": 0}},
            "runs": [{"input_tokens": tokens, "cost_usd": cost, "latency_s": 5.0, "evidence_total": ev_t, "evidence_verified": ev_v, "unplanted_items": unplanted or {"awards": 1, "moments": 2, "running_jokes": 0}}] * n}


def compare(chunk_cost=0.1, ev_v=90, found=4):
    rows = [("dense", _res(3, 270_000, 0.14, ["j1", "j2"], 6, 40, 44), 0.013), ("slice", _res(1, 293_000, 0.15, ["j1", "j2", "m1"], 0, 3, 8), 0.0036),
            ("full", _res(1, 889_000, 0.448, ["j1", "j2"], 0, 13, 25), 0.0039), ("chunked", _res(1, 900_000, chunk_cost, ["j1", "j2", "j3", "j4"], found, ev_v, 100), 0.0039)]
    return evaluate.compare_large(rows, "abc1234")


def test_compare_large_states_each_prediction_from_the_numbers():
    md = compare()
    assert md.count("**held**") == 3 and "**did not hold**" not in md and "abc1234" in md and "n = 1" in md and "3.3 times" in md
    bad = compare(chunk_cost=0.2, ev_v=79, found=2)
    assert bad.count("**did not hold**") == 3
    assert "the rule applies" in md  # the slice control found 0 of 3
    assert "0.36%" in md and "1.30%" in md


def test_compare_large_uses_no_ranking_language(tmp_path):
    md = compare().lower()
    for w in evaluate.WINNER_WORDS:
        assert w not in md
    p = tmp_path / "c.md"
    p.write_text(md)
    assert scan_repo.scan_file(p, tmp_path, set()) == []


def test_max_chunks_refuses_before_any_map_call(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    from gcw import cost

    guard = cost.CostGuard(run_cap=5.0, proj_cap=30.0, ledger_path=str(tmp_path / "ledger.json"))
    fake = Fake(per_line=100)
    with pytest.raises(analyze.AnalysisError, match="more than --max-chunks 2"):
        chunked.run_chunked(mk_df(), ALIASES, client=fake, guard=guard, out_dir=tmp_path / "o", confirm=True, limit=450, budget=5.0, max_chunks=2)
    assert fake.create_calls == [] and fake.count_calls  # planning counted tokens (free); nothing was generated


def test_reduce_version_mismatch_aborts_before_anything_is_sent(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    chat = tmp_path / "c.txt"
    chat.write_text("1/1/26, 09:00 - Sam: hello there\n")
    rc = cli.main(["analyze", str(chat), "--mode", "chunked", "--count", "--expect-reduce-version", "0000..ffff"])
    assert rc == 3 and "reduce prompt is frozen" in capsys.readouterr().err


def test_cli_parses_the_new_flags():
    p = cli.build_parser()
    a = p.parse_args(["analyze", "c.txt", "--max-chunks", "12", "--expect-reduce-version", "6c01..8390a"])
    assert a.max_chunks == 12 and a.expect_reduce_version == "6c01..8390a"
    e = p.parse_args(["evaluate", "c.txt", "--aliases", "a.json", "--phase", "5b", "--slice-end", "2026-03-07"])
    assert e.slice_end == "2026-03-07"
    assert p.parse_args(["compare-large"]).slice_end == "2026-03-07"
