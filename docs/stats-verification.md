# How each stat in `compute_stats` was verified

"Independent" means the expected value was NOT produced by `src/gcw/stats.py` or `src/gcw/parser.py`. It does not mean independent of my reading of the PRD: every derivation below applies the same definitions from `docs/PRD.md` section 3 and the "Stats behaviour" addendum. No real chat was used; there are two datasets: a 15-message hand table (`tests/test_stats.py`, `ROWS`) and the frozen synthetic chat (`synthetic/frozen/`, 5136 messages after removing 8 deletions).

| Stat | PRD definition (short) | Expected value derived from | Independent of stats.py? |
|---|---|---|---|
| Population | non-system, non-deleted messages; media kept | Hand table: 17 rows minus 1 system minus 1 deleted = 15. Frozen: 5144 sender lines minus 8 `You deleted this message` lines, counted from the raw file | Yes (hand; raw-file plain Python) |
| Window | 365 days ending at the last message, both ends inclusive | Hand: rows exactly 365 days and 400 days before the last message, `date`/`Timestamp` bounds | Yes (hand) |
| Top talkers, messages | count per sender | Hand: Sam 6, Alex 5, Maya 4. Frozen: raw `Sender: ` line counts minus deletions | Yes |
| Top talkers, words | whitespace tokens, media excluded | Hand token counts (Alex 15, Sam 13, Maya 7). Frozen: raw `str.split()` per sender with the edit marker removed | Yes. Note: my first raw-file oracle forgot to remove the ` <This message was edited>` marker and disagreed by exactly 4 words per edited message; the oracle was wrong, not stats.py |
| Busiest hour (overall, per sender) | max count, ties to the earlier hour | Hand hour table (overall hour 8; Sam 8, Alex 6, Maya 2). Frozen: per-sender hour counts from raw timestamps | Yes |
| Busiest weekday (overall, per sender) | max count, ties to the earlier weekday | Hand only (calendar worked out by hand: 2026-03-02 is a Monday). NOT checked on the frozen chat | Yes, but one dataset |
| Busiest date | date with most messages | Hand: 03-02 with 8. Frozen: date of the planted 200-message burst from `ground_truth.json` plus a raw count (201) | Yes |
| Night owl / early bird | highest share in 22:00-03:59 / 04:00-08:59, min 30 messages | Hand fractions (Sam 1/6 and 3/6, Alex 1/5 and 2/5, Maya 2/4 and 1/4). Frozen: shares recomputed from raw hours; winners expected from the `night owl` / `early bird` profiles in `synthetic/config.json`. The per-sender `leaning` field is my own addition and is hand-tested only | Yes |
| Longest silence | largest gap between consecutive messages | Hand: 10:00 to 23:30 = 13.5h (the deleted 10:05 message is ignored). Frozen: max gap over raw timestamps, plus containment of the 10 generated silent days in `ground_truth.json` | Yes |
| Conversation starters | message after a gap >= 6h (first message excluded) | Hand: gap arithmetic for rows 9 and 17 (workings below). Frozen: a plain-loop re-implementation of the same rule inside the test | Hand: yes. Frozen: NO (re-implementation of the same rule) |
| Median response time | different-sender reply within 1h, per-sender median | Hand: the delays listed below. Frozen: a plain-loop re-implementation inside the test | Hand: yes. Frozen: NO (re-implementation) |
| Laughs | messages matching the laugh regex | Hand: I applied the regex by eye to each of the 15 messages; unit strings hand-written (lollipop, LOL!, lmaooo, rofl, hahaha, pillow...). Frozen: the same regex text re-applied to the raw lines in the test | Hand: yes (by eye). Frozen: NO (same pattern re-applied) |
| Emojis (total, per sender, top 10) | one per grapheme cluster | Hand cluster counts; unit strings hand-counted (the 8-emoji line, hahaha 3, heart with FE0F, ZWJ family, skin tone, flag, keycap, (c)/(r)/TM with and without FE0F, bare heart and sun). Frozen: independent `re` scan of emoji codepoint ranges (a different method), valid because the test first asserts the data has no ZWJ, skin-tone, flag or keycap sequences | Yes (frozen comparison depends on that checked precondition) |
| Media | `<Media omitted>` messages | Hand: rows 4 and 17. Frozen: raw `<Media omitted>` lines per sender (136) | Yes |
| Links | `https?://` occurrences | Hand: Sam 1, Alex 2. Frozen: raw regex count (2) | Yes |
| JSON-serialisable, no `anthropic` import | stats-only mode makes no API calls | `json.dumps` round trip; subprocess import check | Structural tests |

Mutation check: `.cache/tmp/mutate_stats.py` (not committed) applies one mutation at a time to `stats.py` (window edges, `>=` versus `>`, tie rules, band edges to the minute, emoji and laugh rules). All mutants are killed by the tests; the surviving ones found in the first pass led to new tests.

## Workings for the hand table (15 messages)

Rows kept: row 2 to row 7 and row 9 to row 17 (the system row 1 and the deleted row 8 are removed). The first day, 2026-03-02, is a Monday.

Starters (gap >= 6h, first message excluded):
- Row 9, Alex: previous kept message is row 7 (Maya, 03-02 10:00); the deleted row 8 at 10:05 is invisible. 10:00 to 23:30 = 13h30m >= 6h, so Alex has a starter.
- Row 17, Sam: previous is row 16 (Alex, 03-03 12:40). 12:40 to 18:40 = exactly 6h00 >= 6h, so Sam has a starter.
- Row 15 (Sam 12:00) follows row 14 at 06:10: 5h50m < 6h, no. Row 2 is the first message, not counted.

Response times (previous message is from a different sender, delay <= 1h): Maya's four delays are row 4 (08:25, after Alex 08:20) = 300 s; row 7 (10:00, after Alex 09:30) = 1800 s; row 10 (23:50, after Alex 23:30) = 1200 s; row 12 (02:30, after Sam 02:00) = 1800 s. Sorted: 300, 1200, 1800, 1800; even count, so the median is (1200 + 1800) / 2 = 1500 s.

Silence: the gaps between consecutive kept messages are 20m, 5m, 0, 65m, 30m, 13h30m (10:00 to 23:30), 20m, 2h10m, 30m, 3h30m, 10m, 5h50m, 40m, 6h00m. The maximum is 13h30m = 13.5 hours.

## Limits worth knowing

- The longest silence ignores deleted messages: a deleted message does not split a gap (the population is `messages(df)`).
- Laughs are English-style only (`haha`, `lol`, `lmao`, `rofl` and two laughing emoji); other languages are not detected.
- Timestamps have minute resolution (WhatsApp exports have no seconds), so response times are multiples of 60 seconds in practice: a reply in the same minute is 0 s and the next minute is 60 s. Response-time medians therefore separate senders only coarsely.
