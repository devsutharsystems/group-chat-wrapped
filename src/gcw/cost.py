"""Cost guard: per-run cap, cumulative ledger cap, explicit confirm flag."""
from __future__ import annotations

import os

LEDGER_PATH = ".gcw_ledger.json"  # gitignored


def per_run_cap() -> float:
    return float(os.environ.get("GCW_COST_CAP_USD", "1.00"))


def project_cap() -> float:
    return float(os.environ.get("GCW_PROJECT_CAP_USD", "3.00"))


def guard(estimate_usd: float, *, confirm: bool) -> None:
    """Refuse any call without confirm=True or above the caps. (stub)"""
    raise NotImplementedError("stub: not implemented in Phase 0")
