"""Command line: python -m gcw stats-card CHAT --out out/card.png [--aliases F] [--since D] [--until D] [--date-order mdy|dmy].

Stats-only: parse_chat -> compute_stats -> HTML -> PNG. Zero API calls (this module never imports anthropic).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gcw import card
from gcw.parser import parse_chat
from gcw.stats import compute_stats


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="gcw", description="Group Chat Wrapped")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("stats-card", help="render the stats-only card (no AI, no API calls)")
    sc.add_argument("chat", help="WhatsApp export (.txt)")
    sc.add_argument("--out", default="out/card.png", help="PNG path (default out/card.png)")
    sc.add_argument("--aliases", help="JSON file mapping export names to display names (card only)")
    sc.add_argument("--since", help="first day/time to include (YYYY-MM-DD or ISO datetime)")
    sc.add_argument("--until", help="last day/time to include, inclusive (YYYY-MM-DD means the whole day)")
    sc.add_argument("--date-order", choices=["mdy", "dmy"], help="override the inferred day/month order")
    sc.add_argument("--html", help="also write the card HTML here (debugging)")
    pv = sub.add_parser("preview", help="show the exact (pseudonymised, redacted) text that would be sent to the model; makes no API call")
    pv.add_argument("chat", help="WhatsApp export (.txt)")
    pv.add_argument("--aliases", help="aliases JSON ({\"members\": [...]} or flat); without it only senders are pseudonymised")
    pv.add_argument("--out", default="out/payload_preview.txt", help="where to write the full payload (default out/payload_preview.txt; gitignored)")
    pv.add_argument("--date-order", choices=["mdy", "dmy"], help="override the inferred day/month order")
    an = sub.add_parser("analyze", help="AI analysis of a slice of the chat (running jokes, moments, awards); offline unless --count or --confirm")
    an.add_argument("chat", help="WhatsApp export (.txt)")
    an.add_argument("--aliases", help="aliases JSON (see aliases.example.json)")
    an.add_argument("--slice-start", help="first day to include (YYYY-MM-DD); default: start of the chat")
    an.add_argument("--slice-end", help="last day to include, inclusive (YYYY-MM-DD)")
    an.add_argument("--config", choices=["A", "B", "C"], default="A", help="A: thinking off, effort low; B: adaptive thinking, low; C: adaptive, medium")
    an.add_argument("--count", action="store_true", help="exact token count via the free count_tokens endpoint (SENDS the payload to Anthropic, generates nothing)")
    an.add_argument("--confirm", action="store_true", help="count, then make the paid call (without it no generation happens)")
    an.add_argument("--budget", type=float, default=0.15, help="phase budget in USD over ledger labels starting 3b: (default 0.15)")
    an.add_argument("--save-response", action="store_true", help="also save the raw model response and the verified report under out/runs/ (OFF by default; they hold pseudonymised quotes, delete them afterwards)")
    an.add_argument("--phase", default="3b", help="ledger label prefix for the phase budget (default 3b)")
    an.add_argument("--truth", help="ground_truth.json of a synthetic chat: score found planted items")
    an.add_argument("--label", default="slice", help="label suffix for the ledger entry")
    an.add_argument("--date-order", choices=["mdy", "dmy"], help="override the inferred day/month order")
    return ap


def analyze_cmd(args: argparse.Namespace) -> int:
    import json
    import random

    from gcw import analyze as az
    from gcw import cost, privacy

    chat = Path(args.chat)
    if not chat.is_file():
        print(f"gcw: chat file not found: {chat}", file=sys.stderr)
        return 2
    aliases = None
    if args.aliases:
        try:
            aliases = privacy.load_aliases(args.aliases)
        except (OSError, ValueError) as e:
            print(f"gcw: bad aliases file: {e}", file=sys.stderr)
            return 2
    else:
        print("gcw: warning: no --aliases file: names inside message text are not replaced (only senders are)", file=sys.stderr)
    truth = None
    if args.truth:
        try:
            truth = json.loads(Path(args.truth).read_text(encoding="utf-8"))["items"]
        except (OSError, ValueError, KeyError) as e:
            print(f"gcw: bad --truth file: {e}", file=sys.stderr)
            return 2
    df, report = parse_chat(chat, date_order=args.date_order)
    if report.n_messages == 0:
        print("gcw: no messages could be parsed from this file", file=sys.stderr)
        return 3
    try:
        res = az.run_analysis(df, aliases, config=args.config, slice_start=args.slice_start, slice_end=args.slice_end, confirm=args.confirm,
                              count_only=args.count, budget=args.budget, truth_items=truth, label_suffix=args.label,
                              phase=args.phase, save_response=args.save_response)
    except (az.AnalysisError, cost.CostError, OSError, RuntimeError) as e:
        print(f"gcw: {e}", file=sys.stderr)
        return 3
    lines = [r for r in res["prep"]["payload_text"].splitlines()]
    print(f"slice: {res['messages']} messages, {res['withheld']} withheld, {res['payload_bytes']} bytes, ~{res['rough_tokens']} tokens (rough, offline: bytes / 2.37)")
    print(f"config {args.config}: {az.CONFIGS[args.config]}; max_tokens {az.MAX_TOKENS}")
    for i in sorted(random.Random(0).sample(range(len(lines)), min(20, len(lines)))):
        print("  " + lines[i])
    if "request_tokens" not in res:
        print("offline only: nothing was sent. Use --count for the exact token count (free, sends the payload) or --confirm to run.")
        return 0
    print(f"exact request tokens (count_tokens WITH output_config): {res['request_tokens']}; worst-case cost if all {az.MAX_TOKENS} output tokens are used: ${res['worst_case_cost_usd']:.4f}")
    if "stats" not in res:
        return 0
    st = res["stats"]
    rate = st["evidence_verified"] / st["evidence_total"] if st["evidence_total"] else 0.0
    print(f"items in/kept {st['items_in_by_type']} / {st['items_kept_by_type']}; evidence {st['evidence_verified']}/{st['evidence_total']} verified ({rate:.0%}); drops {st['drop_reasons']}")
    print(f"thinking_tokens {res['thinking_tokens']}, output_tokens {res['output_tokens']}, latency {res['latency_s']}s, attempts {res['attempts']}, cost ${res['cost_usd']:.6f}, stop_reason {res['stop_reason']}")
    print(f"injection obeyed (PWNED in a title/summary/award/member field): {res['injection_obeyed']}")
    if "score" in res:
        for typ, s in res["score"].items():
            print(f"planted {typ}: in slice {s['planted_in_slice']}, found {s['found']}, recall {s['recall']}, items matching {s['items_matching_planted']}, unplanted {s['items_unplanted']}")
    print(f"ledger total: ${cost.ledger_total():.6f}")
    return 0


def preview(args: argparse.Namespace) -> int:
    import json
    import random

    from gcw import privacy

    chat = Path(args.chat)
    if not chat.is_file():
        print(f"gcw: chat file not found: {chat}", file=sys.stderr)
        return 2
    aliases = None
    if args.aliases:
        try:
            aliases = privacy.load_aliases(args.aliases)
        except (OSError, ValueError) as e:
            print(f"gcw: bad aliases file: {e}", file=sys.stderr)
            return 2
    else:
        print("gcw: warning: no --aliases file: names inside message text are not replaced (only senders are)", file=sys.stderr)
    df, report = parse_chat(chat, date_order=args.date_order)
    if report.n_messages == 0:
        print("gcw: no messages could be parsed from this file", file=sys.stderr)
        return 3
    try:
        text, counts, _mapping = privacy.build_payload(df, aliases)  # the mapping is deliberately not printed or written
    except (OSError, ValueError) as e:
        print(f"gcw: {e}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(json.dumps(counts, indent=2, ensure_ascii=False))
    lines = text.splitlines()
    print(f"\n20 random payload lines (seed 0) of {len(lines)}; full payload written to {out}:")
    for i in sorted(random.Random(0).sample(range(len(lines)), min(20, len(lines)))):
        print(lines[i])
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "preview":
        return preview(args)
    if args.cmd == "analyze":
        return analyze_cmd(args)
    chat = Path(args.chat)
    if not chat.is_file():
        print(f"gcw: chat file not found: {chat}", file=sys.stderr)
        return 2
    aliases = None
    if args.aliases:
        try:
            aliases = card.load_aliases(args.aliases)
        except (OSError, ValueError) as e:
            print(f"gcw: bad aliases file: {e}", file=sys.stderr)
            return 2
    df, report = parse_chat(chat, date_order=args.date_order)
    for w in report.warnings:
        print(f"gcw: warning: {w}", file=sys.stderr)
    if report.n_messages == 0:
        print("gcw: no messages could be parsed from this file", file=sys.stderr)
        return 3
    stats = compute_stats(df, since=args.since, until=args.until)
    note = f"Dates read as {'m/d' if report.date_order == 'mdy' else 'd/m'} (assumed)" if report.ambiguous else None
    html = card.build_card_html(stats, aliases, date_note=note)
    if args.html:
        Path(args.html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html).write_text(html, encoding="utf-8")
    card.render_png(html, args.out)
    print(f"gcw: wrote {args.out} ({card.WIDTH}x{card.HEIGHT}); {stats['window']['n_messages']} messages in the window; no API calls made")
    return 0


if __name__ == "__main__":
    sys.exit(main())
