# Full-chat evaluation, single mode, config A, phase 4a (n = 3 runs)

Messages in the payload: 5136. Counts, rates and planted ids only; no chat text. Ranges are over n = 3 runs; no ranking of anything.

## Per run

| run | input tokens | output tokens | thinking tokens | stop reason | latency s | cost USD | items in (jokes; moments; awards) | items kept | evidence verified of total | rule-compliant | grounding |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261107T110344-A | 269809 | 2255 | 0 | end_turn | 11.7 | 0.1405 | 7; 6; 3 | 7; 6; 2 | 41 of 44 | 93% | 93% |
| 20261107T110407-A | 269809 | 1710 | 0 | end_turn | 10.1 | 0.1392 | 7; 3; 2 | 7; 3; 2 | 34 of 35 | 97% | 97% |
| 20261107T110421-A | 269809 | 2430 | 0 | end_turn | 9.7 | 0.1410 | 8; 3; 3 | 8; 3; 3 | 48 of 52 | 92% | 92% |

## Summary over runs

- rule-compliant rate: mean 94%; min 92%; max 97%
- grounding rate: mean 94%; min 92%; max 97%
- items kept, running_jokes: mean 7.3; min 7.0; max 8.0
- items kept, moments: mean 4.0; min 3.0; max 6.0
- items kept, awards: mean 2.3; min 2.0; max 3.0
- unplanted items, running_jokes: mean 0.7; min 0.0; max 2.0
- unplanted items, moments: mean 2.3; min 1.0; max 4.0
- unplanted items, awards: mean 2.3; min 2.0; max 3.0
- output tokens: mean 2132; min 1710; max 2430
- thinking tokens: mean 0; min 0; max 0
- latency seconds: mean 10.5; min 9.7; max 11.7
- cost USD: mean 0.1402; min 0.1392; max 0.1410

Drop reasons per run (evidence status counts):

- 20261107T110344-A: other_message 3; verified 41
- 20261107T110407-A: other_message 1; verified 34
- 20261107T110421-A: other_message 4; verified 48

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
| jL | running_jokes | long-range | dev | 2025-11-25 | 2026-10-15 | 2 of 3 | 2 of 3 | - |
| m1 | moments | first | dev | 2026-02-07 | 2026-02-07 | 3 of 3 | 3 of 3 | 3 of 3 |
| m2 | moments | middle | held-out | 2026-04-25 | 2026-04-25 | 2 of 3 | 2 of 3 | 2 of 3 |
| m3 | moments | last | held-out | 2026-10-17 | 2026-10-17 | 0 of 3 | 0 of 3 | 0 of 3 |

### By third of the chat

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| first | j1, j2, m1 | 9 | 9 | 9 | 100% | 100% |
| middle | j3, j4, m2 | 8 | 8 | 9 | 89% | 89% |
| last | j5, j6, m3 | 6 | 6 | 9 | 67% | 67% |
| long-range | jL | 2 | 2 | 3 | 67% | 67% |

### Dev versus held-out

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| dev | j1, j2, jL, m1 | 11 | 11 | 12 | 92% | 92% |
| held-out | j3, j4, j5, j6, m2, m3 | 14 | 14 | 18 | 78% | 78% |

### By type

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| running_jokes | j1, j2, j3, j4, j5, j6, jL | 20 | 20 | 21 | 95% | 95% |
| moments | m1, m2, m3 | 5 | 5 | 9 | 56% | 56% |

Found by date, moments: 5 of 9 item-runs (56%).

## Length distributions of verified items, all runs pooled (characters; numbers only)

| type | field | n | min | median | max | share at most 32 / 110 |
|---|---|---|---|---|---|---|
| running_jokes | title | 22 | 15 | 20.0 | 30 | 100% (limit 32) |
| running_jokes | summary | 22 | 58 | 90.5 | 125 | 82% (limit 110) |
| moments | title | 12 | 20 | 22.0 | 28 | 100% (limit 32) |
| moments | summary | 12 | 63 | 90.0 | 108 | 100% (limit 110) |
| awards | title | 7 | 9 | 16 | 23 | 100% (limit 32) |
| awards | summary | 7 | 69 | 78 | 103 | 100% (limit 110) |
