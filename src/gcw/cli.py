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
    return ap


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
