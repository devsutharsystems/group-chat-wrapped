"""Deliberate proof that real API access is impossible inside the test run. Each attempt below is a REAL attempt (construct a client,
send a request, start a subprocess that tries); each must fail loudly with the blocking message. Run with -v -s to see the messages."""
from __future__ import annotations

import os
import subprocess
import sys

import anthropic
import pytest

from conftest import http_module
from gcw import analyze, llm
from test_analyze import SMALL, SMALL_AL
from test_privacy import ROOT

BLOCKED = "REAL API ACCESS BLOCKED IN TESTS"


def test_environment_is_locked_for_the_whole_session():
    assert os.environ["GCW_TEST_NO_NETWORK"] == "1" and os.environ["ANTHROPIC_API_KEY"] == ""


def test_llm_get_client_refuses():
    with pytest.raises(RuntimeError, match=BLOCKED) as e:
        llm.get_client()
    print("\n[blocked] llm.get_client():", e.value)


def test_constructing_an_anthropic_client_fails_loudly():
    with pytest.raises(AssertionError, match=BLOCKED) as e:
        anthropic.Anthropic(api_key="NOT-A-REAL-KEY")
    print("\n[blocked] anthropic.Anthropic(...):", e.value)
    with pytest.raises(AssertionError, match=BLOCKED):
        anthropic.AsyncAnthropic(api_key="NOT-A-REAL-KEY")


def test_sending_an_http_request_to_the_api_fails_loudly():
    httpx = http_module()
    with httpx.Client() as c:
        with pytest.raises(AssertionError, match=BLOCKED) as e:
            c.send(httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    print("\n[blocked] " + httpx.__name__ + ".Client.send:", e.value)


def test_a_paid_analysis_without_a_fake_client_cannot_reach_the_api(tmp_path):
    from gcw import cost

    guard = cost.CostGuard(run_cap=1.0, proj_cap=3.0, ledger_path=str(tmp_path / "ledger.json"))
    with pytest.raises(RuntimeError, match=BLOCKED) as e:
        analyze.run_analysis(SMALL, SMALL_AL, config="A", confirm=True, guard=guard, out_dir=tmp_path / "runs")  # no client= on purpose
    print("\n[blocked] run_analysis(confirm=True) with no fake client:", e.value)
    assert cost.ledger_entries(guard.ledger_path) == []


def test_a_subprocess_started_by_a_test_inherits_the_block():
    code = "from gcw import llm; llm.get_client()"
    r = subprocess.run([sys.executable, "-c", code], env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True)
    assert r.returncode != 0 and BLOCKED in r.stderr
    print("\n[blocked] subprocess llm.get_client(): exit", r.returncode, "-", r.stderr.strip().splitlines()[-1])
