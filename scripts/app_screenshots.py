"""Three headless screenshots of the app on the bundled SYNTHETIC demo chat -> docs/img/. No API call.

One Streamlit server (127.0.0.1, nice -n 10) for the whole run; three SEQUENTIAL browser sessions (Chromium --disable-gpu, one page, deviceScaleFactor 1), each
closed before the next starts. The only moment a second Chromium exists is the app's own card render child, started when the stats card is rendered in
session 1; that is measured. A sampler sums the resident memory of this script's whole process tree (server, browsers, render child) per step, prints
the maximum per step and the per-process breakdown at the peak, and kills everything if the sum goes above 1 GB (the limit is not configurable here).

The review screenshot loads a SAVED MODEL RUN (config A, slice to 2026-02-08, the synthetic chat) through the app's saved-report upload.
  PYTHONPATH=src nice -n 10 .venv/bin/python scripts/app_screenshots.py --report out/runs/20261106T203833-A.report.json
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8599
LIMIT_MB = 1024
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache" / "ms-playwright"))  # the browsers live inside the project


def tree() -> list[tuple[int, int, str]]:
    """[(pid, rss_mb, command)] of this process's descendants (ps; only our own tree is looked at)."""
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,rss=,comm="], capture_output=True, text=True).stdout.splitlines()
    rows = {}
    for ln in out:
        p = ln.split(None, 3)
        if len(p) == 4:
            rows[int(p[0])] = (int(p[1]), int(p[2]) // 1024, p[3])
    me = os.getpid()
    keep = {me}
    changed = True
    while changed:
        changed = False
        for pid, (pp, _, _) in rows.items():
            if pp in keep and pid not in keep:
                keep.add(pid)
                changed = True
    return [(pid, rows[pid][1], Path(rows[pid][2]).name) for pid in keep if pid in rows]


class Sampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.step = "start"
        self.peaks: dict[str, tuple[int, list]] = {}
        self.stop_flag = False
        self.blown: str | None = None

    def run(self) -> None:
        while not self.stop_flag:
            t = tree()
            total = sum(r for _, r, _ in t)
            best = self.peaks.get(self.step, (0, []))
            if total > best[0]:
                self.peaks[self.step] = (total, sorted(t, key=lambda x: -x[1]))
            if total > LIMIT_MB and not self.blown:
                self.blown = f"step {self.step}: {total} MB"
                for pid, _, _ in t:
                    if pid != os.getpid():
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except OSError:
                            pass
                return
            time.sleep(0.1)


def wait_up(url: str, secs: int = 60) -> None:
    t = time.time()
    while time.time() - t < secs:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("the Streamlit server did not start")


def session(pw, fn) -> None:
    browser = pw.chromium.launch(args=["--disable-gpu"])
    try:
        ctx = browser.new_context(viewport={"width": 1280, "height": 1100}, device_scale_factor=1)
        page = ctx.new_page()
        page.set_default_timeout(150_000)
        page.goto(f"http://127.0.0.1:{PORT}")
        page.get_by_text("Group Chat Wrapped").first.wait_for()
        fn(page, page.locator('[data-testid="stSidebar"]'))
        ctx.close()
    finally:
        browser.close()


def load_demo(page, side) -> None:
    page.get_by_text("Bundled synthetic demo chat").click()
    page.get_by_role("button", name="Load the demo chat").click()
    page.get_by_text("Loaded: synthetic demo chat").wait_for()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True, help="a saved verified report (.report.json) of a real model run on the demo chat")
    ap.add_argument("--aliases", default=str(ROOT / "aliases.example.json"))
    ap.add_argument("--until", default="2026/02/08", help="window end of that run, YYYY/MM/DD")
    ap.add_argument("--out-dir", default="docs/img")
    a = ap.parse_args(argv)
    out = ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    env.pop("ANTHROPIC_API_KEY", None)
    samp = Sampler()
    samp.start()
    samp.step = "server start"
    server = subprocess.Popen(["nice", "-n", "10", sys.executable, "-m", "streamlit", "run", str(ROOT / "src" / "gcw" / "app.py"), "--server.port", str(PORT),
                               "--server.headless", "true", "--server.address", "127.0.0.1", "--browser.gatherUsageStats", "false"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rc = 0
    try:
        wait_up(f"http://127.0.0.1:{PORT}/_stcore/health")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            def shot1(page, side):  # the stats card step: the only step in which the app's render child runs
                load_demo(page, side)
                side.get_by_text("3 Stats card").click()
                samp.step = "1 stats card (browser + server + render child)"
                page.get_by_role("button", name="Render stats card").click()
                page.locator('[data-testid="stImage"] img').first.wait_for()
                time.sleep(1)
                page.screenshot(path=str(out / "app_1_stats_card.png"), full_page=True)

            def shot2(page, side):  # the payload preview before consent: checkbox unticked, Run disabled
                load_demo(page, side)
                side.get_by_text("2 Settings").click()
                page.get_by_text("AI (sends pseudonymised text").click()
                samp.step = "2 payload preview (browser + server)"
                side.get_by_text("4 AI").click()
                page.get_by_text("Exactly what would be sent").wait_for()
                time.sleep(1)
                assert page.get_by_role("button", name="Run").is_disabled()
                page.screenshot(path=str(out / "app_2_payload_preview_before_consent.png"), full_page=True)

            def shot3(page, side):  # the review step: a saved model run, loaded through the saved-report upload
                load_demo(page, side)
                side.get_by_text("2 Settings").click()
                page.get_by_text("Upload aliases.json").click()
                page.locator('input[type="file"]').set_input_files(a.aliases)
                page.get_by_text("members loaded").wait_for()
                until = page.get_by_label("Until (inclusive)")
                until.fill(a.until)
                until.press("Enter")
                time.sleep(1)
                samp.step = "3 review (browser + server)"
                side.get_by_text("5 Review").click()
                page.locator('input[type="file"]').set_input_files(a.report)
                page.get_by_text("Review state").wait_for()
                for lab in page.get_by_text("approved", exact=True).all()[:3]:
                    lab.click()
                time.sleep(1)
                page.screenshot(path=str(out / "app_3_review.png"), full_page=True)

            for n, fn in enumerate((shot1, shot2, shot3), 1):
                samp.step = f"{n} browser start"
                session(pw, fn)
                samp.step = f"{n} browser closed"
                time.sleep(0.5)
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {type(e).__name__}: {str(e)[:400]}")
        rc = 1
    finally:
        samp.step = "server stop"
        server.terminate()
        try:
            server.wait(15)
        except subprocess.TimeoutExpired:
            server.kill()
        samp.stop_flag = True
        samp.join(5)
    if samp.blown:
        print("STOPPED, over the 1 GB limit:", samp.blown)
        rc = 2
    print("peak total RSS per step (MB):")
    for k, (mb, procs) in samp.peaks.items():
        print(f"  {k}: {mb}")
    worst = max(samp.peaks.items(), key=lambda kv: kv[1][0])
    print(f"maximum: {worst[1][0]} MB in step '{worst[0]}'; processes then:", ", ".join(f"{n} {r}" for _, r, n in worst[1][1][:8]))
    for f in sorted(out.glob("app_*.png")):
        print(f.relative_to(ROOT), f.stat().st_size)
    return rc


if __name__ == "__main__":
    sys.exit(main())
