"""Build the static demo site into site/ (committed; there is no build step in CI).

  .venv/bin/python scripts/build_site.py [--repo-url URL] [--render]

index.html shows the two cards in site/img/ (the stats card and the AI demo card, both from the synthetic frozen chat); methodology.html is generated from the
README's generated blocks and its Limits list (so it carries the same numbers). No JavaScript, no external fonts, images or scripts, no analytics; every string is escaped
with html.escape. --render re-renders the two PNGs with the CLI (one Chromium at a time, nice -n 10, --disable-gpu) from the synthetic frozen chat and the saved config A
run (out/runs, gitignored; needs that file). The repository link is only written when --repo-url is given.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
MAX_SITE_BYTES = 5 * 1024 * 1024
RUN = "out/runs/20261106T202238-A"
CSS = ("body{font:16px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif;margin:0 auto;max-width:860px;padding:24px 16px;color:#1d1b17;background:#faf6ee}"
       "img{max-width:100%;height:auto;border-radius:8px}table{border-collapse:collapse;display:block;overflow-x:auto;font-size:14px}"
       "td,th{border:1px solid #cfc6b4;padding:4px 8px;text-align:left;vertical-align:top}code{font-size:13px;word-break:break-all}figure{margin:24px 0}"
       "figcaption{font-size:14px;color:#5b5548}a{color:#a33a10}@media (prefers-color-scheme:dark){body{color:#eee8dc;background:#1b1914}td,th{border-color:#4a4436}figcaption{color:#b9b09c}a{color:#f0a070}}")


def e(s: str) -> str:
    return html.escape(s, quote=True)


def inline(s: str) -> str:
    """Escape, then turn `code` into <code> (the only markup kept)."""
    return re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", e(s))


def block(readme: str, name: str) -> str:
    m = re.search(rf"<!-- BEGIN:{name} -->\n(.*?)\n<!-- END:{name} -->", readme, re.S)
    if not m:
        raise ValueError(f"README.md has no block {name}")
    return m.group(1)


def md_to_html(md: str) -> str:
    """Tables, bullet lists and paragraphs of the generated blocks; everything escaped."""
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[2:]]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table>")
            continue
        if ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:])
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue
        if ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "\n".join(out)


def page(title: str, body: str) -> str:
    return (f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{e(title)}</title><style>{CSS}</style></head><body>\n{body}\n</body></html>\n")


def repo_line(repo_url: str) -> str:
    return f"<p>Source: <a href=\"{e(repo_url)}\">{e(repo_url)}</a></p>" if repo_url else "<p>Source repository: the link is added when the repository is published.</p>"


def index_html(repo_url: str) -> str:
    body = f"""<h1>Group Chat Wrapped</h1>
<p>A card for a WhatsApp group chat: counted statistics, and optionally running jokes, moments and awards found by a language model, each backed by a quote that code has checked against the real message. Both cards below come from the bundled synthetic chat; no real chat is shown here.</p>
<figure><img src="img/stats_card.png" alt="Stats-only card for the synthetic chat: top talkers, busiest day, longest silence, emoji and laugh counts" width="540" height="675">
<figcaption>Stats-only card (no AI, no network call), synthetic frozen chat.</figcaption></figure>
<figure><img src="img/ai_card.png" alt="Card for the synthetic chat with the AI zone filled: a running joke, a moment and two awards" width="540" height="675">
<figcaption>Card with AI items, synthetic chat. The AI items come from a saved config A run; all items were auto-approved for this demo (auto-approved demo). The run is one I judged to be the same as the earlier demo card, based on its visible fields; the card's source data was not saved.</figcaption></figure>
<p>Pseudonymised text is sent to Anthropic in AI mode; stats-only mode sends nothing. See <a href="methodology.html">the methodology page</a> for the measured results, their sample sizes and the limits.</p>
{repo_line(repo_url)}"""
    return page("Group Chat Wrapped", body)


def methodology_html(readme: str, repo_url: str) -> str:
    limits = readme.split("## Limits", 1)[1].split("\n## ", 1)[0]
    limits = re.sub(r"<!-- (BEGIN|END):\w+ -->\n?", "", limits)
    for name in ("scale_limits",):
        limits = limits.replace(f"<!-- BEGIN:{name} -->", "")
    body = f"""<h1>Methodology and measured results</h1>
<p><a href="index.html">Back to the demo</a>. Everything below is generated from the repository's results files; the numbers are measurements on synthetic chats with planted ground truth, not claims about real chats.</p>
<h2>Results in brief</h2>
{md_to_html(block(readme, "brief"))}
<h2>Evaluation</h2>
{md_to_html(block(readme, "eval_table"))}
{md_to_html(block(readme, "hypothesis_note"))}
{md_to_html(block(readme, "dropped_note"))}
<p>Rows with n = 1 are single observations. The large-chat rows have a lower planted density than the dense chat, so the rows are not a controlled comparison.</p>
<h2>Cost, latency and memory</h2>
{md_to_html(block(readme, "cost_block"))}
<h2>Precision</h2>
{md_to_html(block(readme, "precision_block"))}
<h2>Frozen identifiers</h2>
{md_to_html(block(readme, "versions"))}
<h2>Limits</h2>
{md_to_html(limits)}
{repo_line(repo_url)}"""
    return page("Methodology and measured results", body)


def render_cards() -> None:
    """Re-render the two cards with the CLI, one Chromium at a time, under nice, with --disable-gpu (the card renderer's default)."""
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".cache" / "ms-playwright"))
    (SITE / "img").mkdir(parents=True, exist_ok=True)
    chat = "synthetic/frozen/chat_synthetic.txt"
    for cmd in ([sys.executable, "-m", "gcw", "stats-card", chat, "--out", "site/img/stats_card.png"],
                [sys.executable, "-m", "gcw", "card", chat, "--aliases", "aliases.example.json", "--report", RUN + ".json", "--auto-approve-synthetic", "--until", "2026-02-08",
                 "--out", "site/img/ai_card.png"]):
        subprocess.run(["nice", "-n", "10", *cmd], check=True, cwd=ROOT, env=env)


def build(root: Path = ROOT, repo_url: str = "") -> dict[str, str]:
    readme = (root / "README.md").read_text(encoding="utf-8")
    return {"index.html": index_html(repo_url), "methodology.html": methodology_html(readme, repo_url)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-url", default="")
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args(argv)
    if a.render:
        render_cards()
    SITE.mkdir(exist_ok=True)
    for name, text in build(ROOT, a.repo_url).items():
        (SITE / name).write_text(text, encoding="utf-8")
    total = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file())
    print(f"site/ written: {total:,} bytes")
    if total > MAX_SITE_BYTES:
        print("site/ is over 5 MB", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
