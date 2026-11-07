"""Freeze the generated large chat into synthetic/frozen_large/ (chat, ground truth, manifest) and print the SHA-256 constants for gcw/dataset.py.
  .venv/bin/python scripts/freeze_large.py [--src data/synthetic_large] [--config synthetic/config_large.json]
Refuses to overwrite an existing frozen_large chat."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gcw.dataset import LARGE_CHAT_FILE, LARGE_DIR, LARGE_GROUND_TRUTH_FILE, sha256_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/synthetic_large")
    ap.add_argument("--config", default="synthetic/config_large.json")
    a = ap.parse_args(argv)
    src = ROOT / a.src
    if (LARGE_DIR / LARGE_CHAT_FILE).exists():
        print("frozen_large already exists: refusing to overwrite", file=sys.stderr)
        return 2
    LARGE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(src / "chat_full.txt", LARGE_DIR / LARGE_CHAT_FILE)
    shutil.copy(src / "ground_truth.json", LARGE_DIR / LARGE_GROUND_TRUTH_FILE)
    gen = json.loads((src / "manifest_full.json").read_text())
    chat = LARGE_DIR / LARGE_CHAT_FILE
    man = {**gen, "chat_file": LARGE_CHAT_FILE, "chat_sha256": sha256_file(chat), "chat_bytes": chat.stat().st_size, "ground_truth_sha256": sha256_file(LARGE_DIR / LARGE_GROUND_TRUTH_FILE),
           "config": a.config, "config_sha256": hashlib.sha256((ROOT / a.config).read_bytes()).hexdigest(),
           "note": "Synthetic and fictional (claude-haiku-5-5 filler, planted ground truth). Separate from synthetic/frozen/. Checked by gcw.dataset.verify_large_dataset()."}
    (LARGE_DIR / "manifest.json").write_text(json.dumps(man, indent=1) + "\n")
    print(f'LARGE_CHAT_SHA256 = "{man["chat_sha256"]}"\nLARGE_GROUND_TRUTH_SHA256 = "{man["ground_truth_sha256"]}"\nbytes {man["chat_bytes"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
