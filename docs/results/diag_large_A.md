# Diagnosis of the saved near-1M run (numbers and ids only)

Definitions: the nearest verbatim match is the closest message (by id distance) whose normalised text contains the quote; ambiguous = the quote's text appears in more than one message; exact = it equals the whole message.

## (a) Dropped evidence items

| item | evidence index | status | cited id | nearest match | distance | matches | ambiguous | exact | nearest is planted | planted among all matches |
|---|---|---|---|---|---|---|---|---|---|---|
| running_jokes[2] | 1 | other_message | m015653 | m010653 | 5000 | 4 | yes | yes | j3 | j3 |
| running_jokes[3] | 1 | other_message | m015525 | m015526 | 1 | 4 | yes | yes | j5 | j5 |
| running_jokes[5] | 0 | other_message | m009535 | m009526 | 9 | 4 | yes | yes | j4 | j4 |
| running_jokes[5] | 1 | too_short | m011150 | m011123 | 27 | 51 | yes | yes | no | - |
| moments[1] | 0 | other_message | m011673 | m011677 | 4 | 1 | no | no | no | - |
| moments[1] | 1 | other_message | m015496 | none | - | 0 | no | no | no | - |
| awards[0] | 0 | other_message | m014823 | m014826 | 3 | 1 | no | yes | no | - |
| awards[0] | 1 | other_message | m015231 | m011555 | 3676 | 1 | no | yes | no | - |
| awards[1] | 0 | other_message | m010506 | m010510 | 4 | 1 | no | yes | no | - |
| awards[1] | 1 | other_message | m016718 | m005713 | 11005 | 1 | no | yes | no | - |
| awards[2] | 0 | not_found | m011538 | none | - | 0 | no | no | no | - |
| awards[2] | 1 | other_message | m015011 | m010297 | 4714 | 1 | no | no | no | - |

## (b) Proposed items: evidence items that quote a planted line

| item | evidence items | quoting planted lines (planted id: count) |
|---|---|---|
| running_jokes[0] | 2 | none |
| running_jokes[1] | 2 | j1: 1 |
| running_jokes[2] | 2 | j3: 2 |
| running_jokes[3] | 2 | j5: 2 |
| running_jokes[4] | 2 | j6: 2 |
| running_jokes[5] | 2 | j4: 1 |
| moments[0] | 1 | none |
| moments[1] | 2 | none |
| moments[2] | 2 | none |
| moments[3] | 2 | none |
| awards[0] | 2 | none |
| awards[1] | 2 | none |
| awards[2] | 2 | none |

## (c) Planted items

Evidence quoting a planted line of the item, by any proposed item of any type:

| planted id | proposed items | evidence kept | evidence dropped |
|---|---|---|---|
| j1 | 1 | 1 | 0 |
| j2 | 0 | 0 | 0 |
| j3 | 1 | 1 | 1 |
| j4 | 1 | 0 | 1 |
| j5 | 1 | 1 | 1 |
| j6 | 1 | 2 | 0 |
| jL | 0 | 0 | 0 |
| m1 | 0 | 0 | 0 |
| m2 | 0 | 0 | 0 |
| m3 | 0 | 0 | 0 |

Hypothetical re-pointing (measure only; the pipeline is unchanged):

- as run: strict found none
- every dropped quote re-pointed to its nearest verbatim match (9 quotes): evidence verified 22 of 25; items kept {'running_jokes': 0, 'moments': 4, 'awards': 3}; strict found none
- only unambiguous quotes re-pointed (6 quotes): evidence verified 19 of 25; items kept {'running_jokes': 0, 'moments': 4, 'awards': 3}; strict found none

## (d) Planted-line density

| chat | planted messages | payload messages | fraction |
|---|---|---|---|
| original chat | 67 | 5136 | 1.30% |
| large chat | 67 | 17097 | 0.39% |

Large chat, planted lines excluded: 19 distinct messages of 4+ words appear more than 3 times. Top 10 word 3-grams with counts: so we can 229; i think the 198; and we can 193; i keep thinking 174; honestly i think 170; on the way 167; let's do it 166; sounds like a 165; honestly though i 163; i'll sort the 160.
