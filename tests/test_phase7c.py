"""Phase 7c: untracked data/, mentions, the history rewrite script (on tiny temporary repositories), and the hash-reference updater. No network, no browser."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

import prepublish_check as pp
import update_hash_refs as uh
from gcw import privacy
from test_privacy import ROOT

SCRIPT = ROOT / "scripts" / "rewrite_history.sh"


# ---------------------------------------------------------------- untracked data/, mentions, licence
def tracked() -> list[str]:
    return [x for x in subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True).stdout.split("\0") if x]


def test_top_level_data_is_untracked_and_the_packaged_keyword_file_is_not():
    files = tracked()
    assert [f for f in files if f.startswith("data/")] == []
    assert "src/gcw/data/sensitive_keywords.json" in files
    assert privacy.load_keywords()  # the packaged file still loads
    assert "data/" in (ROOT / ".gitignore").read_text().splitlines()


def test_the_named_mentions_are_gone_and_the_licence_text_is_otherwise_exact():
    hits = [h for h in pp.mentions(ROOT)]
    assert not [h for h in hits if "Prateek" in h or "devsuthar" in h.lower()], hits
    assert "the project brief" in (ROOT / "CLAUDE.md").read_text() and "the project brief" in (ROOT / "docs/PRD.md").read_text()
    lines = (ROOT / "LICENSE").read_text().split("\n")
    assert lines[0] == "MIT License" and lines[2] == "Copyright (c) 2026 Dev Suthar"
    assert hashlib.sha256("\n".join(lines[3:]).encode()).hexdigest() == "21a76c19ae398e37fc00bca26e6850feee362e8188f8507ad44a53475ee62c33"  # the MIT text is unchanged
    assert pp.license_mit(ROOT)[0]


# ---------------------------------------------------------------- rewrite_history.sh on temporary repositories
def sh(cwd: Path, *cmd: str, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    import os

    r = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    if check and r.returncode:
        raise AssertionError(f"{cmd}: {r.stdout}{r.stderr}")
    return r


def git(cwd: Path, *a: str) -> str:
    return sh(cwd, "git", *a).stdout.strip()


def make(tmp: Path) -> Path:
    git(tmp, "init", "-q", "-b", "main")
    git(tmp, "config", "user.name", "Old Name")
    git(tmp, "config", "user.email", "old@example.com")

    def commit(msg: str, files: dict[str, str]):
        for n, b in files.items():
            p = tmp / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(b)
        git(tmp, "add", "-A", "-f")
        git(tmp, "commit", "-q", "-m", msg)

    commit("first", {"README.md": "a", "build/lib/x.py": "x", "src/gcw/data/k.json": "{}", "docs/data/keep.txt": "nested data dir survives"})
    commit("predictions committed before the live run", {"data/a.txt": "a"})  # a commit that only touches data/ becomes empty but is kept
    commit("third", {"README.md": "b", "data/b.txt": "b"})
    return tmp


def run_script(repo: Path, env: dict | None = None, check: bool = True):
    return sh(repo, "bash", str(SCRIPT), env=env, check=check)


def test_the_script_drops_top_level_build_and_data_keeps_commit_count_and_writes_the_map(tmp_path):
    r = make(tmp_path)
    old = git(r, "rev-list", "--reverse", "main").split()
    out = run_script(r).stdout
    new = git(r, "rev-list", "--reverse", "main").split()
    assert len(old) == len(new) == 3 and "3 commits (was 3)" in out and "Nothing was pushed" in out
    tree = git(r, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert "src/gcw/data/k.json" in tree and "docs/data/keep.txt" in tree and not [t for t in tree if t.startswith(("build/", "data/"))]
    assert git(r, "log", "--all", "--name-only", "--pretty=format:").count("build/") == 0
    assert git(r, "for-each-ref", "--format=%(refname)") == "refs/heads/main" and git(r, "tag") == ""
    for o in old:  # the old objects are gone after gc
        assert sh(r, "git", "cat-file", "-e", o, check=False).returncode != 0
    rows = [ln for ln in (r / "docs/results/commit_map.md").read_text().splitlines() if ln.startswith("| ") and ln[2:42].strip("0123456789abcdef") == ""]
    assert len(rows) == 3
    for row, o, n in zip(rows, old, new):
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[0] == o and cells[1] == n and cells[0] != cells[1]
    assert "predictions committed before the live run" in rows[1] and rows[0].split("|")[4].strip() == "first"
    assert git(r, "log", "-1", "--format=%an <%ae>") == "Old Name <old@example.com>"  # the author is untouched by default


def test_the_optional_author_rewrite_needs_both_variables(tmp_path):
    r = make(tmp_path)
    one = run_script(r, env={"NEW_NAME": "Only Name"}, check=False)
    assert one.returncode == 1 and "both NEW_NAME and NEW_EMAIL" in one.stderr and git(r, "tag") == ""  # refused before any change
    run_script(r, env={"NEW_NAME": "New Person", "NEW_EMAIL": "new@example.com"})
    assert set(git(r, "log", "--all", "--format=%an <%ae>|%cn <%ce>").splitlines()) == {"New Person <new@example.com>|New Person <new@example.com>"}


@pytest.mark.parametrize("setup, msg", [
    (lambda r: git(r, "remote", "add", "origin", "https://example.invalid/x.git"), "a remote exists"),
    (lambda r: (r / "dirty.txt").write_text("x"), "not clean"),
    (lambda r: git(r, "checkout", "-q", "-b", "other"), "HEAD is not on main"),
    (lambda r: git(r, "branch", "extra"), "refs other than main exist"),
    (lambda r: (git(r, "rm", "-q", "-r", "src"), git(r, "commit", "-q", "-m", "drop packaged data")), "src/gcw/data/ is not tracked"),
])
def test_the_script_refuses_and_changes_nothing(tmp_path, setup, msg):
    r = make(tmp_path)
    setup(r)
    head = git(r, "rev-parse", "HEAD")
    refs = git(r, "for-each-ref")
    res = run_script(r, check=False)
    assert res.returncode == 1 and msg in res.stderr
    assert git(r, "rev-parse", "HEAD") == head and git(r, "for-each-ref") == refs and git(r, "tag") == ""


def test_the_script_never_pushes_or_adds_a_remote():
    text = SCRIPT.read_text()
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert "git push" not in code and "remote add" not in code and "set -euo pipefail" in code
    assert all("--prune-empty" not in ln for ln in code.splitlines() if "filter-branch" in ln)
    assert "-- build data" in code and "src/gcw/data" in code and "refs/original" in code and "commit_map.md" in code


# ---------------------------------------------------------------- update_hash_refs.py
OLD1, NEW1 = "a" * 7 + "1" * 33, "b" * 7 + "2" * 33
OLD2, NEW2 = "c0ffee0" + "3" * 33, "d1ce5e5" + "4" * 33


def mk_root(tmp: Path) -> Path:
    (tmp / "docs" / "results").mkdir(parents=True)
    (tmp / "README.md").write_text(f"see commit {OLD1[:7]} and also {OLD2[:7]}.\nunrelated 1234567 and deadbee stay.\n")
    (tmp / "docs" / "a.md").write_text(f"predictions in `{OLD1[:7]}`; another {OLD1[:7]}x is not a hash\n")
    (tmp / "docs" / "results" / "commit_map.md").write_text(f"| old hash | new hash | date | subject |\n|---|---|---|---|\n| {OLD1} | {NEW1} | 2026-11-01 | one |\n| {OLD2} | {NEW2} | 2026-11-02 | two |\n")
    return tmp


def test_the_updater_lists_then_replaces_only_mapped_hashes(tmp_path, capsys):
    root = mk_root(tmp_path)
    before = (root / "docs/results/commit_map.md").read_text()
    assert uh.main(["--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert f"README.md:1  {OLD1[:7]} -> {NEW1[:7]}" in out and f"{OLD2[:7]} -> {NEW2[:7]}" in out and "docs/a.md:1" in out and "3 reference(s) would change (dry run" in out
    assert OLD1[:7] in (root / "README.md").read_text()  # a dry run changes nothing
    assert uh.main(["--root", str(root), "--apply"]) == 0
    assert "replaced 3 reference(s)" in capsys.readouterr().out
    assert (root / "README.md").read_text() == f"see commit {NEW1[:7]} and also {NEW2[:7]}.\nunrelated 1234567 and deadbee stay.\n"
    assert (root / "docs/a.md").read_text() == f"predictions in `{NEW1[:7]}`; another {OLD1[:7]}x is not a hash\n"
    assert (root / "docs/results/commit_map.md").read_text() == before  # the map itself is never rewritten


def test_the_updater_needs_the_map_and_rejects_prefix_collisions(tmp_path, capsys):
    assert uh.main(["--root", str(tmp_path)]) == 2 and "not found" in capsys.readouterr().err
    m = tmp_path / "m.md"
    m.write_text(f"| {OLD1} | {NEW1} | d | s |\n| {OLD1[:7] + 'f' * 33} | {NEW2} | d | s |\n")
    with pytest.raises(ValueError, match="share the 7-character prefix"):
        uh.load_map(m)
