"""FREE: why were planted items missed in the saved phase 4a runs? Numbers only (docs/results/miss_diagnostic_A.json and .md).
  .venv/bin/python scripts/diagnose_misses.py CHAT --aliases aliases.example.json --truth synthetic/frozen/ground_truth.json --phase 4a"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gcw import evaluate, privacy  # noqa: E402
from gcw.parser import parse_chat  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chat")
    ap.add_argument("--aliases", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--phase", required=True)
    ap.add_argument("--config", default="A")
    ap.add_argument("--runs-dir", default="out/runs")
    ap.add_argument("--out", default="docs/results/miss_diagnostic_A")
    a = ap.parse_args(argv)
    df, _ = parse_chat(a.chat)
    aliases = privacy.load_aliases(a.aliases)
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8"))["items"]
    runs = []
    for f in evaluate.pick_runs(a.runs_dir, a.phase, a.config):
        log, rep = evaluate.load_run(f)
        runs.append((f.stem, log, rep))
    if not runs:
        print("no saved runs found", file=sys.stderr)
        return 3
    d = evaluate.diagnose_misses(df, aliases, runs, truth)
    base = Path(a.out)
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_suffix(".json").write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    base.with_suffix(".md").write_text(evaluate.render_diagnostic_markdown(d), encoding="utf-8")
    print(evaluate.render_diagnostic_markdown(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
