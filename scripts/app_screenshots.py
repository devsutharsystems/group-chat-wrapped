"""Four headless images of the app on the bundled SYNTHETIC demo chat -> docs/img/. No API call.

One Streamlit server (127.0.0.1, nice -n 10) for the whole run; three SEQUENTIAL browser sessions (Chromium --disable-gpu, one page, deviceScaleFactor 1), each
closed before the next starts. The only moment a second Chromium exists is the app's own card render child, started when the stats card is rendered in
session 1; that is measured. A sampler sums the resident memory of this script's whole process tree (server, browsers, render child) per step, prints
the maximum per step and the per-process breakdown at the peak, and kills everything if the sum goes above the ceiling below.

Why the ceiling here is 1.4 GB and not 1 GB: the harness holds one browser (with its Node driver) while the app starts its own render child (a second Chromium
stack and a second Node driver), so two stacks coexist during the Render click. The other project's benchmark, which the 1 GB rule protected, has finished.
Summed RSS probably overcounts pages the processes share (unverified). This is a dev tool; it is not part of the app's footprint. Above 1.4 GB the sampler kills
the tree and the script prints the per-process breakdown; nothing raises the ceiling.

The review screenshot loads a SAVED MODEL RUN (the earliest config A run with slice end 2026-02-08, stamp 20261106T202238, on the synthetic chat) through the app's saved-report upload.
  PYTHONPATH=src nice -n 10 .venv/bin/python scripts/app_screenshots.py --report out/runs/20261106T202238-A.report.json
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
LIMIT_MB = 1433  # 1.4 GB: a ceiling for THIS dev-only script step only; the 1 GB rule in CLAUDE.md stays for everything else (see the docstring)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache" / "ms-playwright"))  # the browsers live inside the project


def demo_ledger(directory: Path) -> str:
    """A throw-away cost ledger with ONE fictional entry (US$0.05), so no screenshot shows, reads or writes the real ledger (.gcw_ledger.json)."""
    import json

    directory.mkdir(parents=True, exist_ok=True)
    p = directory / "demo_ledger.json"
    p.write_text(json.dumps({"entries": [{"label": "demo:fictional", "cost_usd": 0.05}]}), encoding="utf-8")
    return str(p)


def server_env(workdir: Path) -> dict[str, str]:
    """Environment of the Streamlit server: the source tree on the path, no API key, and the demo ledger instead of the real one."""
    # STREAMLIT_CLIENT_TOOLBAR_MODE=minimal hides the three-dot menu for the screenshots only (docs: environment variables override .streamlit/config.toml, which keeps
    # toolbarMode = "viewer" for the real app): https://docs.streamlit.io/develop/concepts/configuration/options
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), GCW_LEDGER_PATH=demo_ledger(workdir), STREAMLIT_CLIENT_TOOLBAR_MODE="minimal")
    env.pop("ANTHROPIC_API_KEY", None)
    return env


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


def session(pw, fn, height: int = 1100) -> None:
    browser = pw.chromium.launch(args=["--disable-gpu"])
    try:
        ctx = browser.new_context(viewport={"width": 1280, "height": height}, device_scale_factor=1)
        page = ctx.new_page()
        page.set_default_timeout(150_000)
        page.goto(f"http://127.0.0.1:{PORT}")
        page.get_by_text("Group Chat Wrapped").first.wait_for()
        try:
            fn(page, page.locator('[data-testid="stSidebar"]'))
        except Exception:
            alerts = [t[:300] for t in page.locator('[data-testid="stAlert"]').all_inner_texts()]
            print("page alerts at the failure:", alerts, "file inputs:", page.locator('input[type="file"]').count(),
                  "date segments:", [(x.get_attribute("aria-label"), x.inner_text()) for x in page.get_by_role("spinbutton").all()][:8])
            page.screenshot(path=str(ROOT / ".cache" / "tmp" / "fail.png"), full_page=True)
            raise
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
    ap.add_argument("--until", default="2026-02-08", help="the window end of the saved run (YYYY-MM-DD); stats and AI items must cover the same window")
    ap.add_argument("--out-dir", default="docs/img")
    a = ap.parse_args(argv)
    out = ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    import shutil

    work = ROOT / ".cache" / "tmp" / f"shots_{os.getpid()}"
    env = server_env(work)
    report, runlog = work / "demo.report.json", work / "demo.json"  # short file names, so the page shows them without truncating
    shutil.copyfile(a.report, report)
    shutil.copyfile(a.report.replace(".report.json", ".json"), runlog)
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
                img = page.locator('[data-testid="stImage"] img').first
                img.wait_for()
                time.sleep(1)
                assert img.bounding_box()["width"] >= 700, img.bounding_box()
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
                assert not page.get_by_role("checkbox").is_checked()
                page.screenshot(path=str(out / "app_2_payload_preview_before_consent.png"), full_page=True)

            def shot3(page, side):  # the review step: a saved model run, loaded through the saved-report upload
                load_demo(page, side)
                side.get_by_text("2 Settings").click()
                page.get_by_text("Upload aliases.json").click()
                page.locator('input[type="file"]').set_input_files(a.aliases)
                page.get_by_text("members loaded").wait_for()
                # the stats must cover the same window as the saved run (it ends 2026-02-08): type the end date into the date field (year, month, day segments)
                y, m, d = a.until.split("-")
                segs = page.get_by_role("group", name="Until (inclusive)").get_by_role("spinbutton")
                for i in range(segs.count()):  # the segment order follows the browser locale, so each segment is found by its own label
                    label = (segs.nth(i).get_attribute("aria-label") or "").lower()
                    value = y if "year" in label else m if "month" in label else d if "day" in label else None
                    if value is not None:
                        segs.nth(i).click()
                        page.keyboard.type(value)
                page.keyboard.press("Tab")  # the date field commits on blur, not on Enter
                page.get_by_text("Date window").click()
                time.sleep(1.5)
                samp.step = "3 review (browser + server)"
                side.get_by_text("5 Review").click()
                page.get_by_text("Nothing to review yet").wait_for()  # let the step settle before the upload, or the widget is re-created and drops the file
                page.locator('input[type="file"]').first.set_input_files(str(report))
                page.get_by_text("Context around the first quote").first.wait_for()
                page.locator('input[type="file"]').nth(1).set_input_files(str(runlog))  # the run log gives the original "proposed" count
                page.get_by_text("demo.json").first.wait_for()
                page.get_by_text("Review state").wait_for()
                # the approvals are made with the app's own button (shown only for the bundled synthetic chat); nothing is written to a review file by hand
                page.get_by_role("button", name="Auto-approve all (synthetic demo only)").click()
                page.get_by_text("approvals made by: auto-synthetic").wait_for()
                page.get_by_text("'approved': 12").wait_for()  # every decision is registered and the rerun is over
                time.sleep(1.5)
                # an element-sized capture: from the top of the page to the bottom of the controls (decision and rank) of the THIRD item, measured from the DOM
                main = page.locator('[data-testid="stMain"]')
                main.evaluate("e => e.scrollTo(0, 0)")
                time.sleep(0.5)
                third = [main.locator('[data-testid="stRadio"]').nth(2).bounding_box(), main.locator('[data-testid="stNumberInput"]').nth(2).bounding_box()]
                assert all(third), third
                bottom = max(b["y"] + b["height"] for b in third) + 24
                vh = page.viewport_size["height"]
                assert 0 < bottom <= vh, (bottom, vh)  # item 3's controls lie inside the capture, and the capture inside the viewport
                clip = {"x": 0, "y": 0, "width": page.viewport_size["width"], "height": bottom}
                p3 = out / "app_3_review.png"
                page.screenshot(path=str(p3), clip=clip)
                from PIL import Image

                assert Image.open(p3).size[1] >= max(b["y"] + b["height"] for b in third), "the capture does not cover item 3's controls"
                # 4. render the card from the approved items: the app starts its own render child here (a second Chromium stack)
                samp.step = "4 review render card (browser + server + render child)"
                page.get_by_role("button", name="Render card").click()
                page.get_by_text("Download card with AI items").wait_for()
                img = page.locator('[data-testid="stImage"] img').first
                img.wait_for()
                img.scroll_into_view_if_needed()
                time.sleep(1.5)
                box = img.bounding_box()
                assert box["width"] >= 700 and abs(box["height"] - box["width"] * 1350 / 1080) <= 2, box  # the whole card is on screen
                # the card file the user would get: the download button's file is the real 1080x1350 PNG (st.image shows a 720-px JPEG re-encode, which is not the card file)
                path4 = out / "app_4_review_rendered_card.png"
                with page.expect_download() as dl:
                    page.get_by_role("button", name="Download card with AI items (PNG)").click()
                dl.value.save_as(str(path4))
                from PIL import Image

                assert Image.open(path4).size == (1080, 1350) and Image.open(path4).format == "PNG"

            for n, (fn, height) in enumerate(((shot1, 1400), (shot2, 1500), (shot3, 2400)), 1):
                samp.step = f"{n} browser start"
                session(pw, fn, height)
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
        shutil.rmtree(work, ignore_errors=True)
        samp.stop_flag = True
        samp.join(5)
    if samp.blown:
        print("STOPPED, over the ceiling:", samp.blown)
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
