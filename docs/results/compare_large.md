# Scale comparison on the large synthetic chat (config A, prompt v1; counts and ids only, no chat text)

Predictions were written to `docs/PRD.md` and committed before any live call in commit 429cb2d. n is the number of runs per row; rows with n = 1 are single observations. Costs are computed from usage fields times list prices (requests above 100,000 prompt tokens use the higher tier) and are not reconciled with the Console. Latency of a chunked row is the sum of all call latencies; its map calls run in parallel, so the wall-clock time is shorter. Input tokens of a chunked row are the sum over all its calls. The planted density differs between rows, so the rows are not a controlled comparison: the large chat holds the same 67 planted lines as the original in 3.3 times more chat.

| row | n | messages | input tokens (mean) | planted density | planted items in scope | strict found (item-runs) | verified evidence | unplanted items (awards / moments / jokes) | cost USD per run | latency s per run |
|---|---|---|---|---|---|---|---|---|---|---|
| dense chat, single-pass | 3 | 5136 | 269809 | 1.30% | j1, j2, j3, j4, j5, j6, jL, m1, m2, m3 | 25 of 30 | 123 of 131 (94%) | 7 / 7 / 2 | 0.1402 | 10.5 |
| sparse chat, first third, single-pass | 1 | 5802 | 296849 | 0.36% | j1, j2, m1 | 3 of 3 | 29 of 37 (78%) | 3 / 3 / 0 | 0.1534 | 13.8 |
| sparse chat, whole, single-pass | 1 | 17097 | 889497 | 0.39% | j1, j2, j3, j4, j5, j6, jL, m1, m2, m3 | 0 of 10 | 13 of 25 (52%) | 0 / 3 / 0 | 0.4483 | 39.8 |
| sparse chat, whole, chunked | 1 | 17097 | 923596 | 0.39% | j1, j2, j3, j4, j5, j6, jL, m1, m2, m3 | 5 of 10 | 245 of 282 (87%) | 6 / 6 / 5 | 0.1029 | 102.1 |

## Predictions (chunked run on the large chat)

1. Chunked cost under $0.18: $0.1029: **held**.
2. Verified-evidence rate at least 80% (over the map calls): 245 of 282 (87%): **held**.
3. At least 3 of the 10 planted items found (strict): 5 of 10: **held**.

## Recorded rule for the sparse slice

If the sparse first-third control finds none of its scored planted items (j1, j2, m1), the README says signal sparsity, not context length alone, explains the near-1M result. The control found 3 of 3 (strict): the rule does not apply. The full-size single-pass row found 0 of 10.

