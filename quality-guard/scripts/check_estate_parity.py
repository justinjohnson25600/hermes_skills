#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check that every profile's quality-guard copy agrees.

The original review found five copies in two different versions, with the
default profile a month stale and missing the destructive-action row -- the one
row backed by a real incident. Nothing detected that, because nothing was
looking.

This script looks. Run it after any skill edit, or on a schedule.

Exit codes:
    0  every copy present, identical, and passing its content checks
    1  divergence, a missing copy, or a failed content check
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

BASE = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"
SKILL_REL = Path("skills") / "software-development" / "quality-guard"
PROFILES = ("g0ksc", "hermesdev", "bloods", "critic")

#: (label, predicate, why it matters)
CONTENT_CHECKS = (
    ("version 1.0.2",
     lambda t: bool(re.search(r"^version:\s*1\.0\.2", t, re.M)),
     "version field missing or stale"),
    ("destructive-action row",
     lambda t: "Destructive system action" in t,
     "the row backed by a real incident is missing"),
    ("unattended-runs rung",
     lambda t: "Unattended runs" in t,
     "no escalation path for cron/batch contexts"),
    ("footer placeholder rule",
     lambda t: "Fill it, or it is not evidence" in t,
     "an unfilled template would count as evidence"),
    ("wide drift class",
     lambda t: "\\u3040-\\u309f" in t,
     "narrow CJK class misses 9 of 11 drift samples"),
    ("no stale tool cell",
     lambda t: "Context7, web_fetch" not in t,
     "names tools that do not exist in this runtime"),
    ("no bare relative script path",
     lambda t: "Run `scripts/quality_gate.py" not in t,
     "relative path fails outside the skill directory"),
)


def copies():
    yield "default", BASE / SKILL_REL
    for p in PROFILES:
        yield p, BASE / "profiles" / p / SKILL_REL


def main() -> int:
    rc = 0
    skill_digests, script_digests = {}, {}

    print("quality-guard estate parity")
    print("=" * 66)

    for name, root in copies():
        skill, script = root / "SKILL.md", root / "scripts" / "quality_gate.py"
        if not skill.exists():
            print("  {:<10} MISSING SKILL.md".format(name))
            rc = 1
            continue

        body = skill.read_bytes()
        skill_digests[name] = hashlib.sha256(body).hexdigest()
        text = body.decode("utf-8", "replace")

        failures = [why for label, pred, why in CONTENT_CHECKS if not pred(text)]
        if script.exists():
            script_digests[name] = hashlib.sha256(script.read_bytes()).hexdigest()
        else:
            failures.append("scripts/quality_gate.py not shipped alongside")

        print("  {:<10} {:>6} B  {}".format(
            name, len(body), "OK" if not failures else "FAILED"))
        for f in failures:
            print("      - {}".format(f))
            rc = 1

    def agree(label, digests):
        nonlocal rc
        if not digests:
            return
        uniq = set(digests.values())
        if len(uniq) == 1:
            print("  {:<22} identical  sha256 {}".format(
                label, next(iter(uniq))[:16]))
        else:
            print("  {:<22} DIVERGED across {} variants:".format(
                label, len(uniq)))
            for n, d in sorted(digests.items()):
                print("      {:<10} {}".format(n, d[:16]))
            rc = 1

    print("-" * 66)
    agree("SKILL.md", skill_digests)
    agree("quality_gate.py", script_digests)
    print("=" * 66)
    print("PARITY OK" if rc == 0 else "PARITY FAILED — see above")
    return rc


if __name__ == "__main__":
    sys.exit(main())
