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

`python -m gcw analyze CHAT --aliases aliases.json --slice-end 2026-02-08 --config A` prints the payload preview and a rough size and sends nothing. Add `--count` for the exact token count (free, but it sends the pseudonymised payload) and `--confirm` to run (cost guard, $0.15 phase budget, refused over 95,000 tokens). Every claim is checked in code: a running joke, moment or award is kept only if its quotes are exact substrings of the cited messages (see `docs/PRD.md` section 4). Measured cost, token counts and recall of full-chat runs on the synthetic chat are in `docs/results/eval_full_A.md` (costs computed from usage fields times list prices, see `docs/results/README.md`).

**Saved responses.** `--save-response` (off by default) also writes the raw model response and the verified report into `out/runs/`. They contain pseudonymised quotes from your chat: a run on a real chat with the flag leaves them in the gitignored `out/runs/`, so delete them afterwards. Without the flag only a log (config, token counts, cost, verification counts, prompt hash) is written.

**What was tested against prompt injection:** a small probe on one synthetic chat, recorded in `docs/results/injection_probe.md`. That is a probe, not a guarantee: this README does not claim the defence is robust, and real chats may contain phrasings that work. Every model claim is still checked in code against the exact messages, which limits what an injected instruction can put on the card.

## The AI card (3c)

1. Run `analyze ... --confirm --save-response` (the card needs the saved verified report).
2. `python -m gcw review out/runs/<run>.json` lists the items with ids; approve with `--approve ID ...` or reject with `--reject ID ...`. Review files live in `out/reviews/` (gitignored). Pending and rejected items never render.
3. `python -m gcw card CHAT --aliases aliases.json --report out/runs/<run>.json --review out/reviews/<run>.json --until YYYY-MM-DD --out out/card.png` renders Zone 1 (counted stats) plus Zone 2 (approved items, names shown instead of Member tokens). `--until` must equal the analysed slice's end. `--auto-approve-synthetic` exists only for the frozen synthetic chat and says so in the footer.

Configs B and C leave the `thinking` parameter out (the API default is adaptive thinking), but the model used zero thinking tokens in every slice run, so they differ from A only through the effort setting; do not read them as "thinking enabled".

The card's AI text is built for phone feeds: every text in Zone 2 and the footer is at least 20 px (summaries and quotes 22 px), so long titles, summaries and quotes are truncated with an ellipsis on the card (the verified text is untouched). `review --rank ID=N` reorders items of a type; with no ranks the model's order is used.

**Long chats.** `analyze --mode chunked` (or `--mode auto`, which runs single-pass up to 300,000 exact tokens and switches to chunked above with the warning "chat above 300,000 tokens; using chunked map-reduce (single-pass quality at this size was not demonstrated)"; `--mode single` stays available up to the model limit) splits the chat at day boundaries, runs the same request per chunk, merges the findings with one extra grouping call and re-applies every rule after the merge. Measured behaviour on the synthetic chat, compared with single-pass: `docs/results/compare_single_vs_chunked.md`. Single-pass has only been tested at the size recorded in `docs/results/eval_full_A.md`; the chunked mode has been tested on that chat and once on the 889,497-token large chat (5 of 10 planted items found, n = 1).

**Size actually tested.** Single-pass was run on a synthetic chat of 889,497 tokens (one run, config A) and on one of 269,809 tokens (three runs); see `docs/results/eval_large_A.md` and `docs/results/eval_full_A.md`. At the larger size the request was accepted, but the model's answer mostly failed verification (13 of 25 evidence messages verified, no joke kept, no planted item found), so the large run does not show that a million-token chat works well. Single run (n = 1): 39.8 s, computed cost $0.4483, 52% of evidence verified, 0 of 10 planted items found; the large chat holds the same 67 planted lines as the smaller one in 3.3 times more chat (density 0.39% against 1.30%), so this result is confounded by density. Phase 5b added, all n = 1 (`docs/results/compare_large.md`): single-pass on the first third of the large chat (296,849 tokens) found its 3 scored planted items (29 of 37 evidence verified, $0.1534), and the chunked mode on the whole large chat (11 chunks) found 5 of 10 planted items with 245 of 282 map evidence verified, at $0.1029. **Usable recall is not the context window size; the 1M window accepts the input, but quality at that size was not demonstrated.** The 5b control does not support a density-only explanation, and it does not isolate length either: the cause of the 0 of 10 is not established. One run per row, one config, synthetic data; costs are computed from the usage fields (a request above 100,000 prompt tokens is billed at the higher tier) and not reconciled with the Console.

**Why 300,000 (provisional).** The 1M window accepted an 889,497-token request in one call ($0.4483, 39.8 s, n = 1), but strict recall was 0 of 10 planted items: 5 of 7 planted jokes had a proposed item quoting a planted line, and none of those items carried the 3 verified evidence messages the joke rule needs. Chunked mode on the same chat found 5 of 10 planted items for $0.1029 (n = 1). Single-pass worked at 269,809 tokens (n = 3) and 296,849 tokens (n = 1) on development items only, and failed at 889,497 (n = 1); nothing in between was tested. This replaces the original plan of falling back only at the model limit (`docs/PRD.md` R5, `docs/results/compare_large.md`, `docs/results/diag_large_A.md`).

## The app (local only)

```sh
PIP_CACHE_DIR=.cache/pip .venv/bin/pip install -r requirements.txt     # streamlit is pinned there
PLAYWRIGHT_BROWSERS_PATH=.cache/ms-playwright PYTHONPATH=src .venv/bin/streamlit run src/gcw/app.py
```

It binds to 127.0.0.1 only (`.streamlit/config.toml`; usage statistics are off) and has no hosted upload endpoint: there is no server to upload to, the page runs on your machine. Steps in the sidebar: 1 Load (a `.txt` or a `.zip` holding exactly one `.txt`, or the bundled synthetic demo chat), 2 Settings (aliases, date window, date order, mode), 3 Stats card, 4 AI, 5 Review.

- **The chat stays in memory.** Uploaded bytes are never written to disk; a zip is read in memory, must hold exactly one `.txt` (macOS `__MACOSX/` entries are ignored), is limited to 50 MB uncompressed, and encrypted members are refused. The card is rendered in a child process (`nice -n 10`, Chromium `--disable-gpu`, one at a time, no network) that receives the HTML on stdin and returns the PNG on stdout. What the app writes to disk: run logs in `out/runs/` (counts, tokens, cost; no chat text), review files in `out/app/` (item ids, types, statuses and ranks only), and the cost ledger. A downloaded card PNG contains what you approved for it.
- **Stats-only mode (default) makes no network call** and needs no API key.
- **Consent.** In AI mode the page first shows the exact pseudonymised text it would send (20 fixed-seed lines), replacement counts, the withheld count, a rough token estimate (bytes / 2.37, labelled rough) and a worst-case cost upper bound against `GCW_COST_CAP_USD` and `GCW_PROJECT_CAP_USD`. Nothing leaves the machine, not even the exact token count (which sends the text), until you tick "I understand that pseudonymised message text will be sent to Anthropic, and the group members consented" and press Run. Run is disabled without the checkbox, without a key, or when the bound is above a cap. After Run: exact `count_tokens`, caps re-checked, then the analysis through the cost guard with `confirm=True`. The page shows only "key loaded: yes/no".
- **What leaves the machine:** only the pseudonymised, redacted text of the chosen window, and only in AI mode after consent. Names you did not list in the aliases table, and nicknames or surnames you left out, are sent as written. The keyword screen is English-only (`docs/privacy.md`).
- **Review.** Every verified item with its evidence quotes and two messages before and after (display names); approve, reject or rank; only approved items render. You can also load a saved `.report.json` from a CLI run; it is re-verified against the loaded chat and window, so an unverified claim cannot reach the card.
- **Limits.** Chat-derived text is drawn with `st.text` or dataframes, never as markdown or HTML. Measured quality: the numbers in `docs/results/` (single-pass up to 296,849 tokens, chunked on 889,497 tokens, both n = 1 on synthetic chats). Tested on macOS only; uploads were tested through Streamlit's test harness, not through a real browser file dialog.

**Screenshots** (synthetic demo chat only; `docs/img/`): the stats-card step after the real Render click (`docs/img/app_1_stats_card.png`), the payload preview before consent with the checkbox unticked and Run disabled (`docs/img/app_2_payload_preview_before_consent.png`), and the review step (`docs/img/app_3_review.png`). The review image loads a saved model output through the saved-report upload: the config A run stamped 20261106T202238 on the synthetic chat (slice to 2026-02-08), which is the run behind the 3c demo card (its joke, moment and award titles, the joke and moment quotes, both award members and the "13 proposed, 12 verified" counts match the card). All decisions in that image were set to approved in the page for the screenshot ("auto-approved demo"). The harness is `scripts/app_screenshots.py`.

**Measured footprint** (macOS, M2, 8 GB; one run each, not a benchmark):
- App render path (appcore to the render child, no server, no screenshot browser), stats-only on the demo chat: 2.97 s wall-clock, 138 MB for the largest process, 509 MB summed over the process tree (`guarded.py`); the CLI `stats-card` gives a byte-identical PNG (same SHA-256), 1080x1350.
- Screenshot harness (server plus one browser at a time; summed RSS of the whole tree, MB): server start 191-221; browser started 674-720; stats-card step with the real Render click (harness browser, server and the app's own render child) 1,015 to 1,167 over four runs, 1,015 in the run that produced the committed images; payload-preview step about 811; review step about 948. The system-wide free memory reported by `memory_pressure` was 50% before and 47% after the final run.
- The harness is a dev tool and is not part of the app's footprint. Its sampler ceiling is 1.4 GB, for that script only (CLAUDE.md keeps 1 GB elsewhere): the harness holds one browser and its Node driver while the app starts its own render child (a second Chromium stack and a second Node driver), the other project's benchmark that the 1 GB rule protected has finished, and summed RSS probably overcounts pages the processes share (unverified).
