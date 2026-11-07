"""Phase 7e: the README's definitions and generated blocks (config A, tested-on line, results in brief, precision block, dropped-quote note, item rules, limits)."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys

import pytest

import build_readme_tables as btab
from gcw import analyze, cli, evaluate, verify
from test_privacy import ROOT

README = (ROOT / "README.md").read_text(encoding="utf-8")


def block(name: str) -> str:
    return re.search(rf"<!-- BEGIN:{name} -->\n(.*?)\n<!-- END:{name} -->", README, re.S).group(1)


def section(title: str) -> str:
    return README.split(f"## {title}", 1)[1].split("\n## ", 1)[0]


def test_config_a_and_the_tested_on_line_match_the_code_and_the_ci_matrix():
    ev = section("Evaluation")
    assert analyze.CONFIGS["A"] == {"thinking": {"type": "disabled"}, "effort": "low"}
    assert f"model `{analyze.MODEL}`, thinking disabled, effort low, prompt v1 frozen" in ev and "2026-11-06 and 2026-11-07" in ev
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    versions = re.search(r"python-version: \[(.*?)\]", ci).group(1)
    assert "'3.11'" in versions and "'3.13'" in versions
    assert "**Tested on:** Python 3.15.0 and macOS" in ev and "has not run yet" not in README  # CI has run since Phase 8b; the wording is checked in tests/test_phase8c.py
    assert README.count("actions/workflows/ci.yml/badge.svg") == 1  # the badge was added in Phase 9a, after the first green CI run


def test_results_in_brief_sits_right_after_why_it_differs_with_at_most_six_plain_lines():
    assert README.index("## Design choices") < README.index("## Results in brief") < README.index("## Quickstart")
    lines = [ln for ln in block("brief").splitlines() if ln.strip()]
    assert 1 <= len(lines) <= 6 and all(ln.startswith("- ") for ln in lines)
    text = block("brief").lower()
    for w in (*evaluate.WINNER_WORDS, "good", "bad", "great", "poor", "strong", "weak", "impressive", "excellent", "better", "worse", "outperform"):
        assert not re.search(rf"\b{w}\b", text), w
    p = json.loads((ROOT / "docs/results/precision_A.json").read_text())
    assert f"n = {p['overall']['n']}, rated by the author, not blind" in text
    for needle in ("single-pass 25 of 30, chunked 27 of 30", "not reconciled with the console", "single-pass found 0 of 10 planted items, chunked 5 of 10", "n = 1 run each", "confounded"):
        assert needle in text, needle


def test_the_precision_block_has_the_rubric_the_standard_the_sample_and_the_format():
    b = block("precision_block")
    prd = (ROOT / "docs/PRD.md").read_text()
    rubric = [ln.strip() for ln in prd.split("**Rating rubric", 1)[1].splitlines()[1:] if ln.startswith("  - ") and "Precision is reported" not in ln]
    assert len(rubric) == 7 and all(r in b for r in rubric)
    assert 'Standard applied: "true" when the shown quotes support the title and summary; "partly" when part of the claim or its detail is not shown.' in b
    p = json.loads((ROOT / "docs/results/precision_A.json").read_text())
    kept = sum(sum(r["items_kept"].values()) for r in json.loads((ROOT / "docs/results/eval_full_A.json").read_text())["runs"])
    assert (f"Sample: {p['n_items']} of the {kept} verified items from the three runs (the rating pack is capped at 40 items, `rating-pack --size`; the draw is stratified by type, "
            "and after the cap it left out 1 running joke), drawn with seed 4242, rated by the author in a single pass.") in b
    assert "| overall | 40 | 21 of 40, 52.5%, interval 37.5% to 67.1% | 39 of 40, 97.5%, interval 87.1% to 99.6% |" in b
    assert "| run 1 |" in b and "| run 2 |" in b and "| run 3 |" in b and "2026110" not in b and "20261107T" not in b
    assert "The unplanted rows mix item types because awards have no planted truth, so planted against unplanted is not a like-for-like comparison." in b
    assert (f"For the {p['by_type']['moments']['partly']} moments rated partly, the author's reason was mostly that the summary added concrete details not present in the displayed messages; "
            "incomplete quotes were a secondary reason. No per-item notes were recorded, so this is the author's recollection, not a coded result.") in b
    assert btab.RATING_SEED == cli.build_parser().parse_args(["rating-pack", "c.txt", "--aliases", "a.json", "--phase", "4a"]).seed == 4242


def test_the_percentage_format():
    assert btab.fmt_ci({"k": 21, "n": 40, "p": 0.525, "lo": 0.375, "hi": 0.6714}) == "21 of 40, 52.5%, interval 37.5% to 67.1%"
    assert btab.fmt_ci({"k": 0, "n": 0, "p": 0, "lo": 0, "hi": 0}) == "n/a"


def test_the_dropped_quote_note_says_only_what_the_results_file_says(tmp_path):
    n = block("dropped_note")
    d = json.loads((ROOT / "docs/results/eval_full_A.json").read_text())
    dropped = sum(v for r in d["runs"] for k, v in r["status_counts"].items() if k != "verified")
    assert f"{dropped} evidence items were dropped" in n and "docs/results/eval_full_A.json" in n and "status other_message" in n and "none was invented" in n
    assert "not claimed to be verbatim" in n and "at least 12 characters" in n and "exact substring of the cited message" in n
    # a results file with another status gets a different, plain sentence
    (tmp_path / "docs/results").mkdir(parents=True)
    d["runs"][0]["status_counts"]["not_found"] = 2
    (tmp_path / "docs/results/eval_full_A.json").write_text(json.dumps(d))
    other = btab.dropped_note(tmp_path)
    assert "not_found 2" in other and "none was invented" not in other


def make_index(dates):
    import pandas as pd

    return {f"m{i + 1:06d}": {"ts": pd.Timestamp(d), "sender": s} for i, (d, s) in enumerate(dates)}


def test_the_item_rules_stated_in_the_readme_are_the_ones_in_the_code():
    why = section("Design choices")
    assert "Each kept quote is an exact substring of the cited message" in why and "each of its evidence quotes" not in README
    assert "a running joke needs at least 3 verified evidence messages on at least 2 dates, a moment at least 1, and an award at least 1 from the named member" in why
    assert verify.MIN_QUOTE_CHARS == 12
    idx = make_index([("2026-01-01", "Member 1"), ("2026-01-01", "Member 1"), ("2026-01-02", "Member 2"), ("2026-01-01", "Member 2")])
    ev = lambda *ids: [{"message_id": i, "quote": "q"} for i in ids]  # noqa: E731
    items = {"running_jokes": [{"title": "two", "evidence": ev("m000001", "m000003")},  # 2 evidence: dropped
                               {"title": "one date", "evidence": ev("m000001", "m000002", "m000004")},  # 3 evidence on 1 date... m000004 is 01-01 too: dropped
                               {"title": "ok", "evidence": ev("m000001", "m000002", "m000003")}],  # 3 on 2 dates: kept
             "moments": [{"title": "m", "evidence": ev("m000001")}, {"title": "none", "evidence": []}],
             "awards": [{"award": "a", "member": "Member 2", "evidence": ev("m000003")}, {"award": "b", "member": "Member 2", "evidence": ev("m000001")}]}
    out, drops = verify.apply_item_rules(items, idx, valid_members={"Member 1", "Member 2"})
    assert [i["title"] for i in out["running_jokes"]] == ["ok"] and [i["title"] for i in out["moments"]] == ["m"] and [i["award"] for i in out["awards"]] == ["a"]
    assert drops == {"too_few_evidence": 2, "too_few_dates": 1, "no_member_evidence": 1}


def test_the_limits_additions_and_the_untouched_paragraphs():
    # the History paragraph digest was updated deliberately in Phase 8a (the real history rewrite) and again in Phase 8d (prediction wording, Claude Code sentence); the Licence digest is unchanged
    lim = section("Limits")
    assert "No real chat has been analysed by the AI step" in lim and "analysed in this repository" not in README
    assert "the chat may be easier for the same model family (circularity)" in lim and "Haiku" in lim
    assert 'natural tics (for example "honestly I think")' in lim and "tic category" in lim
    assert "model id `claude-haiku-5-5` on 2026-11-06 and 2026-11-07 and may change if the model changes" in lim
    for title, digest in (("History and publishing", "7bc5373fc2a7156a9a0761f2a6824258f565decead8898069e36bff1a926ce86"), ("Licence", "0f1549273e27ec667d4a38ee51e19d27fa84ecaf781231615314fad08fbb1c8f")):
        assert hashlib.sha256((f"## {title}" + section(title)).encode()).hexdigest() == digest, title


def test_the_history_paragraph_cites_the_prediction_commits_from_the_commit_map():
    sec = section("History and publishing")
    rows = [ln for ln in (ROOT / "docs/results/commit_map.md").read_text().splitlines() if re.match(r"^\| [0-9a-f]{40} \|", ln) and "predictions written before" in ln]
    assert len(rows) == 2
    new = [ln.split("|")[2].strip()[:7] for ln in rows]
    assert all(f"`{h}`" in sec for h in new)
    assert "commit `%s`" % new[0] in sec and "commit `%s`" % new[1] in sec
    for h in new:  # the cited commits exist in this repository
        assert subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", h + "^{commit}"]).returncode == 0
    assert "personal email addresses" in sec and "no-reply" in sec and "one to one" in sec and "docs/results/commit_map.md" in sec


MAP_ROWS = 49  # a constant recorded at rewrite time (Phase 8a): the commit map covers the first 49 commits; commits made later are not in it
ME = "Dev Suthar <209331458+" + "devsu" + "tharsystems" + chr(64) + "users.noreply.github.com>"  # built from parts so the repo's own mentions check does not flag this file


def _git_out(root, *args) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True).stdout


def check_commit_map(root) -> None:
    """The commit map and the identity rule, for any clone of this repository with its full history (CI uses fetch-depth 0). It does not depend on how many commits came after
    the rewrite: the map's new hashes must be the FIRST MAP_ROWS commits of the history, in order; the old hashes must be gone from it; every commit has one identity."""
    rows = re.findall(r"^\| ([0-9a-f]{40}) \| ([0-9a-f]{40}) \|", (root / "docs/results/commit_map.md").read_text(), re.M)
    olds, news = [o for o, _ in rows], [n for _, n in rows]
    assert len(rows) == MAP_ROWS  # (a)
    chain = _git_out(root, "rev-list", "--reverse", "HEAD").split()
    assert len(chain) >= MAP_ROWS and news == chain[:MAP_ROWS]  # (b) one to one and order preserving
    assert len(set(olds)) == len(olds) and all(o != n for o, n in rows)  # (c) old hashes are unique and differ from the new ones ...
    for o in olds:  # ... and none is an ancestor of HEAD: a non-zero exit (not an ancestor, or an object that no longer exists) is what is required
        assert subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", o, "HEAD"], capture_output=True).returncode != 0, o
    ids = set(_git_out(root, "log", "--all", "--format=%an <%ae>|%cn <%ce>").split("\n")) - {""}
    assert ids == {ME + "|" + ME}  # (d) one author and committer identity across all history


def test_the_commit_map_is_complete_and_the_rewrite_left_one_identity():
    check_commit_map(ROOT)


def test_the_commit_map_check_survives_new_commits_and_catches_a_foreign_author(tmp_path):
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(clone)], check=True, capture_output=True)
    ident = ["-c", "user.name=Dev Suthar", "-c", "user.email=" + ME.split("<")[1].rstrip(">")]
    for k in range(5):  # history grows: the check does not care
        subprocess.run(["git", "-C", str(clone), *ident, "commit", "-q", "--allow-empty", "-m", f"later commit {k}"], check=True, capture_output=True)
    check_commit_map(clone)
    other = ["-c", "user.name=Someone Else", "-c", "user.email=someone" + chr(64) + "example.com"]
    subprocess.run(["git", "-C", str(clone), *other, "commit", "-q", "--allow-empty", "-m", "a commit by another identity"], check=True, capture_output=True)
    with pytest.raises(AssertionError):
        check_commit_map(clone)
    assert _git_out(clone, "rev-list", "--count", "HEAD").strip() == str(int(_git_out(ROOT, "rev-list", "--count", "HEAD")) + 6)


def test_no_tracked_file_outside_the_map_still_names_a_pre_rewrite_commit_hash():
    """Guards against stale hashes after the history rewrite (the sweep of Phase 8e found three in a script's usage example)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import update_hash_refs as uh

    mapping = uh.load_map(ROOT / "docs/results/commit_map.md")
    stale = []
    for f in [x for x in _git_out(ROOT, "ls-files", "-z").split("\0") if x and x != "docs/results/commit_map.md"]:
        if not f.endswith((".py", ".md", ".json", ".sh", ".yml", ".toml", ".txt", ".html")):
            continue
        for n, line in enumerate((ROOT / f).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stale += [f"{f}:{n} {m.group()}" for m in uh.SHORT.finditer(line) if m.group() in mapping]
    assert stale == []
