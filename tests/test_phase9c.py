"""Phase 9c: the zip loader ignores everything that is not the one .txt chat file (media, contact cards, hidden and macOS entries) and never reads the ignored entries.
Zips are built in pytest tmp_path from synthetic text only."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

import zip_counts
from gcw import appcore
from test_app import APP, chat_text  # noqa: F401
from test_privacy import ROOT

SECRET = "marker line that must never appear in a message"
CHAT = chat_text() + f"1/28, 11:30 PM - Sam: {SECRET}\n".replace("1/28, 11:30 PM", "1/28/26, 11:30 PM")


def make_zip(tmp_path: Path, members: dict[str, bytes | str], name: str = "z.zip") -> bytes:
    p = tmp_path / name
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in members.items():
            z.writestr(n, b)
    return p.read_bytes()


VCARDS = {f"contact {i}.vcf": f"BEGIN:VCARD\nFN:Person {i}\nEND:VCARD\n" for i in range(12)}


def test_one_txt_with_contact_cards_and_media_loads(tmp_path):
    data = make_zip(tmp_path, {"WhatsApp Chat with Test Group.txt": CHAT, **VCARDS, "IMG-0001.jpg": b"\xff\xd8", "PTT-0002.opus": b"x", "docs/photo.PNG": b"x"})
    text, ignored = appcore.read_zip_text(data)
    assert text == CHAT and ignored == 12 + 3  # 12 .vcf, 1 .jpg, 1 .opus, 1 .PNG ... counted as ignored entries
    assert appcore.read_upload("export.zip", data) == CHAT


def test_zero_txt_fails_with_a_message_that_counts_the_other_files_and_holds_no_chat_text(tmp_path):
    with pytest.raises(appcore.AppError) as e:
        appcore.read_upload("x.zip", make_zip(tmp_path, {**VCARDS, "note.md": SECRET}))
    assert str(e.value) == "no .txt chat file was found in the zip; it holds 13 other files" and SECRET not in str(e.value)
    with pytest.raises(appcore.AppError, match="it holds 0 other files"):
        appcore.read_upload("x.zip", make_zip(tmp_path, {}, "e.zip"))
    with pytest.raises(appcore.AppError, match="it holds 1 other file$"):
        appcore.read_upload("x.zip", make_zip(tmp_path, {"a.png": b"x"}, "one.zip"))


def test_two_txt_fails_with_the_count_and_no_chat_text(tmp_path):
    with pytest.raises(appcore.AppError) as e:
        appcore.read_upload("x.zip", make_zip(tmp_path, {"a.txt": CHAT, "b.txt": SECRET, "c.vcf": "x"}))
    assert str(e.value) == "2 .txt files were found in the zip; exactly one is required" and SECRET not in str(e.value)
    with pytest.raises(appcore.AppError, match="3 .txt files"):
        appcore.read_upload("x.zip", make_zip(tmp_path, {"a.txt": "x", "b.TXT": "y", "sub/c.txt": "z"}, "three.zip"))


def test_macos_hidden_and_non_txt_entries_are_ignored(tmp_path):
    members = {"__MACOSX/._chat.txt": b"x", "._chat.txt": b"x", ".hidden.txt": SECRET, ".hiddendir/other.txt": SECRET, "folder/.DS_Store": b"x", "chat.txt.vcf": "x", "chat.txt": CHAT}
    text, ignored = appcore.read_zip_text(make_zip(tmp_path, members))
    assert text == CHAT and ignored == 6
    with pytest.raises(appcore.AppError, match="no .txt chat file was found"):  # only ignored names: nothing to load
        appcore.read_upload("x.zip", make_zip(tmp_path, {"__MACOSX/a.txt": "x", ".b.txt": "y", "c.jpg": "z"}, "ign.zip"))
    assert appcore.read_zip_text(make_zip(tmp_path, {"Chat.TXT": CHAT}, "up.zip"))[0] == CHAT  # the extension test is case-insensitive


def test_ignored_entries_are_never_opened_or_size_checked(tmp_path, monkeypatch):
    data = make_zip(tmp_path, {"chat.txt": "hello there\n" * 20, "big.vcf": b"a" * 50_000, ".hidden": b"b" * 50_000, "huge.jpg": b"c" * 50_000})  # built before the spy is installed
    opened: list[str] = []
    real = zipfile.ZipFile.open

    def spy(self, name, *a, **k):
        opened.append(getattr(name, "filename", name))
        return real(self, name, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "open", spy)
    monkeypatch.setattr(appcore, "MAX_UNCOMPRESSED", 3000)  # the ignored entries are over this cap and still do not matter
    assert appcore.read_zip_text(data)[0].startswith("hello there")
    assert opened == ["chat.txt"]


def test_existing_caps_and_the_plain_txt_upload_still_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(appcore, "MAX_UNCOMPRESSED", 1000)
    with pytest.raises(appcore.AppError, match="larger than"):
        appcore.read_upload("c.zip", make_zip(tmp_path, {"chat.txt": b"a" * 5000, "x.vcf": "x"}))
    monkeypatch.undo()
    monkeypatch.setattr(appcore, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(appcore.AppError, match="larger than"):
        appcore.read_upload("c.txt", b"x" * 11)
    monkeypatch.undo()
    assert appcore.read_upload("plain.txt", CHAT.encode()) == CHAT
    with pytest.raises(appcore.AppError, match="not UTF-8"):
        appcore.read_upload("c.zip", make_zip(tmp_path, {"chat.txt": b"\xff\xfe\x00bad", "a.vcf": "x"}))
    with pytest.raises(appcore.AppError, match="upload a WhatsApp export"):
        appcore.read_upload("c.pdf", b"x")


def test_the_app_upload_widget_loads_a_zip_with_contact_cards(tmp_path):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=60).run()
    at.file_uploader(key="upload").upload("export.zip", make_zip(tmp_path, {"chat.txt": CHAT, **VCARDS}), "application/zip").run()
    at.button(key="use_upload").click().run()
    assert not at.error and not at.exception and at.session_state["text"] == CHAT


def test_the_counts_helper_prints_only_counts(tmp_path, capsys):
    p = tmp_path / "real.zip"
    p.write_bytes(make_zip(tmp_path, {"chat.txt": CHAT, **VCARDS}, "src.zip"))
    assert zip_counts.main(["zip_counts.py", str(p)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("messages ") and "ignored zip entries 12" in out and "date range 2026-01-01 to 2026-01-28" in out and SECRET not in out and "Sam" not in out and "\n" == out[-1] and out.count("\n") == 1
    assert zip_counts.main(["zip_counts.py", str(tmp_path / "missing.zip")]) == 3


def test_the_wording_that_pinned_the_old_rule_is_updated():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "all other files in the zip, such as media and contact cards, are ignored and never read" in readme
    assert "other files in the zip are ignored" in (ROOT / "src/gcw/app.py").read_text()
    assert "holding exactly one .txt)" not in (ROOT / "src/gcw/app.py").read_text()
