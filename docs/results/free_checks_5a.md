# Free checks of Phase 5a (numbers only, no chat text)

## (a) Per-file test counts (collect-only) and deltas

Total 541 before Phase 4b, 648 now (delta 107).

| file | before | now | delta |
|---|---|---|---|
| tests/test_analyze.py | 32 | 32 | 0 |
| tests/test_card.py | 31 | 31 | 0 |
| tests/test_card_ai.py | 27 | 27 | 0 |
| tests/test_chunked.py | 0 | 107 | 107 |
| tests/test_cost.py | 8 | 8 | 0 |
| tests/test_dataset.py | 8 | 8 | 0 |
| tests/test_display.py | 35 | 35 | 0 |
| tests/test_evaluate.py | 18 | 18 | 0 |
| tests/test_gen_chat.py | 28 | 28 | 0 |
| tests/test_llm.py | 7 | 7 | 0 |
| tests/test_no_real_client.py | 6 | 6 | 0 |
| tests/test_parser.py | 26 | 26 | 0 |
| tests/test_phase4a.py | 20 | 20 | 0 |
| tests/test_privacy.py | 93 | 93 | 0 |
| tests/test_rating.py | 17 | 17 | 0 |
| tests/test_rating_tool.py | 8 | 8 | 0 |
| tests/test_review.py | 18 | 18 | 0 |
| tests/test_scan_repo.py | 24 | 24 | 0 |
| tests/test_smoke.py | 9 | 9 | 0 |
| tests/test_stats.py | 79 | 79 | 0 |
| tests/test_textnorm.py | 14 | 14 | 0 |
| tests/test_verify.py | 33 | 33 | 0 |

## (b) eval_full_A.json across the mode field change

Fields that differ between the two commits: mode. Every number is identical, and only `mode` was added: **True**.

## (c) Planted jokes per chunk of the exact chunked plan

The joke rule is: at least 3 evidence messages on at least 2 distinct dates. Cells: planted occurrences / distinct dates; `rule` marks a chunk that satisfies the rule on its own.

| joke | total | chunk 1 | chunk 2 | chunk 3 | chunk 4 | chunks meeting the rule alone |
|---|---|---|---|---|---|---|
| j1 | 7 / 4 | 7 / 4 rule | 0 / 0 | 0 / 0 | 0 / 0 | 1 |
| j2 | 7 / 4 | 7 / 4 rule | 0 / 0 | 0 / 0 | 0 / 0 | 1 |
| j3 | 7 / 4 | 0 / 0 | 6 / 3 rule | 1 / 1 | 0 / 0 | 1 |
| j4 | 7 / 4 | 0 / 0 | 5 / 3 rule | 2 / 1 | 0 / 0 | 1 |
| j5 | 7 / 4 | 0 / 0 | 0 / 0 | 5 / 3 rule | 2 / 1 | 1 |
| j6 | 7 / 4 | 0 / 0 | 0 / 0 | 5 / 3 rule | 2 / 1 | 1 |
| jL | 12 / 9 | 4 / 3 rule | 3 / 2 rule | 4 / 3 rule | 1 / 1 | 3 |

The long-range joke jL satisfies the joke rule inside 3 of 4 chunks on its own, and every other planted joke satisfies it inside at least one chunk. **The planted jL does not test long-range dependence; a sparse joke is untested.**

## (d) Where planted items were lost in the chunked runs

Strict misses: 3. Pipeline-induced (evidence on a planted occurrence existed at some stage but the final report does not credit the item): 2. Never proposed (no evidence on a planted occurrence at any stage): 1. The replay of every run matched its saved final report: True.

| run | planted | raw candidates | after merge | after item rules | after caps | lost at |
|---|---|---|---|---|---|---|
| 20261107T114953275-A-chunked | m1 | yes (1 items; 1 planted messages) | yes (1 items; 1 planted messages) | yes (1 items; 1 planted messages) | no (0 items; 0 planted messages) | the caps |
| 20261107T114953275-A-chunked | m3 | yes (1 items; 1 planted messages) | yes (1 items; 1 planted messages) | yes (1 items; 1 planted messages) | no (0 items; 0 planted messages) | the caps |
| 20261107T115025921-A-chunked | m3 | no (0 items; 0 planted messages) | no (0 items; 0 planted messages) | no (0 items; 0 planted messages) | no (0 items; 0 planted messages) | not lost: never proposed |
