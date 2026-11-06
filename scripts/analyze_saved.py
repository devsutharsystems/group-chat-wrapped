"""FREE: classify every evidence item of saved model responses (no API call). Usage (from the project root):
  .venv/bin/python scripts/analyze_saved.py CHAT --aliases aliases.example.json --truth synthetic/frozen/ground_truth.json [RUN_JSON ...]
Without RUN_JSON files it reads every out/runs/*.json that has a saved response. A run without a `slice` entry in its log needs --slice-start/--slice-end."""
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
    ap.add_argument("--truth")
    ap.add_argument("--slice-start")
    ap.add_argument("--slice-end")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    ap.add_argument("runs", nargs="*")
    a = ap.parse_args(argv)
    df, _ = parse_chat(a.chat)
    aliases = privacy.load_aliases(a.aliases)
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8"))["items"] if a.truth else None
    files = [Path(r) for r in a.runs] or sorted(Path("out/runs").glob("*.json"))
    files = [f for f in files if not f.name.endswith((".report.json",)) and f.with_suffix(".response.txt").exists()]
    for f in files:
        log, report = evaluate.load_run(f)
        sl = log.get("slice") or {"start": a.slice_start, "end": a.slice_end}
        res = evaluate.score_saved(df, aliases, report, slice_start=sl["start"], slice_end=sl["end"], truth_items=truth)
        c = res["classification"]
        print(f"{f.name}: config {log['config']}, slice {sl}, messages {log['messages']}")
        print(f"  evidence {c['evidence_total']}: grounding rate {c['grounding_rate']:.0%}, rule-compliant rate {c['rule_compliant_rate']:.0%}; statuses {c['status_counts']}")
        print(f"  too_short but grounded: {c['too_short_but_grounded']}; other-message distances {c['other_message_distances']}")
        for r in res["records"]:
            if r["status"] == "other_message":
                print(f"    other_message: cited {r['message_id']}, real {r['real_ids']}, distance {r['distance']}")
        if "score" in res:
            for typ, s in res["score"].items():
                if s["planted_in_slice"]:
                    print(f"  {typ}: planted {s['planted_in_slice']}, lenient found {s['found']} ({s['recall']}), strict found {s['found_strict']} ({s['recall_strict']})")
        if a.json:
            print(json.dumps({k: v for k, v in res.items() if k != "records"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
