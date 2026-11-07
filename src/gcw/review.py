"""Human review gate for AI items. Nothing reaches the card unless its status is `approved`.

Stable item ids: the first 12 hex chars of SHA-256 over `type | title (or award name) | first evidence message id`. A review file maps ids to
statuses (pending / approved / rejected) and lives in out/reviews/ (gitignored). Items that are not in the review file are pending; pending and
rejected items never render. No network, never imports anthropic.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

STATUSES = ("pending", "approved", "rejected")
TYPES = ("running_jokes", "moments", "awards")
VERSION = 1
APPROVAL_MODES = ("human", "auto-synthetic")  # "auto-synthetic" is written only by the CLI flag --auto-approve-synthetic and the app's synthetic-demo button


class ReviewError(ValueError):
    """A review file that cannot be used."""


def _head(item: dict) -> str:
    return str(item.get("title") or item.get("award") or "")


def item_id(typ: str, item: dict) -> str:
    ev = item.get("evidence") or []
    first = ev[0].get("message_id", "") if ev and isinstance(ev[0], dict) else ""
    return hashlib.sha256(f"{typ}|{_head(item)}|{first}".encode("utf-8")).hexdigest()[:12]


def new_review(report: dict, run: str = "") -> dict:
    """A review with every item of the report pending."""
    items: dict[str, dict] = {}
    for typ in TYPES:
        for it in report.get(typ) or []:
            items[item_id(typ, it)] = {"type": typ, "title": _head(it), "status": "pending"}
    return {"version": VERSION, "run": run, "approval_mode": "human", "items": items}


def mode_of(review: dict | None) -> str:
    """How the approvals were made: "human" (a person decided each item; also the default of older files) or "auto-synthetic" (everything approved by a script)."""
    return (review or {}).get("approval_mode", "human")


def check_mode(review: dict | None, frozen_chat: bool) -> None:
    """A review marked auto-synthetic is refused for any chat that is not the frozen synthetic chat."""
    if mode_of(review) == "auto-synthetic" and not frozen_chat:
        raise ReviewError("this review is marked auto-synthetic (everything approved by a script); that is allowed only for the frozen synthetic chat")


def set_human(review: dict) -> None:
    """Any manual decision after an auto-approval makes the approvals human again."""
    review["approval_mode"] = "human"


def set_status(review: dict, ids: list[str], status: str) -> list[str]:
    """Set `status` for each id; returns ids that are not in the review (unchanged)."""
    if status not in STATUSES:
        raise ReviewError(f"unknown status {status!r}")
    missing = []
    for i in ids:
        if i in review["items"]:
            review["items"][i]["status"] = status
        else:
            missing.append(i)
    return missing


def merge(review: dict, report: dict) -> dict:
    """Add items of `report` that the review does not know yet (as pending); keeps existing statuses."""
    fresh = new_review(report, review.get("run", ""))
    for i, v in fresh["items"].items():
        review["items"].setdefault(i, v)
    return review


def _rank_of(meta: dict, pos: int) -> int:
    r = meta.get("rank")
    return r if isinstance(r, int) and not isinstance(r, bool) else pos  # no rank: the model's own order


def apply(report: dict, review: dict | None) -> dict:
    """The approved report: only items whose id has status `approved`, sorted by rank then model order. An item without a rank uses its position in
    the model's order as its rank, so with no ranks at all the order is exactly the model's (no cherry-picking). Unknown or missing ids are pending
    and never appear."""
    items = (review or {}).get("items", {})
    out: dict[str, list] = {t: [] for t in TYPES}
    for typ in TYPES:
        picked = []
        for pos, it in enumerate(report.get(typ) or []):
            meta = items.get(item_id(typ, it), {})
            if meta.get("status") == "approved":
                picked.append(((_rank_of(meta, pos), pos), it))
        out[typ] = [it for _, it in sorted(picked, key=lambda x: x[0])]
    return out


def set_rank(review: dict, item: str, rank: int | None) -> bool:
    """Set (or clear, with None) the optional integer rank of an item; returns False if the id is unknown. Lower rank shows first."""
    if item not in review["items"]:
        return False
    if rank is None:
        review["items"][item].pop("rank", None)
    elif isinstance(rank, int) and not isinstance(rank, bool):
        review["items"][item]["rank"] = rank
    else:
        raise ReviewError(f"rank must be an integer, got {rank!r}")
    return True


def approve_all(report: dict, run: str = "") -> dict:
    """Review with every item approved. Only the CLI's --auto-approve-synthetic may call this, and only on the frozen synthetic chat."""
    rv = new_review(report, run)
    for v in rv["items"].values():
        v["status"] = "approved"
    rv["approval_mode"] = "auto-synthetic"
    return rv


def load_review(path: str | Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ReviewError(f"cannot read review file {path}: {e}") from e
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, dict) or any(not isinstance(v, dict) or v.get("status") not in STATUSES or ("rank" in v and (not isinstance(v["rank"], int) or isinstance(v["rank"], bool))) for v in items.values()):
        raise ReviewError(f"review file {path} is malformed (items must map ids to a status in {STATUSES}; an optional rank must be an integer)")
    if data.get("approval_mode", "human") not in APPROVAL_MODES:
        raise ReviewError(f"review file {path} is malformed (approval_mode must be one of {APPROVAL_MODES})")
    return data


def save_review(path: str | Path, review: dict) -> None:
    """Atomic write: a crash leaves the old file or the new one, never half of one."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(review, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def counts(report: dict, review: dict | None) -> dict[str, int]:
    """items in the report by status (missing ids count as pending)."""
    c = {s: 0 for s in STATUSES}
    items = (review or {}).get("items", {})
    for typ in TYPES:
        for it in report.get(typ) or []:
            c[items.get(item_id(typ, it), {}).get("status", "pending")] += 1
    return c
