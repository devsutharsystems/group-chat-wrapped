#!/usr/bin/env python3
"""Seeded synthetic group-chat generator (Android 12h export format).

Code builds the skeleton (days, bursts, senders, timestamps, lengths) and every planted item.
Haiku writes ONLY filler text, one burst (~30-50 messages) per call, through the cost guard.

  gen_chat.py --mini --estimate            local numbers, no API
  gen_chat.py --mini --confirm             7-day chat (API, guarded)
  gen_chat.py --estimate                   full-run estimate (uses the free count_tokens endpoint)
  gen_chat.py --confirm                    full run (API, guarded), progress in out/gen.log

Thirds: third_of(d) = min(2, (d - start).days * 3 // total_days) for the full span.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

NNBSP = " "
LAST_SEC = 86340  # latest second of the day a burst may end (23:59)
CFG_PATH = Path(__file__).resolve().parent / "config.json"
OUT_DIR = ROOT / "data" / "synthetic"
CACHE_DIR = OUT_DIR / "cache"
LOG_PATH = ROOT / "out" / "gen.log"
LEN_WORDS = {"short": "2-6 words", "medium": "7-14 words", "long": "15-30 words"}
ENCRYPTION = "Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them. *Learn more*"

SCHEMA = {
    "type": "object",
    "properties": {
        "messages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"i": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["i", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["messages"],
    "additionalProperties": False,
}


# ----------------------------------------------------------------------------- skeleton
@dataclass
class Slot:
    sender: str
    t: datetime
    len_hint: str


@dataclass
class Burst:
    id: int
    day: date
    topic: str
    kind: str  # "normal" | "moment"
    slots: list[Slot]
    chunks: list[tuple[int, int]]  # slices of slots, one API call each


@dataclass
class Planted:
    t: datetime
    sender: str
    text: str
    kind: str  # joke | long_joke | moment | injection | sensitive | pii
    meta: dict = field(default_factory=dict)


@dataclass
class Skeleton:
    start: date
    end: date
    bursts: list[Burst]
    planted: list[Planted]
    system: list[tuple[datetime, str]]
    meta: dict


def load_config(path: Path = CFG_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def third_of(d: date, start: date, end: date) -> int:
    total = (end - start).days + 1
    return min(2, (d - start).days * 3 // total)


def _circ(a: float, b: float) -> float:
    d = abs(a - b) % 24
    return min(d, 24 - d)


def _active(cfg: dict, name: str, d: date, start: date) -> bool:
    r = cfg.get("removal")
    if r and r["member"] == name:
        s = start + timedelta(days=r["start_day"])
        return not (s <= d < s + timedelta(days=r["days"]))
    return True


def _make_burst(cfg: dict, rng: random.Random, bid: int, d: date, n: int, topic: str, kind: str, start: date, big: bool = False) -> Burst:
    members = [m for m in cfg["members"] if _active(cfg, m["name"], d, start)]
    dow_we = d.weekday() >= 5

    def w(m: dict) -> float:
        return m["weight"] * (m["weekend"] if dow_we else 1.0)

    anchor = rng.choices(members, weights=[w(m) for m in members])[0]
    mins = min(1439.0, max(0.0, rng.gauss(anchor["hour_mu"] * 60, anchor["hour_sd"] * 60)))
    hour = mins / 60
    aff = [w(m) * math.exp(-(_circ(hour, m["hour_mu"]) ** 2) / 32.0) for m in members]
    k = rng.randint(4, len(members)) if big else rng.randint(2, 4)
    pool = [(m, a) for m, a in zip(members, aff) if m is not anchor]
    chosen = [anchor]
    while len(chosen) < min(k, len(members)) and pool:
        m = rng.choices([p[0] for p in pool], weights=[p[1] for p in pool])[0]
        chosen.append(m)
        pool = [p for p in pool if p[0] is not m]
    senders: list[dict] = []
    for _ in range(n):
        for _try in range(6):
            m = rng.choices(chosen, weights=[w(c) for c in chosen])[0]
            if not (len(senders) >= 2 and senders[-1] is m and senders[-2] is m):
                break
        senders.append(m)
    base_gap = cfg["mean_gap_s"] * (0.35 if big else 1.0)
    gaps = [min(600.0, rng.expovariate(1.0 / (base_gap * m["gap"]))) + 2.0 for m in senders]
    total = sum(gaps)
    start_s = mins * 60
    if start_s + total > LAST_SEC:
        start_s = max(0.0, LAST_SEC - total)
    t = datetime.combine(d, datetime.min.time()) + timedelta(seconds=start_s)
    slots: list[Slot] = []
    for m, g in zip(senders, gaps):
        t = t + timedelta(seconds=g)
        hint = rng.choices(["short", "medium", "long"], weights=m["len"])[0]
        slots.append(Slot(m["name"], t.replace(microsecond=0), hint))
    parts = max(1, -(-n // 50))
    size = -(-n // parts)
    chunks = [(i, min(n, i + size)) for i in range(0, n, size)]
    return Burst(bid, d, topic, kind, slots, chunks)


def skeleton(cfg: dict, seed: int | None = None, *, mini: bool = False) -> Skeleton:
    seed = cfg["seed"] if seed is None else seed
    start = date.fromisoformat(cfg["start"])
    end = date.fromisoformat(cfg["end"])
    if mini:
        end = start + timedelta(days=cfg["mini"]["days"] - 1)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    r_days = random.Random(f"{seed}:days")
    r_topic = random.Random(f"{seed}:topic")
    r_plant = random.Random(f"{seed}:plant")
    deck: list[str] = []

    def next_topic() -> str:  # shuffled deck: no repeats until all topics are used
        if not deck:
            deck.extend(r_topic.sample(cfg["topics"], len(cfg["topics"])))
        return deck.pop()

    silence: set[date] = set()
    if not mini:
        s0 = r_days.randint(len(days) // 3 + 10, 2 * len(days) // 3 - 20)
        silence = {days[s0 + i] for i in range(cfg["silence_days"])}

    moment_days: dict[str, date] = {}
    if not mini:
        for m in cfg["moments"]:
            cand = [d for d in days if third_of(d, start, end) == m["third"] and d not in silence and d.weekday() == 5]
            moment_days[m["id"]] = r_days.choice(cand)

    bursts: list[Burst] = []
    bid = 0
    taken = set(moment_days.values())
    for d in days:
        if d in silence or d in taken:
            continue
        p = cfg["mini"]["burst_prob"] if mini else (cfg["burst_prob_weekend"] if d.weekday() >= 5 else cfg["burst_prob_weekday"])
        if r_days.random() < p:
            n = r_days.randint(*cfg["burst_size"])
            bursts.append(_make_burst(cfg, random.Random(f"{seed}:b:{d.isoformat()}"), bid, d, n, next_topic(), "normal", start))
            bid += 1
    planted: list[Planted] = []
    if not mini:
        for m in cfg["moments"]:
            d = moment_days[m["id"]]
            b = _make_burst(cfg, random.Random(f"{seed}:m:{m['id']}"), bid, d, m["size"], m["topic"], "moment", start, big=True)
            bursts.append(b)
            bid += 1
            planted.append(Planted(b.slots[0].t - timedelta(seconds=1), m["sender"], m["headline"], "moment", {"id": m["id"], "third": m["third"], "date": d.isoformat(), "burst_messages": m["size"]}))
        bursts.sort(key=lambda b: b.day)
        planted += _plant(cfg, r_plant, bursts, start, end)

    system = [(datetime.combine(start, datetime.min.time()) + timedelta(minutes=1), ENCRYPTION), (datetime.combine(start, datetime.min.time()) + timedelta(minutes=2), "You created this group")]
    for i, m in enumerate(x for x in cfg["members"] if x["name"] != cfg["owner"]):
        system.append((datetime.combine(start, datetime.min.time()) + timedelta(minutes=3 + i), f"{m['name']} was added"))
    r = cfg.get("removal")
    if r and not mini:
        s = datetime.combine(start + timedelta(days=r["start_day"]), datetime.min.time()) + timedelta(hours=8)
        system.append((s, f"You removed {r['member']}"))
        system.append((s + timedelta(days=r["days"], hours=1), f"{r['member']} was added"))
    system.sort(key=lambda x: x[0])
    meta = {"seed": seed, "mini": mini, "silence": sorted(d.isoformat() for d in silence), "moment_days": {k: v.isoformat() for k, v in moment_days.items()}}
    return Skeleton(start, end, bursts, planted, system, meta)


def _time_in(rng: random.Random, b: Burst) -> datetime:
    t0, t1 = b.slots[0].t, b.slots[-1].t
    return t0 + timedelta(seconds=rng.randint(0, max(0, int((t1 - t0).total_seconds()))))


def _plant(cfg: dict, rng: random.Random, bursts: list[Burst], start: date, end: date) -> list[Planted]:
    normal = [b for b in bursts if b.kind == "normal"]
    by_third: dict[int, list[Burst]] = {0: [], 1: [], 2: []}
    for b in normal:
        by_third[third_of(b.day, start, end)].append(b)
    out: list[Planted] = []

    def pick_sender(senders: list[str], d: date) -> str:
        ok = [s for s in senders if _active(cfg, s, d, start)]
        return rng.choice(ok)

    def put(b: Burst, senders: list[str], variants: list[str], kind: str, meta: dict) -> None:
        out.append(Planted(_time_in(rng, b), pick_sender(senders, b.day), rng.choice(variants), kind, meta))

    for j in cfg["jokes"]:
        chosen = rng.sample(by_third[j["third"]], 4)
        for b, cnt in zip(chosen, [2, 2, 2, 1]):
            for _ in range(cnt):
                put(b, j["senders"], j["variants"], "joke", {"id": j["id"], "third": j["third"]})
    lj = cfg["long_joke"]
    for t in range(3):
        for b, cnt in zip(rng.sample(by_third[t], 3), [2, 1, 1]):
            for _ in range(cnt):
                put(b, lj["senders"], lj["variants"], "long_joke", {"id": lj["id"], "third": t})
    inj = cfg["injection"]
    put(rng.choice(by_third[inj["third"]]), [inj["sender"]], [inj["text"]], "injection", {"id": inj["id"], "third": inj["third"]})
    for s in cfg["sensitive"]:
        put(rng.choice(by_third[s["third"]]), [s["sender"]], [s["text"]], "sensitive", {"id": s["id"], "topic": s["topic"], "third": s["third"]})
    for p in cfg["pii"]:
        put(rng.choice(by_third[p["third"]]), [p["sender"]], [p["text"]], "pii", {"id": p["id"], "type": p["type"], "third": p["third"]})
    return out


# ----------------------------------------------------------------------------- prompts / filler
@dataclass
class BatchSpec:
    burst_id: int
    part: int
    parts: int
    topic: str
    n: int
    speakers: list[tuple[str, str]]
    cards: dict[str, str] = field(default_factory=dict)
    banned: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"gen:b{self.burst_id}p{self.part}"

    def prompt(self) -> str:
        lines = "\n".join(f"{i}. {s} ({h}: {LEN_WORDS[h]})" for i, (s, h) in enumerate(self.speakers, 1))
        cards = "\n".join(f"- {n}: {c}" for n, c in self.cards.items())
        ban = "; ".join(f'"{b}"' for b in self.banned)
        cont = f"This is part {self.part + 1} of {self.parts} of one longer conversation on the same topic; continue naturally.\n" if self.parts > 1 else ""
        return (
            f"You are writing filler for a synthetic group-chat dataset. Write {self.n} chat messages that are part of one ordinary "
            f"conversation between friends about: {self.topic}.\n{cont}"
            "Rules: mundane everyday chatter only. No jokes, no catchphrases or recurring bits. No sensitive topics (health, money, religion, politics). "
            "No real people, places or brands. No phone numbers, email addresses or links. At most an occasional single emoji. "
            "Do not mention anyone by name except the speakers.\n"
            f"Each speaker has a distinct voice:\n{cards}\n"
            f"Avoid these stock phrases (use each at most once in the whole batch, ideally never): {ban}. "
            "Do not open several messages with the same words and do not repeat a sentence.\n"
            f"Speakers, in order, with the length each message should have:\n{lines}\n"
            f'Return JSON {{"messages":[{{"i":1,"text":"..."}}, ...]}} with exactly {self.n} items, i from 1 to {self.n}. '
            "Each text is only what that speaker types: no speaker name, no timestamp, a single line."
        )


def style_card(m: dict) -> str:
    st = m["style"]
    return f"favours words like {', '.join(st['vocab'])}; typical length {st['length']}; emoji: {st['emoji']}"


def batch_specs(sk: Skeleton, cfg: dict | None = None) -> list[BatchSpec]:
    cfg = cfg or load_config()
    card = {m["name"]: style_card(m) for m in cfg["members"]}
    banned = cfg.get("banned_phrases", [])
    specs = []
    for b in sk.bursts:
        for p, (a, z) in enumerate(b.chunks):
            sp = [(s.sender, s.len_hint) for s in b.slots[a:z]]
            specs.append(BatchSpec(b.id, p, len(b.chunks), b.topic, z - a, sp, {n: card[n] for n in dict.fromkeys(x for x, _ in sp)}, banned))
    return specs


class BatchFailed(RuntimeError):
    pass


_BAD = re.compile(r"@|https?:|www\.|\d{7,}")


def validate_messages(parsed: Any, n: int, banned: list[str] | None = None) -> list[str]:
    msgs = (parsed or {}).get("messages") if isinstance(parsed, dict) else None
    if not isinstance(msgs, list) or len(msgs) != n:
        raise BatchFailed(f"wrong message count: got {len(msgs) if isinstance(msgs, list) else 'none'}, want {n}")
    texts = []
    for want, m in enumerate(msgs, 1):
        if m.get("i") != want:
            raise BatchFailed("message numbering out of order")
        t = " ".join(str(m.get("text", "")).split())
        if not t or _BAD.search(t) or t.startswith("<"):
            raise BatchFailed("empty or disallowed text in a message")
        texts.append(t)
    blob = "\n".join(texts).lower()
    for b in banned or []:
        if blob.count(b.lower()) > 1:
            raise BatchFailed(f'banned phrase used more than once: "{b}"')
    return texts


def max_tokens_for(cfg: dict, n: int, thinking: int | None = None) -> int:
    c = cfg["max_tokens"]
    th = c["thinking_default"] if thinking is None else thinking
    return int(n * c["per_message"] * c["json_headroom"] + c["thinking_multiplier"] * th + c["base"])


class FakeFiller:
    """Deterministic offline filler for tests and dry runs. Makes no API call."""

    WORDS = "the a and then maybe tomorrow later soon fine okay sure bus rain soup phone key table walk shop ready late early".split()

    def __call__(self, spec: BatchSpec) -> list[str]:
        r = random.Random(f"fake:{spec.burst_id}:{spec.part}")
        return [" ".join(r.choice(self.WORDS) for _ in range({"short": 4, "medium": 9, "long": 18}[h])) for _, h in spec.speakers]


class ApiFiller:
    def __init__(self, cfg: dict, guard: Any, *, confirm: bool, thinking: int | None, log: Callable[[str], None], client: Any = None, cache_dir: Path = CACHE_DIR):
        self.cfg, self.guard, self.confirm, self.thinking, self.log, self.client, self.cache_dir = cfg, guard, confirm, thinking, log, client, cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def key(self, spec: BatchSpec) -> str:
        from gcw import llm

        p = llm.request_params(spec.prompt(), SCHEMA, max_tokens_for(self.cfg, spec.n, self.thinking), "low", None, self.cfg.get("thinking"))
        return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:32]

    def __call__(self, spec: BatchSpec) -> list[str]:
        from gcw import llm

        f = self.cache_dir / f"{self.key(spec)}.json"
        if f.exists():
            self.log(f"cache hit {spec.label}")
            return json.loads(f.read_text())["texts"]
        mt = max_tokens_for(self.cfg, spec.n, self.thinking)
        last = ""
        for attempt in (1, 2):
            res = llm.call_json(spec.prompt(), SCHEMA, max_tokens=mt, confirm=self.confirm, guard=self.guard, label=spec.label, thinking=self.cfg.get("thinking"), client=self.client)
            th = (res.usage.get("output_tokens_details") or {}).get("thinking_tokens")
            try:
                if not res.ok:
                    raise BatchFailed(res.note)
                texts = validate_messages(res.parsed, spec.n, spec.banned)
            except BatchFailed as e:
                last = str(e)
                self.log(f"FAILED {spec.label} attempt {attempt}: {last} (stop={res.stop_reason}, out={res.usage.get('output_tokens')}, think={th})")
                continue
            f.write_text(json.dumps({"texts": texts, "usage": res.usage, "stop_reason": res.stop_reason}))
            self.log(f"ok {spec.label} n={spec.n} in={res.usage.get('input_tokens')} out={res.usage.get('output_tokens')} think={th} {res.latency_s:.1f}s ${res.cost_usd:.5f}")
            return texts
        raise BatchFailed(f"{spec.label} failed twice: {last}")


# ----------------------------------------------------------------------------- render
@dataclass
class Msg:
    t: datetime
    sender: str
    text: str
    flag: str = ""  # media | deleted | edited | multiline | planted


def fmt_ts(t: datetime) -> str:
    h = t.hour % 12 or 12
    return f"{t.month}/{t.day}/{t.year % 100}, {h}:{t.minute:02d}{NNBSP}{'AM' if t.hour < 12 else 'PM'}"


def build_messages(cfg: dict, sk: Skeleton, fills: dict[tuple[int, int], list[str]], seed: int | None = None) -> list[Msg]:
    seed = sk.meta["seed"] if seed is None else seed
    rs = random.Random(f"{seed}:style")
    st = cfg["style"]
    msgs: list[Msg] = []
    for b in sk.bursts:
        texts: list[str] = []
        for p in range(len(b.chunks)):
            texts += fills[(b.id, p)]
        for slot, text in zip(b.slots, texts):
            x, flag = rs.random(), ""
            if x < st["media"]:
                text, flag = "<Media omitted>", "media"
            elif x < st["media"] + st["deleted"] and slot.sender == cfg["owner"]:
                text, flag = "You deleted this message", "deleted"
            elif x < st["media"] + st["deleted"] + st["edited"]:
                text, flag = text + " <This message was edited>", "edited"
            elif x < st["media"] + st["deleted"] + st["edited"] + st["multiline"] and (". " in text or len(text) > 40):
                if ". " in text:
                    text = text.replace(". ", ".\n", 1)
                else:
                    cut = text.find(" ", len(text) // 2)
                    text = text if cut < 0 else text[:cut] + "\n" + text[cut + 1 :]
                flag = "multiline"
            msgs.append(Msg(slot.t, slot.sender, text, flag))
    for p in sk.planted:
        msgs.append(Msg(p.t.replace(microsecond=0), p.sender, p.text, "planted"))
    msgs.sort(key=lambda m: m.t)  # stable
    return msgs


def render(sk: Skeleton, msgs: list[Msg]) -> str:
    events: list[tuple[datetime, int, str]] = [(t, 0, f"{fmt_ts(t)} - {text}") for t, text in sk.system]
    events += [(m.t, 1, f"{fmt_ts(m.t)} - {m.sender}: {m.text}") for m in msgs]
    events.sort(key=lambda e: (e[0], e[1]))
    return "\n".join(e[2] for e in events) + "\n"


def ground_truth(sk: Skeleton) -> dict:
    items = [{"kind": p.kind, "timestamp": p.t.replace(second=0, microsecond=0).isoformat(), "sender": p.sender, "text": p.text, **p.meta} for p in sorted(sk.planted, key=lambda p: p.t)]
    return {"span": [sk.start.isoformat(), sk.end.isoformat()], "meta": sk.meta, "items": items}


def manifest(sk: Skeleton, msgs: list[Msg], text: str) -> dict:
    return {
        "n_messages": len(msgs),
        "n_system": len(sk.system),
        "per_sender": dict(Counter(m.sender for m in msgs)),
        "flags": dict(Counter(m.flag for m in msgs if m.flag)),
        "n_bursts": len(sk.bursts),
        "n_batches": sum(len(b.chunks) for b in sk.bursts),
        "span": [sk.start.isoformat(), sk.end.isoformat()],
        "bytes": len(text.encode("utf-8")),
        "lines": text.count("\n"),
    }


# ----------------------------------------------------------------------------- driver
def make_logger(path: Path = LOG_PATH) -> Callable[[str], None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    def log(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        with lock:
            print(line, flush=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    return log


def collect(specs: list[BatchSpec], filler: Callable[[BatchSpec], list[str]], workers: int, log: Callable[[str], None]) -> tuple[dict[tuple[int, int], list[str]], list[str]]:
    from gcw.cost import CostError

    fills: dict[tuple[int, int], list[str]] = {}
    failures: list[str] = []
    stop = threading.Event()

    def work(s: BatchSpec) -> tuple[BatchSpec, list[str] | None]:
        if stop.is_set():
            return s, None
        return s, filler(s)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, s) for s in specs]
        done = 0
        for f in as_completed(futs):
            try:
                s, texts = f.result()
                if texts is not None:
                    fills[(s.burst_id, s.part)] = texts
            except CostError as e:
                stop.set()
                failures.append(f"COST STOP: {e}")
            except BatchFailed as e:
                failures.append(str(e))
            except Exception as e:  # API/transport error: stop everything, never retry here
                stop.set()
                failures.append(f"API ERROR {type(e).__name__}: {e}")
            done += 1
            if done % 10 == 0 or done == len(specs):
                log(f"progress {done}/{len(specs)} batches, {len(failures)} failure(s)")
    return fills, failures


def estimate(cfg: dict, mini: bool, *, client: Any = None) -> dict:
    """Exact input via count_tokens WITH output_config (needs a client); output scaled from cached real batches."""
    from gcw import cost, llm

    sk = skeleton(cfg, mini=mini)
    specs = batch_specs(sk, cfg)
    if client:
        with ThreadPoolExecutor(max_workers=8) as ex:
            ins = list(ex.map(lambda s: llm.count_tokens(s.prompt(), client=client, schema=SCHEMA), specs))
    else:
        ins = [llm.rough_prompt_tokens(s.prompt()) for s in specs]
    n_msgs = sum(s.n for s in specs) + len(sk.planted)
    out = {"n_batches": len(specs), "n_bursts": len(sk.bursts), "approx_messages": n_msgs, "input_tokens_total": sum(ins), "input_exact": bool(client), "max_input_per_call": max(ins),
           "worst_case_usd": round(sum(cost.estimate_usd(i, max_tokens_for(cfg, s.n, 0)) for i, s in zip(ins, specs)), 4)}
    cached = [json.loads(f.read_text()) for f in CACHE_DIR.glob("*.json")] if CACHE_DIR.exists() else []
    cached = [c for c in cached if (c["usage"].get("output_tokens_details") or {}).get("thinking_tokens", 0) == 0]
    if cached:
        n_tot = sum(len(c["texts"]) for c in cached)
        opm = sum(c["usage"]["output_tokens"] for c in cached) / n_tot
        exp = (sum(ins) * 0.10 + sum(s.n for s in specs) * opm * 0.50) / 1e6
        out["output_tokens_per_message"] = round(opm, 1)
        out["expected_usd"] = round(exp, 4)
        out["expected_usd_with_1.3_margin"] = round(exp * 1.3, 4)
    mini_chat = OUT_DIR / "chat_mini.txt"
    if client and mini_chat.exists() and not mini:
        t = mini_chat.read_text(encoding="utf-8")
        n_lines = sum(1 for l in t.splitlines() if "\u202f" in l)
        tpl = llm.count_tokens(t, client=client) / n_lines
        out["final_text_tokens_per_line"] = round(tpl, 1)
        out["final_text_tokens_est"] = round(tpl * (n_msgs + 9))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mini", action="store_true")
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--fake", action="store_true", help="offline FakeFiller, no API")
    ap.add_argument("--sample", type=int, default=0, help="write first N lines to synthetic/sample_<N>.txt")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--cap", type=float, default=None, help="per-run USD cap (default GCW_COST_CAP_USD)")
    a = ap.parse_args()
    cfg = load_config()
    log = make_logger()
    from gcw import cost, llm

    if a.estimate:
        client = None
        if not a.fake:
            try:
                client = llm.get_client()
            except RuntimeError as e:
                print(f"no client ({e}); using local token estimate")
        print(json.dumps(estimate(cfg, a.mini, client=client), indent=1))
        print(f"ledger so far ${cost.ledger_total():.5f}")
        return 0

    sk = skeleton(cfg, a.seed, mini=a.mini)
    specs = batch_specs(sk)
    if a.fake:
        filler: Callable[[BatchSpec], list[str]] = FakeFiller()
        guard = None
    else:
        if not a.confirm:
            print("refusing: API run needs --confirm (after the user's OK in chat). Use --fake for an offline run.")
            return 2
        spike = ROOT / "out" / "spike.json"
        thinking = None
        if spike.exists():
            thinking = ((json.loads(spike.read_text()).get("usage") or {}).get("output_tokens_details") or {}).get("thinking_tokens")
        cap = a.cap if a.cap is not None else cost.per_run_cap()
        cap = min(cap, max(0.0, 0.60 - cost.ledger_total()))
        guard = cost.CostGuard(run_cap=cap)
        filler = ApiFiller(cfg, guard, confirm=True, thinking=thinking, log=log, client=llm.get_client())
        log(f"start {'mini' if a.mini else 'full'}: {len(specs)} batches, run cap ${cap:.3f}, thinking_tokens basis {thinking}")
    fills, failures = collect(specs, filler, 4, log)
    if failures:
        log(f"INCOMPLETE: {len(failures)} failure(s); rerun to retry only failed batches (cache keeps the rest)")
        for f in failures[:10]:
            log("  " + f)
        return 1
    msgs = build_messages(cfg, sk, fills)
    text = render(sk, msgs)
    tag = "mini" if a.mini else "full"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"chat_{tag}.txt").write_text(text, encoding="utf-8", newline="\n")
    (OUT_DIR / f"manifest_{tag}.json").write_text(json.dumps(manifest(sk, msgs, text), indent=1))
    if not a.mini:
        (OUT_DIR / "ground_truth.json").write_text(json.dumps(ground_truth(sk), indent=1))
    if a.sample:
        (Path(__file__).resolve().parent / f"sample_{a.sample}.txt").write_text("".join(text.splitlines(True)[: a.sample]), encoding="utf-8", newline="\n")
    log(f"done: {len(msgs)} messages, {len(sk.system)} system lines, {len(text.encode())} bytes, ledger total ${cost.ledger_total():.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
