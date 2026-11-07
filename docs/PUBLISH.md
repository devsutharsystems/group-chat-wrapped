# Publish checklist (in order)

Nothing here has been run. `python scripts/prepublish_check.py` prints one PASS or FAIL line per check; publish only when every blocking check passes. CLAUDE.md applies: no `git remote` and no `git push` until you have seen the exact command and approved it.

## Blockers today (the checks that fail, by their printed names)

| check | why it fails | cleared by |
|---|---|---|
| `precision_A.json exists` | the hand ratings are not made, so there is no precision file | step 1 |
| `commit_map.md exists` | the history has not been rewritten | step 3 |
| `history: no build artefacts` | 26 history entries under `build/` (first added in commit f30416c) | step 3 |
| `history: no blob over 1 MB` | `data/synthetic_large/chat_full.txt` (1.9 MB, a copy of the large synthetic chat) is tracked and in history; `.gitignore` now ignores `data/`, but that does not untrack it | step 3 (drop that path from history) and `git rm --cached` |
| `git status clean` | fails whenever there are uncommitted changes; clear it by committing | any time |
| `readme blocks fresh` | fails only if `docs/results/*.json` changed after the README tables were built | run `scripts/build_readme_tables.py` |

## Steps

1. **Ratings and precision.** Rate every item in `out/rating/ratings.csv` by hand (the blind pack), then `python -m gcw rating-score --ratings out/rating/ratings.csv --key out/rating/key.json --out docs/results/precision_A`. Until then the README says "Precision: not yet measured (hand-rating pending)" and claims no precision number.
2. **README tables.** `python scripts/build_readme_tables.py` (rebuilds every generated block, including the precision block), then `python scripts/build_site.py` so `site/methodology.html` matches. Commit.
3. **History rewrite, once, locally.** Remove from all history: `build/`, `*.egg-info`, `.cache/`, `data/synthetic_large/chat_full.txt`; drop the tall `docs/img/app_3_review.png` blobs if you want the history small. Record old-to-new hashes in `docs/results/commit_map.md` (the README points to that file). The tool is your choice: `git filter-repo` is not installed here (`git filter-repo` is not a git command on this machine), so the exact command is UNVERIFIED; do it on a fresh clone first and keep the original until the checks are green.
4. **Pre-publish check green.** `python scripts/prepublish_check.py` must end with 13 of 13 checks passed. Read the INFO block ("mentions") and decide what stays; it never blocks.
5. **Private push.** Create the repository private, add the remote, push (commands below).
6. **CI green.** `.github/workflows/ci.yml` runs on the push: pytest on Python 3.11 and 3.13, `scan_repo`, and the pre-publish check. It has never run (UNVERIFIED): expect to fix Linux differences (fonts, pinned wheels) before it is green.
7. **Public flip.** GitHub Pages needs a public repository on the Free plan (https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site).
8. **Pages.** Settings, Pages, Build and deployment, Source: GitHub Actions (a branch source can only publish `/` or `/docs`: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site). `.github/workflows/pages.yml` then publishes the committed `site/` folder unchanged. Rebuild `site/` with `python scripts/build_site.py --repo-url <the public URL>` once the URL exists.

## Commands for later (NOT run)

```sh
gh repo create group-chat-wrapped --private                                # empty private repository under the logged-in account
git remote add origin https://github.com/<OWNER>/group-chat-wrapped.git   # or the ssh URL of the repository
git push -u origin main
# Settings > Pages > Source: GitHub Actions   (in the browser)
gh repo edit <OWNER>/group-chat-wrapped --visibility public --accept-visibility-change-consequences
```

`.gitignore` covers `out/`, `data/`, `.env`, `.env.*`, `aliases.json`, `ratings.csv`, `key.json` and `.cache/`.
