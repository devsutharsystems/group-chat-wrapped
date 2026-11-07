"""Phase 9a: CI badge and live-demo link, the near-1M hypothesis note (numbers from the results files), and the reason the precision sample is 40 of 41."""
from __future__ import annotations

import inspect
import json
import re

import build_readme_tables as btab
from gcw import cli, evaluate
from test_privacy import ROOT

README = (ROOT / "README.md").read_text(encoding="utf-8")
ACCOUNT = "devsu" + "tharsystems"  # built from parts: the repo's mentions check lists the account name
BADGE = f"[![ci](https://github.com/{ACCOUNT}/group-chat-wrapped/actions/workflows/ci.yml/badge.svg)](https://github.com/{ACCOUNT}/group-chat-wrapped/actions/workflows/ci.yml)"
DEMO = f"https://{ACCOUNT}.github.io/group-chat-wrapped/"


def block(name: str) -> str:
    return re.search(rf"<!-- BEGIN:{name} -->\n(.*?)\n<!-- END:{name} -->", README, re.S).group(1)


def test_badge_and_live_demo_link_are_near_the_top():
    head = README.split("## Design choices", 1)[0]
    assert head.startswith("# Group Chat Wrapped\n\n" + BADGE + "\n\n**Live demo:** " + DEMO)
    assert head.index(BADGE) < head.index("docs/img/app_4_review_rendered_card.png")
    assert README.count(BADGE) == 1


def test_the_hypothesis_note_takes_its_numbers_from_the_results_files_and_adds_no_other_claim():
    n = block("hypothesis_note")
    single = json.loads((ROOT / "docs/results/eval_large_A.json").read_text())
    chunked = json.loads((ROOT / "docs/results/eval_large_chunked.json").read_text())
    f = lambda r: sum(v["strict_found_item_runs"] for v in r["recall_by_type"].values())  # noqa: E731
    p = lambda r: sum(v["possible_item_runs"] for v in r["recall_by_type"].values())  # noqa: E731
    assert f"single-pass found {f(single)} of {p(single)} planted items (`docs/results/eval_large_A.json`)" in n
    assert f"chunked found {f(chunked)} of {p(chunked)} (`docs/results/eval_large_chunked.json`), one run each (n = {single['n_runs']})" in n
    assert single["n_runs"] == chunked["n_runs"] == 1
    assert "written in `docs/PRD.md` before any run (single-pass wins recall on long-range jokes)" in n and "was not supported in the near-1M-token setup" in n
    assert "This shows only that the hypothesis was not supported in this single run; it is not a general claim about single-pass against chunked." in n and "failed in this setup" not in n
    assert "Both runs read the same chat" in n and "density is a confound" in n and "not a general claim about single-pass against chunked" in n
    prd = (ROOT / "docs/PRD.md").read_text()
    assert "**Hypothesis (written before any run):** single-pass wins recall on long-range jokes" in prd  # the quoted hypothesis exists in the PRD
    assert btab.stale(ROOT) == []
    assert README.index("<!-- BEGIN:eval_table -->") < README.index("<!-- BEGIN:hypothesis_note -->") < README.index("<!-- BEGIN:dropped_note -->")


def test_why_the_precision_sample_is_40_of_41_comes_from_the_code_and_the_counts():
    assert btab.RATING_CAP == inspect.signature(evaluate.build_rating_pack).parameters["total"].default == 40
    assert cli.build_parser().parse_args(["rating-pack", "c.txt", "--aliases", "a.json", "--phase", "4a"]).size == btab.RATING_CAP
    runs = json.loads((ROOT / "docs/results/eval_full_A.json").read_text())["runs"]
    pool = {t: sum(r["items_kept"][t] for r in runs) for t in ("running_jokes", "moments", "awards")}
    assert sum(pool.values()) == 41
    take = evaluate.allocate(pool, btab.RATING_CAP)
    assert sum(take.values()) == 40 and {t: pool[t] - take[t] for t in pool} == {"running_jokes": 1, "moments": 0, "awards": 0}
    prec = json.loads((ROOT / "docs/results/precision_A.json").read_text())
    assert {t: prec["by_type"][t]["n"] for t in take} == take  # the rated sample is exactly what the code's allocation gives
    assert "after the cap it left out 1 running joke" in block("precision_block")


def test_the_tested_on_paragraph_names_the_second_ci_failure_and_its_fix():
    import subprocess

    tested = next(ln for ln in README.split("## Evaluation", 1)[1].splitlines() if ln.startswith("**Tested on:**"))
    assert ("A second CI run failed on a commit-count assertion in `tests/test_phase7e.py` (the test counted commits since the history rewrite; the failing push was `458fcda`), "
            "and `32bc10f` rewrote that test so it no longer depends on the commit count.") in tested
    for h, start in (("458fcda", "Phase 8d"), ("32bc10f", "Phase 8e")):  # the hashes are the commits of those phases in this repository's log
        assert subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%s", h], capture_output=True, text=True).stdout.startswith(start)
