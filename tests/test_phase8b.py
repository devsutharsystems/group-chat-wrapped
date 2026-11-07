"""Phase 8b: the CI workflow installs the browsers into the folder the code and tests use, and nothing is weakened. CI itself can only be verified by a real run."""
from __future__ import annotations

import re
from pathlib import Path

from gcw import card
from test_privacy import ROOT

CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
FOLDER = "${{ github.workspace }}/.cache/ms-playwright"


def test_the_browser_folder_is_set_once_at_job_level_to_the_folder_the_code_expects():
    assert CI.count("PLAYWRIGHT_BROWSERS_PATH:") == 1
    job = CI.split("  test:\n", 1)[1]
    assert re.search(r"^    env:\n(      #.*\n)+      PLAYWRIGHT_BROWSERS_PATH: " + re.escape(FOLDER) + r"\n", job, re.M)
    assert job.index("PLAYWRIGHT_BROWSERS_PATH:") < job.index("    steps:")  # job level, not inside a step
    assert not re.search(r"^\s{8,}.*PLAYWRIGHT_BROWSERS_PATH:", job, re.M)  # no step-level override that could point elsewhere
    # the code and the tests default to <repo>/.cache/ms-playwright, and the workspace is the repository root
    assert Path(card.__file__).resolve().parents[2] == ROOT and "ms-playwright" in (ROOT / "src/gcw/card.py").read_text()
    assert FOLDER.endswith("/.cache/ms-playwright") and 'ROOT / ".cache" / "ms-playwright"' in (ROOT / "tests/test_card.py").read_text() + (ROOT / "src/gcw/card.py").read_text()


def test_install_uses_the_documented_command_and_a_diagnostic_lists_the_folder_before_the_tests():
    assert "python -m playwright install --with-deps chromium" in CI  # https://playwright.dev/python/docs/browsers , /ci
    names = re.findall(r"^      - name: (.*)$", CI, re.M)
    i = next(k for k, n in enumerate(names) if n.startswith("Install"))
    d = next(k for k, n in enumerate(names) if n.startswith("Diagnostic - browser folder"))
    t = next(k for k, n in enumerate(names) if n.startswith("Tests"))
    assert i < d < t
    diag = CI.split("Diagnostic - browser folder", 1)[1].split("      - name:", 1)[0]
    assert "-mindepth 1 -maxdepth 2" in diag and "%P" in diag and 'test -d "$PLAYWRIGHT_BROWSERS_PATH"' in diag and "exit 1" in diag  # names only, two levels, fails if the folder is missing


def test_the_step_labels_and_nothing_is_weakened():
    assert "      - name: Pre-publish checks\n" in CI and "red until" not in CI and "precision_A.json" not in CI
    assert "run: python -m pytest -q\n" in CI and "run: python scripts/scan_repo.py\n" in CI and "run: python scripts/prepublish_check.py\n" in CI
    for bad in ("continue-on-error", "|| true", "--deselect", "--ignore", " -k ", "-m not", "skip", "--no-header --co"):
        assert bad not in CI.replace("# ", "#"), bad
    assert "if: matrix.python-version == '3.13'" in CI and CI.count("if:") == 1  # the only conditional is the single pre-publish run
    assert "pip install -e" not in CI and "secrets." not in CI
