"""Phase 6: the Streamlit app (streamlit.testing.v1.AppTest) and appcore. Fake clients and a fake renderer only; a socket blocker proves what the app touches.
No real network, no API, no browser (the card subprocess is replaced by a fake that returns PNG bytes)."""
from __future__ import annotations

import io
import json
import os
import socket
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from gcw import appcore, chunked, cost

APP = str(Path(__file__).resolve().parents[1] / "src" / "gcw" / "app.py")
HOSTILE_SENDER = "<script>alert(1)</script>"
HOSTILE_TEXT = "<img src=x onerror=alert(1)> **bold** [x](javascript:alert(1))"
MARKS = ("<script", "<img", "onerror")
def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, "PNG")
    return buf.getvalue()


PNG = _png()


def chat_text() -> str:
    L = []
    for d in range(1, 29):
        for h, who, t in ((9, "Sam", f"good morning everyone day {d}"), (10, "Alex", f"the stapler has opinions again{' today' if d % 7 == 0 else ''}" if d % 7 in (1, 3, 5) else f"talking about lunch plans day {d}"),
                          (11, HOSTILE_SENDER, HOSTILE_TEXT + f" {d}")):
            L.append(f"1/{d}/26, {h}:00 AM - {who}: {t}")
    L.append("1/20/26, 1:00 PM - Sam: I got the job! Starting next month.")
    return "\n".join(L) + "\n"


class FakeClient:
    """count_tokens and create; builds a joke from the stapler lines it finds in the request and a moment from the job line."""

    def __init__(self):
        self.count_calls, self.create_calls = [], []
        self.messages = SimpleNamespace(count_tokens=self._count, create=self._create)

    def _count(self, **kw):
        self.count_calls.append(kw)
        return SimpleNamespace(input_tokens=2000)

    def _create(self, **kw):
        self.create_calls.append(kw)
        content = kw["messages"][0]["content"]
        import re

        lines = [m.groups() for m in re.finditer(r"^(m\d{6}) \| (\d{4}-\d{2}-\d{2}) [\d:]+ \| [^|]+ \| (.*)$", content, re.M)]
        stap = [(i, t) for i, d, t in lines if "stapler has opinions" in t][:3]
        job = [(i, t) for i, d, t in lines if "got the job" in t][:1]
        rep = {"running_jokes": [{"title": "Stapler opinions", "summary": "The stapler keeps having opinions.", "evidence": [{"message_id": i, "quote": t} for i, t in stap]}],
               "moments": [{"title": "The job news", "summary": "Someone got a job.", "evidence": [{"message_id": i, "quote": t} for i, t in job]}], "awards": []}
        usage = SimpleNamespace(input_tokens=2000, output_tokens=200, cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(rep))], usage=usage, stop_reason="end_turn")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(appcore, "LEDGER_PATH", str(tmp_path / "ledger.json"))
    fake = FakeClient()
    monkeypatch.setattr(appcore, "client_factory", lambda: fake)
    renders = []
    monkeypatch.setattr(appcore, "render_png_bytes", lambda html: (renders.append(html), PNG)[1])
    monkeypatch.setattr(appcore, "key_loaded", lambda: True)
    monkeypatch.delenv("GCW_COST_CAP_USD", raising=False)
    sockets = []
    real_connect = socket.socket.connect

    def spy(self, addr):
        sockets.append(addr)
        raise OSError("sockets are blocked in this test")

    monkeypatch.setattr(socket.socket, "connect", spy)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError("blocked")))
    return SimpleNamespace(fake=fake, renders=renders, sockets=sockets, root=tmp_path, real_connect=real_connect)


def start(text: str | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.session_state["text"] = text if text is not None else chat_text()
    at.session_state["chat_label"] = "test chat"
    return at.run()


def go(at: AppTest, step: str) -> AppTest:
    at.sidebar.radio[0].set_value(step).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def ai_mode(at: AppTest, mode: str = "auto") -> AppTest:
    go(at, "2 Settings")
    at.radio(key="mode_radio").set_value("AI (sends pseudonymised text to Anthropic after consent)").run()
    at.selectbox(key="ai_mode_w").set_value(mode).run()
    assert not at.exception
    return at


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# ---------------------------------------------------------------- (a), (b): nothing is sent before consent; stats-only needs no key
def test_steps_1_to_3_and_step_4_before_consent_make_no_client_call_and_use_no_socket(env, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(appcore, "key_loaded", lambda: False)  # stats-only must work with no key at all
    at = start()
    go(at, "1 Load")
    assert [m.value for m in at.metric][0] == "85"
    go(at, "2 Settings")
    go(at, "3 Stats card")
    at.button(key="render_stats").click().run()
    assert not at.exception and len(env.renders) == 1 and at.session_state["png"] == PNG
    ai_mode(at)
    go(at, "4 AI")
    assert "key loaded: no" in " ".join(t.value for t in at.text)
    run = at.button(key="run_ai")
    assert run.disabled  # no consent, no key
    assert env.fake.count_calls == [] and env.fake.create_calls == [] and env.sockets == []


def test_stats_only_never_touches_the_client_at_all(env, monkeypatch):
    called = []
    monkeypatch.setattr(appcore, "client_factory", lambda: called.append(1))
    at = start()
    go(at, "3 Stats card")
    at.button(key="render_stats").click().run()
    assert not at.exception and called == [] and env.sockets == []


# ---------------------------------------------------------------- (g), (f): Run needs the checkbox; caps stop it
def test_run_is_disabled_without_the_consent_checkbox_and_enabled_with_it(env):
    at = ai_mode(start())
    go(at, "4 AI")
    assert at.button(key="run_ai").disabled
    assert appcore.CONSENT_TEXT in [c.label for c in at.checkbox]
    at.checkbox(key="consent").check().run()
    assert not at.button(key="run_ai").disabled and env.fake.count_calls == []


def test_a_cost_cap_below_the_worst_case_bound_disables_run_and_run_ai_refuses(env, monkeypatch):
    monkeypatch.setenv("GCW_COST_CAP_USD", "0.0001")
    at = ai_mode(start())
    go(at, "4 AI")
    at.checkbox(key="consent").check().run()
    assert at.button(key="run_ai").disabled and any("above a cost cap" in e.value for e in at.error)
    df, _ = appcore.parse_view(chat_text())
    with pytest.raises(appcore.AppError, match="exceeds the cap"):
        appcore.run_ai(df, None, "2026-01-01", "2026-01-28", "auto", consent=True)
    assert env.fake.count_calls == [] and env.fake.create_calls == []
    with pytest.raises(appcore.AppError, match="consent is required"):
        appcore.run_ai(df, None, "2026-01-01", "2026-01-28", "auto", consent=False)


def test_the_project_cap_is_enforced_from_the_ledger(env, monkeypatch):
    monkeypatch.setenv("GCW_PROJECT_CAP_USD", "1.0")
    (Path(appcore.LEDGER_PATH)).write_text(json.dumps({"entries": [{"label": "x", "cost_usd": 0.999999}]}))
    st = appcore.cap_status(0.05)
    assert not st["ok"] and st["project_room"] < 0.05


# ---------------------------------------------------------------- (c), (d): a full run writes no chat text; hostile text is escaped
def test_full_synthetic_run_writes_no_chat_text_and_escapes_hostile_strings(env):
    before = snapshot(env.root)
    at = start()
    for step in ("1 Load", "2 Settings", "3 Stats card"):
        go(at, step)
    at.button(key="render_stats").click().run()
    ai_mode(at)
    go(at, "4 AI")
    at.checkbox(key="consent").check().run()
    at.button(key="run_ai").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    res = at.session_state["ai_result"]
    assert res["mode"] == "single" and len(env.fake.create_calls) == 1 and len(env.fake.count_calls) >= 1 and env.sockets == []
    assert sum(len(res["verified"][t]) for t in res["verified"]) == 2
    go(at, "5 Review")
    ids = [r.key for r in at.radio if str(r.key).startswith("dec_")]
    assert len(ids) == 2
    for k in ids:
        at.radio(key=k).set_value("approved").run()
    at.button(key="render_review").click().run()
    assert not at.exception and len(env.renders) == 2
    assert "Stapler opinions" in env.renders[-1] and "Member 1" not in env.renders[-1]  # the approved joke renders, with display names instead of tokens
    after = snapshot(env.root)
    new = {k: v for k, v in after.items() if k not in before}
    allowed = {"ledger.json", os.path.join("out", "app", "review_app.json")}
    assert all(k in allowed or (k.startswith(os.path.join("out", "runs")) and k.endswith(".json")) for k in new), sorted(new)
    assert "out/app/review_app.json" in {k.replace(os.sep, "/") for k in new}
    rv = json.loads(new[os.path.join("out", "app", "review_app.json")])
    assert all(set(v) <= {"type", "status", "rank"} for v in rv["items"].values()) and {v["status"] for v in rv["items"].values()} == {"approved"}
    for needle in ("stapler", "got the job", "good morning", "lunch plans", HOSTILE_TEXT[:12], "Sam", "Alex", HOSTILE_SENDER):
        assert all(needle.encode() not in v for v in new.values()), needle
    # (d) hostile strings reach the page only through text elements and dataframes, never through markdown-like elements
    for kind in ("markdown", "caption", "header", "subheader", "title", "info", "warning", "error", "success"):
        for el in getattr(at, kind):
            assert not any(m in str(el.value) for m in MARKS), (kind, el.value)
    for el in at.metric:
        assert not any(m in str(el.label) + str(el.value) for m in MARKS)
    assert "Stapler opinions" in " ".join(t.value for t in at.text)


def test_the_source_never_uses_unsafe_html_and_the_config_is_local_only():
    src = Path(APP).read_text(encoding="utf-8") + Path(appcore.__file__).read_text(encoding="utf-8")
    assert "unsafe_allow_html" not in src and "persist" not in src
    cfg = (Path(APP).parents[2] / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'address = "127.0.0.1"' in cfg and "gatherUsageStats = false" in cfg


def test_the_hostile_chat_is_escaped_in_the_load_and_settings_steps(env):
    at = start()
    for step in ("1 Load", "2 Settings", "3 Stats card", "4 AI", "5 Review"):
        go(at, step)
        for kind in ("markdown", "caption", "header", "subheader", "title", "info", "warning", "error", "success"):
            for el in getattr(at, kind):
                assert not any(m in str(el.value) for m in MARKS), (step, kind)
    go(at, "1 Load")
    assert HOSTILE_SENDER in " ".join(str(df.value) for df in at.dataframe)


# ---------------------------------------------------------------- (e): uploads
def make_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in members.items():
            z.writestr(n, b)
    return buf.getvalue()


def test_upload_accepts_one_txt_and_one_zipped_txt_in_memory():
    t = chat_text()
    assert appcore.read_upload("c.txt", t.encode()) == t
    assert appcore.read_upload("c.zip", make_zip({"_chat.txt": t.encode()})) == t
    assert appcore.read_upload("c.zip", make_zip({"__MACOSX/._chat.txt": b"x", "_chat.txt": t.encode()})) == t  # macOS resource-fork entries are ignored


@pytest.mark.parametrize("name, data, msg", [
    ("c.zip", make_zip({"a.txt": b"x", "b.txt": b"y"}), "exactly one"),
    ("c.zip", make_zip({"a.txt": b"x", "b.png": b"y"}), "exactly one"),
    ("c.zip", make_zip({"a.png": b"x"}), "not a .txt"),
    ("c.zip", make_zip({}), "exactly one"),
    ("c.zip", b"not a zip", "not a readable zip"),
    ("c.pdf", b"x", "upload a WhatsApp export"),
    ("c.txt", b"\xff\xfe\x00bad", "not UTF-8"),
])
def test_upload_refuses_bad_files(name, data, msg):
    with pytest.raises(appcore.AppError, match=msg):
        appcore.read_upload(name, data)


def test_an_oversized_member_is_refused_by_its_header_and_by_what_it_really_contains(monkeypatch):
    monkeypatch.setattr(appcore, "MAX_UNCOMPRESSED", 1000)
    with pytest.raises(appcore.AppError, match="larger than"):
        appcore.read_upload("c.zip", make_zip({"a.txt": b"a" * 5000}))  # compresses to a few bytes; the uncompressed size is what counts
    monkeypatch.setattr(appcore, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(appcore.AppError, match="larger than"):
        appcore.read_upload("c.txt", b"x" * 11)


def test_the_upload_widget_rejects_a_two_txt_zip_and_accepts_a_single_txt_zip(env):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.file_uploader(key="upload").upload("c.zip", make_zip({"a.txt": chat_text().encode(), "b.txt": b"y"}), "application/zip").run()
    at.button(key="use_upload").click().run()
    assert any("exactly one" in e.value for e in at.error) and "text" not in at.session_state
    at.file_uploader(key="upload").upload("c.zip", make_zip({"_chat.txt": chat_text().encode()}), "application/zip").run()
    at.button(key="use_upload").click().run()
    assert not at.error and at.session_state["text"] == chat_text() and [m.value for m in at.metric][0] == "85"
    assert env.sockets == [] and env.fake.count_calls == []


# ---------------------------------------------------------------- small core pieces
def test_default_window_is_365_days_ending_at_the_last_message_and_aliases_come_from_the_table():
    assert appcore.default_window("2026-12-31") == ("2026-01-01", "2026-12-31")
    al = appcore.aliases_from_table([{"export_name": "Sam", "display": "Sammy", "nicknames": "Sam J, sj"}, {"export_name": "Alex", "display": "", "nicknames": ""}])
    assert al.display_map() == {"Sam": "Sammy", "Alex": "Alex"} and al.members[0].nicknames == ("Sam J", "sj")
    with pytest.raises(appcore.AppError):
        appcore.aliases_from_table([{"export_name": "Sam", "display": "S", "nicknames": "x"}])  # a 1-character nickname is refused by the aliases rules


def test_a_saved_report_is_reverified_so_unverified_claims_never_reach_the_card(env):
    df, _ = appcore.parse_view(chat_text())
    prep = appcore.preview(df, None, "2026-01-01", "2026-01-28")
    from gcw import analyze

    p = analyze.prepare(df, None, slice_start="2026-01-01", slice_end="2026-01-28")
    bad = {"running_jokes": [{"title": "t", "summary": "s", "evidence": [{"message_id": "m999999", "quote": "no such quote anywhere"}] * 3}], "moments": [], "awards": []}
    verified, stats = appcore.load_report_upload(json.dumps(bad).encode(), p["index"], set(p["members"]))
    assert verified["running_jokes"] == [] and prep["messages"] == 85
    with pytest.raises(appcore.AppError):
        appcore.load_report_upload(b"[1, 2", p["index"], set(p["members"]))


def test_cost_bounds_and_the_auto_threshold_text():
    b = appcore.cost_bounds(270_000)
    assert b["single_usd"] < 0.25 and b["chunked_usd"] > 0 and b["chunks_upper"] == 4
    assert chunked.SINGLE_PASS_LIMIT == 300_000 and "300,000" in chunked.AUTO_WARNING
    assert cost.estimate_usd(1000, 16000) > 0


def test_context_shows_two_messages_each_side_with_display_names():
    rows = [{"pid": f"m{i:06d}", "ts": pd.Timestamp(year=2026, month=1, day=1, hour=9) + pd.Timedelta(minutes=i), "sender": f"Member {i % 2 + 1}", "body": f"line {i}", "withheld": i == 4}
            for i in range(1, 10)]
    ctx = appcore.context(rows, "m000005", {"Member 1": "Sam", "Member 2": "Alex"})
    assert [c["pid"] for c in ctx] == [f"m{i:06d}" for i in range(3, 8)] and ctx[1]["text"] == "[withheld]" and ctx[2]["is_target"] and ctx[0]["who"] == "Alex"
