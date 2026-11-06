#!/usr/bin/env python3
"""count_tokens calibration: with vs without output_config, against real input_tokens, at 3 sizes.

  calibrate.py --confirm   one real ~50K-token call (cost ~$0.005) through the cost guard.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "synthetic"))

import gen_chat as g  # noqa: E402
import spike  # noqa: E402  (scripts/ is on sys.path when run as a script)
from gcw import cost, llm  # noqa: E402


def row(name: str, actual: int, without: int, with_: int) -> dict:
    return {"point": name, "actual": actual, "count_without": without, "count_with": with_,
            "gap_without": actual - without, "gap_with": actual - with_,
            "pct_without": round(100 * (without - actual) / actual, 2), "pct_with": round(100 * (with_ - actual) / actual, 2)}


def main() -> int:
    if "--confirm" not in sys.argv:
        print("needs --confirm")
        return 2
    loaded, n = llm.key_status()
    print(f"key loaded: {'yes' if loaded else 'no'}, length {n}")
    if not loaded:
        return 3
    client = llm.get_client()
    rows = []
    # A: the spike (actual input_tokens 805 from out/spike.json)
    sp = json.loads((ROOT / "out" / "spike.json").read_text())
    p = spike.prompt()
    rows.append(row("spike", sp["usage"]["input_tokens"], llm.count_tokens(p, client=client), llm.count_tokens(p, client=client, schema=spike.SCHEMA)))
    # B: one real mini-run call (a cached successful batch)
    cfg = g.load_config()
    sk = g.skeleton(cfg, mini=True)
    done = None
    for s in g.batch_specs(sk):
        f = g.CACHE_DIR / f"{g.ApiFiller(cfg, None, confirm=True, thinking=None, log=print, client=client).key(s)}.json"
        if f.exists():
            done = (s, json.loads(f.read_text()))
            break
    if done:
        s, c = done
        p = s.prompt()
        rows.append(row(f"mini call {s.label}", c["usage"]["input_tokens"], llm.count_tokens(p, client=client), llm.count_tokens(p, client=client, schema=g.SCHEMA)))
    # C: one real ~50K-token call, same generator schema, trivial task
    full = g.render(*(lambda sk2: (sk2, g.build_messages(cfg, sk2, {(sp_.burst_id, sp_.part): g.FakeFiller()(sp_) for sp_ in g.batch_specs(sk2)})))(g.skeleton(cfg)))
    lines = full.splitlines(True)

    def mk(k: int) -> str:
        return ("Count the chat lines below. Return JSON with a single message whose i is 1 and whose text is the number of lines, as digits.\n\n" + "".join(lines[:k]))

    k = 3000
    for _ in range(4):
        t = llm.count_tokens(mk(k), client=client, schema=g.SCHEMA)
        if abs(t - 50_000) < 1500:
            break
        k = int(k * 50_000 / t)
    p = mk(k)
    with_ = llm.count_tokens(p, client=client, schema=g.SCHEMA)
    without = llm.count_tokens(p, client=client)
    res = llm.call_json(p, g.SCHEMA, max_tokens=200, confirm=True, guard=cost.CostGuard(run_cap=0.05), label="calibrate-50k", client=client)
    rows.append(row(f"50K call ({k} lines)", res.usage["input_tokens"], without, with_))
    out = {"rows": rows, "big_call": {"stop_reason": res.stop_reason, "usage": res.usage, "latency_s": round(res.latency_s, 2), "cost_usd": res.cost_usd, "ok": res.ok, "note": res.note}}
    (ROOT / "out" / "calibrate.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
