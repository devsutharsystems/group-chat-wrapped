"""FREE checks of Phase 5a, numbers only (docs/results/free_checks_5a.md and .json). No API call, no chat text.
  (a) per-file test counts and deltas between two commits (collect-only, run in a scratch copy: the working tree is never touched)
  (b) eval_full_A.json across the `mode` field change: identical except `mode`
  (c) planted jokes: occurrences and distinct dates per chunk of the exact chunked plan, and which chunks satisfy the joke rule alone
  (d) where planted items were lost in the chunked runs
  .venv/bin/python scripts/free_checks_5a.py --old 959b194 --before-mode 43c1224 --after-mode 40bd887 --chat ... --aliases ... --truth ... --phase 4b"""
from __future__ import annotations

import argparse
import collections
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gcw import evaluate, privacy  # noqa: E402
from gcw.parser import parse_chat  # noqa: E402


def collect_counts(root: Path) -> dict[str, int]:
    env = {"PYTHONPATH": f"{root / 'src'}:{root / 'scripts'}:{root / 'synthetic'}", "PATH": "/usr/bin:/bin"}
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=root, env=env, capture_output=True, text=True)
    counts: collections.Counter = collections.Counter(l.split("::")[0] for l in r.stdout.splitlines() if "::" in l)
    return dict(counts)


def counts_at(commit: str, scratch: Path) -> dict[str, int]:
    d = scratch / f"tree_{commit}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    arc = subprocess.run(["git", "archive", commit], cwd=ROOT, capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(d)], input=arc.stdout, check=True)
    return collect_counts(d)


def git_show(commit: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="commit before Phase 4b (the 541-test state)")
    ap.add_argument("--before-mode", required=True)
    ap.add_argument("--after-mode", required=True)
    ap.add_argument("--chat", required=True)
    ap.add_argument("--aliases", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--phase", default="4b")
    ap.add_argument("--runs-dir", default="out/runs")
    ap.add_argument("--scratch", default=".cache/tmp")
    ap.add_argument("--out", default="docs/results/free_checks_5a")
    a = ap.parse_args(argv)
    res: dict = {}
    # (a)
    old = counts_at(a.old, ROOT / a.scratch)
    new = collect_counts(ROOT)
    files = sorted(set(old) | set(new))
    res["test_counts"] = {"files": {f: {"before": old.get(f, 0), "now": new.get(f, 0), "delta": new.get(f, 0) - old.get(f, 0)} for f in files},
                          "before_total": sum(old.values()), "now_total": sum(new.values())}
    # (b)
    j0 = json.loads(git_show(a.before_mode, "docs/results/eval_full_A.json"))
    j1 = json.loads(git_show(a.after_mode, "docs/results/eval_full_A.json"))
    only_mode = {k for k in set(j0) | set(j1) if j0.get(k) != j1.get(k)}
    res["eval_full_A_mode_change"] = {"fields_that_differ": sorted(only_mode), "identical_except_mode": only_mode == {"mode"} and j1["mode"] == "single"}
    # (c)
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8"))["items"]
    df, _ = parse_chat(a.chat)
    aliases = privacy.load_aliases(a.aliases)
    runs = []
    for f in evaluate.pick_runs(a.runs_dir, a.phase, "A", "chunked"):
        log, raw = evaluate.load_run(f)
        runs.append((f.stem, log, json.loads(f.with_suffix(".report.json").read_text(encoding="utf-8")), raw))
    bounds = [(c["start"], c["end"]) for c in runs[0][1]["chunks"]]
    occ: dict[str, list[str]] = collections.defaultdict(list)
    for it in truth:
        if it["kind"] in ("joke", "long_joke"):
            occ[it["id"]].append(it["timestamp"][:10])
    table = {}
    for tid, ds in sorted(occ.items()):
        per = []
        for lo, hi in bounds:
            inside = [d for d in ds if lo <= d <= hi]
            per.append({"occurrences": len(inside), "distinct_dates": len(set(inside)), "meets_joke_rule_alone": len(inside) >= 3 and len(set(inside)) >= 2})
        table[tid] = {"total_occurrences": len(ds), "total_dates": len(set(ds)), "per_chunk": per, "chunks_meeting_rule_alone": sum(p["meets_joke_rule_alone"] for p in per)}
    res["jokes_per_chunk"] = {"chunk_bounds": bounds, "jokes": table, "jL_chunks_meeting_rule_alone": table["jL"]["chunks_meeting_rule_alone"]}
    # (d)
    res["chunked_losses"] = evaluate.diagnose_chunked(df, aliases, runs, truth)
    base = Path(a.out)
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_suffix(".json").write_text(json.dumps(evaluate.rounded(res), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    base.with_suffix(".md").write_text(render(res), encoding="utf-8")
    print(render(res))
    return 0


def render(res: dict) -> str:
    tc = res["test_counts"]
    L = ["# Free checks of Phase 5a (numbers only, no chat text)", "", "## (a) Per-file test counts (collect-only) and deltas", "",
         f"Total {tc['before_total']} before Phase 4b, {tc['now_total']} now (delta {tc['now_total'] - tc['before_total']}).", "", "| file | before | now | delta |", "|---|---|---|---|"]
    L += [f"| {f} | {v['before']} | {v['now']} | {v['delta']} |" for f, v in tc["files"].items() if v["delta"] or True]
    m = res["eval_full_A_mode_change"]
    L += ["", "## (b) eval_full_A.json across the mode field change", "",
          f"Fields that differ between the two commits: {', '.join(m['fields_that_differ']) or 'none'}. Every number is identical, and only `mode` was added: **{m['identical_except_mode']}**.", "",
          "## (c) Planted jokes per chunk of the exact chunked plan", "", "The joke rule is: at least 3 evidence messages on at least 2 distinct dates. Cells: planted occurrences / distinct dates; `rule` marks a chunk that satisfies the rule on its own.", "",
          "| joke | total | " + " | ".join(f"chunk {k + 1}" for k in range(len(res["jokes_per_chunk"]["chunk_bounds"]))) + " | chunks meeting the rule alone |",
          "|---|---|" + "---|" * (len(res["jokes_per_chunk"]["chunk_bounds"]) + 1)]
    for tid, v in res["jokes_per_chunk"]["jokes"].items():
        L.append(f"| {tid} | {v['total_occurrences']} / {v['total_dates']} | " + " | ".join(f"{p['occurrences']} / {p['distinct_dates']}{' rule' if p['meets_joke_rule_alone'] else ''}" for p in v["per_chunk"]) + f" | {v['chunks_meeting_rule_alone']} |")
    n = res["jokes_per_chunk"]["jL_chunks_meeting_rule_alone"]
    k = len(res["jokes_per_chunk"]["chunk_bounds"])
    if n >= 1:
        L += ["", f"The long-range joke jL satisfies the joke rule inside {n} of {k} chunks on its own. "
              "**The planted jL does not test long-range dependence; a sparse joke is untested.**"]
    else:
        L += ["", f"The long-range joke jL satisfies the joke rule inside none of the {k} chunks on its own, so finding it needs evidence from several chunks."]
    L += ["", "## (d) Where planted items were lost in the chunked runs", ""]
    L.append(evaluate.render_chunked_diagnostic(res["chunked_losses"]).split("\n", 2)[2])
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
