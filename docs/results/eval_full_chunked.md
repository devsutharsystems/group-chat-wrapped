# Full-chat evaluation, chunked mode, config A, phase 4b (n = 3 runs)

Messages in the payload: 5136. Counts, rates and planted ids only; no chat text. Ranges are over n = 3 runs; no ranking of anything.

## Per run

| run | input tokens | output tokens | thinking tokens | stop reason | latency s | cost USD | items in (jokes; moments; awards) | items kept | evidence verified of total | rule-compliant | grounding |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261107T114816188-A-chunked | 283410 | 10340 | 0 | None | 46.4 | 0.0335 | 22; 18; 12 | 10; 6; 6 | 117 of 131 | 89% | 95% |
| 20261107T114953275-A-chunked | 282703 | 9488 | 0 | None | 38.1 | 0.0330 | 22; 20; 11 | 9; 6; 6 | 106 of 121 | 88% | 94% |
| 20261107T115025921-A-chunked | 282000 | 8101 | 0 | None | 39.7 | 0.0323 | 19; 17; 10 | 10; 6; 5 | 102 of 110 | 93% | 97% |

Chunked runs (calls, wall-clock seconds, sum of call latencies, candidates before merging, items after the merge and after the item rules):

| run | chunks | calls | wall-clock s | sum of call latencies s | candidates | after merge | after rules |
|---|---|---|---|---|---|---|---|
| 20261107T114816188-A-chunked | 4 | 5 | 20.9 | 46.4 | 51 | 42 | 37 |
| 20261107T114953275-A-chunked | 4 | 5 | 17.5 | 38.1 | 52 | 38 | 33 |
| 20261107T115025921-A-chunked | 4 | 5 | 17.1 | 39.7 | 45 | 28 | 27 |

## Summary over runs

- rule-compliant rate: mean 90%; min 88%; max 93%
- grounding rate: mean 95%; min 94%; max 97%
- items kept, running_jokes: mean 9.7; min 9.0; max 10.0
- items kept, moments: mean 6.0; min 6.0; max 6.0
- items kept, awards: mean 5.7; min 5.0; max 6.0
- unplanted items, running_jokes: mean 2.7; min 2.0; max 3.0
- unplanted items, moments: mean 4.0; min 3.0; max 5.0
- unplanted items, awards: mean 5.7; min 5.0; max 6.0
- output tokens: mean 9310; min 8101; max 10340
- thinking tokens: mean 0; min 0; max 0
- latency seconds: mean 41.4; min 38.1; max 46.4
- cost USD: mean 0.0329; min 0.0323; max 0.0335
- wall-clock seconds: mean 18.5; min 17.1; max 20.9
- candidates before merging: mean 49.3; min 45.0; max 52.0
- items after the merge: mean 36.0; min 28.0; max 42.0
- items after the item rules: mean 32.3; min 27.0; max 37.0

Drop reasons per run (evidence status counts):

- 20261107T114816188-A-chunked: normalisation_only 1; not_found 1; other_message 5; too_short 7; verified 117
- 20261107T114953275-A-chunked: not_found 1; other_message 5; too_short 9; verified 106
- 20261107T115025921-A-chunked: not_found 1; other_message 2; too_short 5; verified 102

## Planted items: strict recall (headline), lenient (secondary), found by date (moments)

Found in k of 3 runs. Strict: at least min(2, planted occurrences) of the AI item's verified evidence messages are occurrences of that planted item and at least half of them are. Lenient: at least one. Found by date: any verified evidence message on the planted date (moments only). Group: the third of the chat holding the midpoint of the item's date span.

| planted id | type | group | split | span from | span to | strict | lenient | by date |
|---|---|---|---|---|---|---|---|---|
| j1 | running_jokes | first | dev | 2025-11-18 | 2026-02-08 | 3 of 3 | 3 of 3 | - |
| j2 | running_jokes | first | dev | 2025-12-06 | 2025-12-30 | 3 of 3 | 3 of 3 | - |
| j3 | running_jokes | middle | held-out | 2026-03-15 | 2026-06-28 | 3 of 3 | 3 of 3 | - |
| j4 | running_jokes | middle | held-out | 2026-03-22 | 2026-06-30 | 3 of 3 | 3 of 3 | - |
| j5 | running_jokes | last | held-out | 2026-08-06 | 2026-10-23 | 3 of 3 | 3 of 3 | - |
| j6 | running_jokes | last | held-out | 2026-07-28 | 2026-10-15 | 3 of 3 | 3 of 3 | - |
| jL | running_jokes | long-range | dev | 2025-11-25 | 2026-10-15 | 3 of 3 | 3 of 3 | - |
| m1 | moments | first | dev | 2026-02-07 | 2026-02-07 | 2 of 3 | 2 of 3 | 2 of 3 |
| m2 | moments | middle | held-out | 2026-04-25 | 2026-04-25 | 3 of 3 | 3 of 3 | 3 of 3 |
| m3 | moments | last | held-out | 2026-10-17 | 2026-10-17 | 1 of 3 | 1 of 3 | 1 of 3 |

### By third of the chat

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| first | j1, j2, m1 | 8 | 8 | 9 | 89% | 89% |
| middle | j3, j4, m2 | 9 | 9 | 9 | 100% | 100% |
| last | j5, j6, m3 | 7 | 7 | 9 | 78% | 78% |
| long-range | jL | 3 | 3 | 3 | 100% | 100% |

### Dev versus held-out

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| dev | j1, j2, jL, m1 | 11 | 11 | 12 | 92% | 92% |
| held-out | j3, j4, j5, j6, m2, m3 | 16 | 16 | 18 | 89% | 89% |

### By type

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| running_jokes | j1, j2, j3, j4, j5, j6, jL | 21 | 21 | 21 | 100% | 100% |
| moments | m1, m2, m3 | 6 | 6 | 9 | 67% | 67% |

Found by date, moments: 6 of 9 item-runs (67%).

## Length distributions of verified items, all runs pooled (characters; numbers only)

| type | field | n | min | median | max | share at most 32 / 110 |
|---|---|---|---|---|---|---|
| running_jokes | title | 29 | 15 | 29 | 58 | 79% (limit 32) |
| running_jokes | summary | 29 | 63 | 89 | 125 | 86% (limit 110) |
| moments | title | 18 | 13 | 23.5 | 33 | 89% (limit 32) |
| moments | summary | 18 | 69 | 97.5 | 166 | 72% (limit 110) |
| awards | title | 17 | 9 | 19 | 44 | 88% (limit 32) |
| awards | summary | 17 | 63 | 94 | 114 | 82% (limit 110) |
