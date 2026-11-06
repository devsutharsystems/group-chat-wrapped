from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from gcw import dataset
from gcw.dataset import CHAT_FILE, CHAT_SHA256, DEFAULT_DIR, GROUND_TRUTH_FILE, GROUND_TRUTH_SHA256, DatasetError, verify_dataset


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def freeze(tmp_path, chat=b"a\nb\n", gt=b'{"items": []}'):
    (tmp_path / CHAT_FILE).write_bytes(chat)
    (tmp_path / GROUND_TRUTH_FILE).write_bytes(gt)
    return {"chat_sha256": sha(chat), "ground_truth_sha256": sha(gt)}


def test_constants_match_files_in_synthetic_frozen():
    # fails if the constants and the committed files differ, in either direction
    assert dataset.sha256_file(DEFAULT_DIR / CHAT_FILE) == CHAT_SHA256
    assert dataset.sha256_file(DEFAULT_DIR / GROUND_TRUTH_FILE) == GROUND_TRUTH_SHA256


def test_default_verify_passes_on_frozen_dir():
    assert verify_dataset() == {CHAT_FILE: CHAT_SHA256, GROUND_TRUTH_FILE: GROUND_TRUTH_SHA256}


def test_constants_are_full_sha256():
    for c in (CHAT_SHA256, GROUND_TRUTH_SHA256):
        assert len(c) == 64 and int(c, 16) >= 0
    assert CHAT_SHA256.startswith("b6d3add4") and CHAT_SHA256.endswith("ae13b4")
    assert GROUND_TRUTH_SHA256.startswith("b3f2f5af") and GROUND_TRUTH_SHA256.endswith("aca5952")


def test_changed_frozen_chat_fails_against_constants(tmp_path):
    shutil.copytree(DEFAULT_DIR, tmp_path / "f")
    p = tmp_path / "f" / CHAT_FILE
    data = bytearray(p.read_bytes())
    data[100] ^= 1  # flip one bit: same size, same line count
    p.write_bytes(bytes(data))
    with pytest.raises(DatasetError, match="chat_synthetic.txt sha256"):
        verify_dataset(tmp_path / "f")


def test_editing_the_manifest_cannot_make_a_changed_dataset_pass(tmp_path):
    shutil.copytree(DEFAULT_DIR, tmp_path / "f")
    gt = tmp_path / "f" / GROUND_TRUTH_FILE
    gt.write_bytes(gt.read_bytes() + b" ")
    m = tmp_path / "f" / "manifest.json"
    d = json.loads(m.read_text())
    d["ground_truth_sha256"] = dataset.sha256_file(gt)  # attacker updates the manifest too
    m.write_text(json.dumps(d))
    with pytest.raises(DatasetError, match="ground_truth.json sha256"):
        verify_dataset(tmp_path / "f")


def test_tmp_files_with_overrides(tmp_path):
    h = freeze(tmp_path)
    assert verify_dataset(tmp_path, **h)
    (tmp_path / GROUND_TRUTH_FILE).write_bytes(b'{"items": [1]}')
    with pytest.raises(DatasetError, match="ground_truth.json sha256"):
        verify_dataset(tmp_path, **h)


def test_missing_file(tmp_path):
    h = freeze(tmp_path)
    (tmp_path / CHAT_FILE).unlink()
    with pytest.raises(DatasetError, match="missing"):
        verify_dataset(tmp_path, **h)


def test_manifest_counts_still_match():
    m = json.loads((DEFAULT_DIR / "manifest.json").read_text())
    assert (m["n_messages"], m["n_system"], m["lines"], m["bytes"], m["tokens"]) == (5144, 9, 5185, 571701, 241311)
