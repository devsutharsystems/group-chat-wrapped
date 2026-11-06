"""Stats-only shareable card: self-contained HTML (inline CSS, no external anything) rendered to a 1080x1350 PNG.

Zone 1 "By the numbers" is counted locally. Zone 2 "From the chat" is reserved for the AI sections and shows an
"off" state in stats-only mode. Everything that comes from the chat (names, emoji) is HTML-escaped.

Resource rules (this Mac is shared): one browser, one page, --disable-gpu, device scale factor 1, closed after use,
and ALL network requests are blocked (context offline + route abort). Run renders under `nice -n 10`.
This module must never import anthropic.
"""
from __future__ import annotations

import html as _html
import json
import os
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache" / "ms-playwright"))

WIDTH, HEIGHT = 1080, 1350
MIN_RESPONSE_SAMPLES = 20
MIN_RESPONSE_GAP_S = 120  # first place must beat second by this much: minute resolution makes a 50 s reply read 0 s and a 10 s reply read 60 s
MAX_NAME_CHARS = 30
TOP_N = 5
CHROMIUM_ARGS = ["--disable-gpu"]
FOOTER = "Counted locally. No AI used."
ZONE2_OFF = "AI sections off (stats-only mode)"

# bidi controls and C0/C1 controls are removed from names; ZWJ and variation selectors are kept (emoji in names)
_BIDI = {0x061C, 0x200E, 0x200F, 0x2028, 0x2029, *range(0x202A, 0x202F), *range(0x2066, 0x206A)}


# ------------------------------------------------------------------ small helpers (pure)
def esc(x: Any) -> str:
    return _html.escape(str(x), quote=True)


def clean_name(name: Any, limit: int = MAX_NAME_CHARS) -> str:
    s = "".join(c for c in str(name) if ord(c) not in _BIDI and unicodedata.category(c) != "Cc")
    s = " ".join(s.split()) or "?"
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def fmt_int(n: int) -> str:
    return f"{int(n):,}"


def fmt_duration(hours: float) -> str:
    """Days, hours, minutes from a number of hours, e.g. 357.9333 -> '14d 21h 56m'."""
    mins = round(hours * 60)
    d, rem = divmod(mins, 1440)
    h, m = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def fmt_response(seconds: float) -> str:
    """Timestamps have minute resolution, so anything under a minute is shown as such."""
    if seconds < 60:
        return "under 1 min"
    return f"{seconds / 60:g} min"


def load_aliases(path: str | Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError("aliases file must be a JSON object mapping export names to display names (strings)")
    return data


def fastest_responder(stats: dict, min_samples: int = MIN_RESPONSE_SAMPLES, min_gap: float = MIN_RESPONSE_GAP_S) -> dict | None:
    """Lowest median response time among senders with at least `min_samples` replies (ties go to the earlier name).
    None when nobody qualifies or when second place is less than `min_gap` seconds behind (too close to call at minute resolution)."""
    cands = sorted((v["median_seconds"], s, v["n"]) for s, v in stats["response_time"].items() if v["n"] >= min_samples and v["median_seconds"] is not None)
    if not cands or (len(cands) > 1 and cands[1][0] - cands[0][0] < min_gap):
        return None
    med, sender, n = cands[0]
    return {"sender": sender, "median_seconds": med, "n": n}


def busiest_weekday_hour(stats: dict) -> tuple[str, int] | None:
    b = stats["busiest"]
    wd, hr = b["weekday"]["overall"], b["hour"]["overall"]
    return None if wd is None or hr is None else (wd, hr)


def top_starter(stats: dict) -> dict | None:
    st = stats["starters"]
    if not st or max(st.values()) == 0:
        return None
    best = max(st.values())
    tied = sorted(s for s, v in st.items() if v == best)
    return {"sender": tied[0], "count": best, "tied_with": tied[1:]}


# ------------------------------------------------------------------ HTML
ZONE2_HEIGHT = 460  # reserved block at the bottom: identical in stats-only and AI modes
CSS = """
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:#fbf7ef}
.card{width:1080px;height:1350px;padding:32px 48px 28px;display:flex;flex-direction:column;gap:12px;overflow:hidden;background:#fbf7ef;color:#1d1b17;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,"Apple Color Emoji","Segoe UI Emoji",sans-serif}
.card *{min-width:0}
.name{overflow-wrap:anywhere;unicode-bidi:isolate}
header{height:84px;flex:none}
h1{margin:0;font-size:44px;line-height:50px;letter-spacing:-0.5px}
.sub{margin:2px 0 0;font-size:24px;line-height:30px;color:#6b6254}
.zone{display:flex;align-items:center;gap:14px;height:24px;flex:none;font-size:19px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6b6254}
.zone::after{content:"";flex:1;height:2px;background:#e6dccb}
.board{height:262px;flex:none;background:#fff;border:2px solid #e6dccb;border-radius:18px;padding:6px 18px;display:flex;flex-direction:column}
.row{display:flex;align-items:center;gap:12px;height:36px;flex:none;font-size:24px;line-height:28px}
.row.head{height:28px;font-size:17px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#6b6254}
.row .rk{width:30px;flex:none;text-align:center;color:#6b6254;font-weight:700}
.row .nm{flex:1;font-weight:700;position:relative;padding-bottom:6px}
.row.head .nm{padding-bottom:0}
.row .nm.m{font-size:20px}
.row .nm.xs{font-size:17px}
.row .nm .bar{position:absolute;left:0;bottom:0;height:5px;border-radius:3px;background:#f3b58f}
.row .num{width:158px;flex:none;text-align:right;font-variant-numeric:tabular-nums;padding:0 8px;border-radius:8px}
.row .num.lead{color:#c2410c;font-weight:800;background:#fde6d6}
.row.more{height:28px;font-size:20px;color:#6b6254}
.grid{display:grid;grid-template-columns:repeat(3,1fr);grid-auto-rows:124px;gap:12px;flex:none}
.tile{background:#fff;border:2px solid #e6dccb;border-radius:18px;padding:10px 16px;display:flex;flex-direction:column;gap:2px;overflow:hidden}
.lab{font-size:18px;line-height:22px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#6b6254;flex:none}
.lab.s{font-size:15px;letter-spacing:0.5px}
.val{font-size:34px;line-height:40px;font-weight:800;color:#c2410c;flex:none}
.val.m{font-size:28px;line-height:33px}
.val.s{font-size:22px;line-height:26px}
.val.xs{font-size:18px;line-height:22px}
.note{font-size:21px;line-height:25px;color:#4a4338;flex:none}
.strip{height:74px;flex:none;display:flex;background:#fff;border:2px solid #e6dccb;border-radius:18px}
.strip .cell{flex:1;padding:6px 14px;border-left:2px solid #efe6d6;display:flex;flex-direction:column;justify-content:center;overflow:hidden}
.strip .cell:first-child{border-left:0}
.strip .sv{font-size:28px;line-height:32px;font-weight:800;color:#c2410c}
.strip .sl{font-size:20px;color:#4a4338}
.strip .ss{font-size:17px;line-height:20px;color:#6b6254}
.zone2block{height:460px;flex:none;display:flex;flex-direction:column;gap:12px}
.zone2{flex:1;border:3px dashed #c9bda8;border-radius:18px;display:flex;align-items:center;justify-content:center;font-size:25px;color:#6b6254}
footer{height:34px;flex:none;text-align:center;font-size:22px;line-height:26px;color:#6b6254}
footer .small{font-size:17px}
"""


def _vc(text: str) -> str:
    """Font step for tile values by length, so the longest allowed name (30 chars, even all wide capitals) fits."""
    n = len(text)
    return "" if n <= 11 else "m" if n <= 17 else "s" if n <= 24 else "xs"


def _nc(text: str) -> str:
    n = len(text)
    return "" if n <= 18 else "m" if n <= 24 else "xs"


def _tile(label: str, value: str, note: str = "") -> str:
    note_html = f'<div class="note name">{esc(note)}</div>' if note else ""
    return f'<div class="tile"><div class="lab{" s" if len(label) > 17 else ""}">{esc(label)}</div><div class="val name {_vc(value)}">{esc(value)}</div>{note_html}</div>'


def _cell(value: str, label: str, sub: str = "") -> str:
    sub_html = f'<div class="ss">{esc(sub)}</div>' if sub else ""
    return f'<div class="cell"><div><span class="sv">{esc(value)}</span> <span class="sl">{esc(label)}</span></div>{sub_html}</div>'


def build_card_html(stats: dict, aliases: dict[str, str] | None = None, *, date_note: str | None = None) -> str:
    """Pure function: stats dict -> complete HTML document string (no I/O, no network)."""
    aliases = aliases or {}

    def disp(sender: str) -> str:
        return clean_name(aliases.get(sender, sender))

    w = stats["window"]
    n = w["n_messages"]
    sub = f'{esc(w["first_ts"][:10])} to {esc(w["last_ts"][:10])} · {esc(fmt_int(n))} messages' if n else "No messages in this window"
    by_msg, by_words = stats["top_talkers"]["by_messages"], stats["top_talkers"]["by_words"]
    words = {t["sender"]: t["words"] for t in by_words}

    # top-talkers table: the leader of each column is highlighted, so two different winners stay visible
    lead_msg = by_msg[0]["sender"] if by_msg else None
    lead_words = by_words[0]["sender"] if by_words else None
    rows = ['<div class="row head"><span class="rk">#</span><span class="nm">Top talkers</span><span class="num">messages</span><span class="num">words</span></div>']
    top = by_msg[:TOP_N]
    most = top[0]["messages"] if top else 1
    for i, t in enumerate(top, 1):
        s_ = t["sender"]
        pct = max(2, round(100 * t["messages"] / most)) if most else 0
        rows.append(f'<div class="row"><span class="rk">{i}</span><span class="nm name {_nc(disp(s_))}">{esc(disp(s_))}<span class="bar" style="width:{pct}%"></span></span>'
                    f'<span class="num{" lead" if s_ == lead_msg else ""}">{esc(fmt_int(t["messages"]))}</span>'
                    f'<span class="num{" lead" if s_ == lead_words else ""}">{esc(fmt_int(words.get(s_, 0)))}</span></div>')
    if not top:
        rows.append('<div class="row more">No messages in this window</div>')
    hidden = len(by_msg) - TOP_N
    if hidden > 0:
        extra = ""
        if lead_words not in {t["sender"] for t in top}:  # the words leader is not in the top 5 by messages: say so here
            extra = f' · most words: {clean_name(aliases.get(lead_words, lead_words), 18)} {fmt_int(words[lead_words])}'
        rows.append(f'<div class="row more">+{hidden} more{esc(extra)}</div>')
    board = f'<div class="board">{"".join(rows)}</div>'

    # six tiles, two rows of three
    ne = stats["night_early"]
    owl, bird = ne["night_owl"], ne["early_bird"]
    sil, bd, em = stats["longest_silence"], stats["busiest_date"], stats["emojis"]
    st, fr = top_starter(stats), fastest_responder(stats)
    tiles = []
    tiles.append(_tile("Night owl", disp(owl), f'{round(100 * ne["per_sender"][owl]["night_share"])}% sent 22:00-03:59') if owl else _tile("Night owl", "n/a (needs 30+ messages)"))
    tiles.append(_tile("Early bird", disp(bird), f'{round(100 * ne["per_sender"][bird]["early_share"])}% sent 04:00-08:59') if bird else _tile("Early bird", "n/a (needs 30+ messages)"))
    tiles.append(_tile("Longest silence", fmt_duration(sil["hours"]), f'{sil["start"][:10]} to {sil["end"][:10]}') if sil else _tile("Longest silence", "n/a"))
    tiles.append(_tile("Busiest day", bd["date"], f'{fmt_int(bd["messages"])} messages that day') if bd else _tile("Busiest day", "n/a"))
    if st:
        tie = ""
        if st["tied_with"]:
            tie = f', tied with {clean_name(aliases.get(st["tied_with"][0], st["tied_with"][0]), 14)}' + (f' +{len(st["tied_with"]) - 1}' if len(st["tied_with"]) > 1 else "")
        tiles.append(_tile("Top starter", disp(st["sender"]), f'{st["count"]} starts{tie}'))
    else:
        tiles.append(_tile("Top starter", "n/a"))
    bwh = busiest_weekday_hour(stats)
    if fr:  # only when first place is at least 120 s ahead of second
        tiles.append(_tile("Fastest responder", disp(fr["sender"]), f'{fmt_int(fr["n"])} replies · {fmt_response(fr["median_seconds"])}'))
    elif bwh:
        tiles.append(_tile("Busiest weekday and hour", f"{bwh[0][:3]} {bwh[1]:02d}:00", f"{bwh[0]}, {bwh[1]:02d}:00-{bwh[1]:02d}:59"))
    else:
        tiles.append(_tile("Busiest weekday and hour", "n/a"))

    # one stat strip: emoji, laughs, media, links
    top_e = em["top"][0] if em["top"] else None
    strip = "".join([
        _cell(fmt_int(em["total"]), "emoji", f'top: {top_e["emoji"]} ×{fmt_int(top_e["count"])}' if top_e else "none yet"),
        _cell(fmt_int(stats["laughs"]["total"]), "laughs"),
        _cell(fmt_int(stats["media"]["total"]), "media"),
        _cell(fmt_int(stats["links"]["total"]), "links"),
    ])

    foot2 = f' <span class="small">· {esc(date_note)}</span>' if date_note else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src data:\">"
        f"<title>Group Chat Wrapped</title><style>{CSS}</style></head><body>"
        f'<div class="card"><header><h1>Group Chat Wrapped</h1><div class="sub">{sub}</div></header>'
        f'<div class="zone">By the numbers</div>{board}<div class="grid">{"".join(tiles)}</div><div class="strip">{strip}</div>'
        f'<div class="zone2block"><div class="zone">From the chat</div><div class="zone2">{esc(ZONE2_OFF)}</div></div>'
        f"<footer>{esc(FOOTER)}{foot2}</footer></div></body></html>"
    )


# ------------------------------------------------------------------ rendering
@contextmanager
def chromium() -> Iterator[Any]:
    """One Chromium for the caller's lifetime (--disable-gpu). Always closed."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = None
    try:
        browser = pw.chromium.launch(args=CHROMIUM_ARGS)
        yield browser
    finally:
        if browser is not None:
            browser.close()
        pw.stop()


_MEASURE_JS = """() => {
  const card = document.querySelector('.card');
  const c = card ? card.getBoundingClientRect() : {left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0};
  const bad = [];
  const els = card ? [card, ...card.querySelectorAll('*')] : [];
  for (const el of els) {
    const d = getComputedStyle(el).display;
    if (d === 'none' || d === 'inline') continue;
    const tag = el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ').join('.') : '');
    if (el.scrollWidth > el.clientWidth + 1) bad.push({tag, kind: 'scrollWidth', a: el.scrollWidth, b: el.clientWidth});
    if (el.scrollHeight > el.clientHeight + 1) bad.push({tag, kind: 'scrollHeight', a: el.scrollHeight, b: el.clientHeight});
    const r = el.getBoundingClientRect();
    if (r.width > 0 && (r.left < c.left - 0.5 || r.right > c.right + 0.5 || r.top < c.top - 0.5 || r.bottom > c.bottom + 0.5)) bad.push({tag, kind: 'outside', a: Math.round(r.bottom), b: Math.round(c.bottom)});
  }
  const de = document.documentElement;
  const z2 = document.querySelector('.zone2block');
  const zr = z2 ? z2.getBoundingClientRect() : {width: 0, height: 0};
  return {bad, root: [de.scrollWidth, de.clientWidth, de.scrollHeight, de.clientHeight], card: [Math.round(c.width), Math.round(c.height)], zone2: [zr.width, zr.height]};
}"""


def render_png(html_text: str, out_path: str | Path | None = None, *, browser: Any = None, measure: bool = False, request_log: list | None = None, probe: str | None = None) -> dict:
    """Render HTML to a 1080x1350 PNG. Blocks ALL network requests. Returns {'png': bytes, 'overflow': ...}.

    browser: reuse an open Chromium (tests share one); otherwise a single one is started and closed here.
    measure: enable JS for the page and measure overflow (scroll sizes, boxes outside the card).
    request_log: list that receives ('request'|'aborted'|'failed'|'response', url) tuples, to prove nothing got through.
    probe: JavaScript expression evaluated after load (needs measure=True); its value is returned as result['probe'].
    """
    def _do(b: Any) -> dict:
        ctx = b.new_context(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1, offline=True, java_script_enabled=measure)
        page = ctx.new_page()
        try:
            if request_log is not None:
                page.on("request", lambda r: request_log.append(("request", r.url)))
                page.on("requestfailed", lambda r: (request_log.append(("failed", r.url)), request_log.append(("reason", f"{r.url} {r.failure}"))))
                page.on("response", lambda r: request_log.append(("response", r.url)))
            def _block(route: Any) -> None:
                if request_log is not None:
                    request_log.append(("aborted", route.request.url))
                route.abort()

            page.route("**/*", _block)
            page.set_content(html_text, wait_until="load")
            result: dict = {}
            if measure:
                result["overflow"] = page.evaluate(_MEASURE_JS)
            if probe is not None:
                result["probe"] = page.evaluate(probe)
            result["png"] = page.screenshot(type="png", clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT})
            return result
        finally:
            page.close()
            ctx.close()

    if browser is not None:
        res = _do(browser)
    else:
        with chromium() as b:
            res = _do(b)
    if out_path is not None:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(res["png"])
    return res
