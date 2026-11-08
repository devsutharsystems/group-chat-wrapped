"""LOCAL helper for you to run on a real WhatsApp zip: prints ONLY the message count, the date range and the number of ignored zip entries. It prints no message and no name, and it
writes nothing. It uses the app's own loader (gcw.appcore.read_zip_text), so the result is what the app would load.
  PYTHONPATH=src .venv/bin/python scripts/zip_counts.py "path/to/WhatsApp Chat.zip" """
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gcw import appcore  # noqa: E402


def counts(data: bytes) -> dict:
    text, ignored = appcore.read_zip_text(data)
    df, view = appcore.parse_view(text)
    return {"messages": view["messages"], "first": view["first"], "last": view["last"], "ignored_entries": ignored}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: zip_counts.py PATH_TO_ZIP", file=sys.stderr)
        return 2
    try:
        r = counts(Path(argv[1]).read_bytes())
    except (OSError, appcore.AppError) as e:
        print(f"zip_counts: {e}", file=sys.stderr)
        return 3
    print(f"messages {r['messages']}; date range {r['first']} to {r['last']}; ignored zip entries {r['ignored_entries']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
