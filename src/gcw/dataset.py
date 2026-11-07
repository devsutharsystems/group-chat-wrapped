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


# ------------------------------------------------------------------ the large frozen dataset (Phase 5a): its own directory, hashes and verify function
LARGE_DIR = ROOT / "synthetic" / "frozen_large"
LARGE_CHAT_FILE = "chat_synthetic_large.txt"
LARGE_GROUND_TRUTH_FILE = "ground_truth.json"
# Filled in when the dataset is frozen (scripts/freeze_large.py prints them). None = not frozen yet: every check fails closed.
LARGE_CHAT_SHA256: str | None = "0a9f76f0117608ecd4fd3cdc503202e55a15dbe8a2427fc1d1d09d0b7c870b6e"
LARGE_GROUND_TRUTH_SHA256: str | None = "b442a82bc44249fe5e49dfeb5021f0539179072f188912946d653941be47f562"


def verify_large_dataset(directory: str | Path | None = None, *, chat_sha256: str | None = None, ground_truth_sha256: str | None = None) -> dict[str, str]:
    """Like verify_dataset, for synthetic/frozen_large/. The keyword overrides exist only for tests. Fails if the constants are not set yet."""
    chat_sha256 = chat_sha256 or LARGE_CHAT_SHA256
    ground_truth_sha256 = ground_truth_sha256 or LARGE_GROUND_TRUTH_SHA256
    if not chat_sha256 or not ground_truth_sha256:
        raise DatasetError("LARGE DATASET NOT FROZEN: the hash constants in gcw/dataset.py are not set")
    d = Path(directory) if directory else LARGE_DIR
    problems = []
    for name, want in ((LARGE_CHAT_FILE, chat_sha256), (LARGE_GROUND_TRUTH_FILE, ground_truth_sha256)):
        f = d / name
        if not f.exists():
            problems.append(f"{name} is missing")
        elif sha256_file(f) != want:
            problems.append(f"{name} sha256 differs from the frozen constant")
    if problems:
        raise DatasetError("LARGE DATASET NOT FROZEN VERSION: " + "; ".join(problems))
    return {LARGE_CHAT_FILE: chat_sha256, LARGE_GROUND_TRUTH_FILE: ground_truth_sha256}


def is_frozen_large_chat(path: str | Path) -> bool:
    p = Path(path)
    try:
        if not LARGE_CHAT_SHA256 or not p.is_file() or sha256_file(p) != LARGE_CHAT_SHA256:
            return False
        verify_large_dataset()
    except (OSError, DatasetError):
        return False
    return True


def which_frozen(path: str | Path) -> str | None:
    """'original', 'large' or None: which frozen synthetic dataset (hashes and files verified) the chat file is."""
    if is_frozen_chat(path):
        return "original"
    if is_frozen_large_chat(path):
        return "large"
    return None
