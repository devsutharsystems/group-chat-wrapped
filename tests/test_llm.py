from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from gcw import cost, llm


class FakeClient:
    def __init__(self, text='{"ok": true}', stop="end_turn", usage=None):
        self.calls = []
        self.messages = NS(create=self.create, count_tokens=self.count)
        self.text, self.stop = text, stop
        self.usage = usage or {"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}

    def create(self, **kw):
        self.calls.append(kw)
        return NS(content=[NS(type="text", text=self.text)], stop_reason=self.stop, usage=self.usage)

    def count(self, **kw):
        return NS(input_tokens=123)


def guard(tmp_path, cap=1.0):
    return cost.CostGuard(run_cap=cap, proj_cap=3.0, ledger_path=str(tmp_path / "l.json"))


def test_call_shape_and_ledger(tmp_path):
    c, g = FakeClient(), guard(tmp_path)
    r = llm.call_json("hi", {"type": "object"}, max_tokens=500, confirm=True, guard=g, label="t", client=c)
    kw = c.calls[0]
    assert kw["model"] == "claude-haiku-5-5" and kw["max_tokens"] == 500
    assert kw["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": {"type": "object"}}}
    assert "thinking" not in kw and "temperature" not in kw
    assert r.ok and r.parsed == {"ok": True}
    assert cost.ledger_total(str(tmp_path / "l.json")) == pytest.approx(r.cost_usd) and r.cost_usd > 0


def test_no_confirm_no_call(tmp_path):
    c = FakeClient()
    with pytest.raises(cost.CostError):
        llm.call_json("hi", {}, max_tokens=500, confirm=False, guard=guard(tmp_path), label="t", client=c)
    assert c.calls == []


def test_over_cap_no_call(tmp_path):
    c = FakeClient()
    with pytest.raises(cost.CostError):
        llm.call_json("hi", {}, max_tokens=500_000, confirm=True, guard=guard(tmp_path, cap=0.01), label="t", client=c)
    assert c.calls == []


def test_max_tokens_is_not_ok(tmp_path):
    r = llm.call_json("hi", {}, max_tokens=500, confirm=True, guard=guard(tmp_path), label="t", client=FakeClient(text='{"ok":', stop="max_tokens"))
    assert not r.ok and r.parsed is None and "max_tokens" in r.note


def test_invalid_json_is_not_ok(tmp_path):
    r = llm.call_json("hi", {}, max_tokens=500, confirm=True, guard=guard(tmp_path), label="t", client=FakeClient(text="nope"))
    assert not r.ok


def test_api_error_releases_reservation(tmp_path):
    class Boom(FakeClient):
        def create(self, **kw):
            raise RuntimeError("boom")

    g = guard(tmp_path)
    with pytest.raises(RuntimeError):
        llm.call_json("hi", {}, max_tokens=500, confirm=True, guard=g, label="t", client=Boom())
    assert g.reserved == 0


def test_count_tokens_wrapper():
    assert llm.count_tokens("hi", client=FakeClient()) == 123
