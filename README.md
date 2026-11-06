# Group Chat Wrapped

Spotify-Wrapped-style card for a WhatsApp group (Python, pandas, Claude Haiku). Stats-only mode (no AI, no API calls) works today; the AI sections come later.

## Setup

```sh
python3 -m venv .venv
PIP_CACHE_DIR=.cache/pip .venv/bin/pip install -r requirements.txt
PIP_CACHE_DIR=.cache/pip .venv/bin/pip install -e .          # makes `python -m gcw` work from any directory
PLAYWRIGHT_BROWSERS_PATH=.cache/ms-playwright .venv/bin/python -m playwright install chromium
```

macOS note: Python ignores `.pth` files that macOS has flagged hidden. On the machine this was developed on, the flag was re-applied to the editable-install `.pth` within seconds, so `python -m gcw` could fail with "No module named gcw". If that happens, run with `PYTHONPATH=src` (for example `PYTHONPATH=src .venv/bin/python -m gcw ...`) or try `chflags nohidden .venv/lib/python3.*/site-packages/__editable__*.pth`. (Observed here; the cause is unverified.)

## Stats card (no AI, no API calls)

```sh
.venv/bin/python -m gcw stats-card path/to/chat.txt --out out/card.png [--aliases aliases.json] [--since 2026-01-01] [--until 2026-06-30] [--date-order mdy|dmy]
```

Copy `aliases.example.json` to `aliases.json` (gitignored) to show display names on the card. Run renders under `nice -n 10`: one Chromium, one page, closed afterwards.

## Known limits

- Cards were rendered and checked on macOS with Apple Color Emoji only. On Linux, emoji need a colour emoji font (for example Noto Color Emoji); this is unverified.
- Demo PNGs are rendered locally and committed. CI does not render cards.
- Chat timestamps have minute resolution, so response-time medians are coarse (see `docs/stats-verification.md`).
- 24h Android, iOS and multi-line formats are not yet checked against real exports (`docs/PRD.md` section 8).
