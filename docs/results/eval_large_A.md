# Full-chat evaluation, single mode, config A, phase 5a (n = 1 runs)

Messages in the payload: 17097. Counts, rates and planted ids only; no chat text. Ranges are over n = 1 runs; no ranking of anything.

## Per run

| run | input tokens | output tokens | thinking tokens | stop reason | latency s | cost USD | items in (jokes; moments; awards) | items kept | evidence verified of total | rule-compliant | grounding |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261107T155152-A | 889497 | 1434 | 0 | end_turn | 39.8 | 0.4483 | 6; 4; 3 | 0; 3; 0 | 13 of 25 | 52% | 52% |

## Summary over runs

- rule-compliant rate: mean 52%; min 52%; max 52%
- grounding rate: mean 52%; min 52%; max 52%
- items kept, running_jokes: mean 0.0; min 0.0; max 0.0
- items kept, moments: mean 3.0; min 3.0; max 3.0
- items kept, awards: mean 0.0; min 0.0; max 0.0
- unplanted items, running_jokes: mean 0.0; min 0.0; max 0.0
- unplanted items, moments: mean 3.0; min 3.0; max 3.0
- unplanted items, awards: mean 0.0; min 0.0; max 0.0
- output tokens: mean 1434; min 1434; max 1434
- thinking tokens: mean 0; min 0; max 0
- latency seconds: mean 39.8; min 39.8; max 39.8
- cost USD: mean 0.4483; min 0.4483; max 0.4483

Drop reasons per run (evidence status counts):

- 20261107T155152-A: not_found 1; other_message 10; too_short 1; verified 13

## Planted items: strict recall (headline), lenient (secondary), found by date (moments)

Found in k of 1 runs. Strict: at least min(2, planted occurrences) of the AI item's verified evidence messages are occurrences of that planted item and at least half of them are. Lenient: at least one. Found by date: any verified evidence message on the planted date (moments only). Group: the third of the chat holding the midpoint of the item's date span.

| planted id | type | group | split | span from | span to | strict | lenient | by date |
|---|---|---|---|---|---|---|---|---|
| j1 | running_jokes | start | new-dataset | 2025-11-16 | 2026-02-17 | 0 of 1 | 0 of 1 | - |
| j2 | running_jokes | start | new-dataset | 2025-12-19 | 2026-01-06 | 0 of 1 | 0 of 1 | - |
| j3 | running_jokes | middle | new-dataset | 2026-03-18 | 2026-06-25 | 0 of 1 | 0 of 1 | - |
| j4 | running_jokes | middle | new-dataset | 2026-04-01 | 2026-05-25 | 0 of 1 | 0 of 1 | - |
| j5 | running_jokes | end | new-dataset | 2026-09-20 | 2026-10-24 | 0 of 1 | 0 of 1 | - |
| j6 | running_jokes | end | new-dataset | 2026-08-22 | 2026-11-02 | 0 of 1 | 0 of 1 | - |
| jL | running_jokes | long-range | new-dataset | 2026-01-17 | 2026-10-07 | 0 of 1 | 0 of 1 | - |
| m1 | moments | start | new-dataset | 2026-02-07 | 2026-02-07 | 0 of 1 | 0 of 1 | 0 of 1 |
| m2 | moments | middle | new-dataset | 2026-04-25 | 2026-04-25 | 0 of 1 | 0 of 1 | 0 of 1 |
| m3 | moments | end | new-dataset | 2026-10-17 | 2026-10-17 | 0 of 1 | 0 of 1 | 0 of 1 |

### By third of the chat

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| start | j1, j2, m1 | 0 | 0 | 3 | 0% | 0% |
| middle | j3, j4, m2 | 0 | 0 | 3 | 0% | 0% |
| end | j5, j6, m3 | 0 | 0 | 3 | 0% | 0% |
| long-range | jL | 0 | 0 | 1 | 0% | 0% |

### Dev versus held-out

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| new-dataset | j1, j2, j3, j4, j5, j6, jL, m1, m2, m3 | 0 | 0 | 10 | 0% | 0% |

### By type

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| running_jokes | j1, j2, j3, j4, j5, j6, jL | 0 | 0 | 7 | 0% | 0% |
| moments | m1, m2, m3 | 0 | 0 | 3 | 0% | 0% |

Found by date, moments: 0 of 3 item-runs (0%).

## Length distributions of verified items, all runs pooled (characters; numbers only)

| type | field | n | min | median | max | share at most 32 / 110 |
|---|---|---|---|---|---|---|
| running_jokes | title | 0 | None | None | None | n/a (limit 32) |
| running_jokes | summary | 0 | None | None | None | n/a (limit 110) |
| moments | title | 3 | 20 | 26 | 37 | 67% (limit 32) |
| moments | summary | 3 | 82 | 91 | 91 | 100% (limit 110) |
| awards | title | 0 | None | None | None | n/a (limit 32) |
| awards | summary | 0 | None | None | None | n/a (limit 110) |
