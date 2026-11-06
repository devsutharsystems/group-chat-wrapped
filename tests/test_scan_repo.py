from pathlib import Path

import pytest

from scan_repo import scan

NN = " "
ANDROID = "1/5/26, 9:15" + " AM - {}: hi"
ANDROID_NNBSP = "1/5/26, 9:15" + NN + "AM - {}: hi"
IOS = "[05/01/26, 09:15:02] {}: hi"


def make(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tests/fixtures/ALLOWED_NAMES.txt").write_text("Sam\nAlex\n")
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return tmp_path


def test_clean_tree(tmp_path):
    assert scan(make(tmp_path, {"a.py": "x = 1\n"})) == []


@pytest.mark.parametrize("line", [ANDROID, ANDROID_NNBSP, IOS])
def test_chat_line_outside_fixtures_flagged(tmp_path, line):
    assert scan(make(tmp_path, {"docs/x.txt": line.format("Sam")}))


@pytest.mark.parametrize("line", [ANDROID, ANDROID_NNBSP, IOS])
def test_allowed_name_in_fixtures_passes(tmp_path, line):
    assert scan(make(tmp_path, {"tests/fixtures/c.txt": line.format("Sam")})) == []


def test_unlisted_name_in_fixtures_flagged(tmp_path):
    assert scan(make(tmp_path, {"tests/fixtures/c.txt": ANDROID.format("Zed")}))


def test_synthetic_dir_checks_names(tmp_path):
    root = make(tmp_path, {"synthetic/c.txt": ANDROID.format("Zed")})
    assert scan(root)


def test_phone_flagged(tmp_path):
    assert scan(make(tmp_path, {"a.md": "call " + "+91 98765" + " 43210"}))


def test_phone_in_fixtures_still_flagged(tmp_path):
    assert scan(make(tmp_path, {"tests/fixtures/p.txt": "+1 415 555" + " 0132"}))


def test_email_flagged_but_example_ok(tmp_path):
    assert scan(make(tmp_path, {"a.md": "me@" + "gmail.com"}))
    assert scan(make(tmp_path / "ok", {"a.md": "me@" + "example.com"})) == []


def test_key_flagged(tmp_path):
    assert scan(make(tmp_path, {"a.py": "k = 'sk-" + "ant-" + "a" * 30 + "'"}))
    assert scan(make(tmp_path / "e", {"c.txt": "API_KEY=" + "x" * 24}))


def test_findings_do_not_echo_match(tmp_path):
    f = scan(make(tmp_path, {"a.md": "me@" + "gmail.com"}))
    assert all("gmail" not in x for x in f)


def test_skips_venv_and_env_file(tmp_path):
    root = make(tmp_path, {".venv/x.txt": "me@" + "gmail.com", ".env": "ANTHROPIC_API_KEY=" + "z" * 30})
    assert scan(root) == []


def test_iso_date_not_phone(tmp_path):
    assert scan(make(tmp_path, {"a.md": "verified 2026" + "-11-06 ok"})) == []
