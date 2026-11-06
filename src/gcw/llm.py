"""Haiku calls. Every call goes through cost.CostGuard (explicit confirm, caps, ledger).

Call shape: docs/api-notes.md row 12 (output_config effort + json_schema format, no
`thinking` param, no temperature). The key comes only from the ANTHROPIC_API_KEY env var,
loaded from the project's .env by python-dotenv; it is never printed or logged.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gcw import cost

MODEL = "claude-haiku-5-5"
ROOT = Path(__file__).resolve().parents[2]


@dataclass
class LLMResult:
    parsed: Any
    text: str
    stop_reason: str | None
    usage: dict
    latency_s: float
    cost_usd: float
    ok: bool = True
    note: str = ""
    extra: dict = field(default_factory=dict)


def load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)


def key_status() -> tuple[bool, int]:
    """(loaded?, length). Never returns or prints the key itself."""
    load_env()
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(k), len(k)


def get_client() -> Any:
    load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set (create .env in the project root)")
    import anthropic

    return anthropic.Anthropic()


def _usage_dict(usage: Any) -> dict:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return dict(vars(usage))


def rough_prompt_tokens(prompt: str) -> int:
    """Local, conservative (over-)estimate. The new tokenizer is ~30% heavier than older ones."""
    return int(len(prompt) / 2.5) + 50


def request_params(prompt: str, schema: dict, max_tokens: int, effort: str, system: str | None = None, thinking: dict | None = None) -> dict:
    p: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    }
    if system:
        p["system"] = system
    if thinking is not None:  # e.g. {"type": "disabled"}: allowed at effort high or below (api-notes row 9)
        p["thinking"] = thinking
    return p


def count_tokens(prompt: str, *, client: Any, system: str | None = None, schema: dict | None = None, effort: str = "low") -> int:
    """Free endpoint (api-notes row 13). Pass `schema` to include output_config (effort + json_schema) like the real request."""
    kw: dict[str, Any] = {"model": MODEL, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kw["system"] = system
    if schema is not None:
        kw["output_config"] = {"effort": effort, "format": {"type": "json_schema", "schema": schema}}
    return int(client.messages.count_tokens(**kw).input_tokens)


def call_json(
    prompt: str,
    schema: dict,
    *,
    max_tokens: int,
    confirm: bool,
    guard: cost.CostGuard,
    label: str,
    effort: str = "low",
    system: str | None = None,
    thinking: dict | None = None,
    client: Any = None,
) -> LLMResult:
    est = cost.estimate_usd(rough_prompt_tokens(prompt) + (rough_prompt_tokens(system) if system else 0), max_tokens)
    reserved = guard.check(est, confirm=confirm)
    client = client or get_client()
    t0 = time.perf_counter()
    try:
        resp = client.messages.create(**request_params(prompt, schema, max_tokens, effort, system, thinking))
    except Exception:
        guard.release(reserved)
        raise
    latency = time.perf_counter() - t0
    usage = _usage_dict(getattr(resp, "usage", None))
    c = guard.record(label, usage, MODEL, reserved=reserved, extra={"stop_reason": getattr(resp, "stop_reason", None), "thinking_tokens": (usage.get("output_tokens_details") or {}).get("thinking_tokens")})
    text = "".join(getattr(b, "text", "") for b in getattr(resp, "content", []) if getattr(b, "type", "") == "text")
    stop = getattr(resp, "stop_reason", None)
    parsed, ok, note = None, True, ""
    if stop == "max_tokens":
        ok, note = False, "stop_reason=max_tokens (output may be incomplete)"
    else:
        try:
            parsed = json.loads(text)
        except ValueError as e:
            ok, note = False, f"invalid JSON: {e}"
    return LLMResult(parsed, text, stop, usage, latency, c, ok, note)
