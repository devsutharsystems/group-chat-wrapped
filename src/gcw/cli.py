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
    an.add_argument("--config", choices=["A", "B", "C"], default="A", help="A: thinking disabled, effort low; B: effort low, thinking parameter omitted; C: effort medium, thinking parameter omitted")
    an.add_argument("--count", action="store_true", help="exact token count via the free count_tokens endpoint (SENDS the payload to Anthropic, generates nothing)")
    an.add_argument("--confirm", action="store_true", help="count, then make the paid call (without it no generation happens)")
    an.add_argument("--budget", type=float, default=0.15, help="phase budget in USD over ledger labels starting 3b: (default 0.15)")
    an.add_argument("--save-response", action="store_true", help="also save the raw model response and the verified report under out/runs/ (OFF by default; they hold pseudonymised quotes, delete them afterwards)")
    an.add_argument("--phase", default="3b", help="ledger label prefix for the phase budget (default 3b)")
    an.add_argument("--max-input-tokens", type=int, default=95_000, help="refuse a request with more input tokens than this (default 95000)")
    an.add_argument("--max-run-cost", type=float, help="refuse if the worst-case cost estimate of one run is above this many USD")
    an.add_argument("--require-frozen-dataset", action="store_true", help="verify_dataset() and the chat must be the frozen synthetic chat, checked first")
    an.add_argument("--expect-prompt-version", metavar="PREFIX..SUFFIX", help="abort unless PROMPT_VERSION starts with PREFIX and ends with SUFFIX (it is always printed)")
    an.add_argument("--truth", help="ground_truth.json of a synthetic chat: score found planted items")
    an.add_argument("--label", default="slice", help="label suffix for the ledger entry")
    an.add_argument("--date-order", choices=["mdy", "dmy"], help="override the inferred day/month order")
    cd = sub.add_parser("card", help="the shareable card; with --report also the AI Zone 2 (only reviewed/approved items render)")
    cd.add_argument("chat", help="WhatsApp export (.txt)")
    cd.add_argument("--aliases", help="aliases JSON (display names and nicknames)")
    cd.add_argument("--report", help="run log JSON of an analyze run made with --save-response (its .report.json holds the verified report)")
    grp = cd.add_mutually_exclusive_group()
    grp.add_argument("--review", help="review file (out/reviews/...): only items with status approved render")
    grp.add_argument("--auto-approve-synthetic", action="store_true", help="approve every item; allowed ONLY for the frozen synthetic chat; the footer says so")
    cd.add_argument("--until", help="last day to include, inclusive (YYYY-MM-DD); required with --report and must equal the run's slice end")
    cd.add_argument("--since", help="first day to include (YYYY-MM-DD)")
    cd.add_argument("--out", default="out/card.png", help="PNG path (default out/card.png)")
    cd.add_argument("--html", help="also write the card HTML here (debugging)")
    cd.add_argument("--date-order", choices=["mdy", "dmy"], help="override the inferred day/month order")
    for name, hlp in (("evaluate", "FREE: evaluate saved full-chat runs against ground_truth.json; writes counts and ids only (no chat text)"),
                      ("rating-pack", "FREE: a blind, seeded sample of verified items for hand-rating (out/rating/, gitignored)")):
        ev = sub.add_parser(name, help=hlp)
        ev.add_argument("chat", help="WhatsApp export (.txt) the runs were made on")
        ev.add_argument("--aliases", required=True, help="aliases JSON used for the runs")
        ev.add_argument("--truth", help="ground_truth.json of the synthetic chat" + ("" if name == "evaluate" else " (adds planted matches to the private key)"))
        ev.add_argument("--phase", required=True, help="phase label of the runs to read (for example 4a)")
        ev.add_argument("--config", default="A")
        ev.add_argument("--runs-dir", default="out/runs")
        if name == "evaluate":
            ev.add_argument("--out", default="docs/results/eval_full_A", help="output base path (.json and .md are written; counts and ids only)")
        else:
            ev.add_argument("--out", default="out/rating")
            ev.add_argument("--seed", type=int, default=4242)
            ev.add_argument("--size", type=int, default=40)
    rv = sub.add_parser("review", help="list, approve or reject the items of a saved run (the card renders approved items only)")
    rv.add_argument("report", help="run log JSON (its sibling .report.json holds the verified report)")
    rv.add_argument("--file", help="review file (default out/reviews/<run>.json)")
    rv.add_argument("--approve", nargs="*", default=[], metavar="ID")
    rv.add_argument("--reject", nargs="*", default=[], metavar="ID")
    rv.add_argument("--rank", nargs="*", default=[], metavar="ID=N", help="optional integer rank per item (lower shows first; default is the model's order)")
    return ap


def _saved_runs(args: argparse.Namespace):
    """([(name, log, raw report)], df, aliases, truth) for the evaluate / rating-pack commands, or an exit code."""
    import json

    from gcw import evaluate, privacy
    from gcw.parser import messages

    chat = Path(args.chat)
    if not chat.is_file():
        print(f"gcw: chat file not found: {chat}", file=sys.stderr)
        return 2
    try:
        aliases = privacy.load_aliases(args.aliases)
        truth = json.loads(Path(args.truth).read_text(encoding="utf-8"))["items"] if args.truth else None
    except (OSError, ValueError, KeyError) as e:
        print(f"gcw: {e}", file=sys.stderr)
        return 2
    files = evaluate.pick_runs(args.runs_dir, args.phase, args.config)
    if not files:
        print(f"gcw: no saved runs of phase {args.phase}, config {args.config} in {args.runs_dir} (runs need --save-response)", file=sys.stderr)
        return 3
    df, _ = parse_chat(chat)
    n_chat = int(messages(df).shape[0])
    runs = []
    for f in files:
        log, rep = evaluate.load_run(f)
        if log.get("messages") != n_chat:
            print(f"gcw: run {f.name} has {log.get('messages')} messages but this chat has {n_chat}", file=sys.stderr)
            return 3
        runs.append((f.stem, log, rep))
    return runs, df, aliases, truth


def evaluate_cmd(args: argparse.Namespace) -> int:
    from gcw import evaluate

    got = _saved_runs(args)
    if isinstance(got, int):
        return got
    runs, df, aliases, truth = got
    if truth is None:
        print("gcw: --truth is required for evaluate", file=sys.stderr)
        return 2
    res = evaluate.evaluate_runs(df, aliases, runs, truth)
    j, m = evaluate.write_results(res, args.out)
    print(f"gcw: evaluated {res['n_runs']} runs; wrote {j} and {m} (counts and ids only)")
    return 0


def rating_pack_cmd(args: argparse.Namespace) -> int:
    from gcw import evaluate

    got = _saved_runs(args)
    if isinstance(got, int):
        return got
    runs, df, aliases, truth = got
    pack = evaluate.build_rating_pack(df, aliases, runs, truth, seed=args.seed, total=args.size)
    paths = evaluate.write_rating_pack(pack, args.out)
    print(f"gcw: rating pack of {len(pack['items'])} items (pool {pack['key']['pool']}, drawn {pack['key']['drawn']}, seed {args.seed}); wrote {', '.join(str(p) for p in paths.values())}")
    print("gcw: key.json holds run origin and planted matches: do not open it before rating")
    return 0


def _report_of(run_json: str):
    """(log, verified report) of a saved run, or (None, message)."""
    import json

    lp = Path(run_json)
    rp = lp.with_suffix(".report.json")
    try:
        log = json.loads(lp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"cannot read run log {lp}: {e}"
    if not rp.is_file():
        return None, f"no saved report next to {lp} ({rp.name}): the run was made without --save-response"
    try:
        return log, json.loads(rp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"cannot read {rp}: {e}"


def review_cmd(args: argparse.Namespace) -> int:
    from gcw import review

    log, report = _report_of(args.report)
    if log is None:
        print(f"gcw: {report}", file=sys.stderr)
        return 3
    path = Path(args.file) if args.file else Path("out/reviews") / (Path(args.report).stem + ".json")
    try:
        rv = review.merge(review.load_review(path), report) if path.is_file() else review.new_review(report, Path(args.report).stem)
    except review.ReviewError as e:
        print(f"gcw: {e}", file=sys.stderr)
        return 2
    missing = review.set_status(rv, args.approve, "approved") + review.set_status(rv, args.reject, "rejected")
    if missing:
        print(f"gcw: unknown item ids: {', '.join(missing)}", file=sys.stderr)
        return 2
    for spec in args.rank:
        i, _, n = spec.partition("=")
        if not n.lstrip("-").isdigit():
            print(f"gcw: bad --rank {spec!r} (expected ID=INTEGER)", file=sys.stderr)
            return 2
        if not review.set_rank(rv, i, int(n)):
            print(f"gcw: unknown item ids: {i}", file=sys.stderr)
            return 2
    review.save_review(path, rv)
    for i, v in rv["items"].items():
        print(f"{i}  {v['status']:<8}  {v['type']:<13}  {('rank ' + str(v['rank'])) if 'rank' in v else '':<8}  {v['title']}")
    print(f"review file: {path}  {review.counts(report, rv)}")
    return 0


def card_cmd(args: argparse.Namespace) -> int:
    from gcw import dataset, display, review

    chat = Path(args.chat)
    if not chat.is_file():
        print(f"gcw: chat file not found: {chat}", file=sys.stderr)
        return 2
    if args.report and not args.until:
        print("gcw: --until is required with --report (stats and AI items must cover the same window)", file=sys.stderr)
        return 2
    if args.auto_approve_synthetic and not dataset.is_frozen_chat(chat):
        print("gcw: --auto-approve-synthetic is only allowed for the frozen synthetic chat (its SHA-256 and dataset must verify); use a review file instead", file=sys.stderr)
        return 2
    aliases_dict = None
    aliases_obj = None
    if args.aliases:
        try:
            from gcw import privacy

            aliases_obj = privacy.load_aliases(args.aliases)
            aliases_dict = aliases_obj.display_map()
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
    ai = None
    if args.report:
        from gcw import analyze
        from gcw.parser import messages

        log, rep = _report_of(args.report)
        if log is None:
            print(f"gcw: {rep}", file=sys.stderr)
            return 3
        if "error" in log:
            print(f"gcw: that run failed ({log['error']}); there is nothing to render", file=sys.stderr)
            return 3
        rec = log.get("slice")
        if rec is not None:
            if rec.get("end") != args.until or rec.get("start") != args.since:
                print(f"gcw: the run covers {rec} but the card covers {args.since or 'chat start'}..{args.until}: stats and AI must cover the same window", file=sys.stderr)
                return 3
        else:  # older logs have no slice field: derive the check from the recorded message count
            import pandas as pd

            n = int((messages(df)["ts"] < pd.Timestamp(args.until) + pd.Timedelta(days=1)).sum())
            if n != log.get("messages") or args.since:
                print(f"gcw: the run recorded {log.get('messages')} messages but chat start..{args.until} has {n}: stats and AI must cover the same window", file=sys.stderr)
                return 3
            print(f"gcw: warning: the run log has no slice field, so the slice end was derived from its message count ({n}); runs made with the current code record the slice", file=sys.stderr)
        try:
            prep = analyze.prepare(df, aliases_obj, slice_start=args.since, slice_end=args.until)
        except analyze.AnalysisError as e:
            print(f"gcw: {e}", file=sys.stderr)
            return 3
        rv = None
        if args.auto_approve_synthetic:
            rv = review.approve_all(rep, Path(args.report).stem)
        elif args.review:
            try:
                rv = review.load_review(args.review)
            except review.ReviewError as e:
                print(f"gcw: {e}", file=sys.stderr)
                return 2
        approved = review.apply(rep, rv)
        k = sum(len(approved[t]) for t in review.TYPES)
        display_map = aliases_dict or {}
        names = {tok: card.clean_name(display_map.get(export, export)) for tok, export in prep["mapping"].items()}
        stat = log.get("stats", {})
        zone = display.build_zone2(approved, prep["index"], names)
        ai = {"zone2": zone, "approved": k, "proposed": stat.get("items_in", 0), "verified": stat.get("items_kept", sum(len(rep.get(t) or []) for t in review.TYPES)),
              "synthetic": bool(args.auto_approve_synthetic)}
        print(f"gcw: AI items: proposed {ai['proposed']}, verified {ai['verified']}, approved {k}; dropped at display {zone['display_drops']}", file=sys.stderr)
        if rv is None:
            print("gcw: nothing is approved yet: run `python -m gcw review RUN_JSON --approve ID ...`, then pass --review FILE", file=sys.stderr)
    html = card.build_card_html(stats, aliases_dict, date_note=note, ai=ai)
    if args.html:
        Path(args.html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html).write_text(html, encoding="utf-8")
    card.render_png(html, args.out)
    print(f"gcw: wrote {args.out} ({card.WIDTH}x{card.HEIGHT}); {stats['window']['n_messages']} messages in the window; no API calls made")
    return 0


def analyze_cmd(args: argparse.Namespace) -> int:
    import json
    import random

    from gcw import analyze as az
    from gcw import cost, privacy
    chat = Path(args.chat)
    if not chat.is_file():
        print(f"gcw: chat file not found: {chat}", file=sys.stderr)
        return 2
    print(f"prompt version: {az.PROMPT_VERSION}")
    if args.expect_prompt_version:
        pre, _, suf = args.expect_prompt_version.partition("..")
        if not (az.PROMPT_VERSION.startswith(pre) and az.PROMPT_VERSION.endswith(suf)):
            print(f"gcw: PROMPT_VERSION {az.PROMPT_VERSION} does not match the expected {args.expect_prompt_version}: prompt v1 is frozen", file=sys.stderr)
            return 3
    if args.require_frozen_dataset:
        from gcw import dataset

        try:
            dataset.verify_dataset()
        except dataset.DatasetError as e:
            print(f"gcw: {e}", file=sys.stderr)
            return 3
        if not dataset.is_frozen_chat(chat):
            print("gcw: --require-frozen-dataset: the chat is not the frozen synthetic chat", file=sys.stderr)
            return 3
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
                              phase=args.phase, save_response=args.save_response, max_input_tokens=args.max_input_tokens, max_run_cost=args.max_run_cost)
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
    if args.cmd == "card":
        return card_cmd(args)
    if args.cmd == "evaluate":
        return evaluate_cmd(args)
    if args.cmd == "rating-pack":
        return rating_pack_cmd(args)
    if args.cmd == "review":
        return review_cmd(args)
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
