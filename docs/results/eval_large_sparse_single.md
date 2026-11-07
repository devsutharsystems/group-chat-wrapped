# Slice evaluation, single mode, config A, phase 5b (n = 1 runs)

Messages in the payload: 5802. Counts, rates and planted ids only; no chat text. Ranges are over n = 1 runs; no ranking of anything.

The payload is the slice that ends on 2026-03-07. Only planted items whose WHOLE span lies inside the slice are scored; items cut by the slice end (jL) are not scored.

## Per run

| run | input tokens | output tokens | thinking tokens | stop reason | latency s | cost USD | items in (jokes; moments; awards) | items kept | evidence verified of total | rule-compliant | grounding |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261107T162630-A | 296849 | 1987 | 0 | end_turn | 13.8 | 0.1534 | 5; 4; 3 | 3; 4; 3 | 29 of 37 | 78% | 84% |

## Summary over runs

- rule-compliant rate: mean 78%; min 78%; max 78%
- grounding rate: mean 84%; min 84%; max 84%
- items kept, running_jokes: mean 3.0; min 3.0; max 3.0
- items kept, moments: mean 4.0; min 4.0; max 4.0
- items kept, awards: mean 3.0; min 3.0; max 3.0
- unplanted items, running_jokes: mean 0.0; min 0.0; max 0.0
- unplanted items, moments: mean 3.0; min 3.0; max 3.0
- unplanted items, awards: mean 3.0; min 3.0; max 3.0
- output tokens: mean 1987; min 1987; max 1987
- thinking tokens: mean 0; min 0; max 0
- latency seconds: mean 13.8; min 13.8; max 13.8
- cost USD: mean 0.1534; min 0.1534; max 0.1534

Drop reasons per run (evidence status counts):

- 20261107T162630-A: id_missing 1; not_found 1; other_message 4; too_short 2; verified 29

## Planted items: strict recall (headline), lenient (secondary), found by date (moments)

Found in k of 1 runs. Strict: at least min(2, planted occurrences) of the AI item's verified evidence messages are occurrences of that planted item and at least half of them are. Lenient: at least one. Found by date: any verified evidence message on the planted date (moments only). Group: the third of the chat holding the midpoint of the item's date span.

| planted id | type | group | split | span from | span to | strict | lenient | by date |
|---|---|---|---|---|---|---|---|---|
| j1 | running_jokes | middle | new-dataset | 2025-11-16 | 2026-02-17 | 1 of 1 | 1 of 1 | - |
| j2 | running_jokes | middle | new-dataset | 2025-12-19 | 2026-01-06 | 1 of 1 | 1 of 1 | - |
| j3 | running_jokes | end | new-dataset | 2026-03-18 | 2026-06-25 | out of scope | out of scope | - |
| j4 | running_jokes | end | new-dataset | 2026-04-01 | 2026-05-25 | out of scope | out of scope | - |
| j5 | running_jokes | end | new-dataset | 2026-09-20 | 2026-10-24 | out of scope | out of scope | - |
| j6 | running_jokes | end | new-dataset | 2026-08-22 | 2026-11-02 | out of scope | out of scope | - |
| jL | running_jokes | long-range | new-dataset | 2026-01-17 | 2026-10-07 | out of scope | out of scope | - |
| m1 | moments | end | new-dataset | 2026-02-07 | 2026-02-07 | 1 of 1 | 1 of 1 | 1 of 1 |
| m2 | moments | end | new-dataset | 2026-04-25 | 2026-04-25 | out of scope | out of scope | - |
| m3 | moments | end | new-dataset | 2026-10-17 | 2026-10-17 | out of scope | out of scope | - |

### By third of the chat

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| start | - | 0 | 0 | 0 | n/a | n/a |
| middle | j1, j2 | 2 | 2 | 2 | 100% | 100% |
| end | m1 | 1 | 1 | 1 | 100% | 100% |
| long-range | - | 0 | 0 | 0 | n/a | n/a |

### Dev versus held-out

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| new-dataset | j1, j2, m1 | 3 | 3 | 3 | 100% | 100% |

### By type

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| running_jokes | j1, j2 | 2 | 2 | 2 | 100% | 100% |
| moments | m1 | 1 | 1 | 1 | 100% | 100% |

Found by date, moments: 1 of 1 item-runs (100%).

## Length distributions of verified items, all runs pooled (characters; numbers only)

| type | field | n | min | median | max | share at most 32 / 110 |
|---|---|---|---|---|---|---|
| running_jokes | title | 3 | 24 | 25 | 32 | 100% (limit 32) |
| running_jokes | summary | 3 | 94 | 99 | 103 | 100% (limit 110) |
| moments | title | 4 | 22 | 23.5 | 31 | 100% (limit 32) |
| moments | summary | 4 | 93 | 94.5 | 106 | 100% (limit 110) |
| awards | title | 3 | 10 | 12 | 17 | 100% (limit 32) |
| awards | summary | 3 | 68 | 81 | 91 | 100% (limit 110) |
