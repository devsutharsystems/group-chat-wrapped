"""Cost guard: per-run cap, cumulative ledger cap, explicit confirm flag, price table.

Prices are USD per million tokens for claude-haiku-5-5, from docs/api-notes.md rows 14-15
(https://platform.claude.com/docs/en/about-claude/pricing). A request whose prompt length
(input + cache reads + cache writes) is over 100,000 tokens is repriced as a whole.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

LEDGER_PATH = str(Path(__file__).resolve().parents[2] / ".gcw_ledger.json")  # gitignored


def default_ledger_path() -> str:
    """The project ledger, or the file named by GCW_LEDGER_PATH (read at call time; used for demos and screenshots so the real ledger is neither read nor written)."""
    return os.environ.get("GCW_LEDGER_PATH") or LEDGER_PATH
THRESHOLD = 100_000

PRICES: dict[str, dict[str, dict[str, float]]] = {
    "claude-haiku-5-5": {
        "lo": {"in": 0.10, "out": 0.50, "cw5": 0.125, "cw1h": 0.20, "cr": 0.01},
        "hi": {"in": 0.50, "out": 2.50, "cw5": 0.625, "cw1h": 1.00, "cr": 0.05},
    }
}
BATCH_FACTOR = 0.5


class CostError(RuntimeError):
    """Raised when a call is refused by the guard."""


def per_run_cap() -> float:
    return float(os.environ.get("GCW_COST_CAP_USD", "1.00"))


def project_cap() -> float:
    return float(os.environ.get("GCW_PROJECT_CAP_USD", "3.00"))


def _get(obj: Any, key: str, default: Any = 0) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        v = obj.get(key, default)
    else:
        v = getattr(obj, key, default)
    return default if v is None else v


def prompt_length(usage: Any) -> int:
    return int(_get(usage, "input_tokens") + _get(usage, "cache_creation_input_tokens") + _get(usage, "cache_read_input_tokens"))


def cost_usd(usage: Any, model: str = "claude-haiku-5-5", *, batch: bool = False) -> float:
    """Cost of one response from its usage block. output_tokens already includes thinking tokens."""
    table = PRICES[model]["hi" if prompt_length(usage) > THRESHOLD else "lo"]
    cw = _get(usage, "cache_creation_input_tokens")
    cc = _get(usage, "cache_creation", None)
    w1h = int(_get(cc, "ephemeral_1h_input_tokens")) if cc is not None else 0
    w5 = cw - w1h
    total = (
        _get(usage, "input_tokens") * table["in"]
        + _get(usage, "output_tokens") * table["out"]
        + w5 * table["cw5"]
        + w1h * table["cw1h"]
        + _get(usage, "cache_read_input_tokens") * table["cr"]
    ) / 1_000_000
    return total * (BATCH_FACTOR if batch else 1.0)


def estimate_usd(prompt_tokens: int, max_output_tokens: int, model: str = "claude-haiku-5-5") -> float:
    """Worst case for one call: all output tokens used (thinking is inside output)."""
    return cost_usd({"input_tokens": prompt_tokens, "output_tokens": max_output_tokens}, model)


class CostGuard:
    """One per run. Thread-safe. `check` reserves an estimate; `record` replaces it with the actual cost."""

    def __init__(self, run_cap: float | None = None, proj_cap: float | None = None, ledger_path: str | None = None):
        self.run_cap = per_run_cap() if run_cap is None else run_cap
        self.proj_cap = project_cap() if proj_cap is None else proj_cap
        self.ledger_path = Path(ledger_path or default_ledger_path())
        self.spent = 0.0
        self.reserved = 0.0
        self._lock = threading.Lock()

    def check(self, estimate: float, *, confirm: bool) -> float:
        if confirm is not True:
            raise CostError("refused: confirm=True is required for every API call")
        with self._lock:
            if self.spent + self.reserved + estimate > self.run_cap + 1e-12:
                raise CostError(f"refused: run cap ${self.run_cap:.2f} would be exceeded (spent ${self.spent:.4f}, estimate ${estimate:.4f})")
            if ledger_total(self.ledger_path) + self.reserved + estimate > self.proj_cap + 1e-12:
                raise CostError(f"refused: project cap ${self.proj_cap:.2f} would be exceeded")
            self.reserved += estimate
        return estimate

    def release(self, reserved: float) -> None:
        with self._lock:
            self.reserved = max(0.0, self.reserved - reserved)

    def record(self, label: str, usage: Any, model: str, *, reserved: float = 0.0, extra: dict | None = None) -> float:
        cost = cost_usd(usage, model)
        entry = {
            "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "label": label,
            "model": model,
            "input_tokens": int(_get(usage, "input_tokens")),
            "output_tokens": int(_get(usage, "output_tokens")),
            "cache_creation_input_tokens": int(_get(usage, "cache_creation_input_tokens")),
            "cache_read_input_tokens": int(_get(usage, "cache_read_input_tokens")),
            "cost_usd": round(cost, 8),
            **(extra or {}),
        }
        with self._lock:
            self.reserved = max(0.0, self.reserved - reserved)
            self.spent += cost
            _append(self.ledger_path, entry)
        return cost


def _read(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, ValueError):
        return []


def _append(path: Path, entry: dict) -> None:
    entries = _read(path)
    entries.append(entry)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"entries": entries}, indent=1), encoding="utf-8")
    tmp.replace(path)


def ledger_total(path: str | Path | None = None) -> float:
    return sum(e.get("cost_usd", 0.0) for e in _read(Path(path or default_ledger_path())))


def ledger_entries(path: str | Path | None = None) -> list[dict]:
    return _read(Path(path or default_ledger_path()))


def guard(estimate_usd: float, *, confirm: bool, guard_obj: CostGuard | None = None) -> float:
    """Refuse any call without confirm=True or above the caps. Returns the reserved estimate."""
    return (guard_obj or CostGuard()).check(estimate_usd, confirm=confirm)
