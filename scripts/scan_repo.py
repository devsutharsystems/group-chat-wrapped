#!/usr/bin/env python3
"""Repo-hygiene scan. Exits 1 if it finds chat-export lines, phones, emails or key-like strings.

Findings never print the matched text, only file:line and the rule, so a leak is not echoed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", ".cache", "out", "__pycache__", ".pytest_cache", "notes", "data"}
SKIP_FILES = {".env", ".gcw_ledger.json"}
SPACE = "[  ]"  # plain or narrow no-break space
ANDROID = re.compile(rf"^‎?\d{{1,2}}/\d{{1,2}}/\d{{2,4}},{SPACE}\d{{1,2}}:\d{{2}}{SPACE}?[AaPp][Mm]{SPACE}-{SPACE}(?P<name>[^:]+):")
IOS = re.compile(r"^‎?\[\d{1,2}/\d{1,2}/\d{2,4},\s\d{1,2}:\d{2}:\d{2}(?:[  ][AaPp][Mm])?\]\s(?P<name>[^:]+):")
PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{8,}\d(?![\w.])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
KEY = re.compile(r"sk-[A-Za-z0-9_-]{16,}|(?i:api[_-]?key|secret|token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,}")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FAKE_PHONE = re.compile(r"^\+?0{2}[\s0-]+$")


def allowed_names(root: Path) -> set[str]:
    f = root / "tests" / "fixtures" / "ALLOWED_NAMES.txt"
    return {l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()} if f.exists() else set()


def is_synthetic_zone(rel: Path) -> bool:
    return rel.parts[:2] == ("tests", "fixtures") or rel.parts[:1] == ("synthetic",)


def scan_file(path: Path, root: Path, names: set[str]) -> list[str]:
    rel = path.relative_to(root)
    zone = is_synthetic_zone(rel)
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    out: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        for pat in (ANDROID, IOS):
            m = pat.match(line)
            if m:
                if not zone:
                    out.append(f"{rel}:{n}: chat-export line outside fixtures")
                elif m.group("name").strip() not in names:
                    out.append(f"{rel}:{n}: chat-export line with sender not in ALLOWED_NAMES")
        for m in PHONE.finditer(line):
            if not ISO_DATE.match(m.group().strip()) and not FAKE_PHONE.match(m.group().strip()) and not ANDROID.match(line) and not IOS.match(line):
                out.append(f"{rel}:{n}: phone-like string")
        for m in EMAIL.finditer(line):
            if not m.group().lower().endswith("@example.com"):
                out.append(f"{rel}:{n}: email")
        if KEY.search(line):
            out.append(f"{rel}:{n}: api-key-like string")
    return out


def scan(root: Path) -> list[str]:
    names = allowed_names(root)
    findings: list[str] = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if not p.is_file() or p.name in SKIP_FILES or SKIP_DIRS & set(rel.parts[:-1]):
            continue
        if p.name == "scan_repo.py" or p.name == "test_scan_repo.py":
            continue  # scanner source holds the patterns
        findings += scan_file(p, root, names)
    return findings


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parent.parent
    findings = scan(root)
    for f in findings:
        print(f)
    print(f"scan_repo: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
