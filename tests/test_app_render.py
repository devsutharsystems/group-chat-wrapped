"""Slow end-to-end check of the app's REAL render path (appcore.render_png_bytes -> render_child subprocess -> Chromium). Deselected by default; run alone:
  nice -n 10 .venv/bin/pytest -m slow -q
It must not share the session with the browser fixture: one Chromium at a time."""
from __future__ import annotations

import hashlib
import struct
import subprocess
import sys

import pytest

import conftest
from gcw import appcore
from test_privacy import ROOT

pytestmark = pytest.mark.slow


def test_the_real_app_render_path_gives_a_1080x1350_png_identical_to_the_cli_card(tmp_path):
    assert conftest.BROWSER_CREATED is False  # no other Chromium exists in this process
    df, view = appcore.parse_view(appcore.demo_text())
    since, until = appcore.default_window(view["last"])
    al = appcore.aliases_from_table(appcore.alias_table(list(view["senders"])))
    png = appcore.render_png_bytes(appcore.card_html(df, al, since, until, view["date_order"] if view["ambiguous"] else None))
    assert struct.unpack(">II", png[16:24]) == (1080, 1350)
    out = tmp_path / "cli.png"
    cmd = [sys.executable, "-m", "gcw", "stats-card", str(appcore.DEMO_CHAT), "--out", str(out), "--since", since]
    subprocess.run(["nice", "-n", "10", *cmd], check=True, capture_output=True, cwd=ROOT, env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")})
    assert hashlib.sha256(png).hexdigest() == hashlib.sha256(out.read_bytes()).hexdigest()


def test_the_real_app_ai_card_render_matches_the_cli_card_for_the_saved_config_a_run(tmp_path):
    """The app's real render path on a saved config A run (all items approved) against `gcw card ... --auto-approve-synthetic`; skipped when the saved run is absent."""
    import json
    import os

    from gcw import analyze, privacy, review

    run = ROOT / "out" / "runs" / "20261106T202238-A"
    if not run.with_suffix(".report.json").is_file():
        pytest.skip("the saved config A run (out/runs, gitignored) is not on this machine")
    assert conftest.BROWSER_CREATED is False
    chat, al_path, until = appcore.DEMO_CHAT, ROOT / "aliases.example.json", "2026-02-08"
    df, view = appcore.parse_view(appcore.demo_text())
    al = privacy.load_aliases(str(al_path))
    prep = analyze.prepare(df, al, slice_start=None, slice_end=until)
    report, stats = appcore.load_report_upload(run.with_suffix(".report.json").read_bytes(), prep["index"], set(prep["members"]))
    rv = review.approve_all(report, "app")
    ai = appcore.zone_for(report, rv, prep["index"], prep["mapping"], al, stats, proposed=appcore.proposed_from_log(run.with_suffix(".json").read_bytes()))  # synthetic: the CLI flag sets the same footer wording
    png = appcore.render_png_bytes(appcore.card_html(df, al, None, until, view["date_order"] if view["ambiguous"] else None, ai=ai))
    assert struct.unpack(">II", png[16:24]) == (1080, 1350)
    out = tmp_path / "cli_ai.png"
    cmd = [sys.executable, "-m", "gcw", "card", str(chat), "--aliases", str(al_path), "--report", str(run.with_suffix(".json")), "--auto-approve-synthetic", "--until", until, "--out", str(out)]
    subprocess.run(["nice", "-n", "10", *cmd], check=True, capture_output=True, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert hashlib.sha256(png).hexdigest() == hashlib.sha256(out.read_bytes()).hexdigest()
    assert json.loads(run.with_suffix(".report.json").read_text())  # the saved report is untouched
