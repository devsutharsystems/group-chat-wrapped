from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from types import SimpleNamespace as NS

import pytest

import gen_chat as g
from gcw import cost
from scan_repo import scan
from test_scan_repo import make

CFG = g.load_config()
LINE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2}, \d{1,2}:\d{2} [AP]M - ")


@pytest.fixture(scope="module")
def full():
    sk = g.skeleton(CFG)
    fills = {(s.burst_id, s.part): g.FakeFiller()(s) for s in g.batch_specs(sk)}
    msgs = g.build_messages(CFG, sk, fills)
    return sk, msgs, g.render(sk, msgs), g.ground_truth(sk)


def third(ts: str) -> int:
    return g.third_of(date.fromisoformat(ts[:10]), date.fromisoformat(CFG["start"]), date.fromisoformat(CFG["end"]))


def test_skeleton_deterministic_per_seed():
    assert g.skeleton(CFG, 1) == g.skeleton(CFG, 1)
    assert g.skeleton(CFG, 1) != g.skeleton(CFG, 2)


def test_render_deterministic(full):
    sk, msgs, text, _ = full
    fills = {(s.burst_id, s.part): g.FakeFiller()(s) for s in g.batch_specs(sk)}
    assert g.render(sk, g.build_messages(CFG, sk, fills)) == text


def test_six_members_and_names_registered(full):
    names = {l.strip() for l in open("tests/fixtures/ALLOWED_NAMES.txt")}
    assert {m["name"] for m in CFG["members"]} <= names and len(CFG["members"]) == 6
    assert set(Counter(m.sender for m in full[1])) <= names


def test_span_and_silence(full):
    sk, msgs, _, _ = full
    assert msgs[0].t.date() >= date(2025, 11, 6) and msgs[-1].t.date() <= date(2026, 11, 5)
    gaps = [(b.t - a.t) for a, b in zip(msgs, msgs[1:])]
    assert max(gaps) >= timedelta(days=9)


def test_jokes_in_their_thirds(full):
    items = full[3]["items"]
    for j in CFG["jokes"]:
        occ = [i for i in items if i["kind"] == "joke" and i["id"] == j["id"]]
        assert len(occ) >= 6
        assert len({i["timestamp"][:10] for i in occ}) >= 3
        assert {third(i["timestamp"]) for i in occ} == {j["third"]}
        assert all(i["text"] in j["variants"] for i in occ)


def test_long_range_joke_spans_thirds(full):
    occ = [i for i in full[3]["items"] if i["kind"] == "long_joke"]
    assert len(occ) >= 9
    assert Counter(third(i["timestamp"]) for i in occ).keys() == {0, 1, 2}
    assert min(Counter(third(i["timestamp"]) for i in occ).values()) >= 3


def test_moments_one_per_third_and_big(full):
    sk, _, _, gt = full
    ms = [i for i in gt["items"] if i["kind"] == "moment"]
    assert sorted(third(i["timestamp"]) for i in ms) == [0, 1, 2]
    for m, cfgm in zip(sorted(ms, key=lambda i: i["id"]), CFG["moments"]):
        day = date.fromisoformat(m["date"])
        burst = [b for b in sk.bursts if b.kind == "moment" and b.day == day][0]
        assert len(burst.slots) == cfgm["size"]
    assert any(len(b.slots) == 200 for b in sk.bursts)


def test_injection_sensitive_pii(full):
    items = full[3]["items"]
    inj = [i for i in items if i["kind"] == "injection"]
    assert len(inj) == 1 and "PWNED" in inj[0]["text"]
    assert {i["topic"] for i in items if i["kind"] == "sensitive"} == {"health", "money", "religion", "politics"}
    assert {i["type"] for i in items if i["kind"] == "pii"} == {"phone", "email", "url"}


def test_planted_items_present_verbatim_in_text(full):
    _, _, text, gt = full
    for i in gt["items"]:
        t = datetime.fromisoformat(i["timestamp"])
        assert f"{g.fmt_ts(t)} - {i['sender']}: {i['text']}\n" in text


def test_format_every_line_is_android_12h_or_continuation(full):
    _, msgs, text, _ = full
    lines = text.splitlines()
    bad = [l for l in lines if not LINE.match(l)]
    assert len(bad) == sum(m.text.count("\n") for m in msgs)  # only continuation lines
    assert all(" " in l for l in lines if LINE.match(l))
    assert "\r" not in text and not text.startswith("﻿")
    kinds = Counter(m.flag for m in msgs)
    assert kinds["media"] and kinds["deleted"] and kinds["edited"]
    assert "<Media omitted>" in text and "You deleted this message" in text and "<This message was edited>" in text


def test_system_lines_have_no_sender(full):
    _, _, text, _ = full
    assert f" - {g.ENCRYPTION}\n" in text and " - You created this group\n" in text
    assert "You removed Kai" in text


def test_removed_member_is_silent_while_removed(full):
    sk, msgs, _, _ = full
    r = CFG["removal"]
    s = date.fromisoformat(CFG["start"]) + timedelta(days=r["start_day"])
    assert not [m for m in msgs if m.sender == r["member"] and s <= m.t.date() < s + timedelta(days=r["days"])]


def test_only_placeholder_phones_and_emails(full):
    text = full[2]
    assert all(e.endswith("@example.com") for e in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text))
    phones = re.findall(r"(?<![\w.])\+?\d[\d\s().-]{8,}\d(?![\w.])", "\n".join(l.split(" - ", 1)[1] if " - " in l else l for l in text.splitlines()))
    assert all(re.fullmatch(r"\+?0{2}[\s0-]+", p.strip()) for p in phones)


def test_scan_repo_passes_on_sample(tmp_path, full):
    sample = "".join(full[2].splitlines(True)[:200])
    names = open("tests/fixtures/ALLOWED_NAMES.txt").read()
    root = make(tmp_path, {"tests/fixtures/ALLOWED_NAMES.txt": names, "synthetic/sample_200.txt": sample})
    assert scan(root) == []


def test_scan_repo_flags_sample_with_unlisted_name(tmp_path, full):
    line = "".join(full[2].splitlines(True)[7:8]).replace("Riley", "Zed").replace("Alex", "Zed").replace("Sam", "Zed").replace("Kai", "Zed").replace("Maya", "Zed").replace("Jordan", "Zed")
    assert scan(make(tmp_path, {"synthetic/s.txt": line}))


def test_mini_is_about_300_messages_and_no_planted():
    sk = g.skeleton(CFG, mini=True)
    n = sum(len(b.slots) for b in sk.bursts)
    assert 200 <= n <= 350 and sk.planted == [] and (sk.end - sk.start).days == 6


def test_batch_prompt_has_rules_and_counts():
    s = g.batch_specs(g.skeleton(CFG, mini=True))[0]
    p = s.prompt()
    assert f"exactly {s.n} items" in p and "No jokes" in p and "No real people" in p and len(s.speakers) == s.n


def test_max_tokens_grows_with_thinking():
    assert g.max_tokens_for(CFG, 40, 1000) > g.max_tokens_for(CFG, 40, 100) > g.max_tokens_for(CFG, 30, 100)


# ---- ApiFiller with a mocked client (no API) ----
class Client:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0
        self.messages = NS(create=self.create)

    def create(self, **kw):
        self.calls += 1
        text, stop = self.replies.pop(0)
        return NS(content=[NS(type="text", text=text)], stop_reason=stop, usage={"input_tokens": 300, "output_tokens": 800, "output_tokens_details": {"thinking_tokens": 100}})


def good(n):
    return json.dumps({"messages": [{"i": i, "text": f"message number {i}"} for i in range(1, n + 1)]})


def filler(tmp_path, client):
    guard = cost.CostGuard(run_cap=1, proj_cap=3, ledger_path=str(tmp_path / "l.json"))
    return g.ApiFiller(CFG, guard, confirm=True, thinking=100, log=lambda m: None, client=client, cache_dir=tmp_path / "cache"), guard


SPEC = g.batch_specs(g.skeleton(CFG, mini=True))[0]


def test_api_filler_ok_cached_and_ledgered(tmp_path):
    c = Client([(good(SPEC.n), "end_turn")])
    f, guard = filler(tmp_path, c)
    assert len(f(SPEC)) == SPEC.n
    assert len(f(SPEC)) == SPEC.n and c.calls == 1  # second is a cache hit, free
    assert len(cost.ledger_entries(str(tmp_path / "l.json"))) == 1


def test_api_filler_retries_once_on_wrong_count(tmp_path):
    c = Client([(good(SPEC.n - 1), "end_turn"), (good(SPEC.n), "end_turn")])
    assert len(filler(tmp_path, c)[0](SPEC)) == SPEC.n and c.calls == 2


def test_api_filler_max_tokens_twice_fails(tmp_path):
    c = Client([('{"messages":[', "max_tokens"), ('{"messages":[', "max_tokens")])
    with pytest.raises(g.BatchFailed):
        filler(tmp_path, c)[0](SPEC)
    assert c.calls == 2


def test_api_filler_rejects_links_and_digits(tmp_path):
    bad = json.dumps({"messages": [{"i": i, "text": "see https://x.y" if i == 1 else "ok"} for i in range(1, SPEC.n + 1)]})
    c = Client([(bad, "end_turn"), (bad, "end_turn")])
    with pytest.raises(g.BatchFailed):
        filler(tmp_path, c)[0](SPEC)


def test_collect_stops_on_cost_error(tmp_path):
    specs = g.batch_specs(g.skeleton(CFG, mini=True))
    guard = cost.CostGuard(run_cap=0.0, proj_cap=3, ledger_path=str(tmp_path / "l.json"))
    f = g.ApiFiller(CFG, guard, confirm=True, thinking=100, log=lambda m: None, client=Client([]), cache_dir=tmp_path / "cache")
    fills, failures = g.collect(specs, f, 4, lambda m: None)
    assert fills == {} and any("COST STOP" in x for x in failures)


# ---- style cards, banned phrases, topics ----
def test_every_member_has_style_card_and_banned_list():
    assert all({"vocab", "length", "emoji"} <= set(m["style"]) for m in CFG["members"])
    assert len({m["style"]["length"] for m in CFG["members"]}) == 6 and len(CFG["banned_phrases"]) >= 8
    s = g.batch_specs(g.skeleton(CFG, mini=True))[0]
    p = s.prompt()
    assert all(n in p for n, _ in s.speakers) and "sounds good" in p and "favours words like" in p


def test_banned_phrase_more_than_once_fails():
    ok = {"messages": [{"i": 1, "text": "Sounds good to me"}, {"i": 2, "text": "plain"}]}
    assert g.validate_messages(ok, 2, ["sounds good"]) == ["Sounds good to me", "plain"]
    bad = {"messages": [{"i": 1, "text": "Sounds good"}, {"i": 2, "text": "yes sounds good again"}]}
    with pytest.raises(g.BatchFailed):
        g.validate_messages(bad, 2, ["sounds good"])


def test_mini_uses_at_least_six_distinct_topics():
    assert len({b.topic for b in g.skeleton(CFG, mini=True).bursts}) >= 6


def test_collect_api_error_stops_without_retry(tmp_path):
    class Boom:
        calls = 0

        def __call__(self, s):
            Boom.calls += 1
            raise RuntimeError("400 invalid_request_error: example")

    fills, failures = g.collect(g.batch_specs(g.skeleton(CFG, mini=True))[:1], Boom(), 1, lambda m: None)
    assert fills == {} and Boom.calls == 1 and failures[0].startswith("API ERROR RuntimeError")


def test_repetition_check_excludes_planted_and_counts():
    import repetition_check as rc

    sep = " "
    L = lambda m, s, t: f"1/{m}/26, 9:0{m}{sep}AM - {s}: {t}"
    text = "\n".join([L(1, "Sam", "see you at the station soon"), L(2, "Sam", "see you at the station soon"), L(3, "Alex", "see you at the station soon"),
                      L(4, "Alex", "see you at the station soon"), L(5, "Alex", "planted joke text goes here"), L(6, "Sam", "<Media omitted>")]) + "\n"
    res = rc.analyse(text)
    assert res["repeated_over_3"] == 1 and res["top_3grams"][0][0] == "see you at"
    gt = {"items": [{"timestamp": "2026-01-05T09:05:00", "text": "planted joke text goes here"}]}
    import json as _j, tempfile, pathlib

    f = pathlib.Path(tempfile.mkdtemp()) / "gt.json"
    f.write_text(_j.dumps(gt))
    assert rc.analyse(text, str(f))["messages_checked"] == 4
