"""FREE, no API: a HAND-MADE verified report for the bundled synthetic demo chat (planted jokes and moment from the ground truth), for the review-step screenshot
and for trying the app's 'load a saved report' path. It is NOT model output; it is built from synthetic ground truth only.
  .venv/bin/python scripts/make_demo_report.py --out .cache/tmp/demo.report.json"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gcw import analyze, appcore, verify  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    df, view = appcore.parse_view(appcore.demo_text())
    since, until = appcore.default_window(view["last"])
    al = appcore.aliases_from_table(appcore.alias_table(list(view["senders"])))
    prep = analyze.prepare(df, al, slice_start=since, slice_end=until)
    truth = json.loads((ROOT / "synthetic" / "frozen" / "ground_truth.json").read_text(encoding="utf-8"))["items"]
    occ = verify.planted_occurrences(truth, prep["index"], prep["mapping"])

    def ev(tid: str, n: int) -> list[dict]:
        out, seen = [], set()
        for pid, ts in occ[tid]["occurrences"]:
            if str(ts.date()) not in seen or len(out) < n:
                out.append({"message_id": pid, "quote": prep["index"][pid]["text"]})
                seen.add(str(ts.date()))
            if len(out) == n:
                break
        return out

    rep = {"running_jokes": [{"title": "Demo running joke", "summary": "A planted joke from the synthetic ground truth.", "evidence": ev("j1", 3)}],
           "moments": [{"title": "Demo moment", "summary": "A planted moment from the synthetic ground truth.", "evidence": ev("m1", 1)}], "awards": []}
    verified, stats = verify.verify_report(rep, prep["index"], valid_members=set(prep["members"]))
    kept = {t: len(v) for t, v in verified.items()}
    if kept["running_jokes"] != 1 or kept["moments"] != 1:
        print(f"the demo items did not verify in the default window: {kept}", file=sys.stderr)
        return 3
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(verified, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {a.out}: {kept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
