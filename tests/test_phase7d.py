"""Phase 7d: approval_mode and the footer wording, the review screen layout, stopword-safe truncation. Fake clients and a fake renderer only; no network, no browser
(the CLI test reuses the session browser fixture through test_card_ai's world)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from gcw import analyze, appcore, card, cli, display, review
from test_app import PNG, ai_mode, env, go, start  # noqa: F401  (env is a fixture)
from test_app import chat_text
from test_card_ai import card_args, visible_text, world  # noqa: F401  (world is a fixture)
from test_privacy import ROOT

REPORT = {"running_jokes": [{"title": "J", "summary": "s", "evidence": [{"message_id": "m000001", "quote": "q"}]}],
          "moments": [{"title": "M", "summary": "s", "evidence": [{"message_id": "m000002", "quote": "q"}]}], "awards": []}


# ---------------------------------------------------------------- approval_mode
def test_approval_mode_defaults_to_human_and_only_approve_all_writes_auto_synthetic(tmp_path):
    assert review.new_review(REPORT)["approval_mode"] == "human" and review.mode_of(None) == "human" and review.mode_of({"items": {}}) == "human"
    rv = review.approve_all(REPORT, "r")
    assert rv["approval_mode"] == "auto-synthetic" and {v["status"] for v in rv["items"].values()} == {"approved"}
    review.save_review(tmp_path / "a.json", rv)
    assert review.load_review(tmp_path / "a.json")["approval_mode"] == "auto-synthetic"
    review.set_human(rv)
    assert review.mode_of(rv) == "human"
    legacy = {"version": 1, "run": "", "items": {}}  # a file from before this field
    (tmp_path / "old.json").write_text(json.dumps(legacy))
    assert review.mode_of(review.load_review(tmp_path / "old.json")) == "human"
    (tmp_path / "bad.json").write_text(json.dumps({**legacy, "approval_mode": "robot"}))
    with pytest.raises(review.ReviewError, match="approval_mode"):
        review.load_review(tmp_path / "bad.json")
    with pytest.raises(review.ReviewError, match="auto-synthetic"):
        review.check_mode(review.approve_all(REPORT), frozen_chat=False)
    review.check_mode(review.approve_all(REPORT), frozen_chat=True)
    review.check_mode(review.new_review(REPORT), frozen_chat=False)


def ai(mode: str, approved: int = 2) -> dict:
    rv = review.approve_all(REPORT) if mode == "auto-synthetic" else review.new_review(REPORT)
    z = appcore.zone_for(REPORT, rv, {}, {}, None, {"items_in_by_type": {"running_jokes": 1, "moments": 1}}, proposed=13)
    return {**z, "approved": approved}


def test_the_footer_wording_follows_the_approval_mode_field():
    human, auto = card.ai_footer(ai("human", approved=7), None)[0], card.ai_footer(ai("auto-synthetic"), None)[0]
    assert human == "AI proposed 13 · 2 verified by code · 7 approved in review"
    assert auto == "AI proposed 13 · 2 verified by code · all auto-approved (synthetic demo)"
    assert "auto-approved" not in human and "approved in review" not in auto


@pytest.fixture
def frozen_report():
    """A verifiable report on the bundled demo chat (a joke on three dates and a moment) built from real payload messages; no model involved."""
    df, view = appcore.parse_view(appcore.demo_text())
    p = analyze.prepare(df, None, slice_start=None, slice_end=None)
    seen, picks = set(), []
    for pid, r in p["index"].items():
        d = str(r["ts"].date())
        if not r["withheld"] and not r["media"] and len(r["text"]) >= 20 and d not in seen:
            seen.add(d)
            picks.append(pid)
        if len(picks) == 4:
            break
    ev = lambda pid: {"message_id": pid, "quote": p["index"][pid]["text"]}  # noqa: E731
    return {"running_jokes": [{"title": "Demo joke", "summary": "s", "evidence": [ev(x) for x in picks[:3]]}], "moments": [{"title": "Demo moment", "summary": "s", "evidence": [ev(picks[3])]}], "awards": []}


def open_review(env_, chat: str, report: dict):  # noqa: ANN001
    at = start(chat)
    go(at, "5 Review")
    at.file_uploader(key="report_up").upload("demo.report.json", json.dumps(report).encode()).run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    return at


def test_the_auto_approve_button_exists_only_for_the_frozen_demo_chat_and_sets_the_mode(env, frozen_report):  # noqa: F811
    at = open_review(env, appcore.demo_text(), frozen_report)
    assert at.button(key="auto_approve").label == "Auto-approve all (synthetic demo only)"
    assert "approvals made by: human" in " ".join(t.value for t in at.text)
    at.button(key="auto_approve").click().run()
    state = " ".join(t.value for t in at.text)
    assert "'approved': 2" in state and "approvals made by: auto-synthetic" in state and not at.exception
    at.button(key="render_review").click().run()
    assert "all auto-approved (synthetic demo)" in env.renders[-1] and "approved in review" not in env.renders[-1]
    saved = json.loads(Path("out/app/review_app.json").read_text())
    assert saved["approval_mode"] == "auto-synthetic" and all(set(v) <= {"type", "status", "rank"} for v in saved["items"].values())
    # a manual decision afterwards makes the approvals human again, and the footer says so
    first = next(r.key for r in at.radio if str(r.key).startswith("dec_"))
    at.radio(key=first).set_value("rejected").run()
    assert "approvals made by: human" in " ".join(t.value for t in at.text)
    at.button(key="render_review").click().run()
    assert "1 approved in review" in env.renders[-1] and "all auto-approved" not in env.renders[-1]
    assert json.loads(Path("out/app/review_app.json").read_text())["approval_mode"] == "human"


def test_the_button_is_absent_for_a_chat_that_is_not_the_frozen_one(env):  # noqa: F811
    at = ai_mode(start())
    go(at, "4 AI")
    at.checkbox(key="consent").check().run()
    at.button(key="run_ai").click().run()
    go(at, "5 Review")
    assert at.session_state["ai_result"] and not [b for b in at.button if b.key == "auto_approve"]
    assert not appcore.is_frozen_text(chat_text()) and appcore.is_frozen_text(appcore.demo_text()) and not appcore.is_frozen_text(appcore.demo_text() + "\n")
    with pytest.raises(appcore.AppError, match="bundled synthetic demo"):
        appcore.auto_approve_all(REPORT, "x", chat_text())


def test_a_review_marked_auto_synthetic_is_refused_for_a_non_frozen_chat_in_the_app(env):  # noqa: F811
    at = ai_mode(start())
    go(at, "4 AI")
    at.checkbox(key="consent").check().run()
    at.button(key="run_ai").click().run()
    go(at, "5 Review")
    at.session_state["review"]["approval_mode"] = "auto-synthetic"  # a tampered or copied review
    n = len(env.renders)
    at.button(key="render_review").click().run()
    assert any("auto-synthetic" in e.value for e in at.error) and len(env.renders) == n


def test_a_review_file_marked_auto_synthetic_is_refused_by_the_cli_for_a_non_frozen_chat(world, capsys):  # noqa: F811
    review.save_review(world.tmp / "auto.json", review.approve_all(world.report, "r"))
    assert cli.main(card_args(world, "--report", str(world.run), "--review", str(world.tmp / "auto.json"))) == 2
    assert "marked auto-synthetic" in capsys.readouterr().err and not (world.tmp / "o.png").exists()
    review.save_review(world.tmp / "human.json", review.new_review(world.report, "r"))
    assert cli.main(card_args(world, "--report", str(world.run), "--review", str(world.tmp / "human.json"))) == 0
    assert "approved in review" in visible_text((world.tmp / "o.html").read_text())


# ---------------------------------------------------------------- review screen layout
def test_the_review_screen_shows_the_first_quote_and_controls_first_and_the_rest_in_expanders(env, frozen_report):  # noqa: F811
    at = open_review(env, appcore.demo_text(), frozen_report)
    texts = [t.value for t in at.text]
    assert any(t.startswith("Verified items: 2 (running jokes 1, moments 1, awards 0)") for t in texts)
    quote = lambda t: bool(re.match(r"^\w+, \d{4}-\d{2}-\d{2}: \"", t))  # noqa: E731
    more = next(e for e in at.expander if e.label == "2 more quotes")
    in_more = [t.value for t in more.text if quote(t.value)]
    assert len(in_more) == 2 and len([t for t in texts if quote(t)]) == 4  # two items show one first quote each; the other two joke quotes are inside the expander
    labels = [e.label for e in at.expander]
    assert labels.count("Context around the first quote") == 2 and "2 more quotes" in labels and not [l for l in labels if "more quote" in l and l != "2 more quotes"]
    assert at.radio(key=next(r.key for r in at.radio if str(r.key).startswith("dec_"))).value == "pending" and len([n for n in at.number_input]) == 2


# ---------------------------------------------------------------- stopword-safe truncation
STOP = "the a an of for to and or in on with by at from".split()


def last_word(s: str) -> str:
    return s.rstrip(display.ELLIPSIS + " ,;:-").rsplit(" ", 1)[-1].strip(".,;:!?").lower()


def test_a_truncated_summary_never_ends_on_a_stopword():
    s = "Consistently organises checklists, timelines and shopping plans for the group."
    assert len(s) == 78 and display.fit(s, 78, no_stopword_end=True) == s  # fits whole: untouched
    cut = display.fit(s, 70, no_stopword_end=True)
    assert cut == "Consistently organises checklists" + display.ELLIPSIS and last_word(cut) not in STOP  # a clause end (comma) is preferred
    g = "Keeps proposing treats, outings and thoughtful gestures for the group."
    assert display.fit(g, 66, no_stopword_end=True) == "Keeps proposing treats, outings and thoughtful gestures" + display.ELLIPSIS  # the early comma is too short a clause: trailing stopwords dropped, not "...gestures for the"
    h = display.fit("Keeps outings and thoughtful gestures for the group of friends", 41, no_stopword_end=True)
    assert last_word(h) not in STOP and h.endswith(display.ELLIPSIS) and h.startswith("Keeps outings and thoughtful gestures")  # no comma: trailing stopwords dropped
    for limit in range(20, 70):
        for text in (s, g):
            o = display.fit(text, limit, no_stopword_end=True)
            assert len(o) <= limit and (o == " ".join(text.split()) or last_word(o) not in STOP), (limit, o)
            assert text.startswith(o.rstrip(display.ELLIPSIS)) or o == text


def test_award_and_summary_displays_use_the_stopword_rule_and_plain_fit_is_unchanged():
    z = display.build_zone2({"awards": [{"award": "Best planner", "member": "Member 1", "summary": "Consistently organises checklists, timelines and shopping plans for the group of friends."}],
                             "running_jokes": [], "moments": []}, {}, {"Member 1": "Jordan"})
    assert z["awards"][0]["summary"] == "Consistently organises checklists" + display.ELLIPSIS  # a clause end is preferred; not "...plans for the…"
    assert display.fit("one two three four five six", 15) == "one two three" + display.ELLIPSIS
    assert display.fit("Alpha beta of the gamma delta", 22) == "Alpha beta of the" + display.ELLIPSIS  # titles and quotes keep the plain cut


# ---------------------------------------------------------------- real-format check (values computed by hand by the project owner; they must not be edited to fit the code)
FIXTURE = ROOT / "tests" / "fixtures" / "android_us_12h.txt"


def test_the_real_android_export_gives_the_hand_computed_stats_and_card_values():
    import pandas as pd
    from gcw.parser import messages, parse_chat
    from gcw.stats import compute_stats

    raw = FIXTURE.read_text(encoding="utf-8")
    assert len(raw.splitlines()) == 14 and " " in raw  # 14 lines, the narrow no-break space before AM/PM
    df, rep = parse_chat(FIXTURE)
    assert (rep.date_order, rep.ambiguous, rep.per_sender) == ("mdy", True, {"Sam": 10}) and any("AMBIGUOUS" in w and "m/d" in w for w in rep.warnings)
    assert (len(df), int(df.is_system.sum()), int(df.is_deleted.sum()), len(messages(df))) == (14, 4, 1, 9)
    st = compute_stats(df)
    assert st["window"]["n_messages"] == 9 and st["top_talkers"]["by_words"] == [{"sender": "Sam", "words": 51}]
    assert st["emojis"]["total"] == 17 and st["emojis"]["top"][0] == {"emoji": "\U0001F602", "count": 3}
    assert (st["laughs"]["total"], st["media"]["total"], st["links"]["total"]) == (1, 1, 1)
    assert pd.Timestamp(st["longest_silence"]["end"]) - pd.Timestamp(st["longest_silence"]["start"]) == pd.Timedelta(minutes=1)
    assert st["busiest"]["slot"] == {"weekday": "Thursday", "hour": 21, "messages": 9}
    assert st["night_early"]["night_owl"] is None and st["night_early"]["early_bird"] is None and st["night_early"]["per_sender"]["Sam"]["messages"] < 30
    assert card.top_starter(st) is None
    t = visible_text(card.build_card_html(st, None, date_note="Dates read as m/d (assumed)"))
    for must in ("Night owl n/a", "Early bird n/a", "Top starter n/a", "Longest silence 1m", "Busiest slot Thursday 21:00 9 messages", "17 emoji", "top: \U0001F602 ×3", "1 laughs", "1 media", "1 links",
                 "9 messages", "Sam 9 51", "Dates read as m/d (assumed)"):
        assert must in t, must


def test_the_real_format_note_exists_with_counts_only_and_the_stated_limits():
    md = (ROOT / "docs" / "results" / "real_format_check.md").read_text(encoding="utf-8")
    low = md.lower()
    for k in ("real export", "names changed", "whitespace-separated", "emoji typed with spaces", "single sender", "9 messages", "multi-line", "ios", "24-hour", "untested"):
        assert k in low, k
    raw = FIXTURE.read_text(encoding="utf-8")
    assert not [ln for ln in raw.splitlines() if len(ln.split(": ", 1)[-1]) > 12 and ln.split(": ", 1)[-1] in md]  # no chat text


# ---------------------------------------------------------------- README wording and generated tables
README = (ROOT / "README.md").read_text(encoding="utf-8")


def table_rows(name: str) -> list[list[str]]:
    body = re.search(rf"<!-- BEGIN:{name} -->\n(.*?)\n<!-- END:{name} -->", README, re.S).group(1)
    return [[c.strip() for c in ln.strip("|").split("|")] for ln in body.splitlines() if ln.startswith("|")][2:]


def test_the_readme_wording_fixes_are_in_place():
    hero = README.split("\n\n")[2]
    assert "auto-approved for this demo, with no human review" in hero
    why = README.split("## Why it differs", 1)[1].split("## Quickstart", 1)[0]
    assert "does not check whether the quotes support the item's title and summary" in why and "what the hand rating will measure" in why
    assert "recall numbers, and precision once the hand ratings exist" in why and "precision-style" not in README
    lim = README.split("## Limits", 1)[1].split("\n## ", 1)[0]
    assert "one real Android export (US 12-hour clock, U+202F before AM/PM, 14 lines, one sender; `docs/results/real_format_check.md`)" in lim
    assert "Awards and unplanted items are not scored until they are hand-rated" in lim and "not blind" in lim
    assert "## History and publishing" in README  # that paragraph is untouched by this phase


def test_every_table_row_shows_wall_clock_and_chunked_rows_keep_the_sum_of_call_latencies_separately():
    for name in ("eval_table", "cost_block"):
        body = re.search(rf"<!-- BEGIN:{name} -->\n(.*?)\n<!-- END:{name} -->", README, re.S).group(1)
        assert "wall-clock per run (s)" in body and "sum of call latencies per run (s, chunked rows only)" in body
    rows = table_rows("eval_table")
    assert len(rows) == 5 and all(r[-2] != "n/a" for r in rows)  # wall-clock is never n/a
    assert [r[-1] == "n/a" for r in rows] == [True, False, True, True, False]  # the sum is only for the two chunked rows
    large = json.loads((ROOT / "docs/results/eval_large_A.json").read_text())["summary"]["latency_s"]["mean"]
    assert rows[3][-2] == f"{large:.1f}"  # single-pass: wall-clock equals the call's latency
    chunk = json.loads((ROOT / "docs/results/eval_large_chunked.json").read_text())["summary"]
    assert rows[4][-2] == f"{chunk['wall_clock_s']['mean']:.1f}" and rows[4][-1] == f"{chunk['latency_s']['mean']:.1f}"
    assert table_rows("cost_block")[0][2] != "n/a"


def test_the_memory_block_shows_the_widened_stats_card_range():
    assert "| 1,015, 1,114, 1,116, 1,121, 1,135, 1,167, 1,171 | 1,015 | 1,171 |" in README and "phase 6-fix; phase 6-fix2; phase 6-fix3; phase 6-fix4" in README


def test_the_privacy_note_explains_the_name_replacement_count():
    t = (ROOT / "docs" / "privacy.md").read_text(encoding="utf-8")
    assert "Name-replacement count (38, then 39)" in t and "3a-fix2" in t and "25 messages" in t
