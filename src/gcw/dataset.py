"""Frozen synthetic dataset check. Every evaluation script must call verify_dataset() first.

The expected hashes are constants in this file, so editing the data AND its manifest together
cannot make a changed dataset pass.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "synthetic" / "frozen"
CHAT_FILE = "chat_synthetic.txt"
GROUND_TRUTH_FILE = "ground_truth.json"
CHAT_SHA256 = "b6d3add40ae93fe79a10f79d19a0a2b374dd0ffb5c3222feaf0425a12cae13b4"
GROUND_TRUTH_SHA256 = "b3f2f5afb24df2c271fd9b3ddc1dd57c41231655275e2fb18e4672f79aca5952"


class DatasetError(RuntimeError):
    """The chat or ground truth on disk does not match the frozen hashes."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_dataset(directory: str | Path | None = None, *, chat_sha256: str = CHAT_SHA256, ground_truth_sha256: str = GROUND_TRUTH_SHA256) -> dict[str, str]:
    """Recompute both hashes and raise DatasetError on any mismatch or missing file. The expected values
    default to the constants above; the keyword overrides exist only for tests."""
    d = Path(directory) if directory else DEFAULT_DIR
    problems = []
    for name, want in ((CHAT_FILE, chat_sha256), (GROUND_TRUTH_FILE, ground_truth_sha256)):
        f = d / name
        if not f.exists():
            problems.append(f"{name} is missing")
        elif sha256_file(f) != want:
            problems.append(f"{name} sha256 differs from the frozen constant")
    if problems:
        raise DatasetError("DATASET NOT FROZEN VERSION: " + "; ".join(problems))
    return {CHAT_FILE: chat_sha256, GROUND_TRUTH_FILE: ground_truth_sha256}


def is_frozen_chat(path: str | Path) -> bool:
    """True only for the frozen synthetic chat: the file's SHA-256 equals the hard-coded constant AND the frozen dataset verifies."""
    p = Path(path)
    try:
        if not p.is_file() or sha256_file(p) != CHAT_SHA256:
            return False
        verify_dataset()
    except (OSError, DatasetError):
        return False
    return True
