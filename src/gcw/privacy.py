"""Privacy layer: build the exact text that would be sent to the model. No network, no LLM, never imports anthropic.

Pipeline per message (build_payload): sensitive screen on the ORIGINAL text -> cleanup (NFC, invisible and bidi characters stripped,
newlines to spaces) -> links/emails/UPI ids -> dates and times protected -> phones -> member names -> @handles -> long digit runs.
Placeholders are private-use sentinels until the very end, so no later rule can corrupt them (a member nicknamed "link" cannot hit "[link]").

The mapping (token -> export name) is returned to the caller and stays local: nothing here writes it into a payload.
Known limits (docs/privacy.md): nicknames missing from the alias file, names in non-Latin scripts only partly (matching is Unicode-aware but
untested on real chats), topics without an English keyword, and over-redaction of long numbers and short bare domains.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import regex

from gcw.parser import messages
from gcw.textnorm import normalise_for_match

ROOT = Path(__file__).resolve().parents[2]
KEYWORDS_PATH = ROOT / "config" / "sensitive_keywords.json"
BYTES_PER_TOKEN = 2.37  # raw frozen chat: 571,701 bytes / 241,311 count_tokens tokens (Phase 1a). Rough; measured on RAW text, not the payload
PREFIXES = ("Member", "Person", "Speaker", "Participant")
WITHHELD = "[withheld: sensitive]"
MEDIA = "[media]"
PLACEHOLDERS = {"link": "[link]", "email": "[email]", "phone": "[phone]", "handle": "[handle]", "number": "[number]"}
OPEN, CLOSE = chr(0xE000), chr(0xE001)  # private-use sentinels
_LAT = "abcdefghijklmnopqrstuvwxyz"


# ------------------------------------------------------------------ aliases
@dataclass(frozen=True)
class Member:
    export_name: str
    display: str
    nicknames: tuple[str, ...] = ()
    case_sensitive: bool = False


@dataclass(frozen=True)
class Aliases:
    members: tuple[Member, ...] = ()

    def display_map(self) -> dict[str, str]:
        return {m.export_name: m.display for m in self.members}


def parse_aliases(data: Any) -> Aliases:
    """Accepts {"members": [...]} or the older flat {"export name": "display name"} form."""
    if not isinstance(data, dict):
        raise ValueError("aliases file must be a JSON object")
    if "members" not in data:
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise ValueError("aliases file must be {\"members\": [...]} or an object mapping export names to display names (strings)")
        return Aliases(tuple(Member(k, v) for k, v in data.items()))
    ms = data["members"]
    if not isinstance(ms, list):
        raise ValueError("aliases 'members' must be a list")
    out, seen = [], set()
    for i, m in enumerate(ms):
        if not isinstance(m, dict) or not isinstance(m.get("export_name"), str) or not m["export_name"].strip():
            raise ValueError(f"aliases member {i}: 'export_name' must be a non-empty string")
        disp = m.get("display", m["export_name"])
        nick = m.get("nicknames", [])
        cs = m.get("case_sensitive", False)
        if not isinstance(disp, str) or not isinstance(nick, list) or not all(isinstance(n, str) for n in nick) or not isinstance(cs, bool):
            raise ValueError(f"aliases member {i}: bad 'display', 'nicknames' or 'case_sensitive'")
        for n in nick:
            if len(n.strip()) < 2:
                raise ValueError(f"aliases member {i}: nickname {n!r} is shorter than 2 characters (it would match inside ordinary words)")
        if m["export_name"] in seen:
            raise ValueError(f"aliases: export_name {m['export_name']!r} appears twice")
        seen.add(m["export_name"])
        out.append(Member(m["export_name"], disp, tuple(n.strip() for n in nick), cs))
    return Aliases(tuple(out))


def load_aliases(path: str | Path) -> Aliases:
    return parse_aliases(json.loads(Path(path).read_text(encoding="utf-8")))


# ------------------------------------------------------------------ cleanup and sentinels
def clean(text: str) -> str:
    """NFC, strip invisible/bidi characters (including U+2066-2069), newlines to spaces, collapse whitespace. Sentinels are removed from input."""
    return normalise_for_match(text.replace(OPEN, "").replace(CLOSE, ""))


def _sent(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = _LAT[r] + s
    return OPEN + s + CLOSE


class _Store:
    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    def put(self, replacement: str) -> str:
        k = _sent(len(self.items))
        self.items[k] = replacement
        return k

    def restore(self, text: str) -> str:
        for _ in range(3):  # sentinels never nest, but loop in case a replacement contains one
            text = re.sub(OPEN + "[a-z]+" + CLOSE, lambda m: self.items.get(m.group(), ""), text)
        return text


# ------------------------------------------------------------------ redaction patterns
_TLDS = "com|org|net|io|in|co|me|ly|app|dev"
URL = regex.compile(r"(?i)(?:https?://|www\.)[^\s<>\"]*[^\s<>\".,;:!?)\]}'" + chr(0x2019) + r"]")
BARE_URL = regex.compile(r"(?i)(?<![\w@./-])(?:[a-z0-9-]+\.)+(?:" + _TLDS + r")(?:/[^\s<>\"]*[^\s<>\".,;:!?)\]}'])?(?![\w@-])")
EMAIL = regex.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
UPI = regex.compile(r"(?<![\w.+-])[\w.\-]{2,}@[A-Za-z]{2,}(?![\w.])")
HANDLE = regex.compile(r"@(?=[\p{L}\p{N}_])[\p{L}\p{N}_.]*[\p{L}\p{N}_]")
ANY_AT_LETTER = regex.compile(r"@(?=\p{L})")
DATE_TIME = regex.compile(
    r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)"
    r"|(?<!\d)\d{1,2}[/.]\d{1,2}[/.]\d{2,4}(?!\d)"
    r"|(?<!\d)\d{1,2}-\d{1,2}-\d{4}(?!\d)"
    r"|(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp]\.?[Mm]\.?(?![\p{L}]))?"
)
PHONE_CAND = regex.compile(r"(?<![\w])\+?\(?\d[\d\s().\-]{6,}\d(?!\w)")
NUMBER = regex.compile(r"(?<!\d)\d{6,}(?!\d)")


def _is_phone(cand: str) -> bool:
    digits = re.sub(r"\D", "", cand)
    d = len(digits)
    plus = cand.startswith("+") or digits.startswith("00")
    contiguous = re.fullmatch(r"\+?\d+", cand) is not None
    if plus and 8 <= d <= 15:
        return True
    if contiguous:
        return d == 10 and digits[0] in "6789"  # bare Indian 10-digit mobile
    return 9 <= d <= 15


def _sub_with(pattern: Any, text: str, store: _Store, kind: str, counts: Counter, accept=None) -> str:
    def f(m: Any) -> str:
        if accept is not None and not accept(m.group()):
            return m.group()
        counts[kind] += 1
        return store.put(PLACEHOLDERS[kind])

    return pattern.sub(f, text)


def _scrub(text: str, names: "NameMatcher | None", counts: Counter) -> str:
    store = _Store()
    t = clean(text)
    t = _sub_with(URL, t, store, "link", counts)
    t = _sub_with(EMAIL, t, store, "email", counts)
    t = _sub_with(UPI, t, store, "handle", counts)
    t = _sub_with(BARE_URL, t, store, "link", counts)
    t = DATE_TIME.sub(lambda m: store.put(m.group()), t)
    t = _sub_with(PHONE_CAND, t, store, "phone", counts, accept=_is_phone)
    if names is not None:
        t = names.sub(t, store, counts)
    t = _sub_with(HANDLE, t, store, "handle", counts)
    t = _sub_with(NUMBER, t, store, "number", counts)
    t = ANY_AT_LETTER.sub(lambda m: store.put(PLACEHOLDERS["handle"]), t)  # last resort: no "@" followed by a letter survives
    return store.restore(t)


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Typed placeholders for links, emails, UPI ids and @handles, phones, and digit runs of 6+ (dates and times survive).
    Returns (text, replacements per category)."""
    counts: Counter = Counter()
    return _scrub(text, None, counts), dict(counts)


# ------------------------------------------------------------------ names
def _first_word(name: str) -> str | None:
    w = name.split()[0] if name.split() else ""
    return w if len(w) >= 2 and any(c.isalpha() for c in w) else None


class NameMatcher:
    """Maps every known name form to its token. Whole-word, Unicode-aware, case-insensitive (per member switchable), longest first."""

    def __init__(self, forms: list[tuple[str, str, bool]]):
        # forms: (name, token, case_sensitive); the first member to claim a form wins
        self.ci: dict[str, str] = {}
        self.cs: dict[str, str] = {}
        self.ambiguous: list[str] = []
        for name, token, cs in forms:
            name = unicodedata.normalize("NFC", name).strip()
            if len(name) < 2:
                continue
            table, key = (self.cs, name) if cs else (self.ci, name.casefold())
            if key in table and table[key] != token:
                self.ambiguous.append(name)
                continue
            table[key] = token
        alts = sorted({*self.cs, *(k for k in self.ci)}, key=lambda s: (-len(s), s))
        parts = []
        for a in alts:
            parts.append("(?-i:" + regex.escape(a) + ")" if a in self.cs else "(?i:" + regex.escape(a) + ")")
        self.pattern = (regex.compile(r"(?<![\p{L}\p{N}_])@?(?:" + "|".join(parts) + r")(?![\p{L}\p{N}_])", regex.FULLCASE | regex.IGNORECASE)
                        if parts else None)

    def token_for(self, matched: str) -> str:
        m = matched.lstrip("@")
        return self.cs.get(m) or self.ci.get(m.casefold()) or self.ci.get(unicodedata.normalize("NFC", m).casefold(), "")

    def sub(self, text: str, store: _Store, counts: Counter) -> str:
        if self.pattern is None:
            return text

        def f(m: Any) -> str:
            tok = self.token_for(m.group())
            if not tok:
                return m.group()
            counts["name"] += 1
            return store.put(tok)

        return self.pattern.sub(f, text)


class Pseudonymiser:
    """Tokens for senders and a matcher for names in text. Built from the chat so unknown senders get tokens too."""

    def __init__(self, df: pd.DataFrame, aliases: Aliases | None):
        pop = messages(df)
        aliases = aliases or Aliases()
        order: list[str] = [m.export_name for m in aliases.members]
        for s in dict.fromkeys(pop["sender"]):  # first appearance
            if s not in order:
                order.append(s)
        self.prefix = _choose_prefix(pop, order)
        self.tokens = {name: self._token(i + 1) for i, name in enumerate(order)}
        forms: list[tuple[str, str, bool]] = []
        by_name = {m.export_name: m for m in aliases.members}
        for name in order:
            tok, m = self.tokens[name], by_name.get(name)
            cs = bool(m and m.case_sensitive)
            cands = [name, _first_word(name)]
            if m:
                cands += [m.display, _first_word(m.display), *m.nicknames]
            forms += [(c, tok, cs) for c in cands if c]
        self.matcher = NameMatcher(forms)
        self.warnings = [f"name form {n!r} belongs to more than one member; mapped to the first" for n in self.matcher.ambiguous]

    def _token(self, n: int) -> str:
        return f"{self.prefix} {n}" if self.prefix in PREFIXES else f"{self.prefix}_{n}"

    @property
    def mapping(self) -> dict[str, str]:
        """token -> export name. LOCAL ONLY: never put this in a payload."""
        return {tok: name for name, tok in self.tokens.items()}

    def sender(self, name: str) -> str:
        return self.tokens[name]

    def names_only(self, text: str) -> tuple[str, int]:
        store, counts = _Store(), Counter()
        t = self.matcher.sub(clean(text), store, counts)
        return store.restore(t), counts["name"]


def _choose_prefix(pop: pd.DataFrame, names: list[str]) -> str:
    """First prefix whose 'Prefix N' form appears nowhere in the chat text or sender names; else P<hash> that does not appear either."""
    blob = "\n".join(str(x) for x in [*pop["text"], *names])
    blob = unicodedata.normalize("NFC", blob)
    for p in PREFIXES:
        if not re.search(r"(?<![\w])" + re.escape(p) + r"\s*\d+", blob, re.IGNORECASE):
            return p
    h = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    for i in range(0, len(h) - 8):
        cand = "P" + h[i:i + 8]
        if cand not in blob:
            return cand
    raise RuntimeError("could not find a collision-free pseudonym prefix")


def pseudonymise(df: pd.DataFrame, aliases: Aliases | None = None) -> tuple[pd.DataFrame, dict[str, str]]:
    """Return (payload_df, mapping). payload_df = messages(df) with sender and in-text names replaced by tokens (nothing else changed
    except cleanup). mapping = token -> export name, to be kept local."""
    ps = Pseudonymiser(df, aliases)
    pop = messages(df).copy()
    pop["text"] = [ps.names_only(t)[0] for t in pop["text"]]
    pop["sender"] = [ps.sender(s) for s in pop["sender"]]
    return pop.reset_index(drop=True), ps.mapping


# ------------------------------------------------------------------ sensitive screen
_screen_cache: dict[str, Any] = {}


def _term_regex(term: str) -> str:
    stem = term.endswith("*")
    body = r"\s+".join(regex.escape(w) for w in term.rstrip("*").split())
    return body + (r"\p{L}*" if stem else "")


def load_keywords(path: Path | str = KEYWORDS_PATH) -> dict[str, list[str]]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"sensitive keyword list not found: {p} (config/sensitive_keywords.json is read from the repo, not packaged)")
    data = json.loads(p.read_text(encoding="utf-8"))
    cats = data.get("categories")
    if not isinstance(cats, dict) or not all(isinstance(v, list) and all(isinstance(t, str) and t.strip() for t in v) for v in cats.values()):
        raise ValueError("sensitive_keywords.json: 'categories' must map names to lists of non-empty strings")
    return cats


def _compiled(path: Path | str) -> dict[str, Any]:
    key = str(path)
    if key not in _screen_cache:
        _screen_cache[key] = {c: regex.compile(r"(?i)(?<![\p{L}\p{N}])(?:" + "|".join(_term_regex(t) for t in terms) + r")(?![\p{L}\p{N}])")
                              for c, terms in load_keywords(path).items() if terms}
    return _screen_cache[key]


def sensitive_hits(text: str, path: Path | str = KEYWORDS_PATH) -> list[str]:
    t = clean(text)
    return [c for c, rx in _compiled(path).items() if rx.search(t)]


def sensitive_screen(text: str, path: Path | str = KEYWORDS_PATH) -> bool:
    """True if the message matches any keyword (it is then withheld). Runs on the original text, before redaction."""
    return bool(sensitive_hits(text, path))


# ------------------------------------------------------------------ payload
def build_payload(df: pd.DataFrame, aliases: Aliases | None = None, keywords: Path | str = KEYWORDS_PATH) -> tuple[str, dict, dict[str, str]]:
    """Return (payload_text, counts, mapping). One line per message of messages(df):
    `<id> | <YYYY-MM-DD HH:MM> | Member 3 | text` (id like m000123); media -> [media]; sensitive -> [withheld: sensitive]. ids are sequential over the filtered chat.
    mapping (token -> export name) is local only."""
    ps = Pseudonymiser(df, aliases)
    pop = messages(df)
    rep: Counter = Counter()
    withheld: Counter = Counter()
    lines = []
    for n, (ts, sender, text, is_media) in enumerate(zip(pop["ts"], pop["sender"], pop["text"], pop["is_media"]), start=1):
        if is_media:
            body = MEDIA
        else:
            hits = sensitive_hits(text, keywords)
            if hits:
                body = WITHHELD
                withheld.update(hits[:1])
            else:
                body = _scrub(text, ps.matcher, rep)
        lines.append(f"m{n:06d} | {ts:%Y-%m-%d %H:%M} | {ps.sender(sender)} | {body}")
    text_out = "\n".join(lines) + ("\n" if lines else "")
    nbytes = len(text_out.encode("utf-8"))
    counts = {
        "messages": len(lines),
        "withheld": int(sum(withheld.values())),
        "withheld_by_category": dict(withheld),
        "replacements": {k: int(rep.get(k, 0)) for k in (*PLACEHOLDERS, "name")},
        "payload_bytes": nbytes,
        "estimated_tokens": math.ceil(nbytes / BYTES_PER_TOKEN),
        "estimated_tokens_note": "rough: bytes / 2.37 (measured on the raw frozen chat, not on this payload); too low for non-Latin scripts",
        "prefix": ps.prefix,
        "warnings": ps.warnings,
    }
    return text_out, counts, ps.mapping
