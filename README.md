# Group Chat Wrapped

![A card built from the bundled synthetic chat: counted statistics on top, AI-found items below](docs/img/app_4_review_rendered_card.png)

*A card from the bundled synthetic demo chat (no real chat). The AI items were loaded from a saved model run and approved in the review step; see the screenshots section for what that means.*

Group Chat Wrapped turns a WhatsApp group export into a one-page card: counted statistics (top talkers, busiest day, longest silence, response times and so on) and, optionally, items found by a language model (running jokes, moments, awards). It is a Python package (pandas, Playwright for rendering, Claude Haiku for the AI step) with a command-line interface and a local Streamlit app.

## Why it differs from common WhatsApp analysers

1. **Every AI claim is checked in code against the real message.** A running joke, moment or award is kept only if each of its evidence quotes is an exact substring of the cited message, and if it meets the item rules (a joke needs several quotes on more than one date). Items that fail are dropped, and the drop counts by reason are reported in the run output and in `docs/results/`. A claim the model cannot back with a real quote does not reach the card.
2. **Privacy by design, with the limits stated.** Names are replaced before anything is sent, a keyword screen withholds sensitive messages, and `preview` shows the exact text that would be sent. Stats-only mode (the default) makes no network call. AI mode needs an explicit consent step and runs under a cost cap. Pseudonymised text is still sent to Anthropic in AI mode; see the privacy section.
3. **A measured evaluation on a synthetic chat with planted ground truth.** The test chats contain jokes, moments and other items planted at known positions, so recall and precision-style numbers are computed rather than asserted. The numbers, their sample sizes and their limits are below; they are not claims about real chats.

## Quickstart

```sh
python3 -m venv .venv
PIP_CACHE_DIR=.cache/pip .venv/bin/pip install -r requirements.txt
PIP_CACHE_DIR=.cache/pip .venv/bin/pip install .
PLAYWRIGHT_BROWSERS_PATH=.cache/ms-playwright .venv/bin/python -m playwright install chromium
```

Developers can run from the source tree with `PYTHONPATH=src` instead of installing (an editable install can fail on macOS because the `.pth` file is flagged hidden; the cause is likely, not verified).

**Stats only (no API, no network).** Copy `aliases.example.json` to `aliases.json` (gitignored) to show display names.

```sh
PLAYWRIGHT_BROWSERS_PATH=.cache/ms-playwright .venv/bin/python -m gcw stats-card path/to/chat.txt --out out/card.png --aliases aliases.json
```

**AI mode.** The key comes from the `ANTHROPIC_API_KEY` environment variable or a `.env` file that you create (gitignored); it is never printed. Every call is explicit and passes the cost guard (`GCW_COST_CAP_USD` per run, `GCW_PROJECT_CAP_USD` for the project).

```sh
.venv/bin/python -m gcw preview path/to/chat.txt --aliases aliases.json                      # the exact text that would be sent; no API call
.venv/bin/python -m gcw analyze path/to/chat.txt --aliases aliases.json --mode auto --count   # exact token count (sends the text to count_tokens), no generation
.venv/bin/python -m gcw analyze path/to/chat.txt --aliases aliases.json --mode auto --confirm --save-response
.venv/bin/python -m gcw review out/runs/<run>.json                                           # list items; --approve ID ... / --reject ID ...
.venv/bin/python -m gcw card path/to/chat.txt --aliases aliases.json --report out/runs/<run>.json --review out/reviews/<run>.json --until YYYY-MM-DD --out out/card.png
```

`--save-response` writes pseudonymised quotes into the gitignored `out/runs/`; delete them afterwards. `--mode auto` runs single-pass up to 300,000 exact tokens and chunked map-reduce above, printing a warning; the threshold is provisional (see Limits).

**The app.**

```sh
PLAYWRIGHT_BROWSERS_PATH=.cache/ms-playwright PYTHONPATH=src .venv/bin/streamlit run src/gcw/app.py
```

## How it works

1. **Parse** (`parser.py`): Android and iOS export formats, system and deleted lines separated, day/month order inferred with a warning when ambiguous.
2. **Stats** (`stats.py`, `card.py`): counted statistics over a date window, rendered to a 1080x1350 PNG by headless Chromium (no network during the render).
3. **Privacy layer** (`privacy.py`, `textnorm.py`): sensitive-keyword screen, link, email, phone and number redaction, member names to `Member N`; output lines look like `m000123 | date time | Member 3 | text`.
4. **Analysis** (`analyze.py`, `llm.py`): one request with a frozen v1 prompt and JSON schema; Claude Haiku returns running jokes, moments and awards with `{message_id, quote}` evidence. **Chunked mode** (`chunked.py`) splits the chat at day boundaries, runs the same request per chunk, and merges the findings with one extra call that only groups candidate ids; the evidence union is built by code and every rule is re-applied after the merge.
5. **Verification** (`verify.py`): ids must exist and not be withheld or media; quotes must be long enough and exact substrings of the cited message after normalisation; item rules and per-type caps are applied; anything else is dropped and counted.
6. **Cost guard** (`cost.py`): explicit confirm for every call, per-run and project caps, a ledger of computed costs.
7. **Review and card** (`review.py`, `display.py`): approve, reject or rank each verified item; only approved items render; names replace `Member N` tokens on the card.
8. **Evaluation** (`evaluate.py`, `dataset.py`): scoring against planted ground truth for the frozen synthetic chats, whose hashes are verified first.
9. **App** (`app.py`, `appcore.py`, `render_child.py`): the Streamlit front end; the chat stays in memory; the card is rendered in a child process.

## Privacy

- **Replaced before sending:** member names and listed nicknames become `Member N`; links, emails, phone-like and long digit strings become placeholders; messages that match the English sensitive-keyword list are replaced by `[withheld: sensitive]`. Full rules: `docs/privacy.md`.
- **What leaks:** nicknames and surnames that are not listed in your aliases file stay in the text; names in non-Latin scripts may; the keyword screen is English-only and cannot catch euphemism, other languages or context. Over-redaction also happens (long numbers, some domain-like strings).
- **What is sent:** in AI mode, the pseudonymised and redacted text of the chosen window (plus a fixed system prompt) is sent to Anthropic. The exact token count (`count_tokens`) also receives that text. Stats-only mode sends nothing.
- **Consent:** the CLI needs `--count` or `--confirm` to send anything; the app shows the exact payload preview and sends nothing until you tick the consent box (pseudonymised text goes to Anthropic and the group members consented) and press Run.
- Pseudonymisation is not anonymisation: a chat can often be recognised from its content.

## Evaluation

All numbers below are generated from `docs/results/*.json` and memory logs by `scripts/build_readme_tables.py`; a test fails if they are stale. Strict recall counts a planted item as found only when the verified evidence of one AI item sits mostly on that item's planted messages. Planted density is the share of payload messages that are planted lines.

<!-- BEGIN:eval_table -->
| row | n | input tokens per run | planted density | strict recall (found of in-scope item-runs) | rule-compliant rate | unplanted items per run (awards / moments / jokes) | cost per run (USD) | latency per run (s) |
|---|---|---|---|---|---|---|---|---|
| dense 270K tokens, single-pass | 3 | 269,809 | 1.30% | 25 of 30 | 94%, range 92% to 97% | 2.3 / 2.3 / 0.7 | 0.1402, range 0.1392 to 0.1410 | 10.5, range 9.7 to 11.7 |
| dense 270K tokens, chunked | 3 | 282,704 (sum over calls) | 1.30% | 27 of 30 | 90%, range 88% to 93% | 5.7 / 4.0 / 2.7 | 0.0329, range 0.0323 to 0.0335 | 41.4, range 38.1 to 46.4 (sum of call latencies) |
| sparse chat, first third, single-pass | 1 | 296,849 | 0.36% | 3 of 3 | 78% | 3.0 / 3.0 / 0.0 | 0.1534 | 13.8 |
| sparse chat, 889K tokens, single-pass | 1 | 889,497 | 0.39% | 0 of 10 | 52% | 0.0 / 3.0 / 0.0 | 0.4483 | 39.8 |
| sparse chat, 889K tokens, chunked | 1 | 923,596 (sum over calls) | 0.39% | 5 of 10 | 87% | 6.0 / 6.0 / 5.0 | 0.1029 | 102.1 (sum of call latencies) |
<!-- END:eval_table -->

Rows with n = 1 are single observations. The large-chat rows hold the same planted lines as the dense chat in a longer chat, so planted density differs between rows (see the density column) and the rows are not a controlled comparison (`docs/results/compare_large.md`, `docs/results/diag_large_A.md`).

**Cost, latency and memory.**

<!-- BEGIN:cost_block -->
Cost is computed from the usage fields times list prices (a request above 100,000 prompt tokens is billed whole at the higher tier) and is not reconciled with the Console. Chunked wall-clock time is shorter than the sum of call latencies because map calls run in parallel.

| row | cost per run (USD) | latency per run (s) | wall-clock per run (s, chunked only) |
|---|---|---|---|
| dense 270K tokens, single-pass | 0.1402, range 0.1392 to 0.1410 | 10.5, range 9.7 to 11.7 | n/a |
| dense 270K tokens, chunked | 0.0329, range 0.0323 to 0.0335 | 41.4, range 38.1 to 46.4 | 18.5, range 17.1 to 20.9 |
| sparse chat, first third, single-pass | 0.1534 | 13.8 | n/a |
| sparse chat, 889K tokens, single-pass | 0.4483 | 39.8 | n/a |
| sparse chat, 889K tokens, chunked | 0.1029 | 102.1 | 42.0 |

Memory and time of the card render paths (Memory and wall-clock measurements recorded from the output of the commands named in 'source'. One run each, macOS, M2, 8 GB. Summed RSS probably overcounts pages shared between processes (unverified). Not a benchmark.)

| render path | wall-clock (s) | largest process (MB) | summed over the process tree (MB) |
|---|---|---|---|
| stats card, app render path (no server, no screenshot browser) | 2.97 | 138 | 509 |
| AI card, app render path (saved config A run, all items approved) | 5.68 | 244 | 455 |

Screenshot harness (a development tool, not part of the app's footprint; ceiling 1433 MB), peak summed RSS per step:

| step | peak (MB) |
|---|---|
| server start | 198 |
| browser start | 704 |
| stats card (browser + server + render child) | 1171 |
| payload preview (browser + server) | 814 |
| review (browser + server) | 959 |
| review with Render card (browser + server + render child) | 1088 |
<!-- END:cost_block -->

**Precision.**

<!-- BEGIN:precision_block -->
Precision: not yet measured (hand-rating pending)
<!-- END:precision_block -->

**Frozen identifiers** (prompts, schema and verification rules are frozen; the datasets are checked by hash before any evaluation):

<!-- BEGIN:versions -->
| identifier | SHA-256 |
|---|---|
| `PROMPT_VERSION (v1 system prompt and schema)` | `a4498b04960adc6bf7fd664cf5c6ef95dc206811d3169a02063b7d7952febc56` |
| `REDUCE_PROMPT_VERSION` | `6c010e09578d01f14dd22c3d553dbd45dad23b3a4fd3b53f173fe22f3c38390a` |
| `synthetic/frozen/chat_synthetic.txt` | `b6d3add40ae93fe79a10f79d19a0a2b374dd0ffb5c3222feaf0425a12cae13b4` |
| `synthetic/frozen/ground_truth.json` | `b3f2f5afb24df2c271fd9b3ddc1dd57c41231655275e2fb18e4672f79aca5952` |
| `synthetic/frozen_large/chat_synthetic_large.txt` | `0a9f76f0117608ecd4fd3cdc503202e55a15dbe8a2427fc1d1d09d0b7c870b6e` |
| `synthetic/frozen_large/ground_truth.json` | `b442a82bc44249fe5e49dfeb5021f0539179072f188912946d653941be47f562` |
<!-- END:versions -->

## The app

The app runs on 127.0.0.1 only (`.streamlit/config.toml`; usage statistics off) and has no hosted upload endpoint. Steps: load (a `.txt`, a `.zip` holding exactly one `.txt`, or the bundled synthetic chat), settings, stats card, AI (payload preview, consent, run), review. The chat stays in memory; the card is rendered in a child process; run logs hold counts only; review files hold item ids and statuses only.

![Step 3: the stats card rendered in the app, AI sections off](docs/img/app_1_stats_card.png)
*Stats card step after the real Render click (synthetic chat, stats-only mode).*

![Step 4: the payload preview before consent, checkbox unticked, Run disabled](docs/img/app_2_payload_preview_before_consent.png)
*Payload preview before consent: nothing has been sent; the checkbox is unticked and Run is disabled. The spend figure comes from a fictional demo ledger.*

![Step 5: the first review items with approve, reject and rank controls, context collapsed](docs/img/app_3_review.png)
*Review step, cropped to the first items; the Render card button sits below the list. A saved model output is loaded through the saved-report upload with its run log. The decisions in this image are auto-approved demo decisions (every item set to approved by the screenshot script).*

![The rendered card after Render card, whole card with the AI zone filled and both footer lines](docs/img/app_4_review_rendered_card.png)
*The rendered card after "Render card" (an element screenshot of the card image); its stats cover the same window as the saved run.*

The review source is a saved config A run on the synthetic chat that I judged to be the same run as the earlier demo card, based on its visible fields (the joke and moment titles and quotes, both award members, and the proposed and verified counts match); the card's source data was not saved, so that is a judgement, not a check of the whole run. The page refuses a run log whose message count differs from the chosen window. The screenshots come from `scripts/app_screenshots.py`, a development tool with its own memory ceiling (see the table above), not part of the app's footprint.

## Limits

- The test chats are synthetic and their planted items are easier than real jokes; results say nothing certain about real chats. No real chat has been analysed in this repository, and dev items were seen during development, so the numbers are not blind.
- Sample sizes are small: n is shown in every table row, and rows with n = 1 are single observations on one configuration.
<!-- BEGIN:scale_limits -->
- Single-pass on the sparse chat at 889,497 tokens found 0 of 10 planted items (n = 1); chunked on the same chat found 5 of 10 (n = 1). The context window accepts the request; quality at that size was not demonstrated.
- Single-pass at 269,809 tokens on the dense chat found 25 of 30 planted item-runs (n = 3); on the first third of the sparse chat (296,849 tokens) it found 3 of 3 (n = 1). These sizes were tested on development items that were seen during development.
<!-- END:scale_limits -->
- The model's context window accepts a request of about a million tokens, but usable recall is not the window size: quality at that size was not demonstrated.
- `--mode auto` switches to chunked above 300,000 exact tokens. The threshold is provisional and was set from a handful of runs (see `docs/PRD.md` R5); it replaced an earlier plan to fall back only at the model limit.
- The planted long joke jL does not test long-range dependence: it has enough evidence inside single chunks.
- The per-type caps rank by evidence count and date spread, which disadvantages moments (one-quote items); chunked and single-pass differ partly because of this.
- Precision is reported only where the table above shows it; until the hand ratings exist, no precision figure is claimed.
- The prompt-injection defence was probed on one synthetic chat with a few phrasings (`docs/results/injection_probe.md`); the README does not claim it is robust. Verification in code limits what an injected instruction can put on the card, nothing more.
- Chat timestamps have minute resolution, so response-time medians are coarse (`docs/stats-verification.md`).
- The sensitive-keyword screen and the laugh detector are English-only; many harmless messages are withheld by the keyword list, and euphemism, other languages and context are not caught.
- Names, nicknames and surnames that are not listed in the aliases file leak into the text sent to Anthropic; names that are common words need `case_sensitive`; non-Latin scripts are untested.
- Android multi-line messages, iOS exports and 24-hour formats were tested on generated data only, not on real exports (`docs/PRD.md` section 8).
- Costs are computed from the usage fields times list prices and are not reconciled with the Console; a request above 100,000 prompt tokens is billed whole at the higher tier.
- Everything was developed and checked on macOS (M2, 8 GB). Cards need a colour emoji font on Linux; this is unverified. The rendered cards were checked with Apple Color Emoji only.
- One config (A) and one prompt version (v1) were evaluated; the other configs differ only through the effort setting.

## History and publishing

The git history of this repository is rewritten once before publishing, to remove build artefacts and local paths. Old-to-new commit hashes are listed in `docs/results/commit_map.md`, which the rewrite step writes. Until that step is done, `scripts/prepublish_check.py` fails, by design.

## Licence

MIT (`LICENSE`).
