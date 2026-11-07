"""One tiny messages call (about 10 tokens) through the cost guard, with the SDK's raw-response access, printing every anthropic-ratelimit-* header.
Header names are those documented at https://platform.claude.com/docs/en/api/rate-limits (response headers table). Needs --confirm. Never prints the key.
  .venv/bin/python scripts/ratelimit_probe.py --confirm [--need-input-tokens 960000]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gcw import cost, llm  # noqa: E402

DOC_URL = "https://platform.claude.com/docs/en/api/rate-limits"
DOCUMENTED = ["retry-after", "anthropic-ratelimit-requests-limit", "anthropic-ratelimit-requests-remaining", "anthropic-ratelimit-requests-reset",
              "anthropic-ratelimit-tokens-limit", "anthropic-ratelimit-tokens-remaining", "anthropic-ratelimit-tokens-reset",
              "anthropic-ratelimit-input-tokens-limit", "anthropic-ratelimit-input-tokens-remaining", "anthropic-ratelimit-input-tokens-reset",
              "anthropic-ratelimit-output-tokens-limit", "anthropic-ratelimit-output-tokens-remaining", "anthropic-ratelimit-output-tokens-reset"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--need-input-tokens", type=int, default=960_000)
    a = ap.parse_args(argv)
    guard = cost.CostGuard()
    est = cost.estimate_usd(20, 8)
    reserved = guard.check(est, confirm=a.confirm)
    client = llm.get_client(max_retries=0)
    raw = client.messages.with_raw_response.create(model=llm.MODEL, max_tokens=8, messages=[{"role": "user", "content": "Reply with the word ok."}])
    resp = raw.parse()
    usage = llm._usage_dict(resp.usage)
    c = guard.record("5a:ratelimit-probe", usage, llm.MODEL, reserved=reserved, extra={"stop_reason": resp.stop_reason})
    print(f"documented at {DOC_URL}")
    print(f"probe: input_tokens {usage.get('input_tokens')}, output_tokens {usage.get('output_tokens')}, cost ${c:.6f}, stop_reason {resp.stop_reason}")
    hdrs = {k.lower(): v for k, v in raw.headers.items()}
    seen = sorted(k for k in hdrs if k.startswith("anthropic-ratelimit-") or k.startswith("anthropic-priority-") or k == "retry-after")
    for k in seen:
        print(f"  {k}: {hdrs[k]}")
    print("documented headers absent from this response: " + (", ".join(k for k in DOCUMENTED if k not in hdrs) or "none"))
    lim = hdrs.get("anthropic-ratelimit-input-tokens-limit")
    req = hdrs.get("anthropic-ratelimit-requests-limit")
    print(f"input-tokens-per-minute limit: {lim}; requests limit: {req}; remaining input tokens now: {hdrs.get('anthropic-ratelimit-input-tokens-remaining')}")
    if lim is None or int(lim) < a.need_input_tokens:
        print(f"STOP: the input-token limit is {lim or 'absent'}, below the {a.need_input_tokens} the near-1M request needs. Do not generate.")
        return 3
    print("PASS: the input-token limit covers the near-1M request.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
