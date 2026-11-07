# Full-chat evaluation, chunked mode, config A, phase 5b (n = 1 runs)

Messages in the payload: 17097. Counts, rates and planted ids only; no chat text. Ranges are over n = 1 runs; no ranking of anything.

## Per run

| run | input tokens | output tokens | thinking tokens | stop reason | latency s | cost USD | items in (jokes; moments; awards) | items kept | evidence verified of total | rule-compliant | grounding |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261107T162947022-A-chunked | 923596 | 21126 | 0 | None | 102.1 | 0.1029 | 44; 46; 27 | 10; 6; 6 | 245 of 282 | 87% | 96% |

Chunked runs (calls, wall-clock seconds, sum of call latencies, candidates before merging, items after the merge and after the item rules):

| run | chunks | calls | wall-clock s | sum of call latencies s | candidates | after merge | after rules |
|---|---|---|---|---|---|---|---|
| 20261107T162947022-A-chunked | 11 | 12 | 42.0 | 102.1 | 115 | 77 | 66 |

## Summary over runs

- rule-compliant rate: mean 87%; min 87%; max 87%
- grounding rate: mean 96%; min 96%; max 96%
- items kept, running_jokes: mean 10.0; min 10.0; max 10.0
- items kept, moments: mean 6.0; min 6.0; max 6.0
- items kept, awards: mean 6.0; min 6.0; max 6.0
- unplanted items, running_jokes: mean 5.0; min 5.0; max 5.0
- unplanted items, moments: mean 6.0; min 6.0; max 6.0
- unplanted items, awards: mean 6.0; min 6.0; max 6.0
- output tokens: mean 21126; min 21126; max 21126
- thinking tokens: mean 0; min 0; max 0
- latency seconds: mean 102.1; min 102.1; max 102.1
- cost USD: mean 0.1029; min 0.1029; max 0.1029
- wall-clock seconds: mean 42.0; min 42.0; max 42.0
- candidates before merging: mean 115.0; min 115.0; max 115.0
- items after the merge: mean 77.0; min 77.0; max 77.0
- items after the item rules: mean 66.0; min 66.0; max 66.0

Drop reasons per run (evidence status counts):

- 20261107T162947022-A-chunked: media 3; normalisation_only 1; not_found 2; other_message 6; too_short 25; verified 245

## Planted items: strict recall (headline), lenient (secondary), found by date (moments)

Found in k of 1 runs. Strict: at least min(2, planted occurrences) of the AI item's verified evidence messages are occurrences of that planted item and at least half of them are. Lenient: at least one. Found by date: any verified evidence message on the planted date (moments only). Group: the third of the chat holding the midpoint of the item's date span.

| planted id | type | group | split | span from | span to | strict | lenient | by date |
|---|---|---|---|---|---|---|---|---|
| j1 | running_jokes | start | new-dataset | 2025-11-16 | 2026-02-17 | 1 of 1 | 1 of 1 | - |
| j2 | running_jokes | start | new-dataset | 2025-12-19 | 2026-01-06 | 1 of 1 | 1 of 1 | - |
| j3 | running_jokes | middle | new-dataset | 2026-03-18 | 2026-06-25 | 1 of 1 | 1 of 1 | - |
| j4 | running_jokes | middle | new-dataset | 2026-04-01 | 2026-05-25 | 0 of 1 | 0 of 1 | - |
| j5 | running_jokes | end | new-dataset | 2026-09-20 | 2026-10-24 | 1 of 1 | 1 of 1 | - |
| j6 | running_jokes | end | new-dataset | 2026-08-22 | 2026-11-02 | 0 of 1 | 0 of 1 | - |
| jL | running_jokes | long-range | new-dataset | 2026-01-17 | 2026-10-07 | 1 of 1 | 1 of 1 | - |
| m1 | moments | start | new-dataset | 2026-02-07 | 2026-02-07 | 0 of 1 | 0 of 1 | 0 of 1 |
| m2 | moments | middle | new-dataset | 2026-04-25 | 2026-04-25 | 0 of 1 | 0 of 1 | 0 of 1 |
| m3 | moments | end | new-dataset | 2026-10-17 | 2026-10-17 | 0 of 1 | 0 of 1 | 0 of 1 |

### By third of the chat

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| start | j1, j2, m1 | 2 | 2 | 3 | 67% | 67% |
| middle | j3, j4, m2 | 1 | 1 | 3 | 33% | 33% |
| end | j5, j6, m3 | 1 | 1 | 3 | 33% | 33% |
| long-range | jL | 1 | 1 | 1 | 100% | 100% |

### Dev versus held-out

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| new-dataset | j1, j2, j3, j4, j5, j6, jL, m1, m2, m3 | 5 | 5 | 10 | 50% | 50% |

### By type

| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |
|---|---|---|---|---|---|---|
| running_jokes | j1, j2, j3, j4, j5, j6, jL | 5 | 5 | 7 | 71% | 71% |
| moments | m1, m2, m3 | 0 | 0 | 3 | 0% | 0% |

Found by date, moments: 0 of 3 item-runs (0%).

## Length distributions of verified items, all runs pooled (characters; numbers only)

| type | field | n | min | median | max | share at most 32 / 110 |
|---|---|---|---|---|---|---|
| running_jokes | title | 10 | 16 | 27.0 | 41 | 70% (limit 32) |
| running_jokes | summary | 10 | 73 | 85.5 | 107 | 100% (limit 110) |
| moments | title | 6 | 15 | 22.0 | 29 | 100% (limit 32) |
| moments | summary | 6 | 86 | 94.5 | 104 | 100% (limit 110) |
| awards | title | 6 | 12 | 16.5 | 29 | 100% (limit 32) |
| awards | summary | 6 | 77 | 86.5 | 95 | 100% (limit 110) |

# Where planted items were lost in the chunked runs (numbers only)

Strict misses: 5. Pipeline-induced (evidence on a planted occurrence existed at some stage but the final report does not credit the item): 3. Never proposed (no evidence on a planted occurrence at any stage): 2. The replay of every run matched its saved final report: True.

| run | planted | raw candidates | after merge | after item rules | after caps | lost at |
|---|---|---|---|---|---|---|
| 20261107T162947022-A-chunked | j4 | yes (2 items; 4 planted messages) | yes (1 items; 4 planted messages) | yes (1 items; 4 planted messages) | no (0 items; 0 planted messages) | the caps |
| 20261107T162947022-A-chunked | j6 | yes (1 items; 4 planted messages) | yes (1 items; 4 planted messages) | yes (1 items; 4 planted messages) | no (0 items; 0 planted messages) | the caps |
| 20261107T162947022-A-chunked | m1 | yes (1 items; 1 planted messages) | yes (1 items; 1 planted messages) | yes (1 items; 1 planted messages) | no (0 items; 0 planted messages) | the caps |
| 20261107T162947022-A-chunked | m2 | no (0 items; 0 planted messages) | no (0 items; 0 planted messages) | no (0 items; 0 planted messages) | no (0 items; 0 planted messages) | not lost: never proposed |
| 20261107T162947022-A-chunked | m3 | no (0 items; 0 planted messages) | no (0 items; 0 planted messages) | no (0 items; 0 planted messages) | no (0 items; 0 planted messages) | not lost: never proposed |
