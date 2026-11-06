"""Frozen synthetic dataset check. Every evaluation script must call verify_dataset() first."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "data" / "synthetic"


class DatasetError(RuntimeError):
    """The chat or ground truth on disk does not match the frozen manifest."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_dataset(directory: str | Path | None = None) -> dict:
    """Recompute the hashes (and size/line count) and raise DatasetError on any mismatch. Returns the manifest."""
    d = Path(directory) if directory else DEFAULT_DIR
    try:
        m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise DatasetError(f"cannot read frozen manifest in {d}: {e}") from e
    problems = []
    for key, name in (("chat_sha256", m["chat_file"]), ("ground_truth_sha256", m["ground_truth_file"])):
        f = d / name
        if not f.exists():
            problems.append(f"{name} is missing")
        elif sha256_file(f) != m[key]:
            problems.append(f"{name} sha256 differs from the frozen manifest")
    chat = d / m["chat_file"]
    if chat.exists():
        if chat.stat().st_size != m["bytes"]:
            problems.append(f"{m['chat_file']} size {chat.stat().st_size} != {m['bytes']}")
        if chat.read_bytes().count(b"\n") != m["lines"]:
            problems.append(f"{m['chat_file']} line count differs from {m['lines']}")
    if problems:
        raise DatasetError("DATASET NOT FROZEN VERSION: " + "; ".join(problems))
    return m
