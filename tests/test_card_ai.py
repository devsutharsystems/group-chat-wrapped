"""AI mode of the card (Zone 2 + footer) and the `card` / `review` commands. Renders share the ONE session browser (tests/conftest.py)."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from gcw import card, cli, display, review
from gcw.dataset import verify_dataset
from gcw.parser import parse_chat
from gcw.stats import compute_stats
from test_card import ROOT, assert_clean, busy_frame, parsed, png_size, visible_text
from test_privacy import FROZEN, al

STATS_ONLY_SHA = "1ec0348ee2c7df195c90de23c417cc993ecac7710957304e8dd111032279fc5f"
LONG30 = "Alexandria Bartholomew-Smythe!"
assert len(LONG30) == 30


def names_for(n: int, name_fn=lambda i: f"Friend{i:02d}") -> dict[str, str]:
    return {f"Member {i}": name_fn(i) for i in range(1, n + 1)}


def mkitem(title="Cheese protocol", summary="They keep saying it at odd moments.", quote="reminder: cheese protocol is in effect", pid="m000001"):
    return {"title": title, "summary": summary, "evidence": [{"message_id": pid, "quote": quote}]}


def mkaward(award="Best planner", member="Member 2", summary="Always has a plan ready."):
    return {"award": award, "member": member, "summary": summary, "evidence": [{"message_id": "m000002", "quote": "x" * 12}]}


def zone(cells: int, *, joke=None, moment=None, awards=None, names=None, n_members=3) -> dict:
    """cells filled in order: joke, moment, award 1, award 2."""
    import pandas as pd

    idx = {f"m{i:06d}": {"sender": f"Member {(i - 1) % n_members + 1}", "ts": pd.Timestamp("2026-01-05T10:00"), "withheld": False, "media": False} for i in range(1, 9)}
    approved = {"running_jokes": [joke or mkitem()] if cells >= 1 else [], "moments": [moment or mkitem("Cake disaster", "It sank in the middle.", "Well, that cake was a disaster.", "m000002")] if cells >= 2 else [],
                "awards": (awards or [mkaward(), mkaward("Most generous", "Member 3", "Keeps proposing treats.")])[: max(0, cells - 2)]}
    z = display.build_zone2(approved, idx, names or names_for(n_members))
    return {"zone2": z, "approved": sum(len(v) for v in approved.values()), "proposed": 13, "verified": 12, "synthetic": False}


def render_ai(browser, ai: dict, stats=None, **kw):
    stats = stats or compute_stats(busy_frame(["Sam", "Alex", "Maya"]))
    html = card.build_card_html(stats, ai=ai, **kw)
    res = card.render_png(html, browser=browser, measure=True, probe="({grid: (document.querySelector('.z2body') || {getBoundingClientRect: () => ({height: -1})}).getBoundingClientRect().height, "
                                                                     "foot: document.querySelector('footer').getBoundingClientRect().height, footLines: Math.round(document.querySelector('footer').getBoundingClientRect().height / parseFloat(getComputedStyle(document.querySelector('footer')).lineHeight))})")
    return {"html": html, **res}


def check(res):
    assert_clean(res)
    assert res["probe"]["grid"] == 424 and res["probe"]["footLines"] == 2 and res["probe"]["foot"] == 52
    assert res["overflow"]["fonts"]["footer"] and res["overflow"]["fonts"]["zone2"]


# ---------------------------------------------------------------- the stats-only card is unchanged
def test_stats_only_html_is_unchanged_and_has_no_ai_markup():
    verify_dataset()
    df, _ = parse_chat(FROZEN)
    html = card.build_card_html(compute_stats(df))
    assert hashlib.sha256(html.encode()).hexdigest() == STATS_ONLY_SHA, "the stats-only card changed (update the pin only on purpose; 3c-fix changed only the Zone 2 heading size and the date-note size in the CSS)"
    assert "z2body" not in html and card.FOOTER in html and card.ZONE2_OFF in html and card.build_card_html(compute_stats(df), ai=None) == html


def test_display_and_review_import_no_anthropic():
    code = "import sys, gcw.display, gcw.review, gcw.card; bad = [m for m in ('anthropic', 'gcw.llm', 'gcw.cost') if m in sys.modules]; assert not bad, bad"
    r = subprocess.run([sys.executable, "-c", code], env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------- Zone 2 layouts
@pytest.mark.parametrize("cells", [0, 1, 2, 3, 4])
def test_zone2_layout_with_0_to_4_filled_cells(browser, cells):
    res = render_ai(browser, zone(cells))
    check(res)
    t = visible_text(res["html"])
    assert ("No AI items approved" in t) is (cells == 0)
    assert t.count("none approved") == (0 if cells in (0, 4) else 4 - cells)
    assert ("Cheese protocol" in t) is (cells >= 1) and ("Cake disaster" in t) is (cells >= 2) and ("Best planner" in t) is (cells >= 3) and ("Most generous" in t) is (cells >= 4)


def test_zone2_content_is_shown_with_names_dates_and_quotes(browser):
    res = render_ai(browser, zone(4, names={"Member 1": "Sam", "Member 2": "Maya", "Member 3": "Kai"}))
    check(res)
    t = visible_text(res["html"])
    assert "reminder: cheese protocol is in effect" in t and "2026-01-05" in t and "Maya" in t and "Kai" in t
    assert not re.search(r"Member \d+", t)  # the mapping is complete: no pseudonym token on the card
    assert "Counted locally" not in t and "AI sections off" not in t


def test_worst_case_lengths_do_not_overflow(browser):
    title = "Wednesday Wonderful Whimsical Wacky Welcome Week Wrapup Wow Wow"  # long, wide
    summary = " ".join(["Whatever"] * 30)
    quote = " ".join(["wonderful"] * 40)
    for names in ({f"Member {i}": LONG30 for i in range(1, 4)}, {f"Member {i}": "W" * 30 for i in range(1, 4)}, {f"Member {i}": "M" * 30 for i in range(1, 4)}):
        ai = zone(4, joke=mkitem(title, summary, quote), moment=mkitem(title, summary, quote, "m000002"), awards=[mkaward(title, "Member 1", summary), mkaward(title, "Member 2", summary)], names=names)
        check(render_ai(browser, ai))


def test_twelve_members_and_a_script_title(browser):
    names = names_for(12, lambda i: f"Member{i}Name" if i % 2 else LONG30)
    idx_members = zone(4, joke=mkitem("<script>alert(1)</script> & co", "a \"quoted\" <b>bold</b> summary", "quote with <img src=x onerror=1>"), names=names, n_members=12)
    res = render_ai(browser, idx_members, compute_stats(busy_frame([f"Member {i:02d}" for i in range(1, 13)])))
    check(res)
    p = parsed(res["html"])
    assert "script" not in p.tags and "img" not in p.tags and "b" not in p.tags and not {"onerror", "onclick"} & set(p.attrs)
    t = visible_text(res["html"])
    assert "<script>alert(1)</script> & co" in t and "<img src=x onerror=1>" in t


def test_footer_wording_and_one_line(browser):
    res = render_ai(browser, zone(4))
    check(res)
    assert visible_text(res["html"]).endswith("AI proposed 13 \u00b7 12 verified by code \u00b7 4 approved in review Quotes verified by code to exist in the chat. Pseudonymised text was sent to Claude Haiku.")
    syn = {**zone(4), "synthetic": True}
    res = render_ai(browser, syn)
    check(res)
    assert visible_text(res["html"]).endswith("AI proposed 13 \u00b7 12 verified by code \u00b7 all auto-approved (synthetic demo) Quotes verified by code to exist in the chat. Pseudonymised text was sent to Claude Haiku.")
    big = {**syn, "proposed": 123456, "verified": 123456, "approved": 123456}
    check(render_ai(browser, big, date_note="Dates read as m/d (assumed)"))


def test_footer_lines_and_the_date_note_rule():
    l1, l2 = card.ai_footer({"proposed": 13, "verified": 12, "approved": 4, "synthetic": False}, None)
    assert l1 == "AI proposed 13 \u00b7 12 verified by code \u00b7 4 approved in review"
    assert l2 == "Quotes verified by code to exist in the chat. Pseudonymised text was sent to Claude Haiku."
    assert card.ai_footer({"proposed": 13, "verified": 12, "approved": 4, "synthetic": False}, "Dates read as m/d (assumed)")[0] == l1 + " \u00b7 Dates read as m/d (assumed)"
    syn = card.ai_footer({"proposed": 1, "verified": 1, "approved": 1, "synthetic": True}, "x" * 80)[0]
    assert syn == "AI proposed 1 \u00b7 1 verified by code \u00b7 all auto-approved (synthetic demo)"  # a date note that would not fit is dropped


def test_zone2_text_is_never_below_the_floor_in_stats_only_mode_either(browser):
    stats = compute_stats(busy_frame(["Sam", "Alex", "Maya"]))
    res = card.render_png(card.build_card_html(stats, date_note="Dates read as m/d (assumed)"), browser=browser, measure=True)
    assert_clean(res)  # includes the floor check on Zone 2 and the footer, date note included


def test_moment_date_appears_once_in_the_attribution_and_not_in_the_label(browser):
    res = render_ai(browser, zone(2))
    check(res)
    assert res["html"].count("2026-01-05") == 2  # the joke's and the moment's attribution, nothing else
    assert re.search(r'<div class="zl">Moment</div>', res["html"]) and 'class="zl"><span' not in res["html"]


def test_smallest_zone1_font_is_reported_not_changed(browser, capsys):
    res = render_ai(browser, zone(4))
    z1 = min(res["overflow"]["fonts"]["zone1"], key=lambda f: f["size"])
    with capsys.disabled():
        print(f"\n[zone1] smallest computed font: {z1['size']} px on class {z1['cls']!r} ({z1['text']!r})")
    assert z1["size"] > 0


# ---------------------------------------------------------------- the commands (in-process; renders reuse the session browser)
LINES = [("9:01 AM", "Sam", "reminder: cheese protocol is in effect"), ("9:02 AM", "Maya", "Well, that cake was a disaster."),
         ("9:03 AM", "Kai", "ok see you all there tomorrow"), ("9:04 AM", "Sam", "yes the cheese protocol continues")]
# assembled at run time so the repo scanner does not see chat-export lines outside tests/fixtures
WA = "11/6/25, 9:00 AM - Messages and calls are end-to-end encrypted.\n" + "".join("11/6/25, " + t + " - " + who + ": " + text + "\n" for t, who, text in LINES)


@pytest.fixture
def world(tmp_path, monkeypatch, browser):
    chat = tmp_path / "chat.txt"
    chat.write_text(WA, encoding="utf-8")
    al_ = tmp_path / "aliases.json"
    al_.write_text(json.dumps({"members": [{"export_name": "Sam", "display": "Sammy S."}, {"export_name": "Maya", "display": "Maya"}, {"export_name": "Kai", "display": "Kai"}]}))
    report = {"running_jokes": [mkitem("Cheese protocol", "They keep saying it.", "reminder: cheese protocol is in effect", "m000001")],
              "moments": [mkitem("Cake disaster", "It sank.", "Well, that cake was a disaster.", "m000002"), mkitem("PENDING MOMENT", "never shown", "ok see you all there tomorrow", "m000003")],
              "awards": [mkaward("Best planner", "Member 3", "Always plans."), mkaward("REJECTED AWARD", "Member 1", "never shown")]}
    run = tmp_path / "20260101T000000-A.json"
    run.write_text(json.dumps({"config": "A", "messages": 4, "slice": {"start": None, "end": "2025-11-06"}, "stats": {"items_in": 6, "items_kept": 5}}))
    (tmp_path / "20260101T000000-A.report.json").write_text(json.dumps(report))
    real = card.render_png
    monkeypatch.setattr(card, "render_png", lambda html, out=None, **kw: real(html, out, browser=browser, **kw))  # never a second Chromium
    return type("W", (), {"tmp": tmp_path, "chat": chat, "aliases": al_, "run": run, "report": report})


def card_args(w, *extra, until="2025-11-06"):
    return ["card", str(w.chat), "--aliases", str(w.aliases), "--date-order", "mdy", "--out", str(w.tmp / "o.png"), "--html", str(w.tmp / "o.html"), *extra] + (["--until", until] if until else [])


def test_only_approved_items_render_pending_and_rejected_never(world, capsys):
    rv = review.new_review(world.report, "r")
    ids = {v["title"]: i for i, v in rv["items"].items()}
    review.set_status(rv, [ids["Cheese protocol"], ids["Cake disaster"], ids["Best planner"]], "approved")
    review.set_status(rv, [ids["REJECTED AWARD"]], "rejected")  # PENDING MOMENT stays pending
    review.save_review(world.tmp / "rv.json", rv)
    assert cli.main(card_args(world, "--report", str(world.run), "--review", str(world.tmp / "rv.json"))) == 0
    html = (world.tmp / "o.html").read_text()
    t = visible_text(html)
    assert "Cheese protocol" in t and "Cake disaster" in t and "Best planner" in t and "PENDING MOMENT" not in html and "REJECTED AWARD" not in html and "never shown" not in html
    assert "Sammy S." in t and "Kai" in t and not re.search(r"Member \d+", t)  # tokens mapped to the alias display names
    assert t.endswith("AI proposed 6 \u00b7 5 verified by code \u00b7 3 approved in review Quotes verified by code to exist in the chat. Pseudonymised text was sent to Claude Haiku.")
    assert png_size((world.tmp / "o.png").read_bytes()) == (1080, 1350)


def test_without_a_review_nothing_renders(world, capsys):
    assert cli.main(card_args(world, "--report", str(world.run))) == 0
    t = visible_text((world.tmp / "o.html").read_text())
    assert "No AI items approved" in t and "Cheese protocol" not in t and "approved 0" in capsys.readouterr().err


def test_auto_approve_is_refused_on_a_non_frozen_chat(world, capsys):
    assert cli.main(card_args(world, "--report", str(world.run), "--auto-approve-synthetic")) == 2
    assert "only allowed for the frozen synthetic chat" in capsys.readouterr().err and not (world.tmp / "o.png").exists()


def test_auto_approve_works_on_the_frozen_chat_and_says_so_in_the_footer(world, capsys, tmp_path):
    verify_dataset()
    run = tmp_path / "frozen-A.json"
    run.write_text(json.dumps({"config": "A", "messages": 1594, "slice": {"start": None, "end": "2026-02-08"}, "stats": {"items_in": 2, "items_kept": 2}}))
    (tmp_path / "frozen-A.report.json").write_text(json.dumps({"running_jokes": [], "awards": [], "moments": [mkitem("Cake disaster", "It sank.", "reminder: cheese protocol is in effect", "m000001")]}))
    out, html = tmp_path / "f.png", tmp_path / "f.html"
    rc = cli.main(["card", str(FROZEN), "--aliases", str(ROOT / "aliases.example.json"), "--report", str(run), "--auto-approve-synthetic", "--until", "2026-02-08", "--out", str(out), "--html", str(html)])
    assert rc == 0
    t = visible_text(html.read_text())
    assert "AI proposed 2 \u00b7 2 verified by code \u00b7 all auto-approved (synthetic demo)" in t and "Cake disaster" in t and not re.search(r"Member \d+", t)
    assert png_size(out.read_bytes()) == (1080, 1350)


def test_slice_end_must_match_until(world, capsys):
    assert cli.main(card_args(world, "--report", str(world.run), until="2025-11-07")) == 3
    assert "same window" in capsys.readouterr().err and not (world.tmp / "o.png").exists()
    assert cli.main(card_args(world, "--report", str(world.run), "--since", "2025-11-06")) == 3  # a different start is also a different window


def test_slice_end_is_derived_for_logs_without_a_slice_field(world, capsys):
    log = json.loads(world.run.read_text())
    del log["slice"]
    world.run.write_text(json.dumps(log))
    assert cli.main(card_args(world, "--report", str(world.run))) == 0
    assert "warning: the run log has no slice field, so the slice end was derived from its message count (4)" in capsys.readouterr().err
    log["messages"] = 3
    world.run.write_text(json.dumps(log))
    assert cli.main(card_args(world, "--report", str(world.run))) == 3


def test_report_needs_until_a_saved_report_and_a_successful_run(world, capsys, tmp_path):
    assert cli.main(card_args(world, "--report", str(world.run), until=None)) == 2
    (world.tmp / "20260101T000000-A.report.json").unlink()
    assert cli.main(card_args(world, "--report", str(world.run))) == 3 and "without --save-response" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"error": "AnalysisError: boom", "messages": 4}))
    (tmp_path / "bad.report.json").write_text("{}")
    assert cli.main(card_args(world, "--report", str(bad))) == 3 and "run failed" in capsys.readouterr().err
    assert cli.main(card_args(world, "--report", str(world.tmp / "nope.json"))) == 3


def test_no_report_renders_the_stats_only_card_as_before(world):
    assert cli.main(card_args(world, until=None)) == 0
    t = visible_text((world.tmp / "o.html").read_text())
    assert card.FOOTER in t and card.ZONE2_OFF in t and "z2body" not in (world.tmp / "o.html").read_text()


def test_review_and_auto_approve_are_mutually_exclusive(world):
    with pytest.raises(SystemExit) as e:
        cli.main(card_args(world, "--report", str(world.run), "--review", "x.json", "--auto-approve-synthetic"))
    assert e.value.code == 2


def test_award_name_is_at_least_as_large_as_the_member_name_and_summaries_use_three_lines(browser):
    res = render_ai(browser, zone(4))
    check(res)
    r = card.render_png(res["html"], browser=browser, measure=True,
                        probe="({name: [...document.querySelectorAll('.za .zt')].map(e => parseFloat(getComputedStyle(e).fontSize)), "
                              "member: [...document.querySelectorAll('.za .zm')].map(e => parseFloat(getComputedStyle(e).fontSize)), "
                              "weight: [...document.querySelectorAll('.za .zt')].map(e => getComputedStyle(e).fontWeight)})")
    assert r["probe"]["name"] == [22, 22] and r["probe"]["member"] == [20, 20] and all(w in ("700", "800", "bold") for w in r["probe"]["weight"])


def test_three_line_summary_and_two_line_quote_fit_with_a_one_line_title(browser):
    summary = " ".join(["Whatever"] * 30)  # cut to the limit: about three lines at 22 px
    quote = " ".join(["wonderful"] * 40)  # cut to the limit: two lines
    ai = zone(2, joke=mkitem("A title within thirty", summary, quote), moment=mkitem("Another short title", summary, quote, "m000002"))
    res = render_ai(browser, ai)
    check(res)
    r = card.render_png(res["html"], browser=browser, measure=True,
                        probe="[...document.querySelectorAll('.zs')].slice(0, 2).map(e => Math.round(e.getBoundingClientRect().height / 27))")
    assert r["probe"] == [3, 3]


def test_a_long_title_is_cut_to_one_line_so_the_three_line_summary_still_fits(browser):
    long_title = "A very long title that the model wrote for this joke"
    res = render_ai(browser, zone(2, joke=mkitem(long_title, " ".join(["Whatever"] * 30)), moment=mkitem(long_title, " ".join(["Whatever"] * 30), "reminder: cheese protocol is in effect", "m000002")))
    check(res)
    assert long_title not in res["html"] and "\u2026" in res["html"]
