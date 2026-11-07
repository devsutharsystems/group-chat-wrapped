"""The blind rating tool: ONE self-contained HTML file (no network, CSP, no framework, no external anything).

Item text is rendered here, on the server side, with html.escape; the page's script only shows or hides sections, tracks ratings and notes, saves
them to localStorage (inside try/catch: it may be unavailable and the page must still work) and writes or reads ratings.csv. The script receives
only the item ids and types (as JSON with '<' escaped). It never receives, and the page never shows, a run name, a planted match or any other key information.
"""
from __future__ import annotations

import html as _html
import json

RUBRIC = [
    ("JOKE true", "the evidence shows a recurring bit or phrase said with joking intent on at least 2 dates."),
    ("MOMENT true", "the cited messages show one notable event that the title describes."),
    ("AWARD true", "the evidence supports the award for that member."),
    ("PARTLY", "the evidence supports only part of the title or summary, or the joking intent is weak."),
    ("FALSE", "the evidence does not support the claim."),
    ("TIC", "a verbal tic or stock phrase, not a joke (jokes only)."),
]
RUBRIC_NOTE = "Rate from the evidence shown, not from guesses about the chat."
RATINGS = ("true", "partly", "false", "tic")
CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"

CSS = """
body{font:16px/1.4 -apple-system,Helvetica,Arial,sans-serif;max-width:940px;margin:0 auto;padding:0 16px 80px;color:#1d1b17;background:#fbf7ef}
#bar{position:sticky;top:0;background:#fbf7ef;border-bottom:1px solid #d9cfbd;padding:8px 0;z-index:5}
#bar .row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
button,label.btn{font:inherit;padding:6px 12px;border:1px solid #bdb19c;border-radius:8px;background:#fff;cursor:pointer}
button:disabled{opacity:.4;cursor:default}
#progress{font-weight:700;margin-right:8px}
#nav{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
#nav button{min-width:36px;padding:3px 6px;font-size:13px}
#nav button.cur{outline:3px solid #1d1b17}
.s-none{background:#fff}.s-true{background:#bfe5b9}.s-partly{background:#f6e3a1}.s-false{background:#f2b8b0}.s-tic{background:#d4c4ee}
details{margin:10px 0;border:1px solid #d9cfbd;border-radius:8px;padding:6px 12px;background:#fff}
summary{font-weight:700;cursor:pointer}
.item{border:1px solid #d9cfbd;border-radius:10px;padding:12px 16px;margin:14px 0;background:#fff}
.item[hidden]{display:none}
h2{margin:0 0 4px}.t{color:#6b6254;font-size:13px}
.ev{margin:10px 0;padding-left:10px;border-left:4px solid #e6dccb}
.c{color:#6b6254;font-size:14px}.q{background:#fff3e6;padding:2px 4px}.m{font-weight:600}
#controls{margin:12px 0}
#controls button.on{outline:3px solid #1d1b17}
#note{width:100%;min-height:70px;font:inherit;margin-top:8px;box-sizing:border-box}
#status{color:#6b6254;font-size:14px;margin-left:8px}
"""

JS = r"""
(function () {
  var meta = JSON.parse(document.getElementById('meta').textContent);
  var N = meta.length, cur = 0, state = {}, i;
  var VALID = {true: 1, partly: 1, false: 1, tic: 1};
  var KEY = 'gcw-ratings-v1:' + meta.map(function (m) { return m.id; }).join(',');
  for (i = 0; i < N; i++) state[meta[i].id] = {rating: '', note: ''};
  var byId = {}; for (i = 0; i < N; i++) byId[meta[i].id] = i;
  var sections = document.querySelectorAll('section.item');
  var navButtons = [], status = document.getElementById('status');

  function allowed(id, r) { return VALID.hasOwnProperty(r) && (r !== 'tic' || meta[byId[id]].type === 'running_jokes'); }
  function save() { try { window.localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  function restore() {
    try {
      var raw = window.localStorage.getItem(KEY);
      if (!raw) return;
      var o = JSON.parse(raw);
      for (var id in o) { if (state.hasOwnProperty(id) && o[id]) {
        if (o[id].rating === '' || allowed(id, o[id].rating)) state[id].rating = o[id].rating;
        if (typeof o[id].note === 'string') state[id].note = o[id].note;
      } }
    } catch (e) {}
  }
  function render() {
    var m = meta[cur], st = state[m.id], r;
    for (i = 0; i < N; i++) sections[i].hidden = (i !== cur);
    var rated = 0;
    for (i = 0; i < N; i++) { r = state[meta[i].id].rating; if (r) rated++;
      navButtons[i].className = 's-' + (r || 'none') + (i === cur ? ' cur' : ''); }
    document.getElementById('progress').textContent = (cur + 1) + ' / ' + N;
    document.getElementById('rated').textContent = rated + ' rated';
    ['true', 'partly', 'false', 'tic'].forEach(function (k) {
      var b = document.getElementById('b-' + k);
      b.className = (st.rating === k ? 'on s-' + k : 's-none');
      if (k === 'tic') b.style.display = (m.type === 'running_jokes') ? '' : 'none';
    });
    var note = document.getElementById('note');
    if (note.value !== st.note) note.value = st.note;
    document.getElementById('prev').disabled = (cur === 0);
    document.getElementById('next').disabled = (cur === N - 1);
  }
  function go(n) { if (n >= 0 && n < N) { cur = n; render(); window.scrollTo(0, 0); } }
  function rate(r) { var id = meta[cur].id; if (!allowed(id, r)) return; state[id].rating = r; save(); render(); }
  function q(s) { return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
  function toCsv() {
    var lines = ['id,type,rating,note'];
    for (i = 0; i < N; i++) { var m = meta[i], st = state[m.id]; lines.push([m.id, m.type, st.rating, st.note].map(q).join(',')); }
    return lines.join('\r\n') + '\r\n';
  }
  function parseCsv(text) {
    var rows = [], row = [], f = '', inq = false, k, c;
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
    for (k = 0; k < text.length; k++) {
      c = text[k];
      if (inq) {
        if (c === '"') { if (text[k + 1] === '"') { f += '"'; k++; } else inq = false; } else f += c;
      } else if (c === '"') inq = true;
      else if (c === ',') { row.push(f); f = ''; }
      else if (c === '\n' || c === '\r') { if (c === '\r' && text[k + 1] === '\n') k++; row.push(f); rows.push(row); row = []; f = ''; }
      else f += c;
    }
    if (f !== '' || row.length) { row.push(f); rows.push(row); }
    return rows;
  }
  function loadCsv(text) {
    var rows = parseCsv(text), head = rows.shift() || [], ci = head.indexOf('id'), cr = head.indexOf('rating'), cn = head.indexOf('note');
    var ok = 0, skipped = 0;
    if (ci < 0 || cr < 0) { status.textContent = 'Not a ratings file (needs id and rating columns).'; return; }
    rows.forEach(function (r) {
      var id = r[ci];
      if (!byId.hasOwnProperty(id)) { skipped++; return; }
      var rating = (r[cr] || '').trim();
      if (rating !== '' && !allowed(id, rating)) { skipped++; return; }
      state[id].rating = rating; state[id].note = cn >= 0 ? (r[cn] || '') : ''; ok++;
    });
    save(); render();
    status.textContent = 'Loaded ' + ok + ' rows' + (skipped ? ', skipped ' + skipped : '') + '.';
  }

  var nav = document.getElementById('nav');
  meta.forEach(function (m, k) {
    var b = document.createElement('button'); b.type = 'button'; b.textContent = String(k + 1);
    b.addEventListener('click', function () { go(k); }); nav.appendChild(b); navButtons.push(b);
  });
  ['true', 'partly', 'false', 'tic'].forEach(function (k) { document.getElementById('b-' + k).addEventListener('click', function () { rate(k); }); });
  document.getElementById('clear').addEventListener('click', function () { state[meta[cur].id].rating = ''; save(); render(); });
  document.getElementById('prev').addEventListener('click', function () { go(cur - 1); });
  document.getElementById('next').addEventListener('click', function () { go(cur + 1); });
  document.getElementById('note').addEventListener('input', function (e) { state[meta[cur].id].note = e.target.value; save(); });
  document.getElementById('download').addEventListener('click', function () {
    var blob = new Blob([toCsv()], {type: 'text/csv;charset=utf-8'}), a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'ratings.csv'; document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  });
  document.getElementById('load').addEventListener('change', function (e) {
    var file = e.target.files && e.target.files[0]; if (!file) return;
    var rd = new FileReader(); rd.onload = function () { loadCsv(String(rd.result)); e.target.value = ''; }; rd.readAsText(file);
  });
  document.addEventListener('keydown', function (e) {
    var t = e.target && e.target.tagName;
    if (t === 'TEXTAREA' || t === 'INPUT' || e.ctrlKey || e.metaKey || e.altKey) return;  // typing in the note box must not trigger shortcuts
    if (e.key === '1') rate('true'); else if (e.key === '2') rate('partly'); else if (e.key === '3') rate('false'); else if (e.key === '4') rate('tic');
    else if (e.key === 'ArrowLeft') go(cur - 1); else if (e.key === 'ArrowRight') go(cur + 1); else return;
    e.preventDefault();
  });
  restore(); render();
})();
"""


def render(items: list[dict], seed: int) -> str:
    e = _html.escape

    def ln(x: dict, cls: str) -> str:
        return f'<div class="{cls}"><span class="m">{e(x["when"])} {e(x["who"])}</span> {e(x["text"])}</div>'

    meta = json.dumps([{"id": it["id"], "type": it["type"]} for it in items]).replace("<", "\\u003c")
    rubric = "".join(f"<li><b>{e(k)}</b> = {e(v)}</li>" for k, v in RUBRIC)
    head = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{CSP}">'
            f"<title>Blind rating tool</title><style>{CSS}</style></head><body>"
            '<div id="bar"><div class="row"><span id="progress"></span><span id="rated"></span>'
            '<button id="prev" type="button">&larr; prev</button><button id="next" type="button">next &rarr;</button>'
            '<button id="download" type="button">Download ratings.csv</button>'
            '<label class="btn">Load ratings.csv<input id="load" type="file" accept=".csv,text/csv" hidden></label><span id="status"></span></div>'
            '<div id="nav"></div></div>'
            f'<details open><summary>Rubric (read before rating)</summary><ul>{rubric}</ul><p>{e(RUBRIC_NOTE)}</p>'
            f"<p>Keys: 1 true, 2 partly, 3 false, 4 tic (jokes only), left and right arrows move. {len(items)} items, seed {int(seed)}; order is shuffled; the item type is shown and nothing else about where an item came from.</p></details>"
            '<div id="controls"><button id="b-true" type="button">1 true</button> <button id="b-partly" type="button">2 partly</button> '
            '<button id="b-false" type="button">3 false</button> <button id="b-tic" type="button">4 tic</button> <button id="clear" type="button">clear</button>'
            '<textarea id="note" placeholder="note (optional)" aria-label="note"></textarea></div><main>')
    body = []
    for k, it in enumerate(items):
        sec = (f'<section class="item" id="{e(it["id"])}" data-id="{e(it["id"])}" data-type="{e(it["type"])}"{"" if k == 0 else " hidden"}>'
               f'<h2>{e(it["id"])}: {e(it["title"])}</h2><div class="t">{e(it["type"].replace("_", " "))}' + (f' for {e(it["member"])}' if it.get("member") else "") + f'</div><p>{e(it["summary"])}</p>')
        for ev in it["evidence"]:
            sec += ('<div class="ev">' + "".join(ln(x, "c") for x in ev["before"]) + ln(ev["cited"], "cited") + f'<div>quote: <span class="q">{e(ev["quote"])}</span></div>'
                    + "".join(ln(x, "c") for x in ev["after"]) + "</div>")
        body.append(sec + "</section>")
    return head + "".join(body) + f'</main><script type="application/json" id="meta">{meta}</script><script>{JS}</script></body></html>\n'
