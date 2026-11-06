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
