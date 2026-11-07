# Frozen synthetic dataset

Synthetic and fictional; generated with claude-haiku-5-5 filler, planted ground truth in `ground_truth.json`. No real chat or real person is involved.

Files (in `synthetic/frozen/`, checked by `gcw.dataset.verify_dataset()`, which every evaluation script must call first):

| file | SHA256 |
|---|---|
| `chat_synthetic.txt` | `b6d3add40ae93fe79a10f79d19a0a2b374dd0ffb5c3222feaf0425a12cae13b4` |
| `ground_truth.json` | `b3f2f5afb24df2c271fd9b3ddc1dd57c41231655275e2fb18e4672f79aca5952` |

- n_messages 5144, n_system 9, 5185 lines, 571701 bytes
- tokens 241311 (raw text, `count_tokens`, no schema)
- 6 members (Sam, Alex, Maya, Jordan, Riley, Kai)
- span 2025-11-06 to 2026-11-05
- format: Android 12h export (U+202F before AM/PM)
- planted: 6 running jokes, 1 long-range joke, 3 moments, 1 injection ("PWNED"), 4 sensitive messages, fake PII (placeholder forms only)

The generator cache stays in `data/synthetic/cache` (gitignored). Regenerating is not part of evaluation: the frozen files are the dataset.

## Large frozen dataset (Phase 5a), separate from the one above

Files in `synthetic/frozen_large/`, checked by `gcw.dataset.verify_large_dataset()` (own hash constants; the original `verify_dataset()` is untouched):

| file | SHA256 |
|---|---|
| `chat_synthetic_large.txt` | `0a9f76f0117608ecd4fd3cdc503202e55a15dbe8a2427fc1d1d09d0b7c870b6e` |
| `ground_truth.json` | `b442a82bc44249fe5e49dfeb5021f0539179072f188912946d653941be47f562` |

- 17,134 generated messages (17,097 in the payload after removing system and deleted lines), 1,882,623 bytes (committed: under 3 MB), 889,497 exact payload tokens with `output_config` and the system prompt.
- Config `synthetic/config_large.json`: the original config except `burst_prob_weekday` 0.65, `burst_prob_weekend` 0.85, `burst_size` [50, 90]. Same six members, style cards, banned phrases, planted structure (6 jokes plus the long joke, 3 moments, the PWNED line, 4 sensitive messages, fake PII).
- Generation: 479 batches, cost $0.437 over 508 calls (ledger prefix `genL`); batch `b67p0` was rejected twice by the banned-phrase check on its first run, again twice on the first rerun, and passed on the second rerun (5 API calls, 3 generator runs); prompt, validator, banned phrases and config were not changed to get it through.
- Repetition check (planted lines excluded): the top 3-gram is repeated 229 times; 19 distinct non-planted messages of 4+ words appear more than 3 times (target 0; the most repeated, 32 times, is a stock reply).
