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


def chunked_classification(all_rows: list[dict], log: dict, raw: dict) -> dict:
    """Evidence statistics of a chunked run: every raw map response classified against its OWN chunk (rows of the logged day range), then summed."""
    recs: list[dict] = []
    for k, ch in enumerate(log["chunks"]):
        sel = [r for r in all_rows if ch["start"] <= r["ts"].date().isoformat() <= ch["end"]]
        try:
            rep = json.loads(raw["map"][k])
        except (ValueError, IndexError, TypeError):
            continue
        recs += classify_evidence(rep, verify.make_index(sel))
    return summarise_classification(recs)


def pick_runs(runs_dir: str | Path, phase: str, config: str = "A", mode: str = "single") -> list[Path]:
    """Run logs (sorted by file name) of `phase` and `config` with a saved response, no error, and no slice (the whole chat). `mode`: single or chunked."""
    out = []
    for f in sorted(Path(runs_dir).glob("*.json")):
        if f.name.endswith(".report.json") or not f.with_suffix(".response.txt").exists():
            continue
        try:
            log = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        sl = log.get("slice") or {}
        if (log.get("phase") == phase and log.get("config") == config and "error" not in log and sl.get("start") is None and sl.get("end") is None
                and log.get("mode", "single") == mode):
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


def evaluate_runs(df: pd.DataFrame, aliases: privacy.Aliases | None, runs: list[tuple], truth_items: list[dict], mode: str = "single") -> dict:
    """runs: [(name, log, raw report)] for single-pass, or [(name, log, final verified report, raw map responses)] for mode='chunked' (the evidence statistics
    then come from the map calls, each classified against its own chunk). Returns the result dict (counts, rates and planted ids only: NO titles, summaries,
    quotes or message text)."""
    prep = analyze.prepare(df, aliases, slice_start=None, slice_end=None)
    index = prep["index"]
    ts = [r["ts"] for r in prep["rows"]]
    groups = planted_groups(truth_items, min(ts).date(), max(ts).date())
    per_run: list[dict] = []
    lens: dict[str, dict[str, list[str]]] = {t: {"title": [], "summary": []} for t in SIZE_TYPES}
    found = {t: {"strict": 0, "lenient": 0, "by_date": 0} for t in groups}
    planted_in = set()
    for run in runs:
        name, log, report = run[0], run[1], run[2]
        if mode == "chunked":
            verified = report
            summ = chunked_classification(prep["rows"], log, run[3])
            stats = {"items_in_by_type": log["stats"]["items_in_by_type"], "items_kept_by_type": {t: len(verified[t]) for t in verify.TYPES},
                     "evidence_verified": summ["status_counts"].get("verified", 0)}
        else:
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
        tot = log.get("totals") or {}
        per_run.append({
            "name": name, "prompt_version": log.get("prompt_version"), "stop_reason": log.get("stop_reason"),
            "input_tokens": u.get("input_tokens", tot.get("input_tokens")), "output_tokens": u.get("output_tokens", tot.get("output_tokens")),
            "thinking_tokens": (u.get("output_tokens_details") or {}).get("thinking_tokens", tot.get("thinking_tokens")),
            "latency_s": log.get("latency_s", tot.get("latency_sum_s")), "cost_usd": log.get("cost_usd", tot.get("cost_usd")),
            **({"calls": tot.get("calls"), "wall_clock_s": tot.get("wall_clock_s"), "latency_sum_s": tot.get("latency_sum_s"), "candidates_before_merge": log["candidates_before_merge"]["total"],
                "items_after_merge": sum(log["after_merge"].values()), "items_after_rules": sum(log["after_rules"].values()), "chunks": len(log["chunks"])} if mode == "chunked" else {}),
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
        "schema": 1, "mode": mode, "phase": runs[0][1].get("phase") if runs else None, "config": runs[0][1].get("config") if runs else None, "n_runs": n, "messages": len(prep["rows"]),
        "runs": per_run,
        "summary": {
            "rule_compliant_rate": _stat([r["rule_compliant_rate"] for r in per_run]), "grounding_rate": _stat([r["grounding_rate"] for r in per_run]),
            "items_kept": {t: _stat([r["items_kept"][t] for r in per_run]) for t in SIZE_TYPES},
            "unplanted_items": {t: _stat([r["unplanted_items"][t] for r in per_run]) for t in SIZE_TYPES},
            "output_tokens": _stat([r["output_tokens"] for r in per_run if r["output_tokens"] is not None]),
            "thinking_tokens": _stat([r["thinking_tokens"] for r in per_run if r["thinking_tokens"] is not None]),
            "latency_s": _stat([r["latency_s"] for r in per_run if r["latency_s"] is not None]),
            "cost_usd": _stat([r["cost_usd"] for r in per_run if r["cost_usd"] is not None]),
            **({"wall_clock_s": _stat([r["wall_clock_s"] for r in per_run]), "candidates_before_merge": _stat([r["candidates_before_merge"] for r in per_run]),
                "items_after_merge": _stat([r["items_after_merge"] for r in per_run]), "items_after_rules": _stat([r["items_after_rules"] for r in per_run])} if mode == "chunked" else {}),
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
    L = [f"# Full-chat evaluation, {res.get('mode', 'single')} mode, config {res['config']}, phase {res['phase']} (n = {n} runs)", "",
         f"Messages in the payload: {res['messages']}. Counts, rates and planted ids only; no chat text. Ranges are over n = {n} runs; no ranking of anything.", "",
         "## Per run", "", "| run | input tokens | output tokens | thinking tokens | stop reason | latency s | cost USD | items in (jokes; moments; awards) | items kept | evidence verified of total | rule-compliant | grounding |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["runs"]:
        L.append(f"| {r['name']} | {r['input_tokens']} | {r['output_tokens']} | {r['thinking_tokens']} | {r['stop_reason']} | {_fmt(r['latency_s'])} | {_fmt(r['cost_usd'], 4)} | "
                 f"{'; '.join(str(r['items_in'][t]) for t in SIZE_TYPES)} | {'; '.join(str(r['items_kept'][t]) for t in SIZE_TYPES)} | "
                 f"{r['evidence_verified']} of {r['evidence_total']} | {_pct(r['rule_compliant_rate'])} | {_pct(r['grounding_rate'])} |")
    if res.get("mode") == "chunked":
        L += ["", "Chunked runs (calls, wall-clock seconds, sum of call latencies, candidates before merging, items after the merge and after the item rules):", "",
              "| run | chunks | calls | wall-clock s | sum of call latencies s | candidates | after merge | after rules |", "|---|---|---|---|---|---|---|---|"]
        for r in res["runs"]:
            L.append(f"| {r['name']} | {r['chunks']} | {r['calls']} | {_fmt(r['wall_clock_s'])} | {_fmt(r['latency_sum_s'])} | {r['candidates_before_merge']} | {r['items_after_merge']} | {r['items_after_rules']} |")
    L += ["", "## Summary over runs", "",
          f"- rule-compliant rate: {_rng(s['rule_compliant_rate'], True)}", f"- grounding rate: {_rng(s['grounding_rate'], True)}",
          *[f"- items kept, {t}: {_rng(s['items_kept'][t], nd=1)}" for t in SIZE_TYPES], *[f"- unplanted items, {t}: {_rng(s['unplanted_items'][t], nd=1)}" for t in SIZE_TYPES],
          f"- output tokens: {_rng(s['output_tokens'], nd=0)}", f"- thinking tokens: {_rng(s['thinking_tokens'], nd=0)}", f"- latency seconds: {_rng(s['latency_s'])}", f"- cost USD: {_rng(s['cost_usd'], nd=4)}",
          *([f"- wall-clock seconds: {_rng(s['wall_clock_s'])}", f"- candidates before merging: {_rng(s['candidates_before_merge'])}", f"- items after the merge: {_rng(s['items_after_merge'])}", f"- items after the item rules: {_rng(s['items_after_rules'])}"] if res.get("mode") == "chunked" else []),
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


def rounded(obj, nd: int = 4):
    """Floats rounded to `nd` decimals (recursively), so results files hold short numbers (also keeps the repo scanner's phone rule quiet)."""
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, dict):
        return {k: rounded(v, nd) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rounded(v, nd) for v in obj]
    return obj


def write_results(res: dict, base: str | Path) -> tuple[Path, Path]:
    b = Path(base)
    b.parent.mkdir(parents=True, exist_ok=True)
    j, m = b.with_suffix(".json"), b.with_suffix(".md")
    j.write_text(json.dumps(rounded(res), indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
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
    """The working rating tool (see gcw.rating_ui): self-contained, no network, CSP, every dynamic string escaped. The key is never in it."""
    from gcw import rating_ui

    return rating_ui.render(items, seed)


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


# ------------------------------------------------------------------ Phase 4a-fix: precision from hand ratings, and the miss diagnostic
import math

RATING_VALUES = ("true", "partly", "false", "tic")
NOT_INDEPENDENT = ("The three runs are not independent samples: they read the same chat with the same prompt, so the same items and the same mistakes recur "
                   "across runs and the intervals below understate the real uncertainty.")


class RatingError(ValueError):
    """A ratings file that cannot be scored (blank, invalid, or not matching the key)."""


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials (95% for z = 1.96). None when n = 0."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _prop(k: int, n: int) -> dict:
    iv = wilson(k, n)
    return {"k": k, "n": n, "p": (k / n) if n else None, "lo": iv[0] if iv else None, "hi": iv[1] if iv else None}


def _tally(items: list[str]) -> dict:
    c = {r: items.count(r) for r in RATING_VALUES}
    n = len(items)
    return {"n": n, **c, "strict": _prop(c["true"], n), "lenient": _prop(c["true"] + c["partly"], n)}


def score_ratings(rows: list[dict], key: dict) -> dict:
    """Counts only (no text). rows: dicts with id, type, rating, note. Refuses blank or invalid ratings and any mismatch with the key.
    strict = true only; lenient = true plus partly (tic and false never count)."""
    kitems = key["items"]
    blanks = [r["id"] for r in rows if not (r.get("rating") or "").strip()]
    if blanks:
        raise RatingError(f"{len(blanks)} blank rating(s), first ids: {', '.join(blanks[:5])}; rate every item before scoring")
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids) or set(ids) != set(kitems):
        raise RatingError("the ratings file and the key do not hold the same set of ids")
    rating_of = {}
    for r in rows:
        rating = r["rating"].strip().lower()
        meta = kitems[r["id"]]
        if rating not in RATING_VALUES:
            raise RatingError(f"{r['id']}: rating {r['rating']!r} is not one of {', '.join(RATING_VALUES)}")
        if rating == "tic" and meta["type"] != "running_jokes":
            raise RatingError(f"{r['id']}: tic is only for jokes")
        if r.get("type") and r["type"] != meta["type"]:
            raise RatingError(f"{r['id']}: type {r['type']!r} differs from the key")
        rating_of[r["id"]] = rating
    all_ids = list(kitems)
    by_type = {t: _tally([rating_of[i] for i in all_ids if kitems[i]["type"] == t]) for t in SIZE_TYPES}
    runs = sorted({kitems[i]["run"] for i in all_ids})
    matching = [i for i in all_ids if kitems[i]["planted_lenient"]]
    unplanted = [i for i in all_ids if not kitems[i]["planted_lenient"]]
    covered_len = sorted({p for i in all_ids for p in kitems[i]["planted_lenient"]})
    covered_str = sorted({p for i in all_ids for p in kitems[i]["planted_strict"]})
    return {
        "schema": 1, "interval": "Wilson 95%", "note": NOT_INDEPENDENT, "n_items": len(all_ids),
        "overall": _tally([rating_of[i] for i in all_ids]), "by_type": by_type,
        "by_run": {run: _tally([rating_of[i] for i in all_ids if kitems[i]["run"] == run]) for run in runs},
        "planted_matching": _tally([rating_of[i] for i in matching]), "unplanted": _tally([rating_of[i] for i in unplanted]),
        "distinct_planted_covered": {"lenient": len(covered_len), "strict": len(covered_str), "lenient_ids": covered_len, "strict_ids": covered_str},
    }


def _ci(d: dict) -> str:
    if d["n"] == 0:
        return "n/a"
    return f"{d['k']} of {d['n']}; p {d['p']:.3f}; interval lo {d['lo']:.3f}; hi {d['hi']:.3f}"


def render_precision_markdown(res: dict) -> str:
    L = ["# Precision of the verified items from hand ratings (config A, phase 4a)", "", f"**{res['note']}**", "",
         "Counts and intervals only; no chat text. Strict = rated true. Lenient = true plus partly. Interval: Wilson 95%.", "",
         "| group | n | true | partly | false | tic | strict | lenient |", "|---|---|---|---|---|---|---|---|"]

    def row(name, t):
        return f"| {name} | {t['n']} | {t['true']} | {t['partly']} | {t['false']} | {t['tic']} | {_ci(t['strict'])} | {_ci(t['lenient'])} |"

    L.append(row("overall", res["overall"]))
    L += [row(t, v) for t, v in res["by_type"].items()]
    L += [row(f"run {r}", v) for r, v in res["by_run"].items()]
    L += [row("matching a planted item", res["planted_matching"]), row("unplanted", res["unplanted"]), "",
          f"Distinct planted items covered by the rated items: lenient {res['distinct_planted_covered']['lenient']} ({', '.join(res['distinct_planted_covered']['lenient_ids']) or 'none'}); "
          f"strict {res['distinct_planted_covered']['strict']} ({', '.join(res['distinct_planted_covered']['strict_ids']) or 'none'}).", ""]
    return "\n".join(L)


def write_precision(res: dict, base: str | Path) -> tuple[Path, Path]:
    b = Path(base)
    b.parent.mkdir(parents=True, exist_ok=True)
    j, m = b.with_suffix(".json"), b.with_suffix(".md")
    j.write_text(json.dumps(rounded(res), indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    m.write_text(render_precision_markdown(res), encoding="utf-8")
    return j, m


def read_ratings_csv(path: str | Path) -> list[dict]:
    import csv

    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        if not rd.fieldnames or "id" not in rd.fieldnames or "rating" not in rd.fieldnames:
            raise RatingError("a ratings file needs the columns id and rating")
        return [{"id": r["id"], "type": r.get("type", ""), "rating": r.get("rating", ""), "note": r.get("note", "")} for r in rd]


# ---- why were planted items missed? (numbers only)
def diagnose_misses(df: pd.DataFrame, aliases: privacy.Aliases | None, runs: list[tuple[str, dict, dict]], truth_items: list[dict]) -> dict:
    """For every strict miss (planted item, run): (a) did any AI item of the planted item's type carry ANY evidence, kept or dropped, whose quote
    (12+ characters) is a verbatim part of a planted message of that item (an id repair would then have found it)? (b) did the run propose an item
    of ANY type with evidence citing a message on one of the planted item's dates? Also the distance between cited and true ids of dropped evidence."""
    prep = analyze.prepare(df, aliases, slice_start=None, slice_end=None)
    index = prep["index"]
    ts = [r["ts"] for r in prep["rows"]]
    occ = verify.planted_occurrences(truth_items, index, prep["mapping"])
    texts = {t: [normalise_for_match(index[p]["text"]) for p, _ in rec["occurrences"]] for t, rec in occ.items()}
    dates = {t: sorted({str(w.date()) for _, w in rec["occurrences"]}) for t, rec in occ.items()}
    misses, distances = [], []
    for name, _log, report in runs:
        verified, _ = verify.verify_report(report, index, valid_members=set(prep["members"]))
        score = verify.match_planted(verified, index, truth_items, prep["mapping"], slice_start=min(ts), slice_end=max(ts))
        recs = classify_evidence(report, index)
        distances += [r["distance"] for r in recs if r["status"] == "other_message"]
        for typ in ("running_jokes", "moments"):
            for tid in score[typ]["planted_in_slice"]:
                if tid in score[typ]["found_strict"]:
                    continue
                same_type = [r for r in recs if r["type"] == typ and r["quote"]]
                verb = [r for r in same_type if len(normalise_for_match(r["quote"])) >= verify.MIN_QUOTE_CHARS and any(normalise_for_match(r["quote"]) in tx for tx in texts[tid])]
                on_dates = [r for r in recs if r["message_id"] in index and str(index[r["message_id"]]["ts"].date()) in dates[tid]]
                misses.append({
                    "run": name, "planted": tid, "type": typ,
                    "a_verbatim_planted_quote": {"any": bool(verb), "evidence_items": len(verb), "kept": sum(r["status"] == "verified" for r in verb), "dropped": sum(r["status"] != "verified" for r in verb)},
                    "b_evidence_on_planted_dates": {"any": bool(on_dates), "items": len({(r["type"], r["item"]) for r in on_dates}), "evidence_kept": sum(r["status"] == "verified" for r in on_dates),
                                                    "evidence_dropped": sum(r["status"] != "verified" for r in on_dates), "types": sorted({r["type"] for r in on_dates})},
                })
    return {"schema": 1, "misses": misses, "dropped_other_message": {"n": len(distances), "within_10": sum(d <= 10 for d in distances), "beyond_10": sum(d > 10 for d in distances),
                                                                         "distances": sorted(distances)}}


def render_diagnostic_markdown(d: dict) -> str:
    L = ["# Why planted items were missed (config A, phase 4a; numbers only)", "",
         "Strict misses only. (a) Any evidence of an AI item of the same type, kept or dropped, whose quote (12+ characters) is verbatim part of a planted message of that item, so an id repair would have found it. "
         "(b) Any item of any type with evidence citing a message on one of the planted item's dates.", "",
         "| run | planted | (a) verbatim planted quote: evidence items (kept; dropped) | (b) evidence on planted dates: items (kept; dropped) |", "|---|---|---|---|"]
    for m in d["misses"]:
        a, b = m["a_verbatim_planted_quote"], m["b_evidence_on_planted_dates"]
        L.append(f"| {m['run']} | {m['planted']} | {'yes' if a['any'] else 'no'}: {a['evidence_items']} ({a['kept']}; {a['dropped']}) | {'yes' if b['any'] else 'no'}: {b['items']} items ({b['evidence_kept']}; {b['evidence_dropped']}) |")
    o = d["dropped_other_message"]
    L += ["", f"Dropped evidence whose quote exists in another message: {o['n']}. Cited id within 10 of the true id (the nearest other message holding the quote): {o['within_10']}; further away: {o['beyond_10']}. Distances: {', '.join(str(x) for x in o['distances']) or 'none'}.", ""]
    return "\n".join(L)


# ------------------------------------------------------------------ Phase 4b: single-pass versus chunked comparison
WINNER_WORDS = ("winner", "best", "better", "worse", "outperform", "superior", "recommend", "beats")


def _mean_rng(s: dict, pct: bool = False, nd: int = 4) -> str:
    return _rng(s, pct, nd)


def compare_modes(single: dict, chunked: dict, commit: str = "") -> str:
    """Markdown comparing two results dicts (n runs each, counts and ids only). It states which of the written predictions held, from the numbers,
    and uses no ranking language."""
    ns, nc = single["n_runs"], chunked["n_runs"]
    ps, pc = single["planted"], chunked["planted"]
    jokes = [t for t, v in ps.items() if v["type"] == "running_jokes"]
    L = [f"# Single-pass versus chunked map-reduce (n = {ns} runs and n = {nc} runs; frozen synthetic chat; config A, prompt v1)", "",
         f"Predictions were written to `docs/PRD.md` and committed before any chunked run{(' in commit ' + commit) if commit else ''}. Counts and ids only; no chat text. "
         "Real chats differ: the synthetic planted items are easier than real jokes.", "",
         "## Planted items found (strict), in k of n runs", "", "| planted id | type | group | split | single-pass | chunked | single-pass lenient | chunked lenient |", "|---|---|---|---|---|---|---|---|"]
    for t, v in ps.items():
        c = pc.get(t, {})
        L.append(f"| {t} | {v['type']} | {v['group']} | {v['split']} | {v['found_strict_runs']} of {ns} | {c.get('found_strict_runs')} of {nc} | {v['found_lenient_runs']} of {ns} | {c.get('found_lenient_runs')} of {nc} |")
    ss, sc = single["summary"], chunked["summary"]
    L += ["", "## Other numbers (mean; min; max over runs)", "", "| measure | single-pass | chunked |", "|---|---|---|",
          f"| rule-compliant rate | {_mean_rng(ss['rule_compliant_rate'], True)} | {_mean_rng(sc['rule_compliant_rate'], True)} |",
          f"| grounding rate | {_mean_rng(ss['grounding_rate'], True)} | {_mean_rng(sc['grounding_rate'], True)} |",
          *[f"| items kept, {t} | {_mean_rng(ss['items_kept'][t], nd=1)} | {_mean_rng(sc['items_kept'][t], nd=1)} |" for t in SIZE_TYPES],
          *[f"| unplanted items, {t} | {_mean_rng(ss['unplanted_items'][t], nd=1)} | {_mean_rng(sc['unplanted_items'][t], nd=1)} |" for t in SIZE_TYPES],
          f"| cost USD per run (from usage) | {_mean_rng(ss['cost_usd'])} | {_mean_rng(sc['cost_usd'])} |",
          f"| latency seconds (single: the one call; chunked: sum of all call latencies) | {_mean_rng(ss['latency_s'], nd=1)} | {_mean_rng(sc['latency_s'], nd=1)} |",
          f"| wall-clock seconds (chunked, map calls in parallel) | not measured | {_mean_rng(sc['wall_clock_s'], nd=1) if 'wall_clock_s' in sc else 'n/a'} |",
          f"| output tokens | {_mean_rng(ss['output_tokens'], nd=0)} | {_mean_rng(sc['output_tokens'], nd=0)} |", ""]
    # predictions
    cost_s, cost_c = ss["cost_usd"]["mean"], sc["cost_usd"]["mean"]
    p1 = cost_c < 0.4 * cost_s
    jl_s, jl_c = ps["jL"]["found_strict_runs"], pc["jL"]["found_strict_runs"]
    p2 = jl_c < jl_s
    diffs = {t: abs(pc[t]["found_strict_runs"] - ps[t]["found_strict_runs"]) for t in jokes if t != "jL"}
    p3 = all(d <= 1 for d in diffs.values())
    mom = [t for t, v in ps.items() if v["type"] == "moments"]
    L += ["## Predictions", "",
          f"1. Chunked cost per run below 40% of single-pass: chunked mean {cost_c:.4f} against a limit of {0.4 * cost_s:.4f} (40% of the single-pass mean {cost_s:.4f}): **{'held' if p1 else 'did not hold'}**.",
          f"2. jL found (strict) in fewer chunked runs than in single-pass: chunked {jl_c} of {nc}, single-pass {jl_s} of {ns}: **{'held' if p2 else 'did not hold'}**.",
          f"3. Each of the six other jokes within one item-run of single-pass: differences {', '.join(f'{t} {d}' for t, d in sorted(diffs.items()))}: **{'held' if p3 else 'did not hold'}**.",
          f"4. Moments: no prediction. Strict found item-runs, single-pass {sum(ps[t]['found_strict_runs'] for t in mom)} of {len(mom) * ns}, chunked {sum(pc[t]['found_strict_runs'] for t in mom)} of {len(mom) * nc}.", ""]
    md = "\n".join(L) + "\n"
    low = md.lower()
    assert not any(w in low for w in WINNER_WORDS), "ranking language in the comparison"
    return md
