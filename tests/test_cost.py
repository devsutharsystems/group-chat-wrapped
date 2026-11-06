from __future__ import annotations

import pytest

from gcw import cost


def u(i=0, o=0, cw=0, cr=0):
    return {"input_tokens": i, "output_tokens": o, "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}


def test_cost_low_tier():
    assert cost.cost_usd(u(1000, 1000)) == pytest.approx((1000 * 0.10 + 1000 * 0.50) / 1e6)


def test_cost_whole_request_repriced_over_100k_including_cache_reads():
    # 60K uncached + 60K cache read = 120K prompt: the whole request uses the high tier
    c = cost.cost_usd(u(60_000, 1000, cr=60_000))
    assert c == pytest.approx((60_000 * 0.50 + 1000 * 2.50 + 60_000 * 0.05) / 1e6)


def test_batch_half_price():
    assert cost.cost_usd(u(1000, 1000), batch=True) == pytest.approx(cost.cost_usd(u(1000, 1000)) / 2)


def test_guard_requires_confirm(tmp_path):
    g = cost.CostGuard(run_cap=1.0, proj_cap=3.0, ledger_path=str(tmp_path / "l.json"))
    with pytest.raises(cost.CostError):
        g.check(0.001, confirm=False)
    with pytest.raises(cost.CostError):
        g.check(0.001, confirm=1)  # truthy but not True


def test_guard_run_cap_and_reservation(tmp_path):
    g = cost.CostGuard(run_cap=0.01, proj_cap=3.0, ledger_path=str(tmp_path / "l.json"))
    r = g.check(0.006, confirm=True)
    with pytest.raises(cost.CostError):
        g.check(0.006, confirm=True)  # reserved spend counts
    g.release(r)
    g.check(0.006, confirm=True)


def test_guard_project_cap_uses_ledger(tmp_path):
    p = str(tmp_path / "l.json")
    g = cost.CostGuard(run_cap=10, proj_cap=0.01, ledger_path=p)
    g.record("x", u(0, 40_000), "claude-haiku-5-5")  # $0.02
    with pytest.raises(cost.CostError):
        cost.CostGuard(run_cap=10, proj_cap=0.01, ledger_path=p).check(0.001, confirm=True)


def test_ledger_accumulates(tmp_path):
    p = str(tmp_path / "l.json")
    g = cost.CostGuard(run_cap=1, proj_cap=3, ledger_path=p)
    g.record("a", u(1000, 1000), "claude-haiku-5-5")
    g.record("b", u(1000, 1000), "claude-haiku-5-5")
    assert cost.ledger_total(p) == pytest.approx(2 * 0.0006)
    assert [e["label"] for e in cost.ledger_entries(p)] == ["a", "b"]


def test_estimate_is_worst_case():
    assert cost.estimate_usd(1000, 2000) == pytest.approx((1000 * 0.10 + 2000 * 0.50) / 1e6)
