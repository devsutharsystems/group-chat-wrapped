"""Verify the model's claims against the exact text that was sent. Pure code: no network, never imports anthropic.

An evidence item passes only if its message id exists in the payload, the message is not withheld or media, and the quote (after
normalise_for_match on both sides, at least 12 characters) is a substring of THAT message's payload text. Items then need enough verified
evidence (docs/PRD.md section 4). Unverified evidence and items are dropped and counted, never silently.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from gcw import privacy
from gcw.textnorm import normalise_for_match

MIN_QUOTE_CHARS = 12
MAX_EVIDENCE_PER_ITEM = 12
CAPS = {"running_jokes": 10, "moments": 6, "awards": 6}
MAX_TITLE, MAX_SUMMARY, MAX_AWARD = 80, 400, 60
TYPES = ("running_jokes", "moments", "awards")


def neutralise(text: str) -> str:
    """The ONLY sanitising of chat text before it is sent: '<' becomes the fullwidth '＜' so no message can write '</chat>'.
    Verification runs against the neutralised text, so the stored index uses this too."""
    return text.replace("<", chr(0xFF1C))


def make_index(rows: list[dict]) -> dict[str, dict]:
    """payload id -> {parser_id, ts, sender (token), text (neutralised, exactly as sent), withheld, media}. Local only: holds payload text."""
    return {r["pid"]: {"parser_id": r["parser_id"], "ts": r["ts"], "sender": r["sender"], "text": neutralise(r["body"]),
                       "withheld": r["withheld"], "media": r["media"]} for r in rows}


def _s(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _check_evidence(ev: Any, index: dict, seen: set, drops: Counter) -> str | None:
    """Returns the verified message id, or None (reason counted in drops)."""
    if not isinstance(ev, dict) or not isinstance(ev.get("message_id"), str) or not isinstance(ev.get("quote"), str):
        drops["bad_shape"] += 1
        return None
    row = index.get(ev["message_id"])
    if row is None:
        drops["id_missing"] += 1
        return None
    if row["withheld"]:
        drops["withheld"] += 1
        return None
    if row["media"]:
        drops["media"] += 1
        return None
    q = normalise_for_match(ev["quote"])
    if len(q) < MIN_QUOTE_CHARS:
        drops["quote_too_short"] += 1
        return None
    if q not in normalise_for_match(row["text"]):
        drops["quote_not_found"] += 1
        return None
    if ev["message_id"] in seen:
        drops["duplicate"] += 1
        return None
    seen.add(ev["message_id"])
    return ev["message_id"]


def verify_report(report: dict, index: dict[str, dict], *, valid_members: set[str] | frozenset[str]) -> tuple[dict, dict]:
    """Return (verified_report, stats). `valid_members` = tokens that speak in this payload."""
    drops: Counter = Counter()
    out: dict[str, list] = {t: [] for t in TYPES}
    items_in = Counter()
    ev_total = ev_ok = 0
    for typ in TYPES:
        raw = report.get(typ) if isinstance(report, dict) else None
        if not isinstance(raw, list):
            continue
        for pos, item in enumerate(raw):
            items_in[typ] += 1
            ev_list = item.get("evidence") if isinstance(item, dict) else None
            ev_list = ev_list if isinstance(ev_list, list) else []
            ev_total += len(ev_list)
            if pos >= CAPS[typ]:
                drops["over_cap"] += 1
                continue
            seen: set = set()
            good: list[dict] = []
            for k, ev in enumerate(ev_list):
                if k >= MAX_EVIDENCE_PER_ITEM:
                    drops["over_cap"] += 1
                    continue
                pid = _check_evidence(ev, index, seen, drops)
                if pid is not None:
                    good.append({"message_id": pid, "quote": ev["quote"]})
            ev_ok += len(good)
            head = "award" if typ == "awards" else "title"
            ok_shape = (isinstance(item, dict) and _s(item.get(head)) and _s(item.get("summary"))
                        and len(item[head]) <= (MAX_AWARD if typ == "awards" else MAX_TITLE) and len(item["summary"]) <= MAX_SUMMARY
                        and (typ != "awards" or _s(item.get("member"))))
            if not ok_shape:
                drops["bad_shape"] += 1
                continue
            ids = [g["message_id"] for g in good]
            if typ == "running_jokes":
                if len(ids) < 3:
                    drops["too_few_evidence"] += 1
                    continue
                if len({index[i]["ts"].date() for i in ids}) < 2:
                    drops["too_few_dates"] += 1
                    continue
            elif len(ids) < 1:
                drops["too_few_evidence"] += 1
                continue
            if typ == "awards":
                if item["member"] not in valid_members:
                    drops["bad_member"] += 1
                    continue
                if not any(index[i]["sender"] == item["member"] for i in ids):
                    drops["no_member_evidence"] += 1
                    continue
            kept = {k: item[k] for k in (head, "summary") + (("member",) if typ == "awards" else ())}
            kept["evidence"] = good
            out[typ].append(kept)
    kept_by = {t: len(out[t]) for t in TYPES}
    stats = {
        "items_in": sum(items_in.values()), "items_in_by_type": {t: items_in[t] for t in TYPES},
        "items_kept": sum(kept_by.values()), "items_kept_by_type": kept_by,
        "evidence_total": ev_total, "evidence_verified": ev_ok,
        "drop_reasons": dict(drops),
    }
    return out, stats


# ------------------------------------------------------------------ scoring against ground_truth.json (3b evaluation; local only)
TRUTH_TYPE = {"joke": "running_jokes", "long_joke": "running_jokes", "moment": "moments"}


def planted_occurrences(truth_items: list[dict], index: dict, mapping: dict[str, str]) -> dict[str, dict]:
    """planted id -> {type, occurrences: [(pid, ts)]}: an occurrence is matched to a payload row by timestamp (to the minute), sender and cleaned text.
    `mapping` (token -> export name) is local only."""
    by_key: dict[tuple, list[str]] = {}
    for pid, r in index.items():
        by_key.setdefault((r["ts"].isoformat()[:16], mapping.get(r["sender"]), normalise_for_match(r["text"])), []).append(pid)
    out: dict[str, dict] = {}
    for it in truth_items:
        typ = TRUTH_TYPE.get(it["kind"])
        if typ is None:
            continue
        key = (it["timestamp"][:16], it["sender"], normalise_for_match(neutralise(privacy.clean(it["text"]))))
        pids = by_key.get(key, [])
        rec = out.setdefault(it["id"], {"type": typ, "occurrences": []})
        for pid in pids[:1]:
            rec["occurrences"].append((pid, index[pid]["ts"]))
    return out


def match_planted(verified: dict, index: dict, truth_items: list[dict], mapping: dict[str, str], *, slice_start, slice_end) -> dict:
    """Recall rule (docs/PRD.md section 4): an AI item finds a planted item if at least one of its verified evidence messages is a planted
    occurrence of that item. Recall = found / planted, per type, over planted items inside the slice (a running joke counts as in the slice
    when it has at least 3 occurrences on at least 2 dates there; a moment when its key message is there). AI items matching no planted item
    are reported as `unplanted` and are NOT counted in precision until hand-rated."""
    occ = planted_occurrences(truth_items, index, mapping)
    in_slice: dict[str, set[str]] = {}
    for tid, rec in occ.items():
        pids = {pid for pid, ts in rec["occurrences"] if slice_start <= ts <= slice_end}
        if rec["type"] == "running_jokes":
            dates = {ts.date() for pid, ts in rec["occurrences"] if slice_start <= ts <= slice_end}
            ok = len(pids) >= 3 and len(dates) >= 2
        else:
            ok = len(pids) >= 1
        if ok:
            in_slice[tid] = pids
    res: dict[str, dict] = {}
    for typ in TYPES:
        planted = sorted(t for t in in_slice if occ[t]["type"] == typ)
        found: set[str] = set()
        strict: set[str] = set()
        matched_items = unplanted = 0
        for item in verified.get(typ, []):
            ids = {e["message_id"] for e in item["evidence"]}
            hit = {t for t in planted if ids & in_slice[t]}
            found |= hit
            strict |= {t for t in planted if strict_hit(ids, in_slice[t])}
            matched_items += bool(hit)
            unplanted += not hit
        res[typ] = {"planted_in_slice": planted, "found": sorted(found), "recall": (len(found) / len(planted)) if planted else None,
                    "found_strict": sorted(strict), "recall_strict": (len(strict) / len(planted)) if planted else None,
                    "items_matching_planted": matched_items, "items_unplanted": unplanted}
    # secondary, moments only: an AI moment is "found by date" if any verified evidence message falls on the planted date.
    # (A moment has ONE planted line, so strict equals lenient for moments by construction; the date rule is the looser secondary number.)
    date_of = {it["id"]: it.get("date") or it["timestamp"][:10] for it in truth_items if it["kind"] == "moment"}
    by_date: set[str] = set()
    for item in verified.get("moments", []):
        days = {index[e["message_id"]]["ts"].date().isoformat() for e in item["evidence"]}
        by_date |= {t for t in res["moments"]["planted_in_slice"] if date_of.get(t) in days}
    pl = res["moments"]["planted_in_slice"]
    res["moments"]["found_by_date"] = sorted(by_date)
    res["moments"]["recall_by_date"] = (len(by_date) / len(pl)) if pl else None
    return res


def strict_hit(verified_ids: set[str], planted_ids: set[str]) -> bool:
    """Strict rule (headline): at least min(2, planted occurrences in the slice) of the AI item's verified evidence messages are planted occurrences
    of the same planted item, AND at least half of the item's verified evidence messages are. (A planted moment has a single planted occurrence,
    so for it the threshold is 1.)"""
    n = len(verified_ids & planted_ids)
    return bool(verified_ids) and n >= min(2, len(planted_ids)) and 2 * n >= len(verified_ids)


# ------------------------------------------------------------------ chunked mode (Phase 4b): candidates per chunk, item rules AFTER the merge
def _shape_ok(typ: str, item: Any) -> bool:
    head = "award" if typ == "awards" else "title"
    return bool(isinstance(item, dict) and _s(item.get(head)) and _s(item.get("summary"))
                and len(item[head]) <= (MAX_AWARD if typ == "awards" else MAX_TITLE) and len(item["summary"]) <= MAX_SUMMARY
                and (typ != "awards" or _s(item.get("member"))))


def verify_candidates(report: dict, index: dict[str, dict]) -> tuple[list[dict], dict]:
    """Evidence checks only (the same rules as verify_report: id exists, not withheld or media, quote 12+ characters and a substring of THAT message,
    no duplicates, at most 12 evidence per item, at most 10/6/6 items per type). An item becomes a CANDIDATE if its shape is valid and it has at least 1
    verified evidence message. The item rules (3 evidence on 2 dates for a joke, and so on) are NOT applied here: chunked mode applies them after the merge.
    Returns ([{type, pos, item}], stats)."""
    drops: Counter = Counter()
    cands: list[dict] = []
    items_in = Counter()
    ev_total = ev_ok = 0
    for typ in TYPES:
        raw = report.get(typ) if isinstance(report, dict) else None
        if not isinstance(raw, list):
            continue
        for pos, item in enumerate(raw):
            items_in[typ] += 1
            ev_list = item.get("evidence") if isinstance(item, dict) else None
            ev_list = ev_list if isinstance(ev_list, list) else []
            ev_total += len(ev_list)
            if pos >= CAPS[typ]:
                drops["over_cap"] += 1
                continue
            seen: set = set()
            good: list[dict] = []
            for k, ev in enumerate(ev_list):
                if k >= MAX_EVIDENCE_PER_ITEM:
                    drops["over_cap"] += 1
                    continue
                pid = _check_evidence(ev, index, seen, drops)
                if pid is not None:
                    good.append({"message_id": pid, "quote": ev["quote"]})
            ev_ok += len(good)
            if not _shape_ok(typ, item):
                drops["bad_shape"] += 1
                continue
            if not good:
                drops["too_few_evidence"] += 1
                continue
            head = "award" if typ == "awards" else "title"
            kept = {k: item[k] for k in (head, "summary") + (("member",) if typ == "awards" else ())}
            kept["evidence"] = good
            cands.append({"type": typ, "pos": pos, "item": kept})
    stats = {"items_in": sum(items_in.values()), "items_in_by_type": {t: items_in[t] for t in TYPES}, "candidates": len(cands),
             "evidence_total": ev_total, "evidence_verified": ev_ok, "drop_reasons": dict(drops)}
    return cands, stats


def apply_item_rules(items: dict[str, list[dict]], index: dict[str, dict], *, valid_members: set[str] | frozenset[str]) -> tuple[dict, dict]:
    """The v1 item rules on items whose evidence is already verified: running joke 3+ distinct evidence messages on 2+ distinct dates; moment 1+;
    award: the member is a valid token and at least 1 evidence message was written by that member. Order is kept. Returns (report, drop counts)."""
    drops: Counter = Counter()
    out: dict[str, list] = {t: [] for t in TYPES}
    for typ in TYPES:
        for item in items.get(typ, []):
            ids = [e["message_id"] for e in item["evidence"]]
            if typ == "running_jokes":
                if len(ids) < 3:
                    drops["too_few_evidence"] += 1
                    continue
                if len({index[i]["ts"].date() for i in ids}) < 2:
                    drops["too_few_dates"] += 1
                    continue
            elif not ids:
                drops["too_few_evidence"] += 1
                continue
            if typ == "awards":
                if item["member"] not in valid_members:
                    drops["bad_member"] += 1
                    continue
                if not any(index[i]["sender"] == item["member"] for i in ids):
                    drops["no_member_evidence"] += 1
                    continue
            out[typ].append(item)
    return out, dict(drops)


def rank_and_cap(report: dict, index: dict[str, dict]) -> tuple[dict, int]:
    """Caps (10 jokes, 6 moments, 6 awards) ranked by the number of verified evidence messages (descending), ties by date spread (days between the first
    and last evidence date, descending), then the input order. Returns (capped report, number of items cut)."""
    cut = 0
    out: dict[str, list] = {t: [] for t in TYPES}
    for typ in TYPES:
        def key(pair):
            pos, it = pair
            days = [index[e["message_id"]]["ts"].date() for e in it["evidence"]]
            spread = (max(days) - min(days)).days if days else 0
            return (-len(it["evidence"]), -spread, pos)

        ranked = [it for _, it in sorted(enumerate(report.get(typ, [])), key=key)]
        out[typ] = ranked[: CAPS[typ]]
        cut += max(0, len(ranked) - CAPS[typ])
    return out, cut
