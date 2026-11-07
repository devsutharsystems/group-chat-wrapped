"""Phase 7b: memory provenance, the history-blob and mentions checks, the CI and Pages workflows, the static site, .gitignore and the publish checklist. No network, no browser."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import build_readme_tables as btab
import build_site as site
import prepublish_check as pp
from test_phase7a import git, repo
from test_privacy import FROZEN, ROOT

WF = ROOT / ".github" / "workflows"
CI = (WF / "ci.yml").read_text(encoding="utf-8")
PAGES = (WF / "pages.yml").read_text(encoding="utf-8")


# ---------------------------------------------------------------- memory.json provenance
def test_every_memory_entry_has_provenance_and_the_ranges_match_the_observations():
    m = json.loads((ROOT / "docs/results/memory.json").read_text())
    for p in m["render_paths"]:
        pv = p["provenance"]
        assert {"run", "phase", "measured_on", "copied_from_session_output"} <= set(pv)
    steps = {s["step"]: s for s in m["screenshot_harness"]["steps"]}
    for s in steps.values():
        assert s["min_mb"] == min(s["observed_mb"]) and s["max_mb"] == max(s["observed_mb"])
        assert [x["mb"] for x in s["provenance"]] == s["observed_mb"]
        assert all({"run", "phase", "measured_on", "copied_from_session_output"} <= set(x) for x in s["provenance"])
    sc = steps["stats card (browser + server + render child)"]
    assert sc["observed_mb"] == [1116, 1135, 1171] and (sc["min_mb"], sc["max_mb"]) == (1116, 1171)
    # no number was changed: the single observations are the values recorded before this phase
    assert {k: v["observed_mb"] for k, v in steps.items() if k != "stats card (browser + server + render child)"} == {
        "server start": [198], "browser start": [704], "payload preview (browser + server)": [814], "review (browser + server)": [959],
        "review with Render card (browser + server + render child)": [1088]}
    assert [(p["wall_clock_s"], p["largest_process_bytes"], p["process_tree_mb"]) for p in m["render_paths"]] == [(2.97, 138428416, 509), (5.68, 244498432, 455)]


def test_the_readme_memory_block_shows_the_ranges():
    block = re.search(r"<!-- BEGIN:cost_block -->\n(.*?)\n<!-- END:cost_block -->", (ROOT / "README.md").read_text(), re.S).group(1)
    assert "| 1,116, 1,135, 1,171 | 1,116 | 1,171 |" in block and "copied from session output: yes" in block
    assert btab.stale(ROOT) == []


# ---------------------------------------------------------------- prepublish: blobs and mentions
def test_the_blob_check_lists_the_five_largest_and_fails_over_one_megabyte_even_after_deletion(tmp_path):
    big = b"0" * (1024 * 1024 + 1)
    r = repo(tmp_path, {"a.txt": "x", "docs/big.bin": big, "synthetic/frozen_large/ok.bin": big + b"1"})  # different content: git lists one path per identical blob
    ok, msg = pp.blob_history(r)
    assert not ok and "docs/big.bin" in msg and msg.count(" B ") <= 5 and "5 largest blobs" in msg
    git(r, "rm", "-q", "docs/big.bin")
    git(r, "commit", "-q", "-m", "rm")
    assert not pp.blob_history(r)[0]  # still in history
    only_ok = tmp_path / "b"
    only_ok.mkdir()
    repo(only_ok, {"synthetic/frozen_large/ok.bin": big, "a.txt": "x"})
    ok, msg = pp.blob_history(only_ok)
    assert ok and "ok.bin" in msg
    small = tmp_path / "c"
    small.mkdir()
    repo(small, {f"f{i}.txt": "x" * (i + 1) for i in range(8)})
    assert pp.blob_history(small)[1].count(" B ") == 5


def test_the_mentions_check_is_informational_and_finds_each_term_case_insensitively(tmp_path):
    lines = ["thanks Prateek", "the MENTOR said", "an lds project", "Lets Data Science week", "cost $5 only", "the key limit was hit", "by DevSuthar", "I-am-Dev-Suthar"]
    r = repo(tmp_path, {"notes.md": "\n".join(lines) + "\nholds builds fields\nnothing here\n", "img.png": b"Prateek"})
    hits = pp.mentions(r)
    assert len(hits) == 8 and all(h.startswith("notes.md:") for h in hits) and "holds builds" not in " ".join(hits)  # whole-word LDS only; images are skipped
    out: list[str] = []
    code = pp.run(r, out=out.append)
    assert any(x.startswith("INFO  mentions") and "8 line(s)" in x for x in out) and code == 1  # a tmp repo fails other checks; INFO is never counted
    assert sum(x.startswith(("PASS", "FAIL")) for x in out) == len(pp.CHECKS)


# ---------------------------------------------------------------- CI and Pages workflows
def test_ci_triggers_permissions_and_steps():
    assert re.search(r"^on:\n  push:\n  pull_request:", CI, re.M) and re.search(r"^permissions:\n  contents: read\n", CI, re.M)
    assert "fetch-depth: 0" in CI and "pip install ." in CI and "pip install -e" not in CI and "-e ." not in CI
    for cmd in ("pytest -q", "scripts/scan_repo.py", "scripts/prepublish_check.py"):
        assert cmd in CI
    assert "continue-on-error" not in CI and "|| true" not in CI  # nothing is weakened
    assert "secrets." not in CI and "ANTHROPIC" not in CI and "-m slow" not in CI


def test_every_action_is_pinned_by_major_version_and_python_matches_the_floor():
    for text in (CI, PAGES):
        uses = re.findall(r"uses:\s*(\S+)", text)
        assert uses and all(re.fullmatch(r"[\w./-]+@v\d+", u) for u in uses), uses
    floor = re.search(r'requires-python = ">=(\d+\.\d+)"', (ROOT / "pyproject.toml").read_text()).group(1)
    versions = re.search(r"python-version: \[(.*?)\]", CI).group(1)
    assert f"'{floor}'" in versions and "'3.13'" in versions
    assert "setup-python@v7" in CI and "checkout@v7" in CI and "upload-pages-artifact@v3" in PAGES and "deploy-pages@v4" in PAGES


def test_pages_workflow_publishes_the_prebuilt_folder_without_a_build_step():
    assert "path: site" in PAGES and "pages: write" in PAGES and "id-token: write" in PAGES and "name: github-pages" in PAGES
    assert "pip install" not in PAGES and "build_site" not in PAGES and "secrets." not in PAGES


# ---------------------------------------------------------------- static site
def all_html() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "site").glob("*.html")}


def test_the_site_loads_nothing_external_and_has_no_script():
    pages = all_html()
    assert set(pages) == {"index.html", "methodology.html"}
    for name, h in pages.items():
        assert not re.search(r"<script|<iframe|<object|<embed|@import|url\(\s*['\"]?https?:|<link\b[^>]*href=['\"]?https?:", h, re.I), name
        assert not re.search(r"<(img|source|video|audio)\b[^>]*\bsrc=['\"]?(https?:)?//", h, re.I), name
        assert "<link" not in h.lower() or 'rel="stylesheet"' not in h.lower()
        assert "http://" not in h and "https://" not in re.sub(r'<a href="https://[^"]*">', "", h)  # a plain link is the only place a URL may appear
        assert "google" not in h.lower() and "analytics" not in h.lower()


def test_the_site_stays_small_and_holds_only_the_two_demo_cards():
    files = [p for p in (ROOT / "site").rglob("*") if p.is_file()]
    assert sum(p.stat().st_size for p in files) < 5 * 1024 * 1024
    assert sorted(str(p.relative_to(ROOT / "site")) for p in files) == ["img/ai_card.png", "img/stats_card.png", "index.html", "methodology.html"]


def test_the_site_has_no_chat_text_and_uses_the_readme_demo_wording():
    text = " ".join(all_html().values())
    from gcw.parser import messages, parse_chat

    bodies = [t for t in messages(parse_chat(FROZEN)[0])["text"] if len(t) >= 25]
    assert len(bodies) > 1000 and not [b for b in bodies if b[:40] in text]
    idx = all_html()["index.html"]
    assert "auto-approved demo" in idx and "judged to be the same as the earlier demo card" in idx and "sent to Anthropic" in idx and "synthetic" in idx


def test_the_site_is_escaped_and_the_repo_link_is_only_written_when_given():
    bad = '"><script>alert(1)</script>'
    h = site.build(ROOT, repo_url=bad)["index.html"]
    assert "<script" not in h and "&lt;script&gt;" in h
    assert 'href="https' not in site.build(ROOT, "")["index.html"] and "added when the repository is published" in site.build(ROOT, "")["index.html"]
    assert site.inline("`a<b` & <i>") == "<code>a&lt;b</code> &amp; &lt;i&gt;"
    md = site.md_to_html("| a | b |\n|---|---|\n| <x> | `y` |\n\n- one <b>\n\ntext & more")
    assert "<td>&lt;x&gt;</td>" in md and "<code>y</code>" in md and "<li>one &lt;b&gt;</li>" in md and "<p>text &amp; more</p>" in md


def test_the_committed_methodology_page_matches_the_readme_blocks():
    strip = lambda s: re.sub(r"<p>Source[^<]*(<a [^>]*>[^<]*</a>)?[^<]*</p>", "", s)  # noqa: E731  the repo line depends on --repo-url
    assert strip(all_html()["methodology.html"]) == strip(site.build(ROOT)["methodology.html"]), "run: .venv/bin/python scripts/build_site.py"


def test_the_site_cards_are_the_cards_the_cli_renders_for_the_demo_chat():
    import hashlib

    assert hashlib.sha256((ROOT / "site/img/stats_card.png").read_bytes()).hexdigest() == "c910ba35b229f37e6c9eb2b0b0c75c61c65cec657c8a02bbfcc8fb34fb51994d"  # the hash the app and CLI renders gave
    assert hashlib.sha256((ROOT / "site/img/ai_card.png").read_bytes()).hexdigest() == "a7e6f9f161c7d03765f74d4d08f438120def39fe7d7a838246af16d127a299ce"


# ---------------------------------------------------------------- hygiene
def test_gitignore_covers_the_private_and_secret_paths():
    gi = (ROOT / ".gitignore").read_text().splitlines()
    for pat in ("out/", "data/", ".env", "aliases.json", "ratings.csv", "key.json", ".cache/"):
        assert pat in gi, pat
    ig = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "out/x", "data/x", ".env", "aliases.json", "ratings.csv", "key.json", ".cache/x"], capture_output=True, text=True)
    assert len(ig.stdout.split()) == 7


def test_the_publish_checklist_names_the_real_blocking_checks_in_order():
    t = (ROOT / "docs/PUBLISH.md").read_text(encoding="utf-8")
    names = {n for n, _ in pp.CHECKS}
    for blocker in ("precision_A.json exists", "commit_map.md exists", "history: no build artefacts", "history: no blob over 1 MB"):
        assert blocker in names and f"`{blocker}`" in t
    order = [t.index(k) for k in ("1. **Ratings", "2. **Precision", "3. **README tables", "4. **History rewrite", "5. **Update stale", "6. **Pre-publish", "7. **Private push", "8. **CI green", "9. **Public flip", "10. **Pages")]
    assert order == sorted(order)
    assert "NOT run" in t and "--private" in t and "git push -u origin main" in t
