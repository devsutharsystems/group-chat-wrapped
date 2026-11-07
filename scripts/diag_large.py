"""FREE: diagnose the saved near-1M run (phase 5a). Numbers and ids only -> docs/results/diag_large_A.md and .json. No API call.
  .venv/bin/python scripts/diag_large.py --chat synthetic/frozen_large/chat_synthetic_large.txt --truth synthetic/frozen_large/ground_truth.json
      --orig-chat synthetic/frozen/chat_synthetic.txt --orig-truth synthetic/frozen/ground_truth.json --aliases aliases.example.json --phase 5a"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gcw import evaluate, privacy  # noqa: E402
from gcw.parser import parse_chat  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chat", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--orig-chat", required=True)
    ap.add_argument("--orig-truth", required=True)
    ap.add_argument("--aliases", required=True)
    ap.add_argument("--phase", default="5a")
    ap.add_argument("--runs-dir", default="out/runs")
    ap.add_argument("--out", default="docs/results/diag_large_A")
    a = ap.parse_args(argv)
    files = evaluate.pick_runs(a.runs_dir, a.phase, "A", "single")
    if len(files) != 1:
        print(f"expected exactly one saved single run of phase {a.phase}, found {len(files)}", file=sys.stderr)
        return 3
    log, report = evaluate.load_run(files[0])
    df, _ = parse_chat(a.chat)
    odf, _ = parse_chat(a.orig_chat)
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8"))["items"]
    otruth = json.loads(Path(a.orig_truth).read_text(encoding="utf-8"))["items"]
    aliases = privacy.load_aliases(a.aliases)
    d = evaluate.diagnose_dropped(df, aliases, report, truth)
    dens = {"original chat": evaluate.planted_density(odf, otruth), "large chat": evaluate.planted_density(df, truth)}
    rep = json.loads(subprocess.run([sys.executable, str(ROOT / "scripts" / "repetition_check.py"), a.chat, a.truth], capture_output=True, text=True, check=True).stdout)
    out = {"run": files[0].stem, **d, "density": dens, "repetition_large": {"repeated_over_3": rep["repeated_over_3"], "top_3grams": rep["top_3grams"][:10]}}
    base = Path(a.out)
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_suffix(".json").write_text(json.dumps(evaluate.rounded(out), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    md = evaluate.render_dropped_markdown(d, dens, {"repeated_over_3": rep["repeated_over_3"], "top_3grams": rep["top_3grams"]})
    base.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
