"""Session-wide protection: tests never reach the Anthropic API.

GCW_TEST_NO_NETWORK is set before any test (and so inherited by every subprocess a test starts): llm.get_client() refuses when it is set.
In-process, anthropic.Anthropic construction and httpx.Client.send also raise, so even code that bypasses llm.get_client cannot send a request.
tests/test_no_real_client.py proves all of this. The live commands (python -m gcw analyze ... --confirm) run outside pytest and are unaffected.
"""
from __future__ import annotations

import os

import pytest

BLOCK_MESSAGE = "REAL API ACCESS BLOCKED IN TESTS"
os.environ["GCW_TEST_NO_NETWORK"] = "1"
os.environ["ANTHROPIC_API_KEY"] = ""  # empty (not unset): python-dotenv will not refill it from .env


def http_module():
    """The HTTP library the installed anthropic SDK uses (httpx2 in this environment, httpx elsewhere)."""
    import importlib

    for name in ("httpx2", "httpx"):
        try:
            return importlib.import_module(name)
        except ImportError:
            continue
    raise RuntimeError("no httpx/httpx2 module found")


@pytest.fixture(autouse=True, scope="session")
def _block_real_clients():
    import anthropic

    httpx = http_module()

    mp = pytest.MonkeyPatch()

    def no_init(self, *a, **k):
        raise AssertionError(BLOCK_MESSAGE + ": anthropic client construction")

    def no_send(self, *a, **k):
        raise AssertionError(BLOCK_MESSAGE + ": httpx request")

    mp.setattr(anthropic.Anthropic, "__init__", no_init)
    mp.setattr(anthropic.AsyncAnthropic, "__init__", no_init)
    mp.setattr(httpx.Client, "send", no_send)
    mp.setattr(httpx.AsyncClient, "send", no_send)
    yield
    mp.undo()
