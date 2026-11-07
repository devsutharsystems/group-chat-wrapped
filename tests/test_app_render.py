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
