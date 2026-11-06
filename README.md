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

**Saved responses.** `--save-response` (off by default) also writes the raw model response and the verified report into `out/runs/`. They contain pseudonymised quotes from your chat: a run on a real chat with the flag leaves them in the gitignored `out/runs/`, so delete them afterwards. Without the flag only a log (config, token counts, cost, verification counts, prompt hash) is written.

**What was tested against prompt injection:** 7 attempts (the planted line from the chat plus three rewritten phrasings, configs A and B) on one synthetic chat, 0 obeyed. That is a probe, not a guarantee: this README does not claim the defence is robust, and real chats may contain phrasings that work. Every model claim is still checked in code against the exact messages, which limits what an injected instruction can put on the card.

## The AI card (3c)

1. Run `analyze ... --confirm --save-response` (the card needs the saved verified report).
2. `python -m gcw review out/runs/<run>.json` lists the items with ids; approve with `--approve ID ...` or reject with `--reject ID ...`. Review files live in `out/reviews/` (gitignored). Pending and rejected items never render.
3. `python -m gcw card CHAT --aliases aliases.json --report out/runs/<run>.json --review out/reviews/<run>.json --until YYYY-MM-DD --out out/card.png` renders Zone 1 (counted stats) plus Zone 2 (approved items, names shown instead of Member tokens). `--until` must equal the analysed slice's end. `--auto-approve-synthetic` exists only for the frozen synthetic chat and says so in the footer.

Configs B and C leave the `thinking` parameter out (the API default is adaptive thinking), but the model used zero thinking tokens in every slice run, so they differ from A only through the effort setting; do not read them as "thinking enabled".
