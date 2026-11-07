# Commit map: history rewritten once before publishing

Old and new hashes of every commit, oldest first. Removed from history: top-level build/ and data/. Commit count before and after: 49 and 49 (one to one).
Author and committer were rewritten.

| old hash | new hash | date | subject |
|---|---|---|---|
| 96330fa2b932ad62fba09982dfe85d8b5b765ca9 | f81ff2bc32d8071d1d94ab4a6c2fb6c2ebe05aa9 | 2026-11-06 | Phase 0: guardrails, repo scan, scaffold stubs, PRD, API notes |
| 90eb92d9e8aa20f2c6bba0cb528099cfd23de67b | ae5435ce4e7aaefc570624a7f09c3ba0a5cd8d13 | 2026-11-06 | Phase 0b-A: android fixture, PRD parser facts, read denies, scanner phone tests |
| 4c5f79ef138bd2ce861e1db08d7949f4773f9050 | 1d9d688f6cb05e34c7d7821702707326a96d921e | 2026-11-06 | Phase 0b-A2: move local-path deny to gitignored settings.local.json, scan for local paths |
| 1fc15b9b129040935c8c8974d1681261563fa669 | 8192b5917eb922d659e016300958cd033919e3b9 | 2026-11-06 | Phase 0b-A3: scan tracked files only, pre-push path check in CLAUDE.md |
| 476e95da2d0bcd1aa44d8ff68b121d98687329d5 | d26f8bb915c1d31122e2163e7cbb6faae51dace7 | 2026-11-06 | Phase 0b-B: complete api-notes from official docs |
| 4aeeed6eae32a2dea6d86a0ee20b43e9e9a51b60 | 0ecdcfc34f4bd462854773c380a401d41f219a7f | 2026-11-06 | Phase 1a (part 1): cost guard, llm wrapper, spike script, synthetic generator, tests |
| 2b87bc9e3947421ac6e11fbd1cb6d9b5a2f4ae47 | a7b0ae2a2bb026bca7cd4c0d1747c70a1eb86f72 | 2026-11-06 | Phase 1a: spike results, key status line |
| 2d021420db2ce86b673e4b7bbd9af59c98d5333d | 11126b8a85d9b3ccb79aa78701c783b6bcc7325c | 2026-11-06 | Phase 1a: count_tokens calibration, mini-run findings, thinking-disabled option, smaller chat config |
| e5a697d6735fb7e45c464c2148da76515929d0b9 | 2c53dcdcde355f492d46d8d5df69be5407a618a6 | 2026-11-06 | Phase 1a: style cards, banned phrases, repetition check, thinking-disabled mini run, exact estimate |
| fc933fa81398bf8c9f36cfcd22f9023932434a5b | d51932e08f7576df6cfcdccba786e830342d22fd | 2026-11-06 | Phase 1a: full synthetic chat run, 200-line sample, PRD precision rubric |
| f11a8e99aab37b2eb9e0faae4826cd9227f3237b | ea25101a1bc5141470daa86377d34e3eb8102fb3 | 2026-11-06 | Phase 1a: freeze synthetic dataset (verify_dataset), final precision rubric |
| 7defc33a8241108416218599400e86abd222848d | fcb126b60f9a999bfeeb637434154d020f30f100 | 2026-11-06 | Phase 1a close-out: frozen dataset in synthetic/frozen, dataset doc, gate rule |
| c04ca08605ba252ec6d688d320525220873721fc | 86f36fd0755f2d19ad0f0cb24c2cabf5fe81a040 | 2026-11-06 | Hard-code frozen dataset hashes in dataset.py; verify against constants |
| 32a264706f9ca889e6e8e7e809baac4316b1d133 | aadca3e6d5aa83cf533158bf2a9072f3c7cad9ae | 2026-11-06 | Phase 1b: WhatsApp parser, textnorm, tests |
| 4d78b55b38b081ff10ba4613332a46d8b7a2bc14 | ff31b9842d1bb31c3ccb24e767928bc4825f2e1f | 2026-11-06 | Phase 1b-fix: messages() helper, first/last message timestamps, mutation-killing test |
| 4d794f0962f2bb2e479e5a7e2627630a5862236d | d4d19ed45d13db348439882d5ab3c63ff312311e | 2026-11-06 | Phase 2a: stats (compute_stats), regex dependency, PRD stats behaviour, scratch-dir rule |
| 25cc1117536e24603cc0543d7e8f5077ea3f51cd | 24219f8d424d1e9a1846583d49f3842da50440e5 | 2026-11-06 | Phase 2a-fix: whole-word laughs, (c)(r)TM need FE0F, stats verification doc |
| 6a6e9c079a25a3316cb85e15102062e47fddcfa8 | 78fa7ab98cf2b976e9cda9605add2e40d966edab | 2026-11-06 | Phase 2b: stats-only card (card.py, cli.py), window first/last timestamps, R4 split, resource rules |
| 6132626992e8f6440da3de58280bfbd19070d3c2 | 1f408ebcd40d2b12c47f684471bbff14f39a5781 | 2026-11-06 | Phase 2b-fix: reserved 460px Zone 2, top-talkers leaders highlighted, six tiles + stat strip, editable install, one-browser guard, README |
| f30416c921e984a9760da236aba9ae385e44df2e | 4e0013cc018898f422c72c3a0992e673264393a1 | 2026-11-06 | Phase 2b-fix2: non-editable install test (cannot skip), fastest responder needs 120 s gap, busiest weekday/hour tile, docs |
| f366d9c13bed5e619c836b873bdae90945f9d2cd | 750f7c66bbf99d0982ca7698ce6961f7f1394e9d | 2026-11-06 | Phase 3a: privacy layer (pseudonymise, redact, sensitive screen, payload preview); untrack build/ |
| 16035cb290c335e5ba01b9d76cc4a404ab7a5613 | 782b83192c915b485ce1cb5d1b61b164bfa0cbe0 | 2026-11-06 | Phase 3a-fix: keyword list packaged (fine -> fined), joint busiest-slot tile, survivor tests, pre-push history check |
| f9a3c31fdfc88530d1ba0601abac3558e200e19a | 30f75028a0500e5102e92b576a5d3ed12258944f | 2026-11-06 | Phase 3a-fix2: party -> political party in the keyword list, planted-item test now passes, privacy limits documented |
| 6dab3eeaa9c92b19d519d9c4b02d6e72e4739f41 | ecc8f8693e380c05cbe3c99c53428075876e7eb6 | 2026-11-06 | Phase 3b: analyze (Haiku configs A/B/C), verify (exact-quote evidence), injection defence, live runs on the frozen slice |
| b18fa249e86e6e9c090fffb0752e033bd7eef670 | 1ccff3ae6f39dbbcf632ed5e639eca44495c5e8c | 2026-11-06 | Phase 3b-fix: prompt v1 hash, strict recall, evidence analysis, replication and injection probe, global network block, opt-in response saving |
| 426baf58305f343bdf2178ff8398e489427c7b3c | 913731160462acf1bbe65a702d672f2bf0168dfe | 2026-11-06 | Phase 3c: review gate, display layer, AI Zone 2 and footer, card/review commands, found-by-date, render rules |
| 20a5272cf41ec2a1698278e8fe8be9f6dc954e9e | 423fe4a453553b189861903df2062bb37becfb26 | 2026-11-06 | Phase 3c-fix: 20 px font floor in Zone 2 and footer, two-line AI footer, tighter cards, review rank, derived-slice warning |
| 11a98b414cf54e4fea29da619f832f445651f63b | 9e56bb56a40d582b854b88a280b9ba21a5fc14a3 | 2026-11-06 | Phase 3c-fix: test that kills the boolean-rank mutant |
| e25f9a0a4c108ab0d6ad17b6e4dcd9d012ef1de6 | 40cb235ceb7aaa6c6c7487ac95a5059bffa8801d | 2026-11-07 | Phase 3c-fix2: 3-line summaries with sentence-end truncation, 22 px award names, 20 px member names |
| e5fcfbfc9890f4d94ee4a29ce11d0b3a0200cf97 | cd369754a6d2e1f3a63a7bb3d800a15739238881 | 2026-11-07 | Phase 4a tooling: evaluate and rating-pack commands, big-run guards (max input tokens, max run cost, frozen dataset, prompt version check) |
| 43c122459e5256673b76a40cc21f5528690f3fe5 | 4cf2c38c7ec2468623024ae26f4b077fb511927d | 2026-11-07 | Phase 4a: full-chat evaluation (3 runs, config A, prompt v1), results files, README citation rule |
| 959b194ad197c10f014b9ead5301665d7f700b5f | 35a521f3194ed5e0c1e382a09c1e7556c66f4f84 | 2026-11-07 | Phase 4a-fix: rubric, working rating tool, rating-score, miss diagnostic |
| f12bba35692410f368b110416cc4882ee2203f37 | cd8e87fe7c0213e794fe5e0039848e109ff2f1ba | 2026-11-07 | Phase 4b tooling: chunked map-reduce (R5), reduce prompt, candidate verification, compare-modes; PRD predictions written before any chunked run |
| 40bd88772c7de043c6c8370627e1a1764bd6ebbb | d678cbc5e61cfd4caf59c2674ab340bf02d3bc72 | 2026-11-07 | Phase 4b: three chunked runs, eval_full_chunked, compare_single_vs_chunked, README note |
| c83f302a8b76e3516de20d0737153c0efbab93ec | 43d86a9746e2df2db058c953f8ae37aa24ccfc51 | 2026-11-07 | Phase 5a stage 1: free checks, large-dataset tooling (config, generator options, dataset check), no-retry, chunked-loss diagnostic |
| c377a9702dc5e8a5e3df0d2f7db4b1fdb2e3d29e | 2846d0f9f748b2428ed50ea07b4a90339bdc0367 | 2026-11-07 | Phase 5a: large frozen dataset (17K messages, 889K tokens), near-1M single-pass run (n=1), eval_large_A, rate-limit probe, docs |
| 4109bc94c8fd798b9c67770d2361a90512a53651 | 429cb2d8a35202931bf0a1228d8a6fd59746e40c | 2026-11-07 | Phase 5b tooling: free diagnosis of the near-1M run, slice scoring, max-chunks and reduce-version guards, compare-large; PRD predictions written before any live call |
| 185f6a3c268ef5d2800de2589cd09ffe25f3ba07 | 2b840e547ac7821bac5d846ec222485b25e80dda | 2026-11-07 | Phase 5b results: sparse-slice control, chunked run on the large chat, compare_large, PRD R5 and README facts |
| 40ed957bb52f480d0101045453fcca923a07c5ea | a2dd7999e9d49bec14ac4d05f21de6ecdfdb2845 | 2026-11-07 | Phase 6: Streamlit app (appcore, app, render child), auto threshold 300,000 tokens, diag reconciliation, README/PRD |
| c9c09bb789f2a363e896eff15909fa35514f1cf6 | b06d96f4e62f974bc8f817de2f3bca428694605d | 2026-11-07 | Phase 6-fix (partial): slow end-to-end render test, sequential-session screenshot script with per-step RSS sampler; screenshots not produced (1 GB limit) |
| 79b9df6e91f2b7caca5ef7daeed5e26c2be188ed | c68bbe9f57c26108580804dba2a5cd78e6902fde | 2026-11-07 | Phase 6-fix2: screenshots of the app on the synthetic demo chat, harness ceiling 1.4 GB with reason, measured footprint in README |
| a054e34e1542404e5aa11dcea13e806dd2fc3b3b | 2c5ca0aab3e2fb79417490383951eb8977a1c168 | 2026-11-07 | Phase 6-fix3: GCW_LEDGER_PATH, demo ledger and toolbarMode viewer for screenshots, four images, run-log window check, AI-card render test |
| ca79b6e8aaa917f379ef1f20fd6acbe384dceec0 | 6528a1f79bcdbe0ecef97a08cc95540ef18adcb5 | 2026-11-07 | Phase 6-fix4: screenshots without the menu, whole review page and complete card, harness assertions |
| e2eef3f1b65b4b32aaec74d108d7aec293a37942 | fa0f6f5fe71e2b6b5b2974e9f9f5cf4665bbfbad | 2026-11-07 | Phase 7a: README rewrite with generated tables, prepublish check, cropped review image |
| c6cb02d5473837af2b5161625f814a41b9d9d042 | bb46c18bee086de3b618d249b36c1d7b9856b079 | 2026-11-07 | Phase 7b: memory provenance, history-blob and mentions checks, CI and Pages workflows, static demo site, publish checklist |
| 1bc8db8ed4ea8d55b72fb5064aa09d58ef1efd7c | 41bb41ae902e7a673d60a11db324d3798312230a | 2026-11-07 | Phase 7c: untrack data/, name mentions and licence line, rewrite_history.sh and update_hash_refs.py (not run on the real repo), publish checklist |
| 57b86b6cf37091de62adae5d765489beb247ba73 | 8d1723f1e4f981e4ecbc458525ab0feabf01b6ed | 2026-11-07 | Phase 7d: approval_mode and honest footer, review screen layout and DOM-sized capture, stopword-safe truncation, real-format check, README and memory fixes |
| fb1b613e75d46b14cfca9047c889d36ea42578e2 | 041071a78e1fdb11c544debc848da78730fa5983 | 2026-11-07 | Precision from hand ratings (counts only), README precision block with per-run and planted rows, stale precision wording corrected |
| c1cdbf541af06685c9a2b840c1991a321874c159 | 8074a5710e0d2ae1d8e361733f7e2ee59b791ac5 | 2026-11-07 | Phase 7e: README definitions (config A, tested on, rule-compliant rate, item rules), results in brief, rubric and standard in the precision block, limits additions |
