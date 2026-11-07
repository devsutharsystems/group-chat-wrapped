"""Child process of the app's card render: HTML on stdin, PNG on stdout. One Chromium (--disable-gpu), one page, closed afterwards; no network (card.render_png
blocks every request). Started by appcore.render_png_bytes under `nice -n 10`; nothing is written to disk."""
from __future__ import annotations

import sys

from gcw import card


def main() -> int:
    html = sys.stdin.buffer.read().decode("utf-8")
    png = card.render_png(html)["png"]
    sys.stdout.buffer.write(png)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
