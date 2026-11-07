"""The rating tool in a real browser (the shared session browser): keys, notes, CSV download, resume, no network, escaping. No API."""
from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import expect

from gcw import evaluate, rating_ui
from test_phase4a import ALIASES, RUNS, TRUTH, mk_df

HTTP_FREE = ("file:", "blob:", "data:", "about:")


@pytest.fixture(scope="module")
def pack():
    return evaluate.build_rating_pack(mk_df(), ALIASES, RUNS, TRUTH, seed=4242)


@pytest.fixture
def view(pack, tmp_path):
    return evaluate.write_rating_pack(pack, tmp_path / "rating")["view"]


class Page:
    """A page in its own offline context of the shared browser; records every request URL."""

    def __init__(self, browser, accept_downloads=True):
        self.ctx = browser.new_context(viewport={"width": 1000, "height": 900}, offline=True, accept_downloads=accept_downloads)
        self.page = self.ctx.new_page()
        self.urls: list[str] = []
        self.page.on("request", lambda r: self.urls.append(r.url))
        self.errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))

    def close(self):
        self.ctx.close()


@pytest.fixture
def tool(browser):
    pages: list[Page] = []

    def make(**kw):
        p = Page(browser, **kw)
        pages.append(p)
        return p

    yield make
    for p in pages:
        p.close()


def csv_of(p: Page, tmp_path: Path) -> str:
    with p.page.expect_download() as d:
        p.page.click("#download")
    dl = d.value
    assert dl.suggested_filename == "ratings.csv"
    target = tmp_path / "dl.csv"
    dl.save_as(str(target))
    return target.read_bytes().decode("utf-8")


def header_and_ids(pack):
    return [(it["id"], it["type"]) for it in pack["items"]]


def expected_csv(pack, ratings: dict[str, tuple[str, str]]) -> str:
    lines = ["id,type,rating,note"]
    for i, t in header_and_ids(pack):
        r, n = ratings.get(i, ("", ""))
        q = '"' + n.replace('"', '""') + '"' if any(c in n for c in ',"\r\n') else n
        lines.append(f"{i},{t},{r},{q}")
    return "\r\n".join(lines) + "\r\n"


def test_keys_notes_download_and_exact_csv(tool, view, pack, tmp_path):
    p = tool()
    p.page.goto(view.as_uri())
    assert p.page.text_content("#progress") == f"1 / {len(pack['items'])}"
    p.page.keyboard.press("1")  # item 1: true
    p.page.keyboard.press("ArrowRight")
    assert p.page.text_content("#progress") == f"2 / {len(pack['items'])}"
    p.page.keyboard.press("2")  # item 2: partly
    p.page.click("#note")
    p.page.keyboard.type('kept 1, 2 and "3" and 4')  # digits typed in the note must NOT trigger shortcuts
    assert p.page.input_value("#note") == 'kept 1, 2 and "3" and 4'
    p.page.locator("body").click(position={"x": 5, "y": 400})  # leave the note box
    p.page.keyboard.press("ArrowRight")
    p.page.keyboard.press("3")  # item 3: false
    ids = header_and_ids(pack)
    got = csv_of(p, tmp_path)
    assert got == expected_csv(pack, {ids[0][0]: ("true", ""), ids[1][0]: ("partly", 'kept 1, 2 and "3" and 4'), ids[2][0]: ("false", "")})
    assert [ln.split(",")[0] for ln in got.split("\r\n")[1:-1]] == [i for i, _ in ids]  # same ids, same order as ratings.csv
    ratings_csv = evaluate.write_rating_pack(pack, tmp_path / "pack")["csv"].read_text()
    assert [ln.split(",")[:2] for ln in ratings_csv.splitlines()] == [ln.split(",")[:2] for ln in got.split("\r\n")[:-1]]
    assert p.errors == []


def test_arrow_keys_progress_nav_colours_and_clear(tool, view, pack):
    p, n = tool(), len(pack["items"])
    p.page.goto(view.as_uri())
    p.page.keyboard.press("ArrowLeft")  # at the first item: stays
    assert p.page.text_content("#progress") == f"1 / {n}" and p.page.is_disabled("#prev")
    p.page.keyboard.press("1")
    assert "s-true" in p.page.get_attribute("#nav button:nth-child(1)", "class") and "s-none" in p.page.get_attribute("#nav button:nth-child(2)", "class")
    assert p.page.text_content("#rated") == "1 rated"
    p.page.click(f"#nav button:nth-child({n})")  # jump to the last
    assert p.page.text_content("#progress") == f"{n} / {n}" and p.page.is_disabled("#next")
    p.page.keyboard.press("ArrowRight")
    assert p.page.text_content("#progress") == f"{n} / {n}"
    visible = p.page.locator("section.item:visible")
    assert visible.count() == 1 and visible.first.get_attribute("data-id") == pack["items"][-1]["id"]
    p.page.click("#nav button:nth-child(1)")
    p.page.click("#clear")
    assert "s-none" in p.page.get_attribute("#nav button:nth-child(1)", "class") and p.page.text_content("#rated") == "0 rated"


def test_tic_is_only_offered_for_jokes(tool, view, pack):
    p = tool()
    p.page.goto(view.as_uri())
    for k, it in enumerate(pack["items"]):
        p.page.click(f"#nav button:nth-child({k + 1})")
        shown = p.page.is_visible("#b-tic")
        assert shown is (it["type"] == "running_jokes"), it["type"]
        p.page.keyboard.press("4")
        want = "tic" if it["type"] == "running_jokes" else ""
        assert ("s-tic" in p.page.get_attribute(f"#nav button:nth-child({k + 1})", "class")) is bool(want)


def test_each_item_shows_type_title_summary_quotes_and_context_but_no_key_information(tool, view, pack):
    p = tool()
    p.page.goto(view.as_uri())
    first = pack["items"][0]
    text = p.page.text_content("section.item:visible")
    assert first["title"] in text and first["summary"] in text and first["type"].replace("_", " ") in text
    for ev in first["evidence"]:
        assert ev["quote"] in text and ev["cited"]["who"] in text and ev["cited"]["when"] in text
    page_text = p.page.text_content("body")
    for secret in [RUNS[0][0], RUNS[1][0], RUNS[2][0], "planted", "key.json", "j1", "j2", "j3", "jL", "m1"]:
        assert secret not in page_text and secret not in view.read_text(), secret
    assert "Rubric" in page_text and "JOKE true" in page_text and p.page.is_visible("#download") and p.page.is_visible("label.btn")
    assert p.page.locator("details").first.get_attribute("open") is not None  # the rubric is open at the top


def test_autosave_resume_and_load_csv_after_clearing_local_storage(tool, view, pack, tmp_path):
    p = tool()
    p.page.goto(view.as_uri())
    p.page.keyboard.press("1")
    p.page.keyboard.press("ArrowRight")
    p.page.keyboard.press("3")
    p.page.click("#note")
    p.page.keyboard.type("a, b")
    ids = header_and_ids(pack)
    saved = expected_csv(pack, {ids[0][0]: ("true", ""), ids[1][0]: ("false", "a, b")})
    assert csv_of(p, tmp_path) == saved
    p.page.reload()  # autosave: still there
    assert p.page.text_content("#rated") == "2 rated"
    p.page.evaluate("window.localStorage.clear()")
    p.page.reload()
    assert p.page.text_content("#rated") == "0 rated"
    f = tmp_path / "resume.csv"
    f.write_bytes(saved.encode("utf-8"))
    p.page.set_input_files("#load", str(f))
    expect(p.page.locator("#rated")).to_have_text("2 rated")  # (wait_for_function would evaluate a string, which the page's CSP forbids)
    assert "Loaded" in p.page.text_content("#status")
    assert csv_of(p, tmp_path) == saved  # a full round trip
    # a file with unknown ids, a bad rating and a tic on a non-joke is skipped row by row, never fatal
    non_joke = next(i for i, t in ids if t != "running_jokes")
    bad = f"id,type,rating,note\r\nzzz,moments,true,\r\n{ids[2][0]},{ids[2][1]},maybe,\r\n{non_joke},x,tic,\r\n{ids[3][0]},{ids[3][1]},partly,\"q \"\"x\"\"\"\r\n"
    f.write_bytes(bad.encode("utf-8"))
    p.page.set_input_files("#load", str(f))
    expect(p.page.locator("#status")).to_contain_text("skipped 3")
    assert p.page.text_content("#rated") == "3 rated"


def test_works_when_local_storage_is_unavailable(tool, view, pack, tmp_path):
    p = tool()
    p.page.set_content(view.read_text(encoding="utf-8"))  # about:blank has an opaque origin: window.localStorage throws
    assert p.page.evaluate("(() => { try { window.localStorage.getItem('x'); return 'works'; } catch (e) { return 'throws'; } })()") == "throws"
    p.page.keyboard.press("2")
    assert p.page.text_content("#rated") == "1 rated"
    ids = header_and_ids(pack)
    assert csv_of(p, tmp_path) == expected_csv(pack, {ids[0][0]: ("partly", "")})
    assert p.errors == []


def test_no_network_request_is_ever_made(tool, view, pack, tmp_path):
    p = tool()
    p.page.goto(view.as_uri())
    p.page.keyboard.press("1")
    csv_of(p, tmp_path)
    f = tmp_path / "x.csv"
    f.write_text("id,type,rating,note\r\n")
    p.page.set_input_files("#load", str(f))
    assert p.urls and all(u.startswith(HTTP_FREE) for u in p.urls), p.urls
    assert "Content-Security-Policy" in view.read_text() and "default-src 'none'" in view.read_text() and "connect-src" not in view.read_text()


def test_hostile_text_is_escaped_not_executed(tool, tmp_path):
    hostile = '<img src=x onerror="window.__pwned=1"> & "q" </script><script>window.__pwned2=1</script>'
    ev = {"quote": hostile, "cited": {"pid": "m1", "who": "<b>Eve</b>", "when": "2026-01-01" + " 10:00", "text": hostile}, "before": [{"pid": "m0", "who": hostile, "when": "w", "text": hostile}], "after": []}
    items = [{"id": "r01", "type": "running_jokes", "title": hostile, "summary": hostile, "evidence": [ev]},
             {"id": "r02", "type": "awards", "title": "ok", "summary": "ok", "member": hostile, "evidence": [ev]}]
    f = tmp_path / "v.html"
    f.write_text(rating_ui.render(items, 1), encoding="utf-8")
    p = tool()
    p.page.goto(f.as_uri())
    assert p.page.evaluate("typeof window.__pwned") == "undefined" and p.page.evaluate("typeof window.__pwned2") == "undefined"
    assert p.page.locator("main img").count() == 0 and p.page.locator("main b").count() == 0
    assert hostile in p.page.text_content("section.item:visible")  # shown literally as text
    assert f.read_text().count("<script") == 2  # the meta JSON and the tool's own code: nothing from the data
    p.page.keyboard.press("1")
    assert p.page.text_content("#rated") == "1 rated" and p.errors == []
