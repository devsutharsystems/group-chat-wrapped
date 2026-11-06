import importlib

import pytest

MODULES = ["parser", "stats", "privacy", "llm", "verify", "card", "cost", "app"]


@pytest.mark.parametrize("name", MODULES)
def test_modules_import(name):
    importlib.import_module(f"gcw.{name}")


def test_cost_cap_defaults(monkeypatch):
    monkeypatch.delenv("GCW_COST_CAP_USD", raising=False)
    monkeypatch.delenv("GCW_PROJECT_CAP_USD", raising=False)
    from gcw import cost

    assert cost.per_run_cap() == 1.00
    assert cost.project_cap() == 3.00
