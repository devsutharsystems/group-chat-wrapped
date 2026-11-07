"""Phase 8d: final README wording before the public flip (headings, no claims about other tools, requires-python line, History paragraph facts)."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess

from test_privacy import ROOT

README = (ROOT / "README.md").read_text(encoding="utf-8")


def section(title: str) -> str:
    return README.split(f"## {title}", 1)[1].split("\n## ", 1)[0]


def test_design_choices_heading_and_no_claims_about_other_tools():
    heads = re.findall(r"^## (.*)$", README, re.M)
    assert heads[:3] == ["Design choices", "Results in brief", "Quickstart"] and "Why it differs from common WhatsApp analysers" not in heads
    low = README.lower()
    for w in ("other tools", "common whatsapp", "analysers", "analyzers", "competitor", "unlike other", "most other", "than other"):
        assert w not in low, w
    dc = section("Design choices")
    assert dc.lstrip().startswith("1. **Every quote behind an AI claim is checked in code against the real message.**")
    assert "it does not check whether the quotes support the item's title and summary" in dc and "That is what the hand rating measures" in dc


def test_quickstart_states_the_python_requirement_from_pyproject():
    floor = re.search(r'requires-python = ">=(\d+\.\d+)"', (ROOT / "pyproject.toml").read_text()).group(1)
    q = section("Quickstart")
    assert f"Requires Python {floor} or newer (`requires-python` in `pyproject.toml`). CI covers Python 3.11 and 3.13; local runs used Python 3.15.0." in q
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "'3.11'" in ci and "'3.13'" in ci


def test_history_paragraph_prediction_wording_and_commits():
    sec = section("History and publishing")
    assert ("The predictions for the chunked experiment on the dense chat (commit `cd8e87f`) and for the sparse control and the chunked run on the large chat (commit `429cb2d`) "
            "were committed before those live runs; the first large-chat single-pass run (889,497 tokens, n = 1) had no pre-registered prediction.") in sec
    big = json.loads((ROOT / "docs/results/eval_large_A.json").read_text())
    assert f"{big['runs'][0]['input_tokens']:,} tokens, n = {big['n_runs']}" in sec  # the number comes from the results file
    subjects = {h: subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%s", h], capture_output=True, text=True).stdout.strip() for h in ("cd8e87f", "429cb2d")}
    assert subjects["cd8e87f"].startswith("Phase 4b tooling") and "PRD predictions written before any chunked run" in subjects["cd8e87f"]
    assert subjects["429cb2d"].startswith("Phase 5b tooling") and "PRD predictions written before any live call" in subjects["429cb2d"]
    prd = subprocess.run(["git", "-C", str(ROOT), "show", "cd8e87f:docs/PRD.md"], capture_output=True, text=True).stdout
    assert "predictions written BEFORE any chunked run" in prd
    prd5 = subprocess.run(["git", "-C", str(ROOT), "show", "429cb2d:docs/PRD.md"], capture_output=True, text=True).stdout
    assert "predictions written BEFORE any Phase 5b live call" in prd5
    assert "developed with Claude Code, and the commits carry Co-Authored-By trailers" in sec


def test_the_licence_paragraph_is_untouched():
    assert hashlib.sha256(("## Licence" + section("Licence")).encode()).hexdigest() == "0f1549273e27ec667d4a38ee51e19d27fa84ecaf781231615314fad08fbb1c8f"
