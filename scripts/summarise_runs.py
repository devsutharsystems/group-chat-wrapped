"""FREE: summarise saved dev-slice runs per config (n, mean and range). No API call, no winner is named.
  .venv/bin/python scripts/summarise_runs.py CHAT --aliases aliases.example.json --truth synthetic/frozen/ground_truth.json [--phase 3b --phase 3bfix]
Reads out/runs/*.json that have a saved response (runs made with --save-response, or the 3b runs from before the flag existed)."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gcw import evaluate, privacy  # noqa: E402
from gcw.parser import parse_chat  # noqa: E402

DEV_END = "2026-02-08"


def rng(v: list[float], pct: bool = False) -> str:
    f = (lambda x: f"{x:.0%}") if pct else (lambda x: f"{x:g}")
    return f"mean {f(statistics.mean(v))} (range {f(min(v))}-{f(max(v))})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chat")
    ap.add_argument("--aliases", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--runs-dir", default="out/runs")
    a = ap.parse_args(argv)
    df, _ = parse_chat(a.chat)
    aliases = privacy.load_aliases(a.aliases)
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8"))["items"]
    by_cfg: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(Path(a.runs_dir).glob("*.json")):
        if f.name.endswith(".report.json") or not f.with_suffix(".response.txt").exists():
            continue
        log, report = evaluate.load_run(f)
        sl = log.get("slice") or {"start": None, "end": DEV_END if log["messages"] == 1594 else None}
        if sl.get("start") is not None or sl.get("end") != DEV_END or "error" in log:
            continue  # only the dev slice, successful runs
        res = evaluate.score_saved(df, aliases, report, slice_start=sl["start"], slice_end=sl["end"], truth_items=truth)
        c, sc = res["classification"], res["score"]
        att = log["usage"]
        by_cfg[log["config"]].append({
            "file": f.name, "prompt_version": (log.get("prompt_version") or "n/a (3b run, same prompt text)")[:12], "grounding": c["grounding_rate"], "rule": c["rule_compliant_rate"],
            "kept": res["stats"]["items_kept_by_type"], "lenient": {t: len(sc[t]["found"]) for t in ("running_jokes", "moments")},
            "strict": {t: len(sc[t]["found_strict"]) for t in ("running_jokes", "moments")},
            "planted": {t: len(sc[t]["planted_in_slice"]) for t in ("running_jokes", "moments")},
            "thinking": (att.get("output_tokens_details") or {}).get("thinking_tokens"), "output": att.get("output_tokens"),
            "latency": log["latency_s"], "cost": log["cost_usd"], "statuses": c["status_counts"]})
    for cfg in sorted(by_cfg):
        rs = by_cfg[cfg]
        print(f"config {cfg}: n={len(rs)} runs ({', '.join(r['file'][:15] for r in rs)})")
        print(f"  grounding rate {rng([r['grounding'] for r in rs], True)}; rule-compliant rate {rng([r['rule'] for r in rs], True)}")
        print(f"  items kept per run (jokes/moments/awards): {[tuple(r['kept'].values()) for r in rs]}")
        print(f"  planted in slice {rs[0]['planted']}; lenient found per run {[tuple(r['lenient'].values()) for r in rs]}; strict found per run {[tuple(r['strict'].values()) for r in rs]}")
        print(f"  thinking_tokens {[r['thinking'] for r in rs]}; output_tokens {rng([r['output'] for r in rs])}; latency {rng([r['latency'] for r in rs])}s; cost {rng([r['cost'] for r in rs])}")
        print(f"  drop statuses per run: {[{k: v for k, v in r['statuses'].items() if k != 'verified'} for r in rs]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
