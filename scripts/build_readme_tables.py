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
BLOCKS = ("eval_table", "cost_block", "precision_block", "scale_limits", "versions")
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
    L = ["| row | n | input tokens per run | planted density | strict recall (found of in-scope item-runs) | rule-compliant rate | unplanted items per run (awards / moments / jokes) | cost per run (USD) | latency per run (s) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for label, name, chat, chunked in ROWS:
        r = _load(root, name)
        s, n = r["summary"], r["n_runs"]
        toks = sum(x["input_tokens"] for x in r["runs"]) / n
        d = dens["large_slice"] if r.get("slice_end") else dens[chat]
        found = sum(v["strict_found_item_runs"] for v in r["recall_by_type"].values())
        poss = sum(v["possible_item_runs"] for v in r["recall_by_type"].values())
        unp = " / ".join(f"{s['unplanted_items'][t]['mean']:.1f}" for t in ("awards", "moments", "running_jokes"))
        lat = f"{_rng(s['latency_s'])} (sum of call latencies)" if chunked else _rng(s["latency_s"])
        L.append(f"| {label} | {n} | {toks:,.0f}{' (sum over calls)' if chunked else ''} | {100 * d:.2f}% | {found} of {poss} | {_rng(s['rule_compliant_rate'], pct=True)} | {unp} | {_rng(s['cost_usd'], nd=4)} | {lat} |")
    return "\n".join(L)


def cost_block(root: Path) -> str:
    L = ["Cost is computed from the usage fields times list prices (a request above 100,000 prompt tokens is billed whole at the higher tier) and is not reconciled with the Console. "
         "Chunked wall-clock time is shorter than the sum of call latencies because map calls run in parallel.", "",
         "| row | cost per run (USD) | latency per run (s) | wall-clock per run (s, chunked only) |", "|---|---|---|---|"]
    for label, name, _, chunked in ROWS:
        s = _load(root, name)["summary"]
        wall = _rng(s["wall_clock_s"]) if chunked and "wall_clock_s" in s else "n/a"
        L.append(f"| {label} | {_rng(s['cost_usd'], nd=4)} | {_rng(s['latency_s'])} | {wall} |")
    m = json.loads((root / "docs" / "results" / "memory.json").read_text(encoding="utf-8"))
    L += ["", f"Memory and time of the card render paths ({m['note']})", "", "| render path | wall-clock (s) | largest process (MB) | summed over the process tree (MB) |", "|---|---|---|---|"]
    for p in m["render_paths"]:
        L.append(f"| {p['name']} | {p['wall_clock_s']} | {p['largest_process_bytes'] / 1e6:.0f} | {p['process_tree_mb']} |")
    h = m["screenshot_harness"]
    L += ["", f"Screenshot harness (a development tool, not part of the app's footprint; ceiling {h['ceiling_mb']} MB), peak summed RSS per step:", "", "| step | peak (MB) |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in h["peak_total_rss_mb_per_step"]]
    return "\n".join(L)


def precision_block(root: Path) -> str:
    p = root / "docs" / "results" / "precision_A.json"
    if not p.is_file():
        return PRECISION_LITERAL
    from gcw import evaluate

    r = json.loads(p.read_text(encoding="utf-8"))
    o = r["overall"]
    L = [f"Precision of the verified items from hand ratings ({o['n']} items; strict = rated true, lenient = true plus partly; Wilson 95% interval). {r['note']}", "",
         "| group | n | strict | lenient |", "|---|---|---|---|",
         f"| overall | {o['n']} | {evaluate._ci(o['strict'])} | {evaluate._ci(o['lenient'])} |"]
    L += [f"| {t} | {v['n']} | {evaluate._ci(v['strict'])} | {evaluate._ci(v['lenient'])} |" for t, v in r["by_type"].items()]
    return "\n".join(L)


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
    return {"eval_table": eval_table(root), "cost_block": cost_block(root), "precision_block": precision_block(root), "scale_limits": scale_limits(root), "versions": versions(root)}


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
