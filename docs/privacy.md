# Privacy layer (Phase 3a): what is replaced before anything is sent

`python -m gcw preview CHAT --aliases aliases.json` prints and writes the exact text that would be sent to the model (`src/gcw/privacy.py`). It makes no API call. Pseudonymised text IS sent to Anthropic in AI mode; this layer reduces what is in it, it does not make a chat anonymous.

## Pipeline, per message (of `messages(df)`: no system lines, no deleted messages)
1. **Sensitive screen** on the original text. A keyword hit (`config/sensitive_keywords.json`) replaces the whole message with `[withheld: sensitive]`; the id, time and sender token stay.
2. Cleanup: NFC, invisible and bidi characters stripped (including U+2066-2069), newlines to spaces.
3. Links (`http(s)://`, `www.`, and bare `domain.tld/...` for com, org, net, io, in, co, me, ly, app, dev; whole URL with query string) -> `[link]`; emails -> `[email]`; UPI-style `name@bank` -> `[handle]`.
4. Dates and times are protected (ISO, d/m/y, d.m.y, 21:19, 9:05 PM). Phones (leading + or 00 with 8-15 digits, bare Indian 10-digit starting 6-9, or a separated group of 9-15 digits) -> `[phone]`.
5. Member names (export name, display name, first words, nicknames; whole word, case-insensitive, Unicode-aware, NFC, longest first, `@` prefix and possessives handled) -> the sender's token `Member N`. Senders missing from the alias file get a token too and their names are replaced.
6. Remaining `@handles` -> `[handle]`; digit runs of 6+ -> `[number]`.

Token prefix: `Member`; if the chat already contains `Member <digits>` the next of Person, Speaker, Participant is used, then `P<hash>`. The mapping token -> export name is returned to the caller and stays local.

Line format: `<id> | <YYYY-MM-DD HH:MM> | Member 3 | text` (id like m000123); media is `[media]`.

## Known limits
- Nicknames that are not in the alias file, and names in non-Latin scripts, may leak (matching is Unicode-aware, untested on real chats).
- The screen is English keywords only. It cannot catch other languages, slang, euphemism ("the thing with my knee"), misspellings, topics with no keyword, context (replies to a sensitive message stay in) or media content. Inflections of non-stem terms are missed (`pray` matches, `praying` does not).
- Over-redaction is deliberate: order numbers or amounts of 6+ digits become `[number]`; a missing space after a full stop can turn `ok.in` or `fine.co` into `[link]`; space-separated lists of 9+ digits look like phones.
- The keyword list withholds many harmless messages (see the false-positive list in the Phase 3a report; `fine` alone caused 139 of 196 withheld messages on the frozen chat).
- `config/sensitive_keywords.json` is read from the repo, not packaged: a non-editable `pip install .` has no copy.
- Token estimate: bytes / 2.37, measured on the raw frozen chat (571,701 bytes, 241,311 tokens), not on the payload; too low for non-Latin scripts.
- UNVERIFIED: that real exports wrap `@mentions` in U+2066-2069 (stripped as a precaution).

Mutation pass (`.cache/tmp/mutate_privacy.py`, not committed): 24 mutations, 21 killed. Three survivors are equivalent mutants: `case_sensitive` flag ignored in the pattern (the token lookup rejects the wrong case anyway), phone minimum 8 -> 6 digits with a plus sign (the candidate regex already needs 8 digits), and the last-resort `@letter` rule (the handle rule already covers it).
