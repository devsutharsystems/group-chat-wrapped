# Privacy layer (Phase 3a): what is replaced before anything is sent

`python -m gcw preview CHAT --aliases aliases.json` prints and writes the exact text that would be sent to the model (`src/gcw/privacy.py`). It makes no API call. Pseudonymised text IS sent to Anthropic in AI mode; this layer reduces what is in it, it does not make a chat anonymous.

## Pipeline, per message (of `messages(df)`: no system lines, no deleted messages)
1. **Sensitive screen** on the original text. A keyword hit (`src/gcw/data/sensitive_keywords.json`, packaged and loaded with `importlib.resources`; a missing file fails closed) replaces the whole message with `[withheld: sensitive]`; the id, time and sender token stay.
2. Cleanup: NFC, invisible and bidi characters stripped (including U+2066-2069), newlines to spaces.
3. Links (`http(s)://`, `www.`, and bare `domain.tld/...` for com, org, net, io, in, co, me, ly, app, dev; whole URL with query string) -> `[link]`; emails -> `[email]`; UPI-style `name@bank` -> `[handle]`.
4. Dates and times are protected (ISO, d/m/y, d.m.y, 21:19, 9:05 PM). Phones (leading + or 00 with 8-15 digits, bare Indian 10-digit starting 6-9, or a separated group of 9-15 digits) -> `[phone]`.
5. Member names (export name, display name, first words, nicknames; whole word, case-insensitive, Unicode-aware, NFC, longest first, `@` prefix and possessives handled) -> the sender's token `Member N`. Senders missing from the alias file get a token too and their names are replaced.
6. Remaining `@handles` -> `[handle]`; digit runs of 6+ -> `[number]`.

Token prefix: `Member`; if the chat already contains `Member <digits>` the next of Person, Speaker, Participant is used, then `P<hash>`. The mapping token -> export name is returned to the caller and stays local.

Line format: `<id> | <YYYY-MM-DD HH:MM> | Member 3 | text` (id like m000123); media is `[media]`.

## Known limits
- Only names and nicknames listed in `aliases.json` (plus the senders found in the chat and their first words) are replaced. A surname or other alias that appears alone in text leaks unless it is listed as a nickname: with only "Alex Kim" and "Alex" listed, "ALEX KIM" becomes "Member 2 KIM" (the first name is replaced, the surname is not).
- Members whose first name is also a common word (Will, Hope, Mark, Grace) must be set `"case_sensitive": true`, otherwise ordinary uses of the word are replaced (and with it set, "will" and "WILL" are left alone, so the name written in a different case leaks).
- The keyword screen is English-only.
- Pseudonymised text IS sent to Anthropic in AI mode.
- Nicknames that are not in the alias file, and names in non-Latin scripts, may leak (matching is Unicode-aware, untested on real chats).
- The screen is English keywords only. It cannot catch other languages, slang, euphemism ("the thing with my knee"), misspellings, topics with no keyword, context (replies to a sensitive message stay in) or media content. Inflections of non-stem terms are missed (`pray` matches, `praying` does not).
- Over-redaction is deliberate: order numbers or amounts of 6+ digits become `[number]`; a missing space after a full stop can turn `ok.in` or `fine.co` into `[link]`; space-separated lists of 9+ digits look like phones.
- The keyword list withholds many harmless messages (Phase 3a-fix removed `fine`, which alone caused 139 of 196 withheld messages, and added `fined`; Phase 3a-fix2 then replaced `party` by the phrase `political party`, see below; `vote`, `dead`, `owe` and the rest are unchanged by decision).
- The keyword list ships inside the package (`gcw/data`, package-data in `pyproject.toml`); the packaging test loads it from a non-editable install with no `src` on the path. A missing file raises an error instead of skipping the screen.
- Token estimate: bytes / 2.37, measured on the raw frozen chat (571,701 bytes, 241,311 tokens), not on the payload; too low for non-Latin scripts.
- UNVERIFIED: that real exports wrap `@mentions` in U+2066-2069 (stripped as a precaution).

Mutation pass (`.cache/tmp/mutate_privacy.py`, not committed): 24 mutations, 23 killed. Phase 3a-fix first re-examined the 3 survivors: two were NOT equivalent (a case-sensitive full name swallowing a case-insensitive first name of another member, and a plus-sign number of 6-7 spread-out digits) and now have killing tests. The last, the last-resort `@letter` rule, is unreachable: the handle rule matches every `@` that is followed by a letter, and its matches contain no `@`; a brute-force test over all strings of length <= 5 (8-symbol alphabet) confirms it, and the 3a-fix run covered length <= 6 (299,592 strings, 0 differences).

Resolved in 3a-fix2 (below). Earlier known screen hit: the keyword `party` (politics) withholds the planted moment m1 ("the surprise party is happening this Saturday"). `tests/test_privacy.py::test_planted_jokes_long_joke_and_moments_are_not_withheld_or_altered` is marked strict xfail until the keyword list is decided.

## Keyword pruning decided after seeing its effect on a planted item (3a-fix2)

`party` (politics) accounted for 26 of the 58 withheld messages on the frozen chat. That included the planted moment's message ("the surprise party is happening this Saturday") and most of that burst day. Its political meaning is rare and named parties are covered separately (`bjp`, `congress`, `democrat*`, `republican*`), so it was replaced by the phrase `political party`. **This pruning was decided after seeing its effect on a planted item**, so it is tuned to the synthetic data; real chats may still have other everyday words hitting the screen. Numbers on the frozen chat:

| | before | after |
|---|---|---|
| planted joke/long-joke/moment messages withheld or altered (of 57) | 1 | 0 |
| total withheld | 58 | 33 |
| filler withheld | 54 | 29 (4 planted + 29 filler) |
| percent of 5,136 | 1.13% | 0.64% (filler alone 0.56%) |

The remaining 'dead', 'vote', 'owe' etc. false positives are unchanged by decision.

## What AI mode sends (Phase 3b)

`python -m gcw analyze` sends the payload text (the `<id> | <time> | Member N | text` lines, with `<` replaced by the fullwidth `＜`) plus a fixed system prompt that contains no names. The exact token count uses the free `count_tokens` endpoint, which also receives the payload, so `--count` and `--confirm` both send it; running `analyze` with no flag sends nothing. Saved run files (`out/runs/`, gitignored) hold the model's response, which quotes pseudonymised payload text; they contain Member tokens only, no real names, and never the API key (only its length).
