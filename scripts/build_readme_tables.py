"""Fill the generated blocks of README.md from docs/results/*.json (counts and measured logs only; nothing is typed by hand).

A block is  <!-- BEGIN:name --> ... <!-- END:name -->.  Blocks: eval_table, cost_block, precision_block, scale_limits, versions.
  .venv/bin/python scripts/build_readme_tables.py            # rewrite README.md
  .venv/bin/python scripts/build_readme_tables.py --check    # exit 1 when a block is stale
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PRECISION_LITERAL = "Precision: not yet measured (hand-rating pending)"
BLOCKS = ("brief", "eval_table", "hypothesis_note", "dropped_note", "cost_block", "precision_block", "scale_limits", "versions")
RATING_SEED = 4242  # the default of `gcw rating-pack --seed` (a test checks it)
RATING_CAP = 40  # the default of `gcw rating-pack --size` and of evaluate.build_rating_pack(total=...) (a test checks it)
ROWS = [  # (label, results file, chat key, chunked)
    ("dense 270K tokens, single-pass", "eval_full_A", "dense", False),
    ("dense 270K tokens, chunked", "eval_full_chunked", "dense", True),
    ("sparse chat, first third, single-pass", "eval_large_sparse_single", "large", False),
    ("sparse chat, 889K tokens, single-pass", "eval_large_A", "large", False),
    ("sparse chat, 889K tokens, chunked", "eval_large_chunked", "large", True),
]


def _load(root: Path, name: str) -> dict:
    return json.loads((root / "docs" / "results" / f"{name}.json").read_text(encoding="utf-8"))


def _rng(d: dict, pct: bool = False, nd: int = 1) -> str:
    f = (lambda x: f"{100 * x:.0f}%") if pct else (lambda x: f"{x:.{nd}f}")
    return f(d["mean"]) if d["n"] == 1 or d["min"] == d["max"] else f"{f(d['mean'])}, range {f(d['min'])} to {f(d['max'])}"


def _densities(root: Path) -> dict[str, float]:
    from gcw import evaluate
    from gcw.parser import parse_chat

    out = {}
    for key, chat, truth in (("dense", "synthetic/frozen/chat_synthetic.txt", "synthetic/frozen/ground_truth.json"),
                             ("large", "synthetic/frozen_large/chat_synthetic_large.txt", "synthetic/frozen_large/ground_truth.json")):
        df, _ = parse_chat(root / chat)
        items = json.loads((root / truth).read_text(encoding="utf-8"))["items"]
        out[key] = evaluate.planted_density(df, items)["fraction"]
        if key == "large":
            out["large_slice"] = evaluate.planted_density(df, items, slice_end="2026-03-07")["fraction"]
    return out


def eval_table(root: Path) -> str:
    dens = _densities(root)
    L = ["| row | n | input tokens per run | planted density | strict recall (found of in-scope item-runs) | rule-compliant rate | unplanted items per run (awards / moments / jokes) | cost per run (USD) | wall-clock per run (s) | sum of call latencies per run (s, chunked rows only) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for label, name, chat, chunked in ROWS:
        r = _load(root, name)
        s, n = r["summary"], r["n_runs"]
        toks = sum(x["input_tokens"] for x in r["runs"]) / n
        d = dens["large_slice"] if r.get("slice_end") else dens[chat]
        found = sum(v["strict_found_item_runs"] for v in r["recall_by_type"].values())
        poss = sum(v["possible_item_runs"] for v in r["recall_by_type"].values())
        unp = " / ".join(f"{s['unplanted_items'][t]['mean']:.1f}" for t in ("awards", "moments", "running_jokes"))
        wall = _rng(s["wall_clock_s"]) if chunked else _rng(s["latency_s"])  # single-pass: the one call's latency is the wall-clock time
        calls = _rng(s["latency_s"]) if chunked else "n/a"
        L.append(f"| {label} | {n} | {toks:,.0f}{' (sum over calls)' if chunked else ''} | {100 * d:.2f}% | {found} of {poss} | {_rng(s['rule_compliant_rate'], pct=True)} | {unp} | {_rng(s['cost_usd'], nd=4)} | {wall} | {calls} |")
    return "\n".join(L)


def cost_block(root: Path) -> str:
    L = ["Cost is computed from the usage fields times list prices (a request above 100,000 prompt tokens is billed whole at the higher tier) and is not reconciled with the Console. "
         "Wall-clock time of a single-pass run is its one call's latency; a chunked run's wall-clock time is shorter than the sum of its call latencies because the map calls run in parallel.", "",
         "| row | cost per run (USD) | wall-clock per run (s) | sum of call latencies per run (s, chunked rows only) |", "|---|---|---|---|"]
    for label, name, _, chunked in ROWS:
        s = _load(root, name)["summary"]
        wall = _rng(s["wall_clock_s"]) if chunked else _rng(s["latency_s"])
        calls = _rng(s["latency_s"]) if chunked else "n/a"
        L.append(f"| {label} | {_rng(s['cost_usd'], nd=4)} | {wall} | {calls} |")
    m = json.loads((root / "docs" / "results" / "memory.json").read_text(encoding="utf-8"))
    L += ["", f"Memory and time of the card render paths ({m['note']})", "", "| render path | wall-clock (s) | largest process (MB) | summed over the process tree (MB) | provenance |", "|---|---|---|---|---|"]
    for p in m["render_paths"]:
        pv = p["provenance"]
        L.append(f"| {p['name']} | {p['wall_clock_s']} | {p['largest_process_bytes'] / 1e6:.0f} | {p['process_tree_mb']} | phase {pv['phase']}, {pv['measured_on']}, {pv['run']}; copied from session output: {'yes' if pv['copied_from_session_output'] else 'no'} |")
    h = m["screenshot_harness"]
    L += ["", f"Screenshot harness (a development tool, not part of the app's footprint; ceiling {h['ceiling_mb']} MB), peak summed RSS per step; steps with several observed runs show every value and the range:", "",
          "| step | observed runs (MB) | min (MB) | max (MB) | provenance |", "|---|---|---|---|---|"]
    for st in h["steps"]:
        obs = ", ".join(f"{v:,}" for v in st["observed_mb"])
        phases = "; ".join(sorted({f"phase {x['phase']}" for x in st["provenance"]}))
        copied = "yes" if all(x["copied_from_session_output"] for x in st["provenance"]) else "no"
        L.append(f"| {st['step']} | {obs} | {st['min_mb']:,} | {st['max_mb']:,} | {phases}, {st['provenance'][0]['measured_on']}; copied from session output: {copied} |")
    return "\n".join(L)


def fmt_ci(d: dict) -> str:
    """'21 of 40, 52.5%, interval 37.5% to 67.1%' from a Wilson proportion dict."""
    if d["n"] == 0:
        return "n/a"
    return f"{d['k']} of {d['n']}, {100 * d['p']:.1f}%, interval {100 * d['lo']:.1f}% to {100 * d['hi']:.1f}%"


def rubric_lines(root: Path) -> list[str]:
    """The rating rubric, copied from docs/PRD.md (the bullets under 'Rating rubric', without the reporting line)."""
    text = (root / "docs" / "PRD.md").read_text(encoding="utf-8")
    tail = text.split("**Rating rubric", 1)[1].splitlines()[1:]
    out = []
    for ln in tail:
        if not ln.startswith("  - "):
            break
        if ln.strip().startswith("- Precision is reported"):
            continue
        out.append(ln.strip())
    return out


def cap_clause(root: Path, r: dict) -> str:
    """Why the sample is smaller than the pool: the rating pack is capped at RATING_CAP items (`rating-pack --size`), so the stratified draw left some verified items out. From the code
    (evaluate.TARGETS, allocate, build_rating_pack(total=40); cli --size default 40) and the counts in the results files; empty when nothing was left out."""
    pool: dict[str, int] = {}
    for run in _load(root, "eval_full_A")["runs"]:
        for t, n in run["items_kept"].items():
            pool[t] = pool.get(t, 0) + n
    left = {t: pool[t] - r["by_type"][t]["n"] for t in pool if t in r["by_type"] and pool[t] > r["by_type"][t]["n"]}
    if not left:
        return ""
    singular = {"running_jokes": "running joke", "moments": "moment", "awards": "award"}
    names = ", ".join(f"{k} {singular.get(t, t)}{'' if k == 1 else 's'}" for t, k in sorted(left.items()))
    return f" (the rating pack is capped at {RATING_CAP} items, `rating-pack --size`; the draw is stratified by type, and after the cap it left out {names})"


def precision_block(root: Path) -> str:
    p = root / "docs" / "results" / "precision_A.json"
    if not p.is_file():
        return PRECISION_LITERAL
    r = json.loads(p.read_text(encoding="utf-8"))
    o = r["overall"]
    verified = sum(sum(x["items_kept"].values()) for x in _load(root, "eval_full_A")["runs"])
    moments_partly = r["by_type"]["moments"]["partly"]
    L = ["Rubric (copied from `docs/PRD.md`; fixed before any rating):", "", *rubric_lines(root), "",
         "Standard applied: \"true\" when the shown quotes support the title and summary; \"partly\" when part of the claim or its detail is not shown.", "",
         f"Sample: {r['n_items']} of the {verified} verified items from the three runs{cap_clause(root, r)}, drawn with seed {RATING_SEED}, rated by the author in a single pass. The author designed the dataset, so the ratings are not blind. "
         f"Strict = rated true; lenient = true plus partly; Wilson 95% interval. {r['note']}", "",
         "| group | n | strict | lenient |", "|---|---|---|---|", f"| overall | {o['n']} | {fmt_ci(o['strict'])} | {fmt_ci(o['lenient'])} |"]
    L += [f"| {t} | {v['n']} | {fmt_ci(v['strict'])} | {fmt_ci(v['lenient'])} |" for t, v in sorted(r["by_type"].items())]
    L += [f"| run {i} | {v['n']} | {fmt_ci(v['strict'])} | {fmt_ci(v['lenient'])} |" for i, (_, v) in enumerate(sorted(r["by_run"].items()), 1)]
    L += [f"| {label} | {r[key]['n']} | {fmt_ci(r[key]['strict'])} | {fmt_ci(r[key]['lenient'])} |" for label, key in (("matching a planted item", "planted_matching"), ("unplanted", "unplanted"))]
    L += ["", "The unplanted rows mix item types because awards have no planted truth, so planted against unplanted is not a like-for-like comparison.", "",
          f"For the {moments_partly} moments rated partly, the author's reason was mostly that the summary added concrete details not present in the displayed messages; incomplete quotes were a secondary reason. "
          "No per-item notes were recorded, so this is the author's recollection, not a coded result."]
    return "\n".join(L)


def results_brief(root: Path) -> str:
    """At most six plain lines from the results files; no adjectives, no ranking."""
    dens = _densities(root)
    pr = json.loads((root / "docs" / "results" / "precision_A.json").read_text(encoding="utf-8")) if (root / "docs" / "results" / "precision_A.json").is_file() else None
    a, c = _load(root, "eval_full_A"), _load(root, "eval_full_chunked")
    big_s, big_c = _load(root, "eval_large_A"), _load(root, "eval_large_chunked")

    def recall(r: dict) -> str:
        return f"{sum(v['strict_found_item_runs'] for v in r['recall_by_type'].values())} of {sum(v['possible_item_runs'] for v in r['recall_by_type'].values())}"

    def short(d: dict) -> str:
        return f"{d['k']} of {d['n']} ({100 * d['p']:.1f}%)"

    lines = []
    if pr:
        bt = pr["by_type"]
        lines.append(f"- Hand-rated precision (n = {pr['overall']['n']}, rated by the author, not blind), strict / lenient: overall {short(pr['overall']['strict'])} / {short(pr['overall']['lenient'])}; "
                     + "; ".join(f"{t.replace('_', ' ')} {short(bt[t]['strict'])} / {short(bt[t]['lenient'])}" for t in ("running_jokes", "moments", "awards")) + ".")
    else:
        lines.append("- " + PRECISION_LITERAL)
    lines.append(f"- Strict recall of planted items on the dense chat (item-runs found, n = {a['n_runs']} runs each): single-pass {recall(a)}, chunked {recall(c)}.")
    lines.append(f"- Cost per run on the dense chat, computed from usage fields and not reconciled with the Console: single-pass ${a['summary']['cost_usd']['mean']:.4f}, chunked ${c['summary']['cost_usd']['mean']:.4f}.")
    lines.append(f"- Large chat at {int(sum(x['input_tokens'] for x in big_s['runs']) / big_s['n_runs']):,} tokens (n = {big_s['n_runs']} run each; planted density {100 * dens['large']:.2f}% against {100 * dens['dense']:.2f}% on the dense chat, so the comparison is confounded): "
                 f"single-pass found {recall(big_s)} planted items, chunked {recall(big_c)}.")
    return "\n".join(lines)


def hypothesis_note(root: Path) -> str:
    """One short note on the near-1M experiment against the hypothesis written in docs/PRD.md before any run. Numbers come from the two results files."""
    big_s, big_c = _load(root, "eval_large_A"), _load(root, "eval_large_chunked")
    dens = _densities(root)

    def found(r: dict) -> str:
        return f"{sum(v['strict_found_item_runs'] for v in r['recall_by_type'].values())} of {sum(v['possible_item_runs'] for v in r['recall_by_type'].values())}"

    return (f"The hypothesis written in `docs/PRD.md` before any run (single-pass wins recall on long-range jokes) was not supported in the near-1M-token setup: single-pass found {found(big_s)} planted items "
            f"(`docs/results/eval_large_A.json`) and chunked found {found(big_c)} (`docs/results/eval_large_chunked.json`), one run each (n = {big_s['n_runs']}). Both runs read the same chat, whose planted density "
            f"({100 * dens['large']:.2f}%) is lower than the dense chat's ({100 * dens['dense']:.2f}%), and the density is a confound for any comparison with the dense-chat results "
            "(`docs/results/compare_large.md`). This shows that the hypothesis failed in this setup; it is not a general claim about single-pass against chunked.")


def dropped_note(root: Path) -> str:
    a = _load(root, "eval_full_A")
    counts: dict[str, int] = {}
    for run in a["runs"]:
        for k, v in run["status_counts"].items():
            counts[k] = counts.get(k, 0) + v
    dropped = {k: v for k, v in counts.items() if k != "verified"}
    base = ("Rule-compliant rate: the share of evidence items that pass verification (the message id exists, the quote has at least 12 characters, and it is an exact substring of the cited message). "
            f"In the {a['n_runs']} dense single-pass runs (`docs/results/eval_full_A.json`) {sum(dropped.values())} evidence items were dropped. ")
    if set(dropped) == {"other_message"}:
        return (base + "All of them have the status other_message, none is not_found or any other status: the quote was not in the cited message but was found in another message (defined in `src/gcw/evaluate.py`), "
                "so none was invented. The results file records the status counts only; it does not record whether each match was exact after normalisation or needed the classifier's second pass "
                "(a stronger fold of case and punctuation), so these quotes are not claimed to be verbatim.")
    return base + "Their statuses are: " + ", ".join(f"{k} {v}" for k, v in sorted(dropped.items())) + " (`docs/results/eval_full_A.json`)."


def scale_limits(root: Path) -> str:
    def found(name: str) -> tuple[int, int, int, int]:
        r = _load(root, name)
        return (sum(v["strict_found_item_runs"] for v in r["recall_by_type"].values()), sum(v["possible_item_runs"] for v in r["recall_by_type"].values()), r["n_runs"],
                int(sum(x["input_tokens"] for x in r["runs"]) / r["n_runs"]))
    sf, sp, sn, st = found("eval_large_A")
    cf, cp, cn, _ = found("eval_large_chunked")
    df_, dp, dn, dt = found("eval_full_A")
    lf, lp, ln, lt = found("eval_large_sparse_single")
    return "\n".join([
        f"- Single-pass on the sparse chat at {st:,} tokens found {sf} of {sp} planted items (n = {sn}); chunked on the same chat found {cf} of {cp} (n = {cn}). The context window accepts the request; quality at that size was not demonstrated.",
        f"- Single-pass at {dt:,} tokens on the dense chat found {df_} of {dp} planted item-runs (n = {dn}); on the first third of the sparse chat ({lt:,} tokens) it found {lf} of {lp} (n = {ln}). These sizes were tested on development items that were seen during development.",
    ])


def versions(root: Path) -> str:
    from gcw import analyze, chunked, dataset

    f = dataset.sha256_file
    rows = [("PROMPT_VERSION (v1 system prompt and schema)", analyze.PROMPT_VERSION), ("REDUCE_PROMPT_VERSION", chunked.REDUCE_PROMPT_VERSION),
            ("synthetic/frozen/chat_synthetic.txt", f(root / "synthetic/frozen/chat_synthetic.txt")), ("synthetic/frozen/ground_truth.json", f(root / "synthetic/frozen/ground_truth.json")),
            ("synthetic/frozen_large/chat_synthetic_large.txt", f(root / "synthetic/frozen_large/chat_synthetic_large.txt")),
            ("synthetic/frozen_large/ground_truth.json", f(root / "synthetic/frozen_large/ground_truth.json"))]
    return "\n".join(["| identifier | SHA-256 |", "|---|---|", *[f"| `{k}` | `{v}` |" for k, v in rows]])


def render_blocks(root: Path = ROOT) -> dict[str, str]:
    return {"brief": results_brief(root), "eval_table": eval_table(root), "hypothesis_note": hypothesis_note(root), "dropped_note": dropped_note(root), "cost_block": cost_block(root), "precision_block": precision_block(root),
            "scale_limits": scale_limits(root), "versions": versions(root)}


def fill(text: str, blocks: dict[str, str]) -> str:
    for name, body in blocks.items():
        pat = re.compile(rf"(<!-- BEGIN:{name} -->\n).*?(\n<!-- END:{name} -->)", re.S)
        if not pat.search(text):
            raise ValueError(f"README.md has no block {name}")
        text = pat.sub(lambda m: m.group(1) + body + m.group(2), text, count=1)
    return text


def stale(root: Path = ROOT) -> list[str]:
    """Names of the blocks whose README text differs from a fresh render (or are missing)."""
    text = (root / "README.md").read_text(encoding="utf-8")
    out = []
    for name, body in render_blocks(root).items():
        m = re.search(rf"<!-- BEGIN:{name} -->\n(.*?)\n<!-- END:{name} -->", text, re.S)
        if not m or m.group(1) != body:
            out.append(name)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.check:
        s = stale(root)
        print("README blocks fresh" if not s else "README blocks stale: " + ", ".join(s))
        return 1 if s else 0
    p = root / "README.md"
    p.write_text(fill(p.read_text(encoding="utf-8"), render_blocks(root)), encoding="utf-8")
    print("README blocks written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
