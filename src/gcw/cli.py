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
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
