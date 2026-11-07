# Precision of the verified items from hand ratings (config A, phase 4a)

**The three runs are not independent samples: they read the same chat with the same prompt, so the same items and the same mistakes recur across runs and the intervals below understate the real uncertainty.**

Counts and intervals only; no chat text. Strict = rated true. Lenient = true plus partly. Interval: Wilson 95%.

| group | n | true | partly | false | tic | strict | lenient |
|---|---|---|---|---|---|---|---|
| overall | 40 | 21 | 18 | 1 | 0 | 21 of 40; p 0.525; interval lo 0.375; hi 0.671 | 39 of 40; p 0.975; interval lo 0.871; hi 0.996 |
| running_jokes | 21 | 18 | 3 | 0 | 0 | 18 of 21; p 0.857; interval lo 0.654; hi 0.950 | 21 of 21; p 1.000; interval lo 0.845; hi 1.000 |
| moments | 12 | 1 | 11 | 0 | 0 | 1 of 12; p 0.083; interval lo 0.015; hi 0.354 | 12 of 12; p 1.000; interval lo 0.757; hi 1.000 |
| awards | 7 | 2 | 4 | 1 | 0 | 2 of 7; p 0.286; interval lo 0.082; hi 0.641 | 6 of 7; p 0.857; interval lo 0.487; hi 0.974 |
| run 20261107T110344-A | 15 | 6 | 8 | 1 | 0 | 6 of 15; p 0.400; interval lo 0.198; hi 0.643 | 14 of 15; p 0.933; interval lo 0.702; hi 0.988 |
| run 20261107T110407-A | 12 | 8 | 4 | 0 | 0 | 8 of 12; p 0.667; interval lo 0.391; hi 0.862 | 12 of 12; p 1.000; interval lo 0.757; hi 1.000 |
| run 20261107T110421-A | 13 | 7 | 6 | 0 | 0 | 7 of 13; p 0.538; interval lo 0.291; hi 0.768 | 13 of 13; p 1.000; interval lo 0.772; hi 1.000 |
| matching a planted item | 25 | 18 | 7 | 0 | 0 | 18 of 25; p 0.720; interval lo 0.524; hi 0.857 | 25 of 25; p 1.000; interval lo 0.867; hi 1.000 |
| unplanted | 15 | 3 | 11 | 1 | 0 | 3 of 15; p 0.200; interval lo 0.070; hi 0.452 | 14 of 15; p 0.933; interval lo 0.702; hi 0.988 |

Distinct planted items covered by the rated items: lenient 9 (j1, j2, j3, j4, j5, j6, jL, m1, m2); strict 9 (j1, j2, j3, j4, j5, j6, jL, m1, m2).
