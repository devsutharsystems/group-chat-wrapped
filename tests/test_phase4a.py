"""Phase 4a: evaluate_runs, the markdown/JSON results (counts and ids only), the blind rating pack, run picking, and the new analyze guards.
Everything is built by hand from small fixtures; no API, no real client."""
from __future__ import annotations

import csv
import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import scan_repo
from gcw import analyze, cost, evaluate, privacy, verify
from gcw.parser import parse_chat
from test_analyze import FakeClient, GOOD, SMALL, SMALL_AL
from test_privacy import ROOT, FROZEN, al
from test_stats import frame

SENT = "SENTINEL"  # appears in chat text, titles, summaries and quotes below; it must never reach a results file

# (month-day, hour, minute, sender, text); chronological. Planted occurrences are marked in TRUTH below.
ROWS = [
    ("01-01", 9, 0, "Sam", f"{SENT} opening line of the chat"),
    ("01-10", 9, 0, "Alex", f"{SENT} the lighthouse shines again today"),  # jL 1
    ("02-01", 9, 0, "Sam", f"{SENT} the stapler has opinions again"),  # j1 a
    ("02-05", 9, 0, "Sam", f"{SENT} the stapler has opinions again"),  # j1 b
    ("02-07", 9, 0, "Maya", f"{SENT} I got the job! Starting next month."),  # m1
    ("02-07", 9, 30, "Alex", f"{SENT} congratulations everyone is so happy"),  # another message on m1's date
    ("02-09", 9, 0, "Sam", f"{SENT} the stapler has opinions again"),  # j1 c
    ("04-01", 9, 0, "Alex", f"{SENT} the lighthouse shines again today"),  # jL 2
    ("06-01", 9, 0, "Maya", f"{SENT} cheese protocol is in effect today"),  # j2 a
    ("06-05", 9, 0, "Maya", f"{SENT} cheese protocol is in effect today"),  # j2 b
    ("06-09", 9, 0, "Alex", f"{SENT} cheese protocol is in effect today"),  # j2 c
    ("07-20", 9, 0, "Sam", f"{SENT} the lighthouse shines again today"),  # jL 3
    ("09-01", 9, 0, "Maya", f"{SENT} <script>alert(1)</script> hostile chat text"),
    ("10-01", 9, 0, "Sam", f"{SENT} tuesday pizza rule applies again"),  # j3 a
    ("10-05", 9, 0, "Sam", f"{SENT} tuesday pizza rule applies again"),  # j3 b
    ("10-09", 9, 0, "Alex", f"{SENT} tuesday pizza rule applies again"),  # j3 c
    ("11-15", 9, 0, "Alex", f"{SENT} the lighthouse shines again today"),  # jL 4
    ("12-31", 9, 0, "Maya", f"{SENT} closing line of the chat"),
]


def mk_df() -> pd.DataFrame:
    return frame([(i + 1, f"{d} {h:02d}:{m:02d}", s, t, "") for i, (d, h, m, s, t) in enumerate(ROWS)])


def pid(i: int) -> str:  # payload id of ROWS[i]
    return f"m{i + 1:06d}"


def tr(kind, tid, i, extra=None):
    d, h, m, s, t = ROWS[i]
    return {"kind": kind, "id": tid, "timestamp": f"2026-{d}T{h:02d}:{m:02d}:00", "sender": s, "text": t, **(extra or {})}


TRUTH = [tr("long_joke", "jL", 1), tr("long_joke", "jL", 7), tr("long_joke", "jL", 11), tr("long_joke", "jL", 16),
         tr("joke", "j1", 2), tr("joke", "j1", 3), tr("joke", "j1", 6), tr("joke", "j2", 8), tr("joke", "j2", 9), tr("joke", "j2", 10),
         tr("joke", "j3", 13), tr("joke", "j3", 14), tr("joke", "j3", 15), tr("moment", "m1", 4, {"date": "2026-02-07"}), tr("pii", "p1", 0)]
ALIASES = al("Sam", "Alex", "Maya")


def ev(i, quote=None):
    return {"message_id": pid(i), "quote": quote or ROWS[i][4]}


def item(title, summary, *idx):
    return {"title": title, "summary": summary, "evidence": [ev(i) for i in idx]}


def report(jokes=(), moments=(), awards=()):
    return {"running_jokes": list(jokes), "moments": list(moments), "awards": list(awards)}


J1, J2, J3 = (2, 3, 6), (8, 9, 10), (13, 14, 15)
RUNS_RAW = [
    # run 1: j1 and j2 found; m1 found; one award (Member 1 = Sam, evidence by Sam); a short quote is dropped
    report([item(f"{SENT} stapler", f"{SENT} sum", *J1), item("cheese", "sum two", *J2)], [item("job news", "got a job", 4)],
           [{"award": "Best stapler", "member": "Member 1", "summary": "always says it", "evidence": [ev(2)]}]),
    # run 2: j1 found with extra non-planted evidence (3 of 5 planted: strict), j3 found, a moment on m1's date but another message, an unplanted joke
    report([item("stapler", "s", 2, 3, 6, 5, 17), item("pizza", "s", *J3), item("odd joke", "s", 17, 5, 0)], [item("party", "s", 5)], []),
    # run 3: j1 only with one planted out of three (lenient yes, strict no), nothing else
    report([item("weak stapler", "s", 2, 17, 0)], [], []),
]
LOGS = [{"phase": "4a", "config": "A", "prompt_version": "pv", "stop_reason": "end_turn", "latency_s": 10.0 + k, "cost_usd": 0.14 + k / 100, "messages": 18,
         "usage": {"input_tokens": 1000, "output_tokens": 200 + 100 * k, "output_tokens_details": {"thinking_tokens": 0}}} for k in range(3)]
RUNS = [(f"2026110{k + 1}T000000-A", LOGS[k], RUNS_RAW[k]) for k in range(3)]


@pytest.fixture(scope="module")
def result():
    return evaluate.evaluate_runs(mk_df(), ALIASES, RUNS, TRUTH)


# ---------------------------------------------------------------- evaluate_runs
def test_planted_groups_thirds_by_span_midpoint_and_long_range_apart(result):
    p = result["planted"]
    assert {t: p[t]["group"] for t in p} == {"jL": "long-range", "j1": "first", "j2": "middle", "j3": "last", "m1": "first"}
    assert p["j1"]["span"] == ["2026-02-01", "2026-02-09"] and p["jL"]["span"] == ["2026-01-10", "2026-11-15"]
    assert {t: p[t]["split"] for t in p} == {"jL": "dev", "j1": "dev", "j2": "held-out", "j3": "held-out", "m1": "dev"}  # dev slice ends 2026-02-08
    assert {t: p[t]["type"] for t in p} == {"jL": "running_jokes", "j1": "running_jokes", "j2": "running_jokes", "j3": "running_jokes", "m1": "moments"}


def test_found_in_n_of_3_runs_strict_lenient_and_by_date(result):
    p = result["planted"]
    # j1: run 1 (3 of 3 planted) strict; run 2 (3 planted of 5 verified evidence) strict, 3 >= 2 and 3 of 5 >= half; run 3 (1 of 3): lenient only
    assert (p["j1"]["found_strict_runs"], p["j1"]["found_lenient_runs"]) == (2, 3)
    assert (p["j2"]["found_strict_runs"], p["j2"]["found_lenient_runs"]) == (1, 1)
    assert (p["j3"]["found_strict_runs"], p["j3"]["found_lenient_runs"]) == (1, 1)
    assert (p["jL"]["found_strict_runs"], p["jL"]["found_lenient_runs"]) == (0, 0)
    # m1: found directly in run 1 (message 4); run 2's moment cites another message on the same date: by date only
    assert (p["m1"]["found_strict_runs"], p["m1"]["found_lenient_runs"], p["m1"]["found_by_date_runs"]) == (1, 1, 2)
    assert p["j1"]["found_by_date_runs"] is None and all(v["in_scope"] for v in p.values())


def test_recall_groupings(result):
    third, split, typ = result["recall_by_third"], result["recall_by_split"], result["recall_by_type"]
    assert third["first"]["items"] == ["j1", "m1"] and third["first"]["strict_found_item_runs"] == 3 and third["first"]["possible_item_runs"] == 6
    assert third["first"]["strict_recall"] == 0.5 and third["first"]["lenient_recall"] == pytest.approx(4 / 6)
    assert third["middle"]["items"] == ["j2"] and third["middle"]["strict_recall"] == pytest.approx(1 / 3)
    assert third["last"]["items"] == ["j3"] and third["long-range"]["items"] == ["jL"] and third["long-range"]["strict_recall"] == 0.0
    assert split["dev"]["items"] == ["j1", "jL", "m1"] and split["dev"]["strict_found_item_runs"] == 3 and split["dev"]["possible_item_runs"] == 9
    assert split["held-out"]["items"] == ["j2", "j3"] and split["held-out"]["strict_found_item_runs"] == 2 and split["held-out"]["possible_item_runs"] == 6
    assert typ["running_jokes"]["possible_item_runs"] == 12 and typ["moments"]["strict_found_item_runs"] == 1
    fb = result["found_by_date_moments"]
    assert fb == {"items": ["m1"], "found_item_runs": 2, "possible_item_runs": 3, "recall": pytest.approx(2 / 3)}


def test_per_run_numbers_and_summary_ranges(result):
    r = result["runs"]
    assert [x["items_kept"]["running_jokes"] for x in r] == [2, 3, 1] and [x["items_kept"]["moments"] for x in r] == [1, 1, 0] and [x["items_kept"]["awards"] for x in r] == [1, 0, 0]
    assert [x["unplanted_items"]["running_jokes"] for x in r] == [0, 1, 0]  # run 2's third joke cites non-planted messages only
    assert [x["output_tokens"] for x in r] == [200, 300, 400] and [x["thinking_tokens"] for x in r] == [0, 0, 0]
    s = result["summary"]
    assert s["output_tokens"] == {"mean": 300, "min": 200, "max": 400, "n": 3} and s["cost_usd"]["max"] == pytest.approx(0.16) and s["latency_s"]["min"] == 10.0
    assert s["items_kept"]["running_jokes"] == {"mean": 2, "min": 1, "max": 3, "n": 3}
    for x in r:
        assert 0 <= x["grounding_rate"] <= 1 and x["rule_compliant_rate"] <= x["grounding_rate"] + 1e-9


def test_length_distributions_are_numbers_only(result):
    lj = result["lengths"]["running_jokes"]["title"]
    titles = [it["title"] for rep in RUNS_RAW for it in rep["running_jokes"]]
    kept = [t for t in titles if t != "odd joke"]  # run 2's "odd joke" has 3 evidence on one... check by counting below
    assert lj["n"] <= len(titles) and lj["min"] is not None and lj["min"] <= lj["median"] <= lj["max"]
    assert lj["share_le_32"] == 1.0  # every fixture title is short
    lm = result["lengths"]["moments"]["summary"]
    assert lm["n"] == 2 and lm["share_le_110"] == 1.0


def test_results_files_hold_counts_and_ids_only_no_chat_text(result, tmp_path):
    j, m = evaluate.write_results(result, tmp_path / "res" / "eval")
    blob = j.read_text() + m.read_text()
    for forbidden in (SENT, "stapler", "lighthouse", "cheese", "pizza", "script", "job news", "Best stapler", "hostile", "Sam", "Alex", "Maya"):
        assert forbidden not in blob, forbidden
    data = json.loads(j.read_text())
    assert data["n_runs"] == 3 and data["runs"][0]["name"].endswith("-A") and set(data["planted"]) == {"jL", "j1", "j2", "j3", "m1"}
    assert j.read_text() == json.dumps(evaluate.rounded(result), indent=1, sort_keys=True, ensure_ascii=False) + "\n"  # deterministic
    assert not re.search(r"\d\.\d{5,}", j.read_text()) and evaluate.rounded({"a": [1 / 3, {"b": 2 / 3}]}) == {"a": [0.3333, {"b": 0.6667}]}


def test_markdown_has_ranges_and_n_and_no_winner_language_and_passes_the_repo_scanner(result, tmp_path):
    md = evaluate.render_markdown(result)
    assert "n = 3" in md and "mean " in md and "min " in md and "max " in md and "strict" in md and "lenient" in md and "found by date" in md.lower()
    assert "held-out" in md and "long-range" in md and "| j3 |" in md
    low = md.lower()
    for word in ("winner", "best", "better", "worse", "outperform", "superior", "recommend"):
        assert word not in low, word
    f = tmp_path / "eval.md"
    f.write_text(md)
    assert scan_repo.scan_file(f, tmp_path, set()) == []  # no digit run that the scanner would take for a phone number


def test_pick_runs_filters_by_phase_config_slice_error_and_saved_response(tmp_path):
    def mk(name, log, response=True):
        (tmp_path / f"{name}.json").write_text(json.dumps(log))
        if response:
            (tmp_path / f"{name}.response.txt").write_text("{}")

    base = {"phase": "4a", "config": "A", "slice": {"start": None, "end": None}}
    mk("a1", base)
    mk("a2", {**base, "slice": None})
    mk("b_phase", {**base, "phase": "3b"})
    mk("c_config", {**base, "config": "B"})
    mk("d_slice", {**base, "slice": {"start": None, "end": "2026-02-08"}})
    mk("e_error", {**base, "error": "boom"})
    mk("f_nosaved", base, response=False)
    (tmp_path / "g.report.json").write_text("{}")
    assert [p.name for p in evaluate.pick_runs(tmp_path, "4a")] == ["a1.json", "a2.json"]
    assert [p.name for p in evaluate.pick_runs(tmp_path, "4a", "B")] == ["c_config.json"]


def test_allocate_caps_by_pool_and_redistributes_the_shortfall():
    assert evaluate.allocate({"running_jokes": 20, "moments": 20, "awards": 20}) == {"running_jokes": 14, "moments": 14, "awards": 12}
    assert evaluate.allocate({"running_jokes": 9, "moments": 18, "awards": 9}) == {"running_jokes": 9, "moments": 18, "awards": 9}  # pool of 36 < 40: take all
    assert evaluate.allocate({"running_jokes": 3, "moments": 30, "awards": 30}) == {"running_jokes": 3, "moments": 20, "awards": 17}  # a shortfall of 11 goes round-robin to moments and awards
    assert evaluate.allocate({"running_jokes": 0, "moments": 0, "awards": 0}) == {"running_jokes": 0, "moments": 0, "awards": 0}
    assert evaluate.allocate({"running_jokes": 50, "moments": 50, "awards": 50}, total=10) == {"running_jokes": 4, "moments": 3, "awards": 3}  # trimmed from 14, 14, 12 (largest first, ties to the later type)
    assert sum(evaluate.allocate({"running_jokes": 50, "moments": 50, "awards": 50}).values()) == 40


# ---------------------------------------------------------------- rating pack
@pytest.fixture(scope="module")
def pack():
    return evaluate.build_rating_pack(mk_df(), ALIASES, RUNS, TRUTH, seed=4242, total=40)


def test_the_sample_is_reproducible_and_depends_on_the_seed():
    a = evaluate.build_rating_pack(mk_df(), ALIASES, RUNS, TRUTH, seed=4242)
    b = evaluate.build_rating_pack(mk_df(), ALIASES, RUNS, TRUTH, seed=4242)
    assert a == b and evaluate.render_rating_view(a["items"], 4242) == evaluate.render_rating_view(b["items"], 4242)
    orders = {tuple(it["title"] for it in evaluate.build_rating_pack(mk_df(), ALIASES, RUNS, TRUTH, seed=s)["items"]) for s in range(1, 8)}
    assert len(orders) > 1  # a different seed gives a different order
    # a smaller total draws fewer items but each type at most its pool
    small = evaluate.build_rating_pack(mk_df(), ALIASES, RUNS, TRUTH, seed=1, total=3)
    assert len(small["items"]) == 3


def test_pack_uses_every_verified_item_when_the_pool_is_below_the_target(pack):
    pool = pack["key"]["pool"]
    assert pool == {"running_jokes": 6, "moments": 2, "awards": 1}  # kept items per type over the three runs
    assert pack["key"]["drawn"] == pool and len(pack["items"]) == 9
    assert [it["id"] for it in pack["items"]] == [f"r{k:02d}" for k in range(1, 10)]
    assert [r["id"] for r in pack["csv_rows"]] == [it["id"] for it in pack["items"]]


def test_the_private_key_records_run_and_planted_matches(pack):
    key = pack["key"]["items"]
    by_title = {it["title"]: it["id"] for it in pack["items"]}
    assert key[by_title["stapler"]]["type"] == "running_jokes" and key[by_title["stapler"]]["run"] in {RUNS[0][0], RUNS[1][0]}
    weak = key[by_title["weak stapler"]]
    assert weak["run"] == RUNS[2][0] and weak["planted_lenient"] == ["j1"] and weak["planted_strict"] == []
    assert key[by_title["pizza"]]["planted_strict"] == ["j3"] and key[by_title["job news"]]["planted_strict"] == ["m1"]
    assert key[by_title["Best stapler"]]["planted_strict"] == []  # awards are never planted


def test_the_view_never_shows_the_key_and_escapes_chat_text(pack, tmp_path):
    paths = evaluate.write_rating_pack(pack, tmp_path / "rating")
    view = paths["view"].read_text()
    for secret in [RUNS[0][0], RUNS[1][0], RUNS[2][0], "planted", "key.json", "phase", "jL", "j1", "j2", "j3", "m1"]:
        assert secret not in view, secret
    assert "default-src 'none'" in view and "http://" not in view and "https://" not in view and view.lower().count("<script") == 2 and "<img" not in view and "src=" not in view
    # hostile chat text and titles are escaped: put a script tag into a title and a quote of one run
    bad = [(n, lg, {**rep, "moments": [{"title": "<b onclick=x>t</b>", "summary": "a <script>s</script>", "evidence": [ev(12, verify.neutralise("<script>alert(1)</script> hostile chat"))]}]}) for n, lg, rep in RUNS[:1]]
    p2 = evaluate.build_rating_pack(mk_df(), ALIASES, bad, TRUTH, seed=1)
    html = evaluate.render_rating_view(p2["items"], 1)
    assert html.lower().count("<script") == 2 and "&lt;script&gt;alert(1)&lt;/script&gt; hostile chat" in html and "&lt;b onclick=x&gt;t&lt;/b&gt;" in html and "<b onclick" not in html


def test_context_is_two_messages_each_side_with_names_and_dates(pack):
    it = next(i for i in pack["items"] if i["title"] == "job news")
    e = it["evidence"][0]
    assert [x["pid"] for x in e["before"]] == [pid(2), pid(3)] and [x["pid"] for x in e["after"]] == [pid(5), pid(6)]
    assert e["cited"]["who"] == "Maya" and e["cited"]["when"] == "2026-02-07" + " 09:00" and e["quote"] == ROWS[4][4]
    first = next(i for i in pack["items"] if i["title"] == "weak stapler")["evidence"][0]
    assert first["before"] == [] or len(first["before"]) <= 2  # start of the chat has fewer than two messages before


def test_csv_header_and_blank_ratings(pack, tmp_path):
    paths = evaluate.write_rating_pack(pack, tmp_path / "r")
    rows = list(csv.reader(paths["csv"].open(encoding="utf-8")))
    assert rows[0] == ["id", "type", "rating", "note"] and all(r[2] == "" and r[3] == "" for r in rows[1:]) and len(rows) == 1 + len(pack["items"])
    assert json.loads(paths["key"].read_text())["seed"] == 4242


# ---------------------------------------------------------------- the commands, end to end on a tiny world
def _wa(tmp: Path) -> Path:
    lines = []
    for d, h, m, s, t in ROWS:
        mo, da = d.split("-")
        lines.append(f"{int(mo)}/{int(da)}/26, {(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'} - {s}: {t}")
    p = tmp / "chat.txt"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _env():
    return {**os.environ, "PYTHONPATH": str(ROOT / "src"), "GCW_TEST_NO_NETWORK": "1"}


@pytest.fixture
def world(tmp_path):
    chat = _wa(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    for k, (name, log, rep) in enumerate(RUNS):
        (runs / f"{name}.json").write_text(json.dumps({**log, "slice": {"start": None, "end": None}}))
        (runs / f"{name}.response.txt").write_text(json.dumps(rep))
    al_ = tmp_path / "aliases.json"
    al_.write_text(json.dumps({"members": [{"export_name": n} for n in ("Sam", "Alex", "Maya")]}))
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps({"items": TRUTH}))
    return type("W", (), {"tmp": tmp_path, "chat": chat, "runs": runs, "aliases": al_, "truth": truth})


def _cli(args, cwd):
    return subprocess.run([sys.executable, "-m", "gcw", *args], env=_env(), capture_output=True, text=True, cwd=cwd)


def test_evaluate_command_writes_json_and_markdown(world):
    out = world.tmp / "docs" / "eval"
    r = _cli(["evaluate", str(world.chat), "--aliases", str(world.aliases), "--truth", str(world.truth), "--phase", "4a", "--runs-dir", str(world.runs), "--out", str(out)], world.tmp)
    assert r.returncode == 0, r.stderr
    assert json.loads(out.with_suffix(".json").read_text())["n_runs"] == 3 and "n = 3" in out.with_suffix(".md").read_text()
    assert SENT not in out.with_suffix(".json").read_text() + out.with_suffix(".md").read_text()


def test_evaluate_command_errors(world):
    base = ["--aliases", str(world.aliases), "--runs-dir", str(world.runs)]
    assert _cli(["evaluate", str(world.chat), *base, "--phase", "zz", "--truth", str(world.truth)], world.tmp).returncode == 3  # no such runs
    assert _cli(["evaluate", str(world.chat), *base, "--phase", "4a"], world.tmp).returncode == 2  # evaluate needs --truth
    assert _cli(["evaluate", str(world.tmp / "nope.txt"), *base, "--phase", "4a", "--truth", str(world.truth)], world.tmp).returncode == 2
    other = world.tmp / "other.txt"
    other.write_text(world.chat.read_text().replace("opening line", "opening line\n1/2/26, 9:00 AM - Sam: one more message"))
    r = _cli(["evaluate", str(other), *base, "--phase", "4a", "--truth", str(world.truth)], world.tmp)
    assert r.returncode == 3 and "messages but this chat has" in r.stderr  # the runs were made on a different chat


def test_rating_pack_command_writes_three_files(world):
    out = world.tmp / "rating"
    r = _cli(["rating-pack", str(world.chat), "--aliases", str(world.aliases), "--truth", str(world.truth), "--phase", "4a", "--runs-dir", str(world.runs), "--out", str(out)], world.tmp)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in out.iterdir()) == ["key.json", "rating_view.html", "ratings.csv"] and "do not open it before rating" in r.stdout
    assert "key.json" not in (out / "rating_view.html").read_text()


# ---------------------------------------------------------------- analyze guards for the big run
def test_max_input_tokens_and_max_run_cost_are_run_parameters(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 20)

    def run(n, **kw):
        guard = cost.CostGuard(run_cap=1.0, proj_cap=3.0, ledger_path=str(tmp_path / "ledger.json"))
        return analyze.run_analysis(SMALL, SMALL_AL, config="A", client=FakeClient([GOOD], n_tokens=n), guard=guard, confirm=True, count_only=True, out_dir=tmp_path / "runs", budget=0.60, **kw)

    with pytest.raises(analyze.AnalysisError, match="over the 95000 stop"):
        run(300_000)  # the default stop is unchanged
    res = run(300_000, max_input_tokens=400_000)
    assert res["request_tokens"] == 300_000 and res["worst_case_cost_usd"] == pytest.approx(300_000 * 0.5e-6 + 16_000 * 2.5e-6)  # above 100K: the high tier
    with pytest.raises(analyze.AnalysisError, match="over the 400000 stop"):
        run(400_001, max_input_tokens=400_000)
    with pytest.raises(analyze.AnalysisError, match=r"worst-case estimate \$0\.1900 for one run is over the \$0\.18 stop"):
        run(300_000, max_input_tokens=400_000, max_run_cost=0.18)
    assert run(300_000, max_input_tokens=400_000, max_run_cost=0.25)["request_tokens"] == 300_000


def test_cli_prints_and_checks_the_prompt_version_and_the_frozen_dataset(tmp_path):
    base = [str(FROZEN), "--aliases", str(ROOT / "aliases.example.json"), "--slice-end", "2025-11-09"]
    r = _cli(["analyze", *base, "--expect-prompt-version", "a4498b04..febc56", "--require-frozen-dataset"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert f"prompt version: {analyze.PROMPT_VERSION}" in r.stdout and analyze.PROMPT_VERSION.startswith("a4498b04") and analyze.PROMPT_VERSION.endswith("febc56")
    r = _cli(["analyze", *base, "--expect-prompt-version", "a4498b04..000000"], tmp_path)
    assert r.returncode == 3 and "prompt v1 is frozen" in r.stderr
    r = _cli(["analyze", *base, "--expect-prompt-version", "ffffffff..febc56"], tmp_path)
    assert r.returncode == 3
    copy = tmp_path / "copy.txt"
    copy.write_bytes(FROZEN.read_bytes() + b"\n")
    r = _cli(["analyze", str(copy), "--aliases", str(ROOT / "aliases.example.json"), "--require-frozen-dataset"], tmp_path)
    assert r.returncode == 3 and "not the frozen synthetic chat" in r.stderr
