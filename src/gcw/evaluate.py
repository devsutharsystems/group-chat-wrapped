"""Offline evaluation of saved model responses: why evidence was dropped, grounding versus rule compliance, strict recall. No network.

Everything here re-reads a response and the payload rebuilt from the chat; it never calls the API and never imports anthropic.
`classify_evidence` mirrors verify._check_evidence and refines its `quote_not_found` into other_message / normalisation_only / not_found.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from gcw import analyze, privacy, verify
from gcw.textnorm import normalise_for_match

_QUOTES = {ord(c): "'" for c in "‘’‚‛′`´"} | {ord(c): '"' for c in "“”„‟″"} | \
          {ord(c): "-" for c in "‐‑‒–—―−"}


def strong_fold(s: str) -> str:
    """A deliberately looser comparison than normalise_for_match: NFKC (fullwidth < back to <), casefold, quote/dash/ellipsis unification, whitespace."""
    t = unicodedata.normalize("NFKC", normalise_for_match(s)).casefold().translate(_QUOTES).replace("…", "...")
    return re.sub(r"\s+", " ", t).strip()


def _num(pid: str) -> int:
    return int(pid[1:]) if re.fullmatch(r"m\d+", pid) else -1


def classify_evidence(report: dict, index: dict[str, dict]) -> list[dict]:
    """One record per evidence item of the report, in verify's order. Keys: type, item (position), message_id, quote, status, grounded.
    status: verified | item_over_cap | over_cap | bad_shape | id_missing | withheld | media | too_short | duplicate | other_message |
    normalisation_only | not_found. For other_message also `real_ids` and `distance`; for too_short also `grounded`."""
    folded_rows = {pid: strong_fold(r["text"]) for pid, r in index.items()}
    norm_rows = {pid: normalise_for_match(r["text"]) for pid, r in index.items()}
    out: list[dict] = []
    for typ in verify.TYPES:
        raw = report.get(typ) if isinstance(report, dict) else None
        if not isinstance(raw, list):
            continue
        for pos, item in enumerate(raw):
            evs = item.get("evidence") if isinstance(item, dict) else None
            evs = evs if isinstance(evs, list) else []
            seen: set[str] = set()
            for k, ev in enumerate(evs):
                rec: dict[str, Any] = {"type": typ, "item": pos, "message_id": None, "quote": None, "status": "", "grounded": False}
                out.append(rec)
                if pos >= verify.CAPS[typ]:
                    rec["status"] = "item_over_cap"
                    continue
                if k >= verify.MAX_EVIDENCE_PER_ITEM:
                    rec["status"] = "over_cap"
                    continue
                if not isinstance(ev, dict) or not isinstance(ev.get("message_id"), str) or not isinstance(ev.get("quote"), str):
                    rec["status"] = "bad_shape"
                    continue
                pid, quote = ev["message_id"], ev["quote"]
                rec.update(message_id=pid, quote=quote)
                row = index.get(pid)
                if row is None:
                    rec["status"] = "id_missing"
                    continue
                if row["withheld"]:
                    rec["status"] = "withheld"
                    continue
                if row["media"]:
                    rec["status"] = "media"
                    continue
                q = normalise_for_match(quote)
                rec["grounded"] = bool(q) and q in norm_rows[pid]
                if len(q) < verify.MIN_QUOTE_CHARS:
                    rec["status"] = "too_short"
                    continue
                if not rec["grounded"]:
                    fq = strong_fold(quote)
                    if fq and fq in folded_rows[pid]:
                        rec["status"] = "normalisation_only"
                        continue
                    real = sorted((p for p, t in norm_rows.items() if q in t and p != pid), key=lambda p: (abs(_num(p) - _num(pid)), p))
                    if not real:
                        real = sorted((p for p, t in folded_rows.items() if fq and fq in t and p != pid), key=lambda p: (abs(_num(p) - _num(pid)), p))
                    if real:
                        rec.update(status="other_message", real_ids=real[:5], distance=abs(_num(real[0]) - _num(pid)))
                    else:
                        rec["status"] = "not_found"
                    continue
                if pid in seen:
                    rec["status"] = "duplicate"
                    continue
                seen.add(pid)
                rec["status"] = "verified"
    return out


def summarise_classification(recs: list[dict]) -> dict:
    n = len(recs)
    counts = Counter(r["status"] for r in recs)
    grounded = sum(r["grounded"] for r in recs)
    short = [r for r in recs if r["status"] == "too_short"]
    return {
        "evidence_total": n,
        "status_counts": dict(counts),
        "grounding_rate": grounded / n if n else None,  # quote exists in the cited message after normalisation, ignoring the length rule
        "rule_compliant_rate": counts["verified"] / n if n else None,  # the current verified definition
        "too_short_but_grounded": sum(r["grounded"] for r in short),
        "other_message_distances": sorted(r["distance"] for r in recs if r["status"] == "other_message"),
    }


def load_run(log_path: str | Path) -> tuple[dict, dict | None]:
    """(log, parsed response or None). The response file exists only for runs made with --save-response."""
    lp = Path(log_path)
    log = json.loads(lp.read_text(encoding="utf-8"))
    rp = lp.with_suffix(".response.txt")
    return log, (json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else None)


def score_saved(df: pd.DataFrame, aliases: privacy.Aliases | None, report: dict, *, slice_start: str | None, slice_end: str | None,
                truth_items: list[dict] | None) -> dict:
    """Re-verify a saved raw report against the rebuilt payload slice and score it (lenient and strict). Offline."""
    prep = analyze.prepare(df, aliases, slice_start=slice_start, slice_end=slice_end)
    verified, stats = verify.verify_report(report, prep["index"], valid_members=set(prep["members"]))
    recs = classify_evidence(report, prep["index"])
    res = {"stats": stats, "classification": summarise_classification(recs), "records": recs}
    if truth_items is not None:
        rows = prep["rows"]
        res["score"] = verify.match_planted(verified, prep["index"], truth_items, prep["mapping"], slice_start=rows[0]["ts"], slice_end=rows[-1]["ts"])
    return res


def dev_held_out(truth_items: list[dict], dev_start: str, dev_end: str) -> dict:
    """Planted items split into dev (at least one occurrence inside the dev slice, so the prompt may have been tuned against it) and held-out
    (no occurrence there). Derived from ground_truth.json, never typed by hand. Returns {id: {type, occurrences, in_dev, status}}."""
    lo, hi = pd.Timestamp(dev_start), pd.Timestamp(dev_end) + pd.Timedelta(days=1)
    out: dict[str, dict] = {}
    for it in truth_items:
        typ = verify.TRUTH_TYPE.get(it["kind"])
        if typ is None:
            continue
        rec = out.setdefault(it["id"], {"type": typ, "occurrences": 0, "in_dev": 0})
        rec["occurrences"] += 1
        rec["in_dev"] += lo <= pd.Timestamp(it["timestamp"]) < hi
    for rec in out.values():
        rec["status"] = "dev" if rec["in_dev"] else "held-out"
    return out


# ------------------------------------------------------------------ Phase 4a: full-chat evaluation over several saved runs, and the blind rating pack
import html as _html
import random
import statistics
from datetime import date as _date

TYPES = verify.TYPES
SIZE_TYPES = ("running_jokes", "moments", "awards")


def pick_runs(runs_dir: str | Path, phase: str, config: str = "A") -> list[Path]:
    """Run logs (sorted by file name) of `phase` and `config` with a saved response, no error, and no slice (the whole chat)."""
    out = []
    for f in sorted(Path(runs_dir).glob("*.json")):
        if f.name.endswith(".report.json") or not f.with_suffix(".response.txt").exists():
            continue
        try:
            log = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        sl = log.get("slice") or {}
        if log.get("phase") == phase and log.get("config") == config and "error" not in log and sl.get("start") is None and sl.get("end") is None:
            out.append(f)
    return out


def _stat(vals: list[float]) -> dict:
    return {"mean": statistics.mean(vals), "min": min(vals), "max": max(vals), "n": len(vals)} if vals else {"mean": None, "min": None, "max": None, "n": 0}


def _lengths(texts: list[str], le: int) -> dict:
    if not texts:
        return {"n": 0, "min": None, "median": None, "max": None, f"share_le_{le}": None}
    ls = sorted(len(t) for t in texts)
    return {"n": len(ls), "min": ls[0], "median": statistics.median(ls), "max": ls[-1], f"share_le_{le}": sum(1 for x in ls if x <= le) / len(ls)}


def planted_groups(truth_items: list[dict], first_day: _date, last_day: _date) -> dict[str, dict]:
    """planted id -> {type, span (first and last occurrence dates), group, split}. group: the third of the chat (by date) holding the MIDPOINT of the
    item's own date span ('first' / 'middle' / 'last'); the long-range joke jL is reported on its own ('long-range'). split: dev or held-out."""
    spans: dict[str, list] = {}
    kinds: dict[str, str] = {}
    for it in truth_items:
        typ = verify.TRUTH_TYPE.get(it["kind"])
        if typ is None:
            continue
        spans.setdefault(it["id"], []).append(pd.Timestamp(it["timestamp"]).date())
        kinds[it["id"]] = typ
    total = (last_day - first_day).days or 1
    split = dev_held_out(truth_items, "2025-11-01", "2026-02-08")
    out = {}
    for tid, days in sorted(spans.items()):
        lo, hi = min(days), max(days)
        mid = lo + (hi - lo) / 2
        frac = (mid - first_day).days / total
        group = "long-range" if tid == "jL" else "first" if frac < 1 / 3 else "middle" if frac < 2 / 3 else "last"
        out[tid] = {"type": kinds[tid], "span": [lo.isoformat(), hi.isoformat()], "group": group, "split": split[tid]["status"]}
    return out


def evaluate_runs(df: pd.DataFrame, aliases: privacy.Aliases | None, runs: list[tuple[str, dict, dict]], truth_items: list[dict]) -> dict:
    """runs: [(name, log, raw report)]. Returns the result dict (counts, rates and planted ids only: NO titles, summaries, quotes or message text)."""
    prep = analyze.prepare(df, aliases, slice_start=None, slice_end=None)
    index = prep["index"]
    ts = [r["ts"] for r in prep["rows"]]
    groups = planted_groups(truth_items, min(ts).date(), max(ts).date())
    per_run: list[dict] = []
    lens: dict[str, dict[str, list[str]]] = {t: {"title": [], "summary": []} for t in SIZE_TYPES}
    found = {t: {"strict": 0, "lenient": 0, "by_date": 0} for t in groups}
    planted_in = set()
    for name, log, report in runs:
        verified, stats = verify.verify_report(report, index, valid_members=set(prep["members"]))
        summ = summarise_classification(classify_evidence(report, index))
        score = verify.match_planted(verified, index, truth_items, prep["mapping"], slice_start=min(ts), slice_end=max(ts))
        for typ in TYPES:
            for t in score[typ]["planted_in_slice"]:
                planted_in.add(t)
            for t in score[typ]["found_strict"]:
                found[t]["strict"] += 1
            for t in score[typ]["found"]:
                found[t]["lenient"] += 1
        for t in score["moments"]["found_by_date"]:
            found[t]["by_date"] += 1
        for typ in SIZE_TYPES:
            for it in verified[typ]:
                lens[typ]["title"].append(str(it.get("title") or it.get("award") or ""))
                lens[typ]["summary"].append(str(it.get("summary") or ""))
        u = log.get("usage") or {}
        per_run.append({
            "name": name, "prompt_version": log.get("prompt_version"), "stop_reason": log.get("stop_reason"),
            "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"), "thinking_tokens": (u.get("output_tokens_details") or {}).get("thinking_tokens"),
            "latency_s": log.get("latency_s"), "cost_usd": log.get("cost_usd"),
            "items_in": stats["items_in_by_type"], "items_kept": stats["items_kept_by_type"],
            "evidence_total": summ["evidence_total"], "evidence_verified": stats["evidence_verified"],
            "rule_compliant_rate": summ["rule_compliant_rate"], "grounding_rate": summ["grounding_rate"], "status_counts": summ["status_counts"],
            "unplanted_items": {t: score[t]["items_unplanted"] for t in TYPES},
            "planted_in_scope": {t: score[t]["planted_in_slice"] for t in ("running_jokes", "moments")},
            "found_strict": {t: score[t]["found_strict"] for t in ("running_jokes", "moments")},
            "found_lenient": {t: score[t]["found"] for t in ("running_jokes", "moments")},
            "found_by_date": score["moments"]["found_by_date"],
        })
    n = len(runs)
    planted = {t: {**groups[t], "found_strict_runs": found[t]["strict"], "found_lenient_runs": found[t]["lenient"],
                   "found_by_date_runs": found[t]["by_date"] if groups[t]["type"] == "moments" else None, "in_scope": t in planted_in} for t in groups}

    def agg(key_fn) -> dict:
        res = {}
        for label, members in key_fn.items():
            ids = [t for t in members if planted[t]["in_scope"]]
            possible = len(ids) * n
            res[label] = {"items": ids, "runs": n, "strict_found_item_runs": sum(planted[t]["found_strict_runs"] for t in ids),
                          "lenient_found_item_runs": sum(planted[t]["found_lenient_runs"] for t in ids), "possible_item_runs": possible,
                          "strict_recall": (sum(planted[t]["found_strict_runs"] for t in ids) / possible) if possible else None,
                          "lenient_recall": (sum(planted[t]["found_lenient_runs"] for t in ids) / possible) if possible else None}
        return res

    by_third = agg({g: [t for t, v in planted.items() if v["group"] == g] for g in ("first", "middle", "last", "long-range")})
    by_split = agg({s: [t for t, v in planted.items() if v["split"] == s] for s in ("dev", "held-out")})
    by_type = agg({typ: [t for t, v in planted.items() if v["type"] == typ] for typ in ("running_jokes", "moments")})
    moments = [t for t, v in planted.items() if v["type"] == "moments" and v["in_scope"]]
    by_date_total = sum(planted[t]["found_by_date_runs"] for t in moments)
    return {
        "schema": 1, "phase": runs[0][1].get("phase") if runs else None, "config": runs[0][1].get("config") if runs else None, "n_runs": n, "messages": len(prep["rows"]),
        "runs": per_run,
        "summary": {
            "rule_compliant_rate": _stat([r["rule_compliant_rate"] for r in per_run]), "grounding_rate": _stat([r["grounding_rate"] for r in per_run]),
            "items_kept": {t: _stat([r["items_kept"][t] for r in per_run]) for t in SIZE_TYPES},
            "unplanted_items": {t: _stat([r["unplanted_items"][t] for r in per_run]) for t in SIZE_TYPES},
            "output_tokens": _stat([r["output_tokens"] for r in per_run if r["output_tokens"] is not None]),
            "thinking_tokens": _stat([r["thinking_tokens"] for r in per_run if r["thinking_tokens"] is not None]),
            "latency_s": _stat([r["latency_s"] for r in per_run if r["latency_s"] is not None]),
            "cost_usd": _stat([r["cost_usd"] for r in per_run if r["cost_usd"] is not None]),
        },
        "planted": planted, "recall_by_third": by_third, "recall_by_split": by_split, "recall_by_type": by_type,
        "found_by_date_moments": {"items": moments, "found_item_runs": by_date_total, "possible_item_runs": len(moments) * n,
                                  "recall": (by_date_total / (len(moments) * n)) if moments else None},
        "lengths": {t: {"title": _lengths(lens[t]["title"], 32), "summary": _lengths(lens[t]["summary"], 110)} for t in SIZE_TYPES},
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def _fmt(x: float | None, nd: int = 1) -> str:
    return "n/a" if x is None else (f"{x:.{nd}f}" if nd else f"{x:.0f}")


def _rng(s: dict, pct: bool = False, nd: int = 1) -> str:
    f = _pct if pct else (lambda v: _fmt(v, nd))
    return f"mean {f(s['mean'])}; min {f(s['min'])}; max {f(s['max'])}"


def render_markdown(res: dict) -> str:
    """Markdown of the result dict: ranges and n only, no winner language. Numbers are written so the repo scanner's phone rule never matches
    (percent signs and semicolons, never two numbers separated by a space)."""
    n, s = res["n_runs"], res["summary"]
    L = [f"# Full-chat evaluation, config {res['config']}, phase {res['phase']} (n = {n} runs)", "",
         f"Messages in the payload: {res['messages']}. Counts, rates and planted ids only; no chat text. Ranges are over n = {n} runs; no ranking of anything.", "",
         "## Per run", "", "| run | input tokens | output tokens | thinking tokens | stop reason | latency s | cost USD | items in (jokes; moments; awards) | items kept | evidence verified of total | rule-compliant | grounding |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["runs"]:
        L.append(f"| {r['name']} | {r['input_tokens']} | {r['output_tokens']} | {r['thinking_tokens']} | {r['stop_reason']} | {_fmt(r['latency_s'])} | {_fmt(r['cost_usd'], 4)} | "
                 f"{'; '.join(str(r['items_in'][t]) for t in SIZE_TYPES)} | {'; '.join(str(r['items_kept'][t]) for t in SIZE_TYPES)} | "
                 f"{r['evidence_verified']} of {r['evidence_total']} | {_pct(r['rule_compliant_rate'])} | {_pct(r['grounding_rate'])} |")
    L += ["", "## Summary over runs", "",
          f"- rule-compliant rate: {_rng(s['rule_compliant_rate'], True)}", f"- grounding rate: {_rng(s['grounding_rate'], True)}",
          *[f"- items kept, {t}: {_rng(s['items_kept'][t], nd=1)}" for t in SIZE_TYPES], *[f"- unplanted items, {t}: {_rng(s['unplanted_items'][t], nd=1)}" for t in SIZE_TYPES],
          f"- output tokens: {_rng(s['output_tokens'], nd=0)}", f"- thinking tokens: {_rng(s['thinking_tokens'], nd=0)}", f"- latency seconds: {_rng(s['latency_s'])}", f"- cost USD: {_rng(s['cost_usd'], nd=4)}",
          "", "Drop reasons per run (evidence status counts):", ""]
    for r in res["runs"]:
        L.append(f"- {r['name']}: " + "; ".join(f"{k} {v}" for k, v in sorted(r["status_counts"].items())))
    L += ["", "## Planted items: strict recall (headline), lenient (secondary), found by date (moments)", "",
          f"Found in k of {n} runs. Strict: at least min(2, planted occurrences) of the AI item's verified evidence messages are occurrences of that planted item and at least half of them are. "
          "Lenient: at least one. Found by date: any verified evidence message on the planted date (moments only). Group: the third of the chat holding the midpoint of the item's date span.", "",
          "| planted id | type | group | split | span from | span to | strict | lenient | by date |", "|---|---|---|---|---|---|---|---|---|"]
    for t, v in res["planted"].items():
        bd = v["found_by_date_runs"]
        L.append(f"| {t} | {v['type']} | {v['group']} | {v['split']} | {v['span'][0]} | {v['span'][1]} | {v['found_strict_runs']} of {n} | {v['found_lenient_runs']} of {n} | {'-' if bd is None else f'{bd} of {n}'} |")
    for title, key in (("By third of the chat", "recall_by_third"), ("Dev versus held-out", "recall_by_split"), ("By type", "recall_by_type")):
        L += ["", f"### {title}", "", "| group | planted ids | strict found item-runs | lenient found item-runs | possible item-runs | strict recall | lenient recall |", "|---|---|---|---|---|---|---|"]
        for g, v in res[key].items():
            L.append(f"| {g} | {', '.join(v['items']) or '-'} | {v['strict_found_item_runs']} | {v['lenient_found_item_runs']} | {v['possible_item_runs']} | {_pct(v['strict_recall'])} | {_pct(v['lenient_recall'])} |")
    fb = res["found_by_date_moments"]
    L += ["", f"Found by date, moments: {fb['found_item_runs']} of {fb['possible_item_runs']} item-runs ({_pct(fb['recall'])}).", "",
          "## Length distributions of verified items, all runs pooled (characters; numbers only)", "",
          "| type | field | n | min | median | max | share at most 32 / 110 |", "|---|---|---|---|---|---|---|"]
    for typ, d in res["lengths"].items():
        for field, le in (("title", 32), ("summary", 110)):
            v = d[field]
            L.append(f"| {typ} | {field} | {v['n']} | {v['min']} | {v['median']} | {v['max']} | {_pct(v[f'share_le_{le}'])} (limit {le}) |")
    return "\n".join(L) + "\n"


def write_results(res: dict, base: str | Path) -> tuple[Path, Path]:
    b = Path(base)
    b.parent.mkdir(parents=True, exist_ok=True)
    j, m = b.with_suffix(".json"), b.with_suffix(".md")
    j.write_text(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    m.write_text(render_markdown(res), encoding="utf-8")
    return j, m


# ---- blind rating pack
TARGETS = {"running_jokes": 14, "moments": 14, "awards": 12}


def allocate(pool: dict[str, int], total: int = 40, targets: dict[str, int] = TARGETS) -> dict[str, int]:
    """How many items to draw per type: the targets, capped by each pool; the shortfall goes round-robin to types that still have items."""
    take = {t: min(targets[t], pool.get(t, 0)) for t in SIZE_TYPES}
    want = min(total, sum(pool.get(t, 0) for t in SIZE_TYPES))
    while sum(take.values()) < want:
        moved = False
        for t in SIZE_TYPES:
            if sum(take.values()) < want and take[t] < pool.get(t, 0):
                take[t] += 1
                moved = True
        if not moved:
            break
    while sum(take.values()) > want:  # a total below the targets: trim the largest share first (ties: the later type)
        biggest = max(SIZE_TYPES, key=lambda t: (take[t], SIZE_TYPES.index(t)))
        take[biggest] -= 1
    return take


def build_rating_pack(df: pd.DataFrame, aliases: privacy.Aliases | None, runs: list[tuple[str, dict, dict]], truth_items: list[dict] | None, *,
                      seed: int = 4242, total: int = 40, context: int = 2) -> dict:
    """Return {'items': [...view records...], 'key': {...}, 'csv_rows': [...]}. The sample is reproducible for a seed. Items are drawn from the VERIFIED
    items of the runs, stratified by type; ids r01.. follow a seeded shuffle so neither type nor run can be read from the order."""
    from gcw import card, display

    prep = analyze.prepare(df, aliases, slice_start=None, slice_end=None)
    index, rows = prep["index"], prep["rows"]
    pos = {r["pid"]: i for i, r in enumerate(rows)}
    names = {tok: card.clean_name((aliases.display_map() if aliases else {}).get(exp, exp)) for tok, exp in prep["mapping"].items()}
    pool: dict[str, list[tuple[str, dict]]] = {t: [] for t in SIZE_TYPES}
    for name, _log, report in runs:
        verified, _ = verify.verify_report(report, index, valid_members=set(prep["members"]))
        for typ in SIZE_TYPES:
            for it in verified[typ]:
                pool[typ].append((name, it))
    rng = random.Random(seed)
    take = allocate({t: len(v) for t, v in pool.items()}, total)
    chosen: list[tuple[str, str, dict]] = []
    for typ in SIZE_TYPES:
        for name, it in rng.sample(pool[typ], take[typ]):
            chosen.append((typ, name, it))
    rng.shuffle(chosen)

    def line(pid: str) -> dict:
        r = index[pid]
        body = "[withheld]" if r["withheld"] else display.detokenise(r["text"], names)
        return {"pid": pid, "who": names.get(r["sender"], r["sender"]), "when": r["ts"].strftime("%Y-%m-%d %H:%M"), "text": body}

    out_items, key, csv_rows = [], {}, []
    for k, (typ, name, it) in enumerate(chosen, 1):
        rid = f"r{k:02d}"
        ev_views = []
        for e in it["evidence"]:
            i = pos[e["message_id"]]
            ev_views.append({"quote": display.detokenise(e["quote"], names), "cited": line(e["message_id"]),
                             "before": [line(rows[j]["pid"]) for j in range(max(0, i - context), i)], "after": [line(rows[j]["pid"]) for j in range(i + 1, min(len(rows), i + 1 + context))]})
        head = it.get("title") or it.get("award")
        rec = {"id": rid, "type": typ, "title": display.detokenise(str(head), names), "summary": display.detokenise(str(it.get("summary", "")), names), "evidence": ev_views}
        if typ == "awards":
            rec["member"] = names.get(it.get("member", ""), it.get("member", ""))
        out_items.append(rec)
        entry = {"type": typ, "run": name, "planted_strict": [], "planted_lenient": []}
        if truth_items is not None:
            sc = verify.match_planted({typ: [it]}, index, truth_items, prep["mapping"], slice_start=rows[0]["ts"], slice_end=rows[-1]["ts"])
            if typ in sc:
                entry["planted_strict"], entry["planted_lenient"] = sc[typ]["found_strict"], sc[typ]["found"]
        key[rid] = entry
        csv_rows.append({"id": rid, "type": typ, "rating": "", "note": ""})
    return {"items": out_items, "key": {"seed": seed, "pool": {t: len(v) for t, v in pool.items()}, "drawn": take, "items": key}, "csv_rows": csv_rows}


def render_rating_view(items: list[dict], seed: int) -> str:
    """Self-contained HTML (no network, no script, CSP default-src none); every dynamic string is escaped. The key is never shown here."""
    e = _html.escape

    def ln(x: dict, cls: str) -> str:
        return f'<div class="{cls}"><span class="m">{e(x["when"])} {e(x["who"])}</span> {e(x["text"])}</div>'

    parts = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
             "<title>Blind rating view</title><style>body{font:16px/1.4 -apple-system,Helvetica,Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1d1b17}"
             "section{border:1px solid #d9cfbd;border-radius:10px;padding:12px 16px;margin:18px 0}h2{margin:0 0 4px}.t{color:#6b6254;font-size:13px}.ev{margin:10px 0;padding-left:10px;border-left:4px solid #e6dccb}"
             ".c{color:#6b6254;font-size:14px}.q{background:#fff3e6;padding:2px 4px}.m{font-weight:600}</style></head><body>"
             f"<h1>Blind rating view</h1><p>Rate each item in ratings.csv: <b>true</b> (supported by its evidence), <b>partly</b>, <b>false</b>, or <b>tic</b> (a model verbal habit, not a joke or event). "
             f"{len(items)} items, seed {int(seed)}. Order is shuffled; type and run origin are not shown.</p>"]
    for it in items:
        parts.append(f'<section id="{e(it["id"])}"><h2>{e(it["id"])}: {e(it["title"])}</h2><div class="t">{e(it["type"].replace("_", " "))}'
                     + (f' for {e(it["member"])}' if it.get("member") else "") + f'</div><p>{e(it["summary"])}</p>')
        for ev in it["evidence"]:
            parts.append('<div class="ev">' + "".join(ln(x, "c") for x in ev["before"]) + ln(ev["cited"], "cited") + f'<div>quote: <span class="q">{e(ev["quote"])}</span></div>'
                         + "".join(ln(x, "c") for x in ev["after"]) + "</div>")
        parts.append("</section>")
    return "".join(parts) + "</body></html>\n"


def write_rating_pack(pack: dict, out_dir: str | Path) -> dict[str, Path]:
    import csv

    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    paths = {"csv": d / "ratings.csv", "view": d / "rating_view.html", "key": d / "key.json"}
    with paths["csv"].open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "type", "rating", "note"])
        w.writeheader()
        w.writerows(pack["csv_rows"])
    paths["view"].write_text(render_rating_view(pack["items"], pack["key"]["seed"]), encoding="utf-8")
    paths["key"].write_text(json.dumps(pack["key"], indent=1, sort_keys=True), encoding="utf-8")
    return paths
