# Single-pass versus chunked map-reduce (n = 3 runs and n = 3 runs; frozen synthetic chat; config A, prompt v1)

Predictions were written to `docs/PRD.md` and committed before any chunked run in commit cd8e87f. Counts and ids only; no chat text. Real chats differ: the synthetic planted items are easier than real jokes.

## Planted items found (strict), in k of n runs

| planted id | type | group | split | single-pass | chunked | single-pass lenient | chunked lenient |
|---|---|---|---|---|---|---|---|
| j1 | running_jokes | first | dev | 3 of 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| j2 | running_jokes | first | dev | 3 of 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| j3 | running_jokes | middle | held-out | 3 of 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| j4 | running_jokes | middle | held-out | 3 of 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| j5 | running_jokes | last | held-out | 3 of 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| j6 | running_jokes | last | held-out | 3 of 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| jL | running_jokes | long-range | dev | 2 of 3 | 3 of 3 | 2 of 3 | 3 of 3 |
| m1 | moments | first | dev | 3 of 3 | 2 of 3 | 3 of 3 | 2 of 3 |
| m2 | moments | middle | held-out | 2 of 3 | 3 of 3 | 2 of 3 | 3 of 3 |
| m3 | moments | last | held-out | 0 of 3 | 1 of 3 | 0 of 3 | 1 of 3 |

## Other numbers (mean; min; max over runs)

| measure | single-pass | chunked |
|---|---|---|
| rule-compliant rate | mean 94%; min 92%; max 97% | mean 90%; min 88%; max 93% |
| grounding rate | mean 94%; min 92%; max 97% | mean 95%; min 94%; max 97% |
| items kept, running_jokes | mean 7.3; min 7.0; max 8.0 | mean 9.7; min 9.0; max 10.0 |
| items kept, moments | mean 4.0; min 3.0; max 6.0 | mean 6.0; min 6.0; max 6.0 |
| items kept, awards | mean 2.3; min 2.0; max 3.0 | mean 5.7; min 5.0; max 6.0 |
| unplanted items, running_jokes | mean 0.7; min 0.0; max 2.0 | mean 2.7; min 2.0; max 3.0 |
| unplanted items, moments | mean 2.3; min 1.0; max 4.0 | mean 4.0; min 3.0; max 5.0 |
| unplanted items, awards | mean 2.3; min 2.0; max 3.0 | mean 5.7; min 5.0; max 6.0 |
| cost USD per run (from usage) | mean 0.1402; min 0.1392; max 0.1410 | mean 0.0329; min 0.0323; max 0.0335 |
| latency seconds (single: the one call; chunked: sum of all call latencies) | mean 10.5; min 9.7; max 11.7 | mean 41.4; min 38.1; max 46.4 |
| wall-clock seconds (chunked, map calls in parallel) | not measured | mean 18.5; min 17.1; max 20.9 |
| output tokens | mean 2132; min 1710; max 2430 | mean 9310; min 8101; max 10340 |

## Predictions

1. Chunked cost per run below 40% of single-pass: chunked mean 0.0329 against a limit of 0.0561, which is 40% of the single-pass mean 0.1402: **held**.
2. jL found (strict) in fewer chunked runs than in single-pass: chunked 3 of 3, single-pass 2 of 3: **did not hold**.
3. Each of the six other jokes within one item-run of single-pass: differences j1 0, j2 0, j3 0, j4 0, j5 0, j6 0: **held**.
4. Moments: no prediction. Strict found item-runs, single-pass 5 of 9, chunked 6 of 9.

