"""Phase 7a: generated README blocks, forbidden README claims, and the pre-publish checks (on temporary git repositories). No network, no browser."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import build_readme_tables as btab
import prepublish_check as pp
from gcw import analyze, chunked, dataset, evaluate
from test_privacy import ROOT

README = (ROOT / "README.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- generated blocks
def test_the_readme_blocks_are_fresh_relative_to_the_results_files():
    assert btab.stale(ROOT) == [], "run: .venv/bin/python scripts/build_readme_tables.py"


def test_a_changed_block_is_reported_stale_and_fill_replaces_only_the_blocks(tmp_path, monkeypatch):
    text = "intro\n<!-- BEGIN:eval_table -->\nold\n<!-- END:eval_table -->\nouter\n"
    new = btab.fill(text, {"eval_table": "new body"})
    assert new == "intro\n<!-- BEGIN:eval_table -->\nnew body\n<!-- END:eval_table -->\nouter\n"
    with pytest.raises(ValueError, match="no block"):
        btab.fill("nothing", {"eval_table": "x"})
    (tmp_path / "README.md").write_text(text)
    monkeypatch.setattr(btab, "render_blocks", lambda root: {"eval_table": "old", "cost_block": "x"})
    assert btab.stale(tmp_path) == ["cost_block"]  # eval_table matches; cost_block is missing from the README
    monkeypatch.setattr(btab, "render_blocks", lambda root: {"eval_table": "different"})
    assert btab.stale(tmp_path) == ["eval_table"]


def test_the_precision_block_is_the_literal_line_until_the_ratings_exist(tmp_path):
    (tmp_path / "docs" / "results").mkdir(parents=True)
    assert btab.precision_block(tmp_path) == "Precision: not yet measured (hand-rating pending)"
    t = evaluate._tally(["true", "true", "false", "partly"])
    (tmp_path / "docs" / "results" / "precision_A.json").write_text(json.dumps({"note": "n-note", "overall": t, "by_type": {"running_jokes": t}}))
    out = btab.precision_block(tmp_path)
    assert "2 of 4" in out and "running_jokes" in out and "hand-rating pending" not in out


def test_the_table_rows_and_columns_come_from_the_results_files():
    rows = [ln for ln in re.search(r"<!-- BEGIN:eval_table -->\n(.*?)\n<!-- END:eval_table -->", README, re.S).group(1).splitlines()[2:]]
    assert len(rows) == 5 and all(re.search(r"\| [13] \|", r) for r in rows)  # n appears in every row
    assert rows[0].startswith("| dense 270K tokens, single-pass | 3 |") and "| 889K" not in rows[0]
    j = json.loads((ROOT / "docs/results/eval_large_A.json").read_text())
    assert f"{j['summary']['cost_usd']['mean']:.4f}" in rows[3] and f"{j['runs'][0]['input_tokens']:,}" in rows[3]


def test_the_frozen_identifiers_in_the_readme_match_the_code_and_the_files():
    assert analyze.PROMPT_VERSION in README and chunked.REDUCE_PROMPT_VERSION in README
    for f in ("synthetic/frozen/chat_synthetic.txt", "synthetic/frozen/ground_truth.json", "synthetic/frozen_large/chat_synthetic_large.txt", "synthetic/frozen_large/ground_truth.json"):
        assert dataset.sha256_file(ROOT / f) in README
    assert f"{chunked.SINGLE_PASS_LIMIT:,}" in README


# ---------------------------------------------------------------- forbidden claims
def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def claim_problems(text: str, precision_exists: bool) -> list[str]:
    out = []
    for s in sentences(text):
        low = s.lower()
        if re.search(r"reads?\s+(1m|a million|one million|1,000,000)\s+tokens", low) and "not demonstrated" not in low:
            out.append(f"unqualified million-token claim: {s[:80]}")
        if "injection" in low and "robust" in low and not re.search(r"\bnot\b|n't|does not claim", low):
            out.append(f"robust claim about injection: {s[:80]}")
        if re.search(r"\bprivate\b", low) and "anthropic" not in low:
            out.append(f"private without the Anthropic statement: {s[:80]}")
        if re.search(r"lost in the middle|position effect|position-dependent|recall (drops|falls|declines|is lower|is higher) (with|towards|at|in) .*(position|middle|end|start|beginning)|(start|beginning|middle|end) of the chat (is|are) (better|worse)", low):
            out.append(f"position-dependent conclusion: {s[:80]}")
        if not precision_exists and "precision" in low.replace("precision_a", "") and re.search(r"\d", low.replace("precision_a", "").replace(btab.PRECISION_LITERAL.lower(), "")):
            out.append(f"a precision number without ratings: {s[:80]}")
    return out


def test_the_readme_makes_none_of_the_forbidden_claims():
    assert claim_problems(README, (ROOT / "docs/results/precision_A.json").is_file()) == []


@pytest.mark.parametrize("bad", [
    "Haiku reads 1M tokens in one go.", "The model reads a million tokens easily.", "The injection defence is robust.", "Your chats stay private.",
    "Recall drops with position in the chat.", "This is the lost in the middle effect.", "Precision is 91% on the synthetic chat.",
])
def test_each_forbidden_claim_is_caught(bad):
    assert claim_problems(bad, precision_exists=False) != []


@pytest.mark.parametrize("ok", [
    "Haiku accepts 1M tokens, but quality there was not demonstrated; the model reads a million tokens only in the sense that the request is accepted, which is not demonstrated quality.",
    "The README does not claim the injection defence is robust.", "Private data is sent to Anthropic in AI mode.", "Precision: not yet measured (hand-rating pending)",
])
def test_the_qualified_forms_are_allowed(ok):
    assert claim_problems(ok, precision_exists=False) == []


def test_the_privacy_section_says_pseudonymised_text_goes_to_anthropic():
    sec = README.split("## Privacy", 1)[1].split("\n## ", 1)[0]
    assert re.search(r"pseudonymised[^.]*sent to Anthropic", sec) and "stats-only" in sec.lower()


def test_the_consolidated_limits_list_keeps_every_recorded_limit():
    lim = README.split("## Limits", 1)[1].split("\n## ", 1)[0].lower()
    for k in ["synthetic", "n = 1", "of 10 planted items", "not demonstrated", "300,000", "provisional", "dev items", "jl does not test long-range", "disadvantages moments", "precision is reported only",
              "robust", "minute resolution", "english-only", "aliases file", "ios", "24-hour", "reconciled", "macos", "colour emoji", "one config"]:
        assert k in lim, k
    assert "commit_map.md" in README and "history" in README.lower()


# ---------------------------------------------------------------- prepublish checks on temporary repositories
def git(root: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@example.com", "-c", "user.name=t", *a], check=True, capture_output=True)


def repo(tmp_path: Path, files: dict[str, str | bytes] | None = None) -> Path:
    git(tmp_path, "init", "-q")
    for name, body in (files or {"a.txt": "x"}).items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body if isinstance(body, bytes) else body.encode())
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "c")
    return tmp_path


MIT = "MIT License\n\nCopyright (c) 2026 x\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\n"


def test_markers_are_found_except_the_precision_literal(tmp_path):
    (tmp_path / "docs" / "results").mkdir(parents=True)
    (tmp_path / "README.md").write_text(f"ok\n{btab.PRECISION_LITERAL}\n")
    assert pp.no_markers(tmp_path)[0]
    (tmp_path / "README.md").write_text("ok\nTODO: fix\n")
    ok, msg = pp.no_markers(tmp_path)
    assert not ok and "README.md:2" in msg
    (tmp_path / "README.md").write_text("ok\n")
    (tmp_path / "docs" / "results" / "x.md").write_text("status: TBD\nanother pending item\n")
    ok, msg = pp.no_markers(tmp_path)
    assert not ok and "x.md:1" in msg and "x.md:2" in msg


def test_precision_and_commit_map_checks_look_for_the_files(tmp_path):
    (tmp_path / "docs" / "results").mkdir(parents=True)
    assert not pp.precision_exists(tmp_path)[0] and not pp.commit_map_exists(tmp_path)[0]
    (tmp_path / "docs" / "results" / "precision_A.json").write_text("{}")
    (tmp_path / "docs" / "results" / "commit_map.md").write_text("x")
    assert pp.precision_exists(tmp_path)[0] and pp.commit_map_exists(tmp_path)[0]


def test_scan_check_fails_on_a_chat_export_line_and_passes_on_clean_files(tmp_path):
    clean, dirty = tmp_path / "a", tmp_path / "b"
    clean.mkdir()
    dirty.mkdir()
    repo(clean, {"a.txt": "hello"})
    assert pp.scan_clean(clean)[0]
    repo(dirty, {"chat.txt": "11/5/26, 9:19 PM - Zed Q: hello there\n"})
    assert not pp.scan_clean(dirty)[0]


def test_history_checks_remember_deleted_files(tmp_path):
    path = "/U" + "sers/someone/x"
    r = repo(tmp_path, {"a.txt": f"path {path}\n", "build/lib/m.py": "x"})
    assert not pp.users_history(r)[0] and not pp.build_history(r)[0]
    git(r, "rm", "-q", "-r", "a.txt", "build")
    git(r, "commit", "-q", "-m", "remove")
    assert not pp.users_history(r)[0] and not pp.build_history(r)[0]  # still in history
    clean = tmp_path / "c"
    clean.mkdir()
    repo(clean)
    assert pp.users_history(clean)[0] and pp.build_history(clean)[0]
    assert "26" not in pp.build_history(clean)[1] and ": 0" in pp.build_history(clean)[1]


def test_git_clean_big_files_license_and_secret_checks(tmp_path):
    r = repo(tmp_path, {"LICENSE": MIT, "a.txt": "x"})
    assert pp.git_clean(r)[0] and pp.license_mit(r)[0] and pp.no_secret_files(r)[0] and pp.big_files(r)[0]
    (r / "new.txt").write_text("u")
    assert not pp.git_clean(r)[0]
    (r / "LICENSE").write_text("Apache License\n")
    assert not pp.license_mit(r)[0]
    big = b"0" * (3 * 1024 * 1024 + 1)
    r2 = tmp_path / "r2"
    r2.mkdir()
    repo(r2, {"big.bin": big})
    assert not pp.big_files(r2)[0] and "big.bin" in pp.big_files(r2)[1]
    r3 = tmp_path / "r3"
    r3.mkdir()
    repo(r3, {"synthetic/frozen_large/big.txt": big})
    assert pp.big_files(r3)[0]
    r4 = tmp_path / "r4"
    r4.mkdir()
    repo(r4, {".env": "k", "out/rating/ratings.csv": "x", "q/key.json": "{}"})
    ok, msg = pp.no_secret_files(r4)
    assert not ok and ".env" in msg and "ratings.csv" in msg and "key.json" in msg


def test_image_check_needs_tracked_files_referenced_by_the_readme(tmp_path):
    r = repo(tmp_path, {"README.md": "![a](docs/img/a.png)\n", "docs/img/a.png": b"png"})
    assert pp.images_exist(r)[0]
    (r / "README.md").write_text("![a](docs/img/a.png) ![b](docs/img/b.png)\n")
    ok, msg = pp.images_exist(r)
    assert not ok and "b.png" in msg
    r2 = tmp_path / "r2"
    r2.mkdir()
    repo(r2, {"README.md": "no images\n"})
    assert not pp.images_exist(r2)[0]


def test_run_prints_one_line_per_check_and_exits_nonzero_on_any_failure(tmp_path, monkeypatch, capsys):
    lines: list[str] = []
    monkeypatch.setattr(pp, "CHECKS", [("good", lambda r: (True, "fine")), ("bad", lambda r: (False, "broken")), ("crash", lambda r: 1 / 0)])
    assert pp.run(tmp_path, out=lines.append) == 1
    assert lines[:3] == ["PASS  good: fine", "FAIL  bad: broken", lines[2]] and lines[2].startswith("FAIL  crash: check crashed: ZeroDivisionError") and lines[-1] == "1 of 3 checks passed"
    monkeypatch.setattr(pp, "CHECKS", [("good", lambda r: (True, "fine"))])
    assert pp.run(tmp_path, out=lines.append) == 0


def test_the_real_check_list_covers_the_required_checks():
    assert len(pp.CHECKS) == 13 and {n for n, _ in pp.CHECKS} >= {"readme blocks fresh", "precision_A.json exists", "commit_map.md exists", "scan_repo clean", "git status clean", "LICENSE is MIT"}
