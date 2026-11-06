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
