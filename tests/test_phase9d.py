"""Phase 9d: the Step 1 label 'Sender lines', its caption, and the README sentence. No existing test pinned the old 'Messages' label (they read metric values by position)."""
from __future__ import annotations

from gcw import appcore
from gcw.parser import messages, parse_chat
from test_app import chat_text, env, go, start  # noqa: F401  (env is a fixture)
from test_privacy import ROOT

NOTE = "Sender lines include deleted messages and media. The stats card counts visible messages only: it leaves out deleted messages and system lines."


def test_step_1_names_the_count_sender_lines_and_explains_it_in_a_caption(env):  # noqa: F811
    at = start(chat_text())
    go(at, "1 Load")
    assert [m.label for m in at.metric] == ["Sender lines", "System lines", "Unparsed lines", "Senders"]
    assert "Messages" not in [m.label for m in at.metric]
    assert appcore.SENDER_LINES_NOTE == NOTE and NOTE in [c.value for c in at.caption]
    assert [m.value for m in at.metric][0] == "85"  # the number is unchanged


def test_the_caption_matches_the_bundled_chat_numbers(env):  # noqa: F811
    at = start(appcore.demo_text())
    go(at, "1 Load")
    df, rep = parse_chat(appcore.demo_text())
    assert at.metric[0].value == str(rep.n_messages) == "5144" and NOTE in [c.value for c in at.caption]
    assert len(messages(df)) == 5136 and int(df.is_deleted.sum()) == 8  # the stats card's count: sender lines minus the deleted ones


def test_the_readme_parser_line_says_the_same_thing():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    line = next(ln for ln in readme.splitlines() if ln.startswith("1. **Parse**"))
    assert ("The app's Step 1 counts sender lines, which include deleted messages and media; the stats card counts visible messages only "
            "(it leaves out deleted messages and system lines).") in line
