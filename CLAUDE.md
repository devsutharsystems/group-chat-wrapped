# Group Chat Wrapped — agent rules

## HARD RULES (every phase)
1. Working dir must be `~/Documents/Lets Data Science/week7/group-chat-wrapped`. Run `pwd` first; if it differs, STOP and tell the user. Quote paths with spaces.
2. Never read, list, modify or delete anything outside this folder. Never open any real WhatsApp export. Real chats live outside the project and only the user runs them. Build and test against synthetic data and committed fixtures only.
3. No API calls unless a phase explicitly allows it. API key only via the `ANTHROPIC_API_KEY` env var. Never print it; never write it to a file except `.env` (gitignored, created by the user).
4. Never push. `git init` and local commits are fine. Any `git remote` / `git push`: show the exact command and wait.
5. Caches inside the project: `PIP_CACHE_DIR=.cache/pip`, `PLAYWRIGHT_BROWSERS_PATH=.cache/ms-playwright`. Run `df -h ~` before installing and report free space.

## Conventions
- Stack: Python >=3.11, pandas, Anthropic Haiku (`claude-haiku-5-5`). Machine is an M2 with 8 GB RAM: keep everything light.
- Layout: `src/gcw/` (parser, stats, privacy, llm, verify, card, cost, app), `scripts/`, `synthetic/`, `tests/`, `tests/fixtures/`, `docs/`.
- Use `.venv/bin/python`. Type hints and `from __future__ import annotations`.
- Every API call needs an explicit `confirm=True` and passes the cost guard (`GCW_COST_CAP_USD` default 1.00 per run; `GCW_PROJECT_CAP_USD` default 3.00 cumulative).
- Stats-only mode makes zero API calls.
- Only synthetic names (see `tests/fixtures/ALLOWED_NAMES.txt`) appear in the repo. Run `scripts/scan_repo.py` and `pytest` before each commit.
- Commits end with the Co-Authored-By line from the session attribution.
- Spec is Prateek's, truncated at "…": build to R1–R7 in `docs/PRD.md`.
- Commit only with `&&` after `pytest` and `scripts/scan_repo.py` both pass (e.g. `pytest && scripts/scan_repo.py && git commit ...`); never chain with `;`.
- Before any push, run `git log -p --all | grep -cE '/U[s]ers/'` and expect 0 (the `[s]` keeps this line itself from matching). The scanner only checks tracked files, so `git add -A` before running it.
- Never pipe `pytest` or `scan_repo` into `tail`/`head`/`grep` inside a gate chain; run them unpiped so `&&` sees the exit code.
- Stats and the AI layer read `gcw.parser.messages(df)` (no system lines, no deleted messages), never the raw `parse_chat` DataFrame.
- Scratch files and mutation scripts go in `.cache/tmp` inside the project; never write to `/tmp` (pytest `tmp_path` is the only exception).
- Renders (Playwright/Chromium): run under `nice -n 10`; one render at a time; Chromium with `--disable-gpu`, one browser, one page, `deviceScaleFactor` 1, closed after the render; tests share one session-scoped browser. Gate chain for render tests: `git add -A && .venv/bin/python .cache/tmp/guarded.py -- nice -n 10 .venv/bin/pytest -q && .venv/bin/python scripts/scan_repo.py && git commit ...` (guarded.py samples only its own process tree and kills it above 1 GB; exit code passes through). Never touch, stop or inspect other projects' processes (this Mac also runs another project's benchmark). No Docker, no parallel builds. If RSS goes above about 1 GB: stop and tell the user.
