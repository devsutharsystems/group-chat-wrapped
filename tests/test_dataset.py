from __future__ import annotations

import hashlib
import json

import pytest

from gcw.dataset import DatasetError, verify_dataset


def freeze(tmp_path, chat=b"a\nb\n", gt=b'{"items": []}'):
    (tmp_path / "chat.txt").write_bytes(chat)
    (tmp_path / "gt.json").write_bytes(gt)
    m = {"chat_file": "chat.txt", "ground_truth_file": "gt.json", "chat_sha256": hashlib.sha256(chat).hexdigest(),
         "ground_truth_sha256": hashlib.sha256(gt).hexdigest(), "bytes": len(chat), "lines": chat.count(b"\n")}
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    return m


def test_ok(tmp_path):
    freeze(tmp_path)
    assert verify_dataset(tmp_path)["lines"] == 2


def test_chat_changed(tmp_path):
    freeze(tmp_path)
    (tmp_path / "chat.txt").write_bytes(b"a\nB\n")  # same size and lines, different content
    with pytest.raises(DatasetError, match="chat.txt sha256"):
        verify_dataset(tmp_path)


def test_ground_truth_changed(tmp_path):
    freeze(tmp_path)
    (tmp_path / "gt.json").write_bytes(b'{"items": [1]}')
    with pytest.raises(DatasetError, match="gt.json sha256"):
        verify_dataset(tmp_path)


def test_missing_file_and_manifest(tmp_path):
    with pytest.raises(DatasetError, match="manifest"):
        verify_dataset(tmp_path)
    freeze(tmp_path)
    (tmp_path / "gt.json").unlink()
    with pytest.raises(DatasetError, match="missing"):
        verify_dataset(tmp_path)


def test_committed_frozen_dataset_verifies():
    m = verify_dataset()  # default: synthetic/frozen/
    assert (m["n_messages"], m["n_system"], m["lines"], m["bytes"], m["tokens"]) == (5144, 9, 5185, 571701, 241311)
