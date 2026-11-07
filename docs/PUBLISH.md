# Publish checklist (in order)

Nothing here has been run. `python scripts/prepublish_check.py` prints one PASS or FAIL line per check; publish only when every blocking check passes. CLAUDE.md applies: no `git remote` and no `git push` until you have seen the exact command and approved it.

**Status after Phase 8a:** steps 4 and 5 are done (history rewritten once, hash references updated, `docs/results/commit_map.md` committed); the blockers `commit_map.md exists` and `history: no build artefacts` below are cleared. The table is kept as the record of what each check guards.

## Blockers today (the checks that fail, by their printed names)

| check | why it fails | cleared by |
|---|---|---|
| `precision_A.json exists` | the hand ratings are not made, so there is no precision file | steps 1 and 2 |
| `commit_map.md exists` | the history has not been rewritten | step 4 |
| `history: no build artefacts` | 26 history entries under `build/` (first added in commit 4e0013c) | step 4 |
| `history: no blob over 1 MB` | `data/synthetic_large/chat_full.txt` (1.9 MB) is in history; it is untracked at the tip since Phase 7c, but old commits still hold it | step 4 |
| `git status clean` | fails whenever there are uncommitted changes | commit |
| `readme blocks fresh` | fails only if `docs/results/*.json` changed after the README tables were built | step 3 |

## Steps, in this order

1. **Ratings.** Rate every item in `out/rating/ratings.csv` by hand (the blind pack).
2. **Precision.** `python -m gcw rating-score --ratings out/rating/ratings.csv --key out/rating/key.json --out docs/results/precision_A`. Until then the README says "Precision: not yet measured (hand-rating pending)" and claims no precision number.
3. **README tables and site.** `python scripts/build_readme_tables.py`, then `python scripts/build_site.py` so `site/methodology.html` matches. Commit.
4. **History rewrite (last step before the push).** `scripts/rewrite_history.sh`, once, on the real repository, after the working tree is clean and committed. It refuses if a remote exists, the tree is dirty, HEAD is not on main or any other ref exists; it removes top-level `build/` and `data/` from every commit (never `src/gcw/data`), keeps the commit count 1:1, writes `docs/results/commit_map.md` (uncommitted) and deletes the backup refs. Optional author rewrite: `NEW_NAME='...' NEW_EMAIL='...' scripts/rewrite_history.sh` (both required; off by default; decide first: see the author facts in the Phase 7c report). It was rehearsed in a clone in Phase 7c; it has never been run on the real repository. Keep a copy of the whole folder (`cp -R`) until the checks below are green: the script deletes its own backup refs.
5. **Update stale hash references.** `python scripts/update_hash_refs.py` (dry run lists them), then `--apply`, then commit `docs/results/commit_map.md` together with the updated README and docs (one commit after the rewrite; its hash is not in the map).
6. **Pre-publish check green.** `python scripts/prepublish_check.py` must end with 13 of 13 checks passed. Read the INFO block ("mentions") and decide what stays; it never blocks.
7. **Private push.** Create the repository private, add the remote, push (commands below).
8. **CI green.** `.github/workflows/ci.yml` runs on the push: pytest on Python 3.11 and 3.13, `scan_repo`, and the pre-publish check. It has never run (UNVERIFIED): expect to fix Linux differences (fonts, pinned wheels) before it is green.
9. **Public flip.** GitHub Pages needs a public repository on the Free plan (https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site).
10. **Pages enable.** Settings, Pages, Build and deployment, Source: GitHub Actions (a branch source can only publish `/` or `/docs`: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site). `.github/workflows/pages.yml` then publishes the committed `site/` folder unchanged. Rebuild `site/` with `python scripts/build_site.py --repo-url <the public URL>` once the URL exists.

## Commands for later (NOT run)

```sh
gh repo create group-chat-wrapped --private                                # empty private repository under the logged-in account
git remote add origin https://github.com/<OWNER>/group-chat-wrapped.git   # or the ssh URL of the repository
git push -u origin main
# Settings > Pages > Source: GitHub Actions   (in the browser)
gh repo edit <OWNER>/group-chat-wrapped --visibility public --accept-visibility-change-consequences
```

`.gitignore` covers `out/`, `data/`, `.env`, `.env.*`, `aliases.json`, `ratings.csv`, `key.json` and `.cache/`.
