"""Phase 5a tooling: the large-dataset config and generator options, the large dataset check, --no-retry and verbatim API errors, evaluation labels for the
large dataset, the chunked-loss diagnostic and the free-checks file. Fake clients only; no API."""
from __future__ import annotations

import copy
import json
import re
import shutil
import sys
from collections import Counter
from datetime import date
from types import SimpleNamespace

import pytest

import gen_chat as g
import scan_repo
from gcw import analyze, chunked, cli, dataset, evaluate, llm
from test_analyze import FakeClient as AnalyzeFake
from test_chunked import Fake, groups_by_title, payload_lines, pid, run
from test_phase4a import ALIASES, RUNS, ROWS, TRUTH, mk_df
from test_privacy import FROZEN, ROOT

CFG = g.load_config()
LARGE = g.load_config(ROOT / "synthetic" / "config_large.json")


# ---------------------------------------------------------------- the large config and the generator options
def test_the_large_config_differs_from_the_original_only_in_burst_numbers():
    assert {k for k in CFG if CFG[k] != LARGE[k]} == {"burst_prob_weekday", "burst_prob_weekend", "burst_size"} and set(CFG) == set(LARGE)
    assert (LARGE["burst_prob_weekday"], LARGE["burst_prob_weekend"], LARGE["burst_size"]) == (0.65, 0.85, [50, 90])
    for k in ("members", "jokes", "long_joke", "moments", "injection", "sensitive", "pii", "banned_phrases", "silence_days", "removal", "start", "end", "seed"):
        assert CFG[k] == LARGE[k]


@pytest.fixture(scope="module")
def skeletons():
    return g.skeleton(CFG), g.skeleton(LARGE)


def test_the_large_skeleton_keeps_the_planted_structure_and_scales_the_message_count(skeletons):
    small, big = skeletons
    kinds = lambda sk: Counter(p.kind for p in sk.planted)  # noqa: E731
    assert kinds(small) == kinds(big) and len(big.planted) == len(small.planted) == 67
    n = lambda sk: sum(s.n for s in g.batch_specs(sk, CFG)) + len(sk.planted)  # noqa: E731
    assert 3.0 <= n(big) / n(small) <= 3.6 and n(big) == 17134
    third = lambda sk, kind, id_: sorted({g.third_of(p.t.date(), sk.start, sk.end) for p in sk.planted if p.kind == kind and p.meta.get("id") == id_})  # noqa: E731
    for jid, th in (("j1", 0), ("j2", 0), ("j3", 1), ("j4", 1), ("j5", 2), ("j6", 2)):
        assert third(big, "joke", jid) == [th] == third(small, "joke", jid)
    for mid, th in (("m1", 0), ("m2", 1), ("m3", 2)):
        assert third(big, "moment", mid) == [th]
    assert sum(1 for p in big.planted if p.kind == "injection") == 1 and sum(1 for p in big.planted if p.kind == "sensitive") == 4
    assert sum(1 for p in big.planted if p.kind == "pii") == 5 and {p.t.date() for p in big.planted if p.kind == "long_joke"} and len({p.t.date() for p in big.planted if p.kind == "long_joke"}) >= 9


def test_the_label_prefix_and_the_prefix_scoped_budget(monkeypatch):
    spec = g.batch_specs(g.skeleton(CFG, mini=True), CFG)[0]
    assert spec.label.startswith("gen:b")
    monkeypatch.setattr(g, "LABEL_PREFIX", "genL")
    assert spec.label.startswith("genL:b")
    entries = [{"label": "gen:b1p0", "cost_usd": 0.15}, {"label": "genL:b1p0", "cost_usd": 0.10}, {"label": "5a:A:slice", "cost_usd": 0.50}]
    assert g.run_cap(1.0, 0.60, "genL", entries, 0.75) == pytest.approx(0.50)  # only the genL entries count against its own budget
    assert g.run_cap(1.0, 0.60, "genL", [], 0.76) == pytest.approx(0.60)  # the ledger total of other phases is irrelevant
    assert g.run_cap(0.25, 0.60, "genL", [], 0.0) == 0.25 and g.run_cap(1.0, 0.60, "genL", [{"label": "genL:x", "cost_usd": 0.7}], 0.0) == 0.0
    assert g.run_cap(1.0, None, "gen", entries, 0.2) == pytest.approx(0.40) and g.run_cap(1.0, None, "gen", entries, 0.9) == 0.0  # the original rule is unchanged


# ---------------------------------------------------------------- the large dataset check
def test_large_dataset_fails_closed_until_frozen_and_checks_hashes_with_overrides(tmp_path):
    if not (dataset.LARGE_CHAT_SHA256 and dataset.LARGE_GROUND_TRUTH_SHA256):
        with pytest.raises(dataset.DatasetError, match="not set"):
            dataset.verify_large_dataset()
        assert dataset.which_frozen(FROZEN) == "original" and dataset.is_frozen_large_chat(FROZEN) is False
    d = tmp_path / "large"
    d.mkdir()
    (d / dataset.LARGE_CHAT_FILE).write_text("chat")
    (d / dataset.LARGE_GROUND_TRUTH_FILE).write_text("{}")
    ok = dataset.verify_large_dataset(d, chat_sha256=dataset.sha256_file(d / dataset.LARGE_CHAT_FILE), ground_truth_sha256=dataset.sha256_file(d / dataset.LARGE_GROUND_TRUTH_FILE))
    assert set(ok) == {dataset.LARGE_CHAT_FILE, dataset.LARGE_GROUND_TRUTH_FILE}
    (d / dataset.LARGE_CHAT_FILE).write_text("chat!")
    with pytest.raises(dataset.DatasetError, match="differs"):
        dataset.verify_large_dataset(d, chat_sha256=dataset.sha256_file(d / dataset.LARGE_GROUND_TRUTH_FILE), ground_truth_sha256=dataset.sha256_file(d / dataset.LARGE_GROUND_TRUTH_FILE))
    (d / dataset.LARGE_GROUND_TRUTH_FILE).unlink()
    with pytest.raises(dataset.DatasetError, match="missing"):
        dataset.verify_large_dataset(d, chat_sha256="a", ground_truth_sha256="b")


def test_the_original_dataset_is_untouched_and_still_verifies():
    assert dataset.verify_dataset() and dataset.which_frozen(FROZEN) == "original"
    assert dataset.CHAT_SHA256 == "b6d3add40ae93fe79a10f79d19a0a2b374dd0ffb5c3222feaf0425a12cae13b4" and dataset.GROUND_TRUTH_SHA256 == "b3f2f5afb24df2c271fd9b3ddc1dd57c41231655275e2fb18e4672f79aca5952"


def test_which_frozen_rejects_other_files(tmp_path):
    other = tmp_path / "c.txt"
    shutil.copy(FROZEN, other)
    other.write_bytes(other.read_bytes() + b"\n")
    assert dataset.which_frozen(other) is None and dataset.which_frozen(tmp_path / "missing.txt") is None


# ---------------------------------------------------------------- --no-retry and verbatim API errors
class Raising(AnalyzeFake):
    def __init__(self, where, text):
        super().__init__()
        self.where, self.text = where, text
        self.messages = SimpleNamespace(create=self._boom_create, count_tokens=self._boom_count)

    def _boom_create(self, **kw):
        self.create_calls.append(kw)
        raise RuntimeError("never reached") if False else Exception(self.text)

    def _boom_count(self, **kw):
        self.count_calls.append(kw)
        if self.where == "count":
            raise Exception(self.text)
        return SimpleNamespace(input_tokens=1000)


def cli_run(monkeypatch, capsys, client, *args, record=None):
    def fake_get(max_retries=None):
        if record is not None:
            record.append(max_retries)
        return client

    monkeypatch.setattr(llm, "get_client", fake_get)
    rc = cli.main(["analyze", str(FROZEN), "--aliases", str(ROOT / "aliases.example.json"), "--slice-end", "2025-11-09", *args])
    return rc, capsys.readouterr()


def test_no_retry_builds_the_client_without_sdk_retries(monkeypatch, capsys):
    seen: list = []
    rc, _ = cli_run(monkeypatch, capsys, AnalyzeFake(), "--count", "--no-retry", record=seen)
    assert rc == 0 and seen == [0]
    seen.clear()
    rc, _ = cli_run(monkeypatch, capsys, AnalyzeFake(), "--count", record=seen)
    assert rc == 0 and seen == [None]  # without the flag run_analysis asks for the default client: get_client() with no max_retries


@pytest.mark.parametrize("where", ["create", "count"])
def test_a_rate_limit_or_size_error_is_reported_once_verbatim_and_never_retried(monkeypatch, capsys, where):
    text = "Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': 'This request would exceed the rate limit for your organization'}}"
    fake = Raising(where, text)
    rc, out = cli_run(monkeypatch, capsys, fake, "--confirm", "--no-retry")
    assert rc == 3 and text in out.err and "API or request error (Exception)" in out.err
    assert len(fake.create_calls) == (1 if where == "create" else 0) and len(fake.count_calls) == 1  # exactly one attempt, no retry loop


def test_require_frozen_dataset_accepts_the_original_and_refuses_unknown_chats(monkeypatch, capsys, tmp_path):
    rc, out = cli_run(monkeypatch, capsys, AnalyzeFake(), "--require-frozen-dataset")
    assert rc == 0 and "offline only" in out.out
    other = tmp_path / "c.txt"
    shutil.copy(FROZEN, other)
    other.write_bytes(other.read_bytes() + b"\n")
    monkeypatch.setattr(llm, "get_client", lambda max_retries=None: AnalyzeFake())
    rc = cli.main(["analyze", str(other), "--aliases", str(ROOT / "aliases.example.json"), "--require-frozen-dataset"])
    assert rc == 3 and "not the frozen synthetic chat (original or large)" in capsys.readouterr().err


# ---------------------------------------------------------------- evaluation labels for the large dataset
def test_large_dataset_evaluation_uses_start_middle_end_and_no_dev_split():
    res = evaluate.evaluate_runs(mk_df(), ALIASES, RUNS, TRUTH, dataset="large")
    assert res["dataset"] == "large" and set(res["recall_by_third"]) == {"start", "middle", "end", "long-range"}
    assert {v["group"] for v in res["planted"].values()} <= {"start", "middle", "end", "long-range"} and {v["split"] for v in res["planted"].values()} == {"new-dataset"}
    assert set(res["recall_by_split"]) == {"new-dataset"} and res["recall_by_split"]["new-dataset"]["possible_item_runs"] == 5 * 3
    md = evaluate.render_markdown(res)
    assert "| start |" in md and "dev" not in md.split("## Planted items")[1].split("### By type")[0].replace("device", "")
    orig = evaluate.evaluate_runs(mk_df(), ALIASES, RUNS, TRUTH)
    assert orig["dataset"] == "original" and set(orig["recall_by_third"]) == {"first", "middle", "last", "long-range"} and set(orig["recall_by_split"]) == {"dev", "held-out"}


# ---------------------------------------------------------------- where chunked runs lose planted items
def moment_pairs_reply(kw):
    lines = payload_lines(kw)
    m1 = pid(4)
    others = [l for l in lines if l[0] != m1]
    moments = [{"title": f"moment {a[0]}", "summary": "s", "evidence": [{"message_id": a[0], "quote": a[4]}, {"message_id": b[0], "quote": b[4]}]} for a, b in zip(others[::2], others[1::2])][:5]
    for l in lines:
        if l[0] == m1:
            moments.append({"title": "the job news", "summary": "s", "evidence": [{"message_id": l[0], "quote": l[4]}]})
    return {"running_jokes": [], "moments": moments, "awards": []}


def test_diagnose_chunked_separates_pipeline_losses_from_never_proposed(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)
    from gcw import cost

    guard = cost.CostGuard(run_cap=5.0, proj_cap=30.0, ledger_path=str(tmp_path / "ledger.json"))
    out = tmp_path / "runs"
    res = chunked.run_chunked(mk_df(), ALIASES, client=Fake(per_line=100, map_reply=moment_pairs_reply, reduce_reply=lambda kw: {"groups": []}), guard=guard, out_dir=out, confirm=True,
                              limit=900, save_response=True, label="x", budget=5.0)
    assert len(res["chunks"]) >= 2 and len(res["final"]["moments"]) == 6 and res["log"]["cap_cut"] >= 1
    f = evaluate.pick_runs(out, "4b", "A", "chunked")[0]
    log, raw = evaluate.load_run(f)
    final = json.loads(f.with_suffix(".report.json").read_text())
    d = evaluate.diagnose_chunked(mk_df(), ALIASES, [(f.stem, log, final, raw)], TRUTH)
    assert d["replay_matches_saved_final"] == [True]
    by = {m["planted"]: m for m in d["misses"]}
    m1 = by["m1"]
    assert [m1["stages"][s]["present"] for s in ("raw_candidates", "after_merge", "after_rules", "after_caps")] == [True, True, True, False]
    assert m1["lost_at"] == "the caps" and m1["pipeline_induced"] and not m1["never_proposed"]
    for tid in ("j1", "j2", "j3", "jL"):  # no joke candidate exists at all
        assert by[tid]["never_proposed"] and by[tid]["lost_at"] is None and not by[tid]["pipeline_induced"]
    assert d["n_misses"] == 5 and d["pipeline_induced"] == 1 and d["never_proposed"] == 4
    md = evaluate.render_chunked_diagnostic(d)
    assert "the caps" in md and "never proposed" in md.lower() and "stapler" not in md and "job" not in md.lower().replace("pipeline", "")
    p = tmp_path / "d.md"
    p.write_text(md)
    assert scan_repo.scan_file(p, tmp_path, set()) == []


def test_the_free_checks_file_states_the_jL_limit_only_when_it_is_true():
    sys.path.insert(0, str(ROOT / "scripts"))
    import free_checks_5a as fc

    def res(n_alone):
        per = [{"occurrences": 4, "distinct_dates": 3, "meets_joke_rule_alone": i < n_alone} for i in range(4)]
        return {"test_counts": {"files": {"tests/a.py": {"before": 1, "now": 2, "delta": 1}}, "before_total": 1, "now_total": 2},
                "eval_full_A_mode_change": {"fields_that_differ": ["mode"], "identical_except_mode": True},
                "jokes_per_chunk": {"chunk_bounds": [["a", "b"]] * 4, "jokes": {"jL": {"total_occurrences": 12, "total_dates": 9, "per_chunk": per, "chunks_meeting_rule_alone": n_alone}}, "jL_chunks_meeting_rule_alone": n_alone},
                "chunked_losses": {"schema": 1, "replay_matches_saved_final": [True], "misses": [], "n_misses": 0, "pipeline_induced": 0, "never_proposed": 0}}

    assert "does not test long-range dependence; a sparse joke is untested" in fc.render(res(3))
    none = fc.render(res(0))
    assert "does not test long-range" not in none and "needs evidence from several chunks" in none
