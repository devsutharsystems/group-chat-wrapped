#!/usr/bin/env python3
"""Repetition check on a generated chat, excluding planted lines.

  repetition_check.py CHAT [GROUND_TRUTH.json]
Prints the top 10 repeated word 3-grams and the number of distinct non-planted messages of 4+ words
that appear more than 3 times (target 0).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

LINE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}), (\d{1,2}):(\d{2}) ([AP]M) - (?:([^:\n]+): )?(.*)$")
EDITED = " <This message was edited>"


def parse(text: str) -> list[tuple[str, str, str]]:
    """(timestamp-key, sender, body) for sender lines; continuation lines join the previous message."""
    out: list[list[str]] = []
    for line in text.splitlines():
        m = LINE.match(line)
        if m:
            mo, d, yy, h, mi, ap, sender, body = m.groups()
            if sender is None:
                out.append(["", "", ""])  # system line placeholder, dropped below
                continue
            out.append([f"{int(mo)}/{int(d)}/{yy} {int(h)}:{mi} {ap}", sender, body])
        elif out:
            out[-1][2] += "\n" + line
    return [(a, b, c) for a, b, c in out if b]


def planted_keys(gt_path: str | None) -> set[tuple[str, str]]:
    if not gt_path:
        return set()
    from datetime import datetime

    keys = set()
    for i in json.loads(Path(gt_path).read_text())["items"]:
        t = datetime.fromisoformat(i["timestamp"])
        keys.add((f"{t.month}/{t.day}/{t.year % 100:02d} {t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}", i["text"]))
    return keys


def words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", t.lower())


def analyse(text: str, gt: str | None = None) -> dict:
    skip = planted_keys(gt)
    msgs = []
    for ts, sender, body in parse(text):
        body = body.replace(EDITED, "")
        if (ts, body) in skip or body in ("<Media omitted>", "You deleted this message"):
            continue
        msgs.append(body)
    tri: Counter = Counter()
    for b in msgs:
        w = words(b)
        tri.update(zip(w, w[1:], w[2:]))
    exact = Counter(" ".join(words(b)) for b in msgs if len(words(b)) >= 4)
    over = {k: v for k, v in exact.items() if v > 3}
    return {"messages_checked": len(msgs), "top_3grams": [(" ".join(k), v) for k, v in tri.most_common(10)], "repeated_over_3": len(over), "repeated_over_3_detail": dict(sorted(over.items(), key=lambda kv: -kv[1])[:10])}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    res = analyse(Path(argv[1]).read_text(encoding="utf-8"), argv[2] if len(argv) > 2 else None)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
