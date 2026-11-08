"""Logic behind the Streamlit app (src/gcw/app.py): everything testable without a browser. The chat lives in memory only; nothing here writes chat text to disk.

Network rule: nothing in this module touches the network except `run_ai`, which the page calls only after the consent checkbox and the Run button. Even the
exact token count (count_tokens) sends the pseudonymised text, so it is part of `run_ai`, never of the preview.
"""
from __future__ import annotations

import io
import json
import math
import random
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from gcw import analyze, card, chunked, cost, dataset, display, llm, privacy, review, verify
from gcw.parser import messages, parse_chat
from gcw.stats import compute_stats

MAX_UNCOMPRESSED = 50 * 1024 * 1024  # a chat (or a zip member) above 50 MB is refused
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEMO_CHAT = Path(__file__).resolve().parents[2] / "synthetic" / "frozen" / "chat_synthetic.txt"
CONSENT_TEXT = "I understand that pseudonymised message text will be sent to Anthropic, and the group members consented"
SENDER_LINES_NOTE = ("Sender lines include deleted messages and media. The stats card counts visible messages only: it leaves out deleted messages and system lines.")
LEAK_WARNING = ("Only names and nicknames you list here are replaced by Member N before anything is sent. A nickname or surname you leave out stays in the message text "
                "and would be sent as written.")
MODES = ("auto", "single", "chunked")
SINGLE_MODE_MAX_TOKENS = 1_000_000  # --mode single stays available up to the model limit (the user chose it)
OUT_DIR = Path("out") / "app"
RUNS_DIR = Path("out") / "runs"
LEDGER_PATH: str | None = None  # None: the project ledger (tests point this at a temp file)
client_factory: Callable[[], Any] = lambda: llm.get_client(max_retries=0)  # tests replace this with a fake client


RENDER_LOCK = threading.Lock()  # one render at a time across all sessions of this server


class AppError(ValueError):
    """A user-facing refusal (bad upload, cap exceeded, nothing to do)."""


# ------------------------------------------------------------------ upload handling (memory only)
def _ignored_entry(info: zipfile.ZipInfo) -> bool:
    """Entries the zip loader never reads: directories, macOS __MACOSX/ entries, hidden files (a name or folder starting with a dot) and anything that is not a .txt."""
    name = info.filename
    return info.is_dir() or name.startswith("__MACOSX/") or any(p.startswith(".") for p in name.split("/") if p) or not name.lower().endswith(".txt")


def read_zip_text(data: bytes) -> tuple[str, int]:
    """(text of the single .txt chat file in a zip, number of ignored file entries). Everything stays in memory and only the chosen entry is opened: the other files (media,
    contact cards, hidden and macOS entries) are neither read nor extracted. Error messages never contain chat text."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise AppError(f"not a readable zip file: {e}") from None
    with zf:
        files = [i for i in zf.infolist() if not i.is_dir()]
        chats = [i for i in files if not _ignored_entry(i)]
        if not chats:
            raise AppError(f"no .txt chat file was found in the zip; it holds {len(files)} other file{'' if len(files) == 1 else 's'}")
        if len(chats) > 1:
            raise AppError(f"{len(chats)} .txt files were found in the zip; exactly one is required")
        info = chats[0]
        if info.flag_bits & 0x1:
            raise AppError("the zip member is encrypted")
        if info.file_size > MAX_UNCOMPRESSED:
            raise AppError(f"the zip member is larger than {MAX_UNCOMPRESSED // (1024 * 1024)} MB uncompressed")
        with zf.open(info) as fh:
            raw = fh.read(MAX_UNCOMPRESSED + 1)  # the real size is enforced while reading, whatever the header claims
        if len(raw) > MAX_UNCOMPRESSED:
            raise AppError(f"the zip member is larger than {MAX_UNCOMPRESSED // (1024 * 1024)} MB uncompressed")
    try:
        return raw.decode("utf-8"), len(files) - 1
    except UnicodeDecodeError:
        raise AppError("the file is not UTF-8 text") from None


def read_upload(name: str, data: bytes) -> str:
    """Text of an uploaded .txt, or of the single .txt chat file of an uploaded .zip (other files in the zip are ignored). Everything stays in memory; nothing is extracted to disk."""
    low = (name or "").lower()
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError(f"the file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if low.endswith(".zip"):
        return read_zip_text(data)[0]
    if low.endswith(".txt"):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            raise AppError("the file is not UTF-8 text") from None
    raise AppError("upload a WhatsApp export (.txt) or a .zip with one .txt chat file")


def demo_text() -> str:
    return DEMO_CHAT.read_text(encoding="utf-8")


def parse_view(text: str, date_order: str | None = None) -> tuple[pd.DataFrame, dict]:
    """(dataframe, parse report as plain values). Raises AppError when nothing can be parsed."""
    df, rep = parse_chat(text, date_order=date_order or None)
    if rep.n_messages == 0:
        raise AppError("no messages could be parsed from this file")
    view = {"messages": rep.n_messages, "system_lines": rep.n_system, "unparsed": rep.n_unparsed, "date_order": rep.date_order, "date_order_source": rep.date_order_source,
            "ambiguous": rep.ambiguous, "first": str(rep.first_msg_ts.date()) if rep.first_msg_ts is not None else None,
            "last": str(rep.last_msg_ts.date()) if rep.last_msg_ts is not None else None, "senders": dict(sorted(rep.per_sender.items(), key=lambda kv: -kv[1])),
            "warnings": list(rep.warnings), "format_verified": rep.format_verified}
    return df, view


# ------------------------------------------------------------------ settings
def default_window(last: str, days: int = 365) -> tuple[str, str]:
    end = pd.Timestamp(last)
    return str((end - pd.Timedelta(days=days - 1)).date()), str(end.date())


def alias_table(senders: list[str]) -> list[dict]:
    return [{"export_name": s, "display": s, "nicknames": ""} for s in senders]


def aliases_from_table(rows: list[dict]) -> privacy.Aliases:
    members = []
    for r in rows:
        nick = [n.strip() for n in str(r.get("nicknames") or "").split(",") if n.strip()]
        members.append({"export_name": str(r["export_name"]), "display": str(r.get("display") or r["export_name"]).strip() or str(r["export_name"]), "nicknames": nick})
    try:
        return privacy.parse_aliases({"members": members})
    except ValueError as e:
        raise AppError(str(e)) from None


def aliases_from_upload(data: bytes) -> privacy.Aliases:
    try:
        return privacy.parse_aliases(json.loads(data.decode("utf-8")))
    except (ValueError, UnicodeDecodeError) as e:
        raise AppError(f"bad aliases file: {e}") from None


def display_map(aliases: privacy.Aliases | None) -> dict[str, str]:
    return {k: card.clean_name(v) for k, v in (aliases.display_map() if aliases else {}).items()}


# ------------------------------------------------------------------ stats card (no network)
def card_html(df: pd.DataFrame, aliases: privacy.Aliases | None, since: str, until: str, ambiguous_order: str | None = None, ai: dict | None = None) -> str:
    stats = compute_stats(df, since=since, until=until)
    note = f"Dates read as {'m/d' if ambiguous_order == 'mdy' else 'd/m'} (assumed)" if ambiguous_order else None
    return card.build_card_html(stats, display_map(aliases) or None, date_note=note, ai=ai)


def _child_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = str(root / "src") + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if (root / ".cache" / "ms-playwright").is_dir():
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(root / ".cache" / "ms-playwright"))
    env["GCW_NO_NETWORK_CHILD"] = "1"
    return env


def render_png_bytes(html: str) -> bytes:
    """Render in a child process: `nice -n 10`, Chromium --disable-gpu, one browser and one page, closed afterwards. The HTML goes in over stdin and the PNG
    comes back over stdout, so the chat never touches disk. The page blocks every network request (card.render_png)."""
    if not RENDER_LOCK.acquire(blocking=False):
        raise AppError("another card render is running; wait for it to finish")
    try:
        proc = subprocess.run(["nice", "-n", "10", sys.executable, "-m", "gcw.render_child"], input=html.encode("utf-8"), capture_output=True, env=_child_env(), timeout=180)
    finally:
        RENDER_LOCK.release()
    if proc.returncode != 0 or not proc.stdout.startswith(b"\x89PNG"):
        raise AppError("the card renderer failed: " + proc.stderr.decode("utf-8", "replace")[-300:])
    return proc.stdout


# ------------------------------------------------------------------ AI step: preview (offline) and run
def preview(df: pd.DataFrame, aliases: privacy.Aliases | None, since: str, until: str) -> dict:
    """The payload as it would be sent, built offline. Contains pseudonymised text: show it only to the user, never write it."""
    rows, counts, mapping = privacy.build_payload_rows(df, aliases)
    sel = analyze.select_rows(rows, since, until)
    if not sel:
        raise AppError("the date window contains no messages")
    text = verify.neutralise(privacy.rows_text(sel))
    lines = text.splitlines()
    picked = sorted(random.Random(0).sample(range(len(lines)), min(20, len(lines))))
    nbytes = len(text.encode("utf-8"))
    rough = round(nbytes / privacy.BYTES_PER_TOKEN)
    withheld = sum(r["withheld"] for r in sel)
    return {"lines": [lines[i] for i in picked], "messages": len(sel), "withheld": withheld, "withheld_by_category": counts["withheld_by_category"], "replacements": counts["replacements"],
            "bytes": nbytes, "rough_tokens": rough, "bounds": cost_bounds(rough), "prefix": counts["prefix"], "warnings": counts["warnings"]}


def cost_bounds(rough_tokens: int) -> dict:
    """Upper bounds computed offline from the rough token count (bytes / 2.37, which can be a few percent low): every call is assumed to use all max_tokens."""
    single = cost.estimate_usd(int(rough_tokens * 1.1), analyze.MAX_TOKENS)
    n = max(1, math.ceil(rough_tokens * 1.2 / chunked.CHUNK_LIMIT))
    chunk_total = n * cost.estimate_usd(chunked.CHUNK_LIMIT, analyze.MAX_TOKENS) + cost.estimate_usd(chunked.MAP_CALL_STOP, analyze.MAX_TOKENS)
    return {"single_usd": round(single, 4), "chunked_usd": round(chunk_total, 4), "chunks_upper": n, "auto_usd": round(max(single, chunk_total) if rough_tokens * 1.1 > chunked.SINGLE_PASS_LIMIT * 0.8 else single, 4)}


def cap_status(bound_usd: float, ledger_path: str | None = None) -> dict:
    ledger_path = ledger_path or LEDGER_PATH
    run_cap, proj_cap = cost.per_run_cap(), cost.project_cap()
    spent = cost.ledger_total(ledger_path)
    room = proj_cap - spent
    return {"run_cap": run_cap, "project_cap": proj_cap, "ledger_total": round(spent, 4), "project_room": round(room, 4), "bound": bound_usd,
            "ok": bound_usd <= run_cap + 1e-12 and bound_usd <= room + 1e-12}


def windowed(df: pd.DataFrame, since: str, until: str) -> pd.DataFrame:
    """The chat restricted to the days since..until (inclusive), for the chunked path, which has no slice parameters."""
    return df[(df["ts"] >= pd.Timestamp(since)) & (df["ts"] < pd.Timestamp(until) + pd.Timedelta(days=1))]


def key_loaded() -> bool:
    return bool(llm.key_status()[0])


def run_ai(df: pd.DataFrame, aliases: privacy.Aliases | None, since: str, until: str, mode: str, *, consent: bool, ledger_path: str | None = None,
           out_dir: str | Path = RUNS_DIR, log: Callable[[str], None] = lambda s: None) -> dict:
    """The only network path. Refuses without consent. Exact count_tokens pre-flight, caps re-checked, then the analysis through cost.py with confirm=True.
    Nothing but the run log is written (no --save-response): the verified report stays in memory."""
    ledger_path = ledger_path or LEDGER_PATH
    if consent is not True:
        raise AppError("consent is required before anything is sent")
    if mode not in MODES:
        raise AppError(f"unknown mode {mode!r}")
    prep = preview(df, aliases, since, until)  # offline; also the first cap check
    st = cap_status(prep["bounds"]["single_usd" if mode == "single" else "chunked_usd" if mode == "chunked" else "auto_usd"], ledger_path)
    if not st["ok"]:
        raise AppError(f"refused: the worst-case cost bound ${st['bound']:.2f} exceeds the cap (run cap ${st['run_cap']:.2f}, project room ${st['project_room']:.2f})")
    guard = cost.CostGuard(ledger_path=ledger_path)
    client = client_factory()
    chosen = mode
    if mode == "auto":
        probe = analyze.run_analysis(df, aliases, config="A", slice_start=since, slice_end=until, count_only=True, budget=guard.proj_cap, phase="app", max_input_tokens=10**9,
                                     label_suffix="app", client=client, guard=guard, out_dir=out_dir)
        chosen = chunked.choose_mode(probe["request_tokens"])
        log(f"exact count {probe['request_tokens']} tokens; single-pass limit {chunked.SINGLE_PASS_LIMIT}: using {chosen}")
        if chosen == "chunked":
            log(chunked.AUTO_WARNING)
    if chosen == "single":
        res = analyze.run_analysis(df, aliases, config="A", slice_start=since, slice_end=until, confirm=True, budget=guard.proj_cap, phase="app", label_suffix="app",
                                   max_input_tokens=SINGLE_MODE_MAX_TOKENS if mode == "single" else chunked.SINGLE_PASS_LIMIT, max_run_cost=guard.run_cap, client=client, guard=guard,
                                   out_dir=out_dir, save_response=False)
        p = res["prep"]
        return {"mode": "single", "verified": res["verified"], "stats": res["stats"], "index": p["index"], "rows": p["rows"], "mapping": p["mapping"], "cost_usd": res["cost_usd"],
                "request_tokens": res["request_tokens"], "latency_s": res["latency_s"], "chosen": chosen}
    res = chunked.run_chunked(windowed(df, since, until), aliases, config="A", client=client, guard=guard, confirm=True, budget=guard.proj_cap, phase="app", label="app", out_dir=out_dir, save_response=False)
    return {"mode": "chunked", "verified": res["final"], "stats": res["stats"], "index": res["index"], "rows": res["rows"], "mapping": res["mapping"], "cost_usd": res["totals"]["cost_usd"],
            "request_tokens": sum(c["tokens"] for c in res["chunks"]), "latency_s": res["totals"]["wall_clock_s"], "chosen": chosen, "chunks": len(res["chunks"])}


# ------------------------------------------------------------------ review
def load_report_upload(data: bytes, index: dict, members: set[str]) -> tuple[dict, dict]:
    """A saved .report.json (analyze --save-response): re-verified against the current chat, so nothing unverified can reach the card."""
    try:
        rep = json.loads(data.decode("utf-8"))
        verified, stats = verify.verify_report(rep, index, valid_members=members)
    except (ValueError, UnicodeDecodeError, KeyError, TypeError, AttributeError) as e:
        raise AppError(f"not a usable verified report for this chat and window: {e}") from None
    return verified, stats


def proposed_from_log(data: bytes) -> int | None:
    """How many items the model proposed, from the run log (.json) that belongs to a saved report; None when the log has no such count. Logs hold counts only."""
    try:
        n = json.loads(data.decode("utf-8"))["stats"]["items_in"]
    except (ValueError, UnicodeDecodeError, KeyError, TypeError):
        return None
    return int(n) if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None


def log_messages(data: bytes) -> int | None:
    """The message count the run covered, from its log; None when the log has none."""
    try:
        n = json.loads(data.decode("utf-8"))["messages"]
    except (ValueError, UnicodeDecodeError, KeyError, TypeError):
        return None
    return n if isinstance(n, int) and not isinstance(n, bool) else None


def item_ids(report: dict) -> list[tuple[str, str, dict]]:
    return [(review.item_id(t, it), t, it) for t in review.TYPES for it in report.get(t) or []]


def names_for(mapping: dict[str, str], aliases: privacy.Aliases | None) -> dict[str, str]:
    dm = display_map(aliases)
    return {tok: card.clean_name(dm.get(export, export)) for tok, export in mapping.items()}


def context(rows: list[dict], pid: str, names: dict[str, str], k: int = 2) -> list[dict]:
    """The message `pid` with k messages before and after, display names instead of Member tokens. Withheld messages show a placeholder."""
    pos = next((i for i, r in enumerate(rows) if r["pid"] == pid), None)
    if pos is None:
        return []
    out = []
    for r in rows[max(0, pos - k): pos + k + 1]:
        body = "[withheld]" if r["withheld"] else display.detokenise(r["body"], names)
        out.append({"pid": r["pid"], "when": f"{r['ts']:%Y-%m-%d %H:%M}", "who": names.get(r["sender"], r["sender"]), "text": body, "is_target": r["pid"] == pid})
    return out


def is_frozen_text(text: str) -> bool:
    """True only for the bundled frozen synthetic chat: the text's SHA-256 equals the hard-coded constant and the frozen dataset verifies."""
    import hashlib

    try:
        dataset.verify_dataset()
    except (dataset.DatasetError, OSError):
        return False
    return hashlib.sha256(text.encode("utf-8")).hexdigest() == dataset.CHAT_SHA256


def auto_approve_all(report: dict, run: str, chat_text: str) -> dict:
    """Approve every item (approval_mode auto-synthetic). Refused unless the loaded chat is the frozen synthetic chat."""
    if not is_frozen_text(chat_text):
        raise AppError("auto-approval is only allowed for the bundled synthetic demo chat")
    return review.approve_all(report, run)


def safe_review(rv: dict) -> dict:
    """What may be written to disk: item ids, types, statuses, ranks and the approval mode only, no titles."""
    return {"version": rv.get("version"), "run": rv.get("run", ""), "approval_mode": review.mode_of(rv), "items": {i: {k: v[k] for k in ("type", "status", "rank") if k in v} for i, v in rv["items"].items()}}


def save_safe_review(rv: dict, run: str, out_dir: str | Path = OUT_DIR) -> Path:
    p = Path(out_dir) / f"review_{run}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(safe_review(rv), indent=1), encoding="utf-8")
    return p


def zone_for(report: dict, rv: dict, index: dict, mapping: dict[str, str], aliases: privacy.Aliases | None, stats: dict, proposed: int | None = None) -> dict:
    approved = review.apply(report, rv)
    zone = display.build_zone2(approved, index, names_for(mapping, aliases))
    return {"zone2": zone, "approved": sum(len(approved[t]) for t in review.TYPES), "proposed": proposed if proposed is not None else sum((stats.get("items_in_by_type") or {}).values()),
            "verified": sum(len(report.get(t) or []) for t in review.TYPES), "synthetic": review.mode_of(rv) == "auto-synthetic"}  # the footer wording follows the review file's approval_mode
