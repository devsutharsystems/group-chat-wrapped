"""Phase 9e: the upload cap is stated in Step 1 and the README, with the value Streamlit enforces (server.maxUploadSize, set in .streamlit/config.toml)."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from streamlit import config

from gcw import appcore
from test_app import chat_text, env, go, start  # noqa: F401  (env is a fixture)

ROOT = Path(__file__).resolve().parents[1]
CAP = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())["server"]["maxUploadSize"]


@pytest.fixture
def cap_loaded():
    # Streamlit reads .streamlit/config.toml from the working directory, and other tests change directory, so load the file's value explicitly.
    old = config.get_option("server.maxUploadSize")
    config.set_option("server.maxUploadSize", CAP)
    yield
    config.set_option("server.maxUploadSize", old)


def test_the_cap_is_set_explicitly_in_the_config_file():
    assert CAP == 50


def test_step_1_says_uploads_are_limited_with_the_real_cap_value(env, cap_loaded):  # noqa: F811
    at = start(chat_text())
    go(at, "1 Load")
    at.radio(key="source").set_value("Upload an export").run()
    note = appcore.upload_limit_note()
    assert f"Uploads are limited to {CAP} MB." in note and "unzipped and its .txt uploaded" in note and "re-exported without media" in note
    assert note in [c.value for c in at.caption]


def test_readme_states_the_limit():
    t = (ROOT / "README.md").read_text()
    assert f"Uploads are limited to {CAP} MB" in t and "re-exported without media" in t
