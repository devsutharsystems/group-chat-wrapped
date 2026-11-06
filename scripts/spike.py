#!/usr/bin/env python3
"""API spike: 20 synthetic lines -> claude-haiku-5-5 (effort low + JSON schema) and count_tokens.

  spike.py --estimate   local worst-case cost, NO API call
  spike.py --confirm    runs count_tokens (free) + one messages.create through the cost guard
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from gcw import cost, llm  # noqa: E402

LINES = [
    ("Maya", "Did anyone pick up milk on the way home?"),
    ("Jordan", "I did, it's on the counter."),
    ("Riley", "Thanks! I'll make pancakes tomorrow."),
    ("Kai", "What time are you thinking?"),
    ("Riley", "Around nine, before it gets busy."),
    ("Maya", "Works for me."),
    ("Jordan", "I might be a bit late, the bus is slow on Sundays."),
    ("Kai", "Same, I'll try to leave early."),
    ("Sam", "Is the oven still making that clicking noise?"),
    ("Riley", "Yes, it only does it on the first minute."),
    ("Sam", "Okay, I'll look at it this weekend."),
    ("Alex", "Can someone send the recipe link?"),
    ("Maya", "Sending it now."),
    ("Alex", "Got it, looks easy enough."),
    ("Jordan", "We also need eggs and butter."),
    ("Kai", "I can pick those up after work."),
    ("Riley", "Great, that covers everything."),
    ("Maya", "Should we invite the neighbours?"),
    ("Sam", "Sure, the more the merrier."),
    ("Alex", "I'll knock on their door tonight."),
]
SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "line_count": {"type": "integer"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"i": {"type": "integer"}, "sender": {"type": "string"}, "is_question": {"type": "boolean"}},
                "required": ["i", "sender", "is_question"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["topic", "line_count", "lines"],
    "additionalProperties": False,
}
MAX_TOKENS = 2000


def prompt() -> str:
    body = "\n".join(f"{i}. {s}: {t}" for i, (s, t) in enumerate(LINES, 1))
    return (
        "Below are 20 numbered lines from a synthetic group chat. Return JSON with the overall topic "
        "(a few words), the number of lines, and for every line its number, sender and whether it is a question.\n\n" + body
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    p = prompt()
    est = cost.estimate_usd(llm.rough_prompt_tokens(p), MAX_TOKENS)
    if a.estimate or not a.confirm:
        print(f"spike estimate (local, worst case, no API call): ${est:.5f}  [prompt ~{llm.rough_prompt_tokens(p)} tok, max_tokens {MAX_TOKENS}]")
        print(f"caps: run ${cost.per_run_cap():.2f}, project ${cost.project_cap():.2f}; ledger so far ${cost.ledger_total():.5f}")
        return 0
    loaded, n = llm.key_status()
    print(f"key loaded: {'yes' if loaded else 'no'}, length {n}")
    if not loaded:
        return 3
    client = llm.get_client()
    est_count = llm.count_tokens(p, client=client)
    res = llm.call_json(p, SCHEMA, max_tokens=MAX_TOKENS, confirm=True, guard=cost.CostGuard(), label="spike", client=client)
    actual = res.usage.get("input_tokens")
    out = {
        "request": {k: v for k, v in llm.request_params("<prompt>", SCHEMA, MAX_TOKENS, "low").items() if k != "messages"},
        "stop_reason": res.stop_reason,
        "usage": res.usage,
        "latency_s": round(res.latency_s, 3),
        "count_tokens_estimate": est_count,
        "actual_input_tokens": actual,
        "pct_diff": round(100 * (est_count - actual) / actual, 2) if actual else None,
        "cost_usd": res.cost_usd,
        "ok": res.ok,
        "note": res.note,
        "parsed_line_count": (res.parsed or {}).get("line_count") if res.parsed else None,
    }
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "spike.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
