"""Replace pre-rewrite commit hashes in README.md and docs/ with the new ones, from docs/results/commit_map.md (run once, after scripts/rewrite_history.sh).

  .venv/bin/python scripts/update_hash_refs.py                 # dry run: list the references that would change
  .venv/bin/python scripts/update_hash_refs.py --apply         # rewrite them
Only 7-hex strings that equal the first 7 characters of an OLD hash in the map are touched; the map itself is never rewritten.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROW = re.compile(r"^\|\s*([0-9a-f]{40})\s*\|\s*([0-9a-f]{40})\s*\|", re.M)
SHORT = re.compile(r"(?<![0-9a-zA-Z])[0-9a-f]{7}(?![0-9a-zA-Z])")


def load_map(path: Path) -> dict[str, str]:
    """{old 7-hex: new 7-hex}. Raises ValueError when two old hashes share a 7-character prefix."""
    out: dict[str, str] = {}
    for old, new in ROW.findall(path.read_text(encoding="utf-8")):
        if old[:7] in out and out[old[:7]] != new[:7]:
            raise ValueError(f"two commits share the 7-character prefix {old[:7]}")
        out[old[:7]] = new[:7]
    return out


def targets(root: Path, map_path: Path) -> list[Path]:
    files = [root / "README.md"] if (root / "README.md").is_file() else []
    files += sorted(p for p in (root / "docs").rglob("*") if p.is_file() and p.suffix in {".md", ".json"} and p.resolve() != map_path.resolve())
    return files


def find(root: Path, mapping: dict[str, str], map_path: Path) -> list[tuple[Path, int, str, str]]:
    hits = []
    for f in targets(root, map_path):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in SHORT.finditer(line):
                if m.group() in mapping:
                    hits.append((f, n, m.group(), mapping[m.group()]))
    return hits


def apply(root: Path, mapping: dict[str, str], map_path: Path) -> int:
    n = 0
    for f in targets(root, map_path):
        text = f.read_text(encoding="utf-8")
        new = SHORT.sub(lambda m: mapping.get(m.group(), m.group()), text)
        if new != text:
            n += sum(1 for m in SHORT.finditer(text) if m.group() in mapping)
            f.write_text(new, encoding="utf-8")
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--map", default=None)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root)
    map_path = Path(a.map) if a.map else root / "docs" / "results" / "commit_map.md"
    if not map_path.is_file():
        print(f"update_hash_refs: {map_path} not found (run scripts/rewrite_history.sh first)", file=sys.stderr)
        return 2
    mapping = load_map(map_path)
    hits = find(root, mapping, map_path)
    for f, n, old, new in hits:
        print(f"{f.relative_to(root)}:{n}  {old} -> {new}")
    if a.apply:
        print(f"replaced {apply(root, mapping, map_path)} reference(s)")
    else:
        print(f"{len(hits)} reference(s) would change (dry run; add --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
