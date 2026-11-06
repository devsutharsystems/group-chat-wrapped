# API notes (verified 2026-11-06 from official docs; no API calls were made)

Your Task F text was cut off after "whether structured outputs / JSON schema are". I treated that item as "supported on claude-haiku-5-5, and how to pass it".

| # | Item | Status | Source |
|---|------|--------|--------|
| 1 | `claude-haiku-5-5` is a valid Claude API model ID. Context window 1M, max output 128K. | VERIFIED | https://platform.claude.com/docs/en/models/haiku-5-5/overview |
| 2 | `messages.create` parameters: `model`, `max_tokens`, `messages`, `system`, `output_config` (`effort`, `format`), `thinking`. Roles `user`/`assistant`/`system`. | VERIFIED | https://platform.claude.com/docs/en/api/messages/create |
| 3 | The exact Python call shape `client.messages.create(model=..., max_tokens=..., messages=[...], output_config={...})`. The docs example uses `claude-opus-5-5`; substituting `claude-haiku-5-5` is by the model-ID table, not a Haiku-specific doc example. | VERIFIED (shape) / UNVERIFIED (no Haiku-specific example) | https://platform.claude.com/docs/en/build-with-claude/structured-outputs |
| 4 | `effort` is passed as `output_config={"effort": ...}` (inside `output_config`, not top-level). Allowed values: `low`, `medium`, `high`, `xhigh`, `max`. Haiku 5.5 supports all five and defaults to `medium`. | VERIFIED | https://platform.claude.com/docs/en/build-with-claude/effort |
| 5 | Structured outputs: `output_config={"format": {"type": "json_schema", "schema": {...}}}`. Haiku 5.5 is in the page's supported-models list. `additionalProperties` must be `false`. No `minimum`/`maximum`, `minLength`/`maxLength`, recursive schemas, or `minItems` other than 0 or 1. Unsupported features return 400. `client.messages.parse(..., output_format=<Pydantic>)` is the documented helper. | VERIFIED | same structured-outputs page |
| 6 | Structured outputs vs citations/prefill compatibility (final part of the page). | UNVERIFIED: the fetched page text was truncated | same page, offset 100000 not read |
| 7 | Haiku 5.5 pricing: input $0.10/MTok and output $0.50/MTok for prompts up to 100K tokens; $0.50 and $2.50 for prompts over 100K. Batch API -50%. Cache read $0.01 (up to 100K) / $0.05 (over). | VERIFIED | https://platform.claude.com/docs/en/models/haiku-5-5/overview |
| 8 | Same tokenizer as Claude 4.7+: about 30% more tokens than Haiku 4.5. 1M tokens is roughly 555k words. | VERIFIED | same overview page |
| 9 | Omit `temperature`, `top_p`, `top_k` on Haiku 5.5. Thinking is adaptive and on by default. `thinking: {"type":"disabled"}` is allowed only at effort `high` or below. | VERIFIED | overview page + effort page |
| 10 | `usage.input_tokens` / `usage.output_tokens` / `cache_*` response field names. | UNVERIFIED on the API reference page (response section truncated). The `claude-api` skill documents `usage.input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`. Confirm against a real response in the first approved API phase. | https://platform.claude.com/docs/en/api/messages/create |
| 11 | Thinking tokens are billed as output tokens. Not stated on the pages fetched. | UNVERIFIED | n/a |

## Implications for the PRD
- **R7:** a full ~1M-token prompt costs about $0.50 input (over the 100K tier) plus output at $2.50/MTok, so about $0.51 to $0.60 at the extreme. That is under $1 but not "well under". Chunks under 100K tokens pay $0.10/MTok, so about 5x cheaper input.
- **R5:** the README may state only the size actually tested. The 1M window is a model limit, not a tested claim.
- Use `output_config.format` JSON schema for the AI contract. The code-side verifier is still required, because a schema can't enforce that quotes are real.
