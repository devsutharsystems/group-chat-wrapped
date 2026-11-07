"""Pre-publish gate: one line per check (PASS or FAIL with the reason); exit 1 when any check fails. Read-only: it changes nothing.
  .venv/bin/python scripts/prepublish_check.py [--root DIR]
Each check is a function (root) -> (ok, message), so tests can run it on temporary repositories."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import build_readme_tables as btab  # noqa: E402

MAX_BYTES = 3 * 1024 * 1024
BIG_OK_PREFIX = "synthetic/frozen_large/"
MARKER = re.compile(r"\b(pending|TODO|TBD)\b", re.I)
SECRET_NAMES = {".env", "ratings.csv", "key.json"}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, errors="replace")


def _tracked(root: Path) -> list[str]:
    r = _git(root, "ls-files", "-z")
    return [x for x in r.stdout.split("\0") if x]


def readme_blocks_fresh(root: Path) -> tuple[bool, str]:
    try:
        s = btab.stale(root)
    except (OSError, ValueError, KeyError) as e:
        return False, f"cannot render the blocks: {e}"
    return (not s, "all generated blocks match the results files" if not s else "stale blocks: " + ", ".join(s))


def no_markers(root: Path) -> tuple[bool, str]:
    files = [root / "README.md", *sorted(p for p in (root / "docs" / "results").rglob("*") if p.is_file())]
    hits = []
    for f in files:
        if not f.is_file() or f.suffix.lower() in {".png", ".jpg", ".gif"}:
            continue
        text = f.read_text(encoding="utf-8", errors="replace").replace(btab.PRECISION_LITERAL, "")  # the one literal that says pending by design
        for n, line in enumerate(text.splitlines(), 1):
            m = MARKER.search(line)
            if m:
                hits.append(f"{f.relative_to(root)}:{n} ({m.group(1)})")
    return (not hits, "no pending, TODO or TBD markers" if not hits else "markers at " + ", ".join(hits[:6]))


def precision_exists(root: Path) -> tuple[bool, str]:
    ok = (root / "docs" / "results" / "precision_A.json").is_file()
    return ok, "docs/results/precision_A.json exists" if ok else "docs/results/precision_A.json is missing (hand ratings not scored)"


def commit_map_exists(root: Path) -> tuple[bool, str]:
    ok = (root / "docs" / "results" / "commit_map.md").is_file()
    return ok, "docs/results/commit_map.md exists" if ok else "docs/results/commit_map.md is missing (history not rewritten yet)"


def scan_clean(root: Path) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(HERE / "scan_repo.py"), str(root)], capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [r.stderr.strip()])[-1]
    return r.returncode == 0, f"scan_repo: {last}"


def _count_history(root: Path, args: list[str], pattern: str) -> int:
    p = subprocess.Popen(["git", "-C", str(root), *args], stdout=subprocess.PIPE, text=True, errors="replace")
    rx = re.compile(pattern)
    n = sum(1 for line in p.stdout if rx.search(line))
    p.wait()
    return n


def users_history(root: Path) -> tuple[bool, str]:
    n = _count_history(root, ["log", "-p", "--all"], r"/U[s]ers/")
    return n == 0, f"lines with a home-directory path in history: {n}"


def build_history(root: Path) -> tuple[bool, str]:
    n = _count_history(root, ["log", "--all", "--name-only", "--pretty=format:"], r"^(build/|.*\.egg-info|\.cache/)")
    return n == 0, f"history entries under build/, *.egg-info or .cache/: {n}"


def git_clean(root: Path) -> tuple[bool, str]:
    out = _git(root, "status", "--porcelain").stdout.strip()
    return not out, "working tree clean" if not out else f"{len(out.splitlines())} uncommitted change(s)"


def big_files(root: Path) -> tuple[bool, str]:
    big = [f for f in _tracked(root) if (root / f).is_file() and (root / f).stat().st_size > MAX_BYTES and not f.startswith(BIG_OK_PREFIX)]
    return not big, "no tracked file over 3 MB outside synthetic/frozen_large" if not big else "over 3 MB: " + ", ".join(big[:5])


def license_mit(root: Path) -> tuple[bool, str]:
    p = root / "LICENSE"
    t = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    ok = t.lstrip().startswith("MIT License") and "Permission is hereby granted" in t
    return ok, "LICENSE is MIT" if ok else "LICENSE is missing or not the MIT licence"


def no_secret_files(root: Path) -> tuple[bool, str]:
    bad = [f for f in _tracked(root) if Path(f).name in SECRET_NAMES]
    return not bad, "no .env, ratings.csv or key.json tracked" if not bad else "tracked: " + ", ".join(bad)


def images_exist(root: Path) -> tuple[bool, str]:
    readme = (root / "README.md").read_text(encoding="utf-8") if (root / "README.md").is_file() else ""
    refs = sorted(set(re.findall(r"\((docs/img/[^)\s]+)\)", readme)))
    tracked = set(_tracked(root))
    missing = [r for r in refs if not (root / r).is_file() or r not in tracked]
    ok = bool(refs) and not missing
    return ok, f"{len(refs)} README image(s) exist and are tracked" if ok else ("README references no docs/img image" if not refs else "missing or untracked: " + ", ".join(missing))


CHECKS = [("readme blocks fresh", readme_blocks_fresh), ("no pending/TODO/TBD markers", no_markers), ("precision_A.json exists", precision_exists), ("commit_map.md exists", commit_map_exists),
          ("scan_repo clean", scan_clean), ("history: no home-directory paths", users_history), ("history: no build artefacts", build_history), ("git status clean", git_clean),
          ("no tracked file over 3 MB", big_files), ("LICENSE is MIT", license_mit), ("no secret or rating files tracked", no_secret_files), ("README images exist", images_exist)]


def run(root: Path, out=print) -> int:
    failed = 0
    for name, fn in CHECKS:
        try:
            ok, msg = fn(root)
        except Exception as e:  # noqa: BLE001 - a crashing check is a failing check
            ok, msg = False, f"check crashed: {type(e).__name__}: {e}"
        out(f"{'PASS' if ok else 'FAIL'}  {name}: {msg}")
        failed += not ok
    out(f"{len(CHECKS) - failed} of {len(CHECKS)} checks passed")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    return run(Path(ap.parse_args(argv).root).resolve())


if __name__ == "__main__":
    sys.exit(main())
