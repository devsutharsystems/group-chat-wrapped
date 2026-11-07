"""Phase 6-fix3: the GCW_LEDGER_PATH override (the real ledger is neither read nor modified when it is set), the screenshot script's demo ledger, the toolbar option."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import app_screenshots as shots
from gcw import appcore, cost
from test_app import ai_mode, env, go, start  # noqa: F401  (env is a fixture)

REAL = Path(cost.LEDGER_PATH)


def spy_reads(monkeypatch) -> list[str]:
    seen: list[str] = []
    real = cost._read

    def spy(path):
        seen.append(str(path))
        return real(path)

    monkeypatch.setattr(cost, "_read", spy)
    return seen


def test_default_ledger_path_is_unchanged_without_the_variable(monkeypatch):
    monkeypatch.delenv("GCW_LEDGER_PATH", raising=False)
    assert cost.default_ledger_path() == cost.LEDGER_PATH and cost.CostGuard().ledger_path == REAL
    monkeypatch.setenv("GCW_LEDGER_PATH", "")
    assert cost.default_ledger_path() == cost.LEDGER_PATH  # empty means unset


def test_the_override_is_respected_and_the_real_ledger_is_not_read_or_modified(tmp_path, monkeypatch):
    before = (REAL.read_bytes(), REAL.stat().st_mtime_ns) if REAL.exists() else None
    mine = tmp_path / "other.json"
    monkeypatch.setenv("GCW_LEDGER_PATH", str(mine))
    seen = spy_reads(monkeypatch)
    g = cost.CostGuard()
    assert g.ledger_path == mine and cost.ledger_total() == 0.0
    r = g.check(0.01, confirm=True)
    usage = SimpleNamespace(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    g.record("t:x", usage, "claude-haiku-5-5", reserved=r)
    assert cost.ledger_total() > 0 and len(cost.ledger_entries()) == 1 and mine.exists()
    assert str(REAL) not in seen and set(seen) == {str(mine)}
    assert before == ((REAL.read_bytes(), REAL.stat().st_mtime_ns) if REAL.exists() else None)


def test_the_screenshot_environment_uses_a_demo_ledger_with_one_fictional_entry(tmp_path):
    env_ = shots.server_env(tmp_path)
    p = Path(env_["GCW_LEDGER_PATH"])
    assert p.parent == tmp_path and p != REAL and "ANTHROPIC_API_KEY" not in env_
    assert [e["cost_usd"] for e in json.loads(p.read_text())["entries"]] == [0.05] and cost.ledger_total(p) == 0.05
    src = Path(shots.__file__).read_text(encoding="utf-8")
    assert "import cost" not in src and "ledger_total" not in src  # the harness itself never reads any ledger


def test_the_app_shows_the_demo_spend_and_never_reads_the_real_ledger(env, tmp_path, monkeypatch):  # noqa: F811
    demo = shots.demo_ledger(tmp_path / "w")
    monkeypatch.setattr(appcore, "LEDGER_PATH", None)
    monkeypatch.setenv("GCW_LEDGER_PATH", demo)
    seen = spy_reads(monkeypatch)
    at = ai_mode(start())
    go(at, "4 AI")
    assert "$0.05 already spent" in " ".join(t.value for t in at.text)
    assert seen and str(REAL) not in seen and set(seen) == {demo}


def test_the_toolbar_option_hides_only_developer_items():
    cfg = (Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'toolbarMode = "viewer"' in cfg and "docs.streamlit.io/develop/api-reference/configuration/config.toml" in cfg


def test_proposed_count_comes_from_the_run_log_and_is_none_without_one():
    assert appcore.proposed_from_log(json.dumps({"stats": {"items_in": 13}}).encode()) == 13
    for bad in (b"[1", b'{"stats": {}}', b'{"stats": {"items_in": "x"}}', b'{"stats": {"items_in": true}}', b"\xff"):
        assert appcore.proposed_from_log(bad) is None
    z = appcore.zone_for({"running_jokes": [], "moments": [], "awards": []}, {"items": {}}, {}, {}, None, {"items_in_by_type": {"awards": 2}}, proposed=13)
    assert z["proposed"] == 13 and appcore.zone_for({"running_jokes": [], "moments": [], "awards": []}, {"items": {}}, {}, {}, None, {"items_in_by_type": {"awards": 2}})["proposed"] == 2


def test_a_run_log_for_another_window_is_refused_and_its_message_count_is_read(env):  # noqa: F811
    assert appcore.log_messages(json.dumps({"messages": 85}).encode()) == 85
    for bad in (b"[", b"{}", b'{"messages": "x"}', b'{"messages": true}'):
        assert appcore.log_messages(bad) is None
    at = start()
    go(at, "5 Review")
    empty = json.dumps({"running_jokes": [], "moments": [], "awards": []}).encode()
    at.file_uploader(key="report_up").upload("demo.report.json", empty).run()
    at.file_uploader(key="log_up").upload("demo.json", json.dumps({"messages": 999, "stats": {"items_in": 0}}).encode()).run()
    assert any("covers 999 messages but the window" in e.value for e in at.error) and not at.exception
    assert not [r for r in at.radio if str(r.key).startswith("dec_")]


def test_only_the_screenshot_server_hides_the_menu_and_the_app_config_keeps_its_setting(tmp_path):
    assert shots.server_env(tmp_path)["STREAMLIT_CLIENT_TOOLBAR_MODE"] == "minimal"
    cfg = (Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'toolbarMode = "viewer"' in cfg and "minimal" not in cfg
