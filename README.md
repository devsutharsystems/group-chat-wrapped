# Group Chat Wrapped

Spotify-Wrapped-style card for a WhatsApp group (Python, pandas, Claude Haiku). Stats-only mode (no AI, no API calls) works today; the AI sections come later.

## Setup

```sh
python3 -m venv .venv
PIP_CACHE_DIR=.cache/pip .venv/bin/pip install -r requirements.txt
PIP_CACHE_DIR=.cache/pip .venv/bin/pip install .             # users: regular (non-editable) install
PLAYWRIGHT_BROWSERS_PATH=.cache/ms-playwright .venv/bin/python -m playwright install chromium
```

Developers run from the source tree with `PYTHONPATH=src .venv/bin/python -m gcw ...` (no editable install). macOS can flag the `.pth` file of an editable install as hidden and Python 3.13+ skips hidden `.pth` files; that is the likely cause of the failed editable install here, not verified.

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

## Privacy

`python -m gcw preview CHAT --aliases aliases.json` shows the exact text that would be sent to the model (names replaced by `Member N`, links, emails, phones and long numbers redacted, sensitive-keyword messages withheld). Copy `aliases.example.json` to `aliases.json` (gitignored) and list your members and nicknames. Pseudonymised text IS sent to Anthropic in AI mode. Limits: only names and nicknames listed in `aliases.json` are replaced (a surname alone, for example "ALEX KIM" with only "Alex Kim" and "Alex" listed, becomes "Member 2 KIM"); members whose first name is a common word (Will, Hope) need `"case_sensitive": true`; the keyword screen is English-only. See `docs/privacy.md`.

## AI analysis (3b)

`python -m gcw analyze CHAT --aliases aliases.json --slice-end 2026-02-08 --config A` prints the payload preview and a rough size and sends nothing. Add `--count` for the exact token count (free, but it sends the pseudonymised payload) and `--confirm` to run (cost guard, $0.15 phase budget, refused over 95,000 tokens). Every claim is checked in code: a running joke, moment or award is kept only if its quotes are exact substrings of the cited messages (see `docs/PRD.md` section 4). On the synthetic slice one call cost about $0.009.
