"""Three headless screenshots of the app on the bundled SYNTHETIC demo chat -> docs/img/. One Streamlit server (127.0.0.1, nice -n 10), one Chromium
(--disable-gpu), one page, deviceScaleFactor 1, everything closed afterwards. No API call: the review step loads a hand-made report
(scripts/make_demo_report.py). Run under nice and the guarded wrapper:
  PYTHONPATH=src nice -n 10 .venv/bin/python scripts/app_screenshots.py --report .cache/tmp/demo.report.json"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8599
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache" / "ms-playwright"))  # the browsers live inside the project


def wait_up(url: str, secs: int = 60) -> None:
    t = time.time()
    while time.time() - t < secs:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("the Streamlit server did not start")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out-dir", default="docs/img")
    a = ap.parse_args(argv)
    out = ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".cache" / "ms-playwright"))
    env.pop("ANTHROPIC_API_KEY", None)
    server = subprocess.Popen(["nice", "-n", "10", sys.executable, "-m", "streamlit", "run", str(ROOT / "src" / "gcw" / "app.py"), "--server.port", str(PORT),
                               "--server.headless", "true", "--server.address", "127.0.0.1", "--browser.gatherUsageStats", "false"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_up(f"http://127.0.0.1:{PORT}/_stcore/health")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--disable-gpu"])
            try:
                ctx = browser.new_context(viewport={"width": 1280, "height": 1100}, device_scale_factor=1)
                page = ctx.new_page()
                page.set_default_timeout(150_000)
                page.goto(f"http://127.0.0.1:{PORT}")
                page.get_by_text("Group Chat Wrapped").first.wait_for()
                side = page.locator('[data-testid="stSidebar"]')
                # 1. load the demo chat, render the stats card
                page.get_by_text("Bundled synthetic demo chat").click()
                page.get_by_role("button", name="Load the demo chat").click()
                page.get_by_text("Loaded: synthetic demo chat").wait_for()
                side.get_by_text("3 Stats card").click()
                page.get_by_role("button", name="Render stats card").click()
                page.locator('[data-testid="stImage"] img').first.wait_for()
                time.sleep(1)
                page.screenshot(path=str(out / "app_1_stats_card.png"), full_page=True)
                # 2. AI mode: the payload preview before consent
                side.get_by_text("2 Settings").click()
                page.get_by_text("AI (sends pseudonymised text").click()
                side.get_by_text("4 AI").click()
                page.get_by_text("Exactly what would be sent").wait_for()
                time.sleep(1)
                page.screenshot(path=str(out / "app_2_payload_preview_before_consent.png"), full_page=True)
                # 3. review: a hand-made report, approve both items, render the card
                side.get_by_text("5 Review").click()
                page.locator('input[type="file"]').set_input_files(a.report)
                page.get_by_text("Demo running joke").first.wait_for()
                for lab in page.get_by_text("approved", exact=True).all():
                    lab.click()
                page.get_by_role("button", name="Render card").click()
                page.get_by_text("Download card with AI items").wait_for()
                time.sleep(1)
                page.screenshot(path=str(out / "app_3_review.png"), full_page=True)
                ctx.close()
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(15)
        except subprocess.TimeoutExpired:
            server.kill()
    for f in sorted(out.glob("app_*.png")):
        print(f.relative_to(ROOT), f.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
