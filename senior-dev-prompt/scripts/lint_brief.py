#!/usr/bin/env python3
"""Self-check for a senior-dev-prompt brief: the Step 6 and Step 7b gate.

Usage:  python3 lint_brief.py BRIEF.md [--tier T0..T4] [--json]
Exit:   0 = pass, 1 = findings, 2 = usage or read error.

Standard library only, Python 3.8+. The rules are the ones written in
references/brief-template.md; a rule change ships with its script change.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FULL_SECTIONS = [
    "For you", "Operating obligations", "Original request", "Context",
    "Outcome, users and scenario", "Scope and deliverables", "Requirements and safeguards",
    "Approach and design", "Decision register", "Prerequisites you provide", "Workflow mandate",
    "Acceptance criteria and verification", "Boundaries and stop conditions",
    "Risks and mitigations", "Definition of done",
]
COMPACT_SECTIONS = [
    "For you", "Objective and scenario", "Scope", "Decisions", "Safeguards", "Route",
    "Acceptance criteria", "Stop conditions",
]
OPTIONAL_LAST = "Co-developer review"      # present only when reviewers ran
CONDITIONAL = {"Safeguards"}                # compact: required only when a risk flag fired
EXEMPT = {"co-developer review", "co-developer reviews"}   # reviewer output, kept verbatim
REQUEST = "original request"                                # only its quoted lines are exempt

STATUSES = ("draft", "blocked", "approved", "running", "built")
TIERS = ("T0", "T1", "T2", "T3", "T4")
REQUIRED_META = ("version", "status", "date", "tier", "type", "route", "pack", "risk")
BUDGETS = {"T0": 350, "T1": 350, "T2": 1500, "T3": 3000, "T4": 3000}
NO_RISK = {"", "none", "no", "n/a", "na", "-", "—"}
EMPTY_CELL = {"", "-", "—", "–", "tbd", "todo", "n/a", "na", "none", "?", "..."}

CODES = {
    "NO_METADATA": "no **Metadata:** line",
    "META_MISSING_KEY": "a required metadata key is missing",
    "BAD_STATUS": "status is not draft / blocked / approved / running / built",
    "BAD_TIER": "tier is not T0-T4",
    "MISSING_SECTION": "a required section is missing",
    "SECTION_ORDER": "sections are out of order",
    "PLACEHOLDER": "a placeholder token in generated text",
    "UNCOVERED_ID": "an FR / NFR / SG / SC item has no acceptance-criteria row",
    "NO_AC_ROWS": "no acceptance-criteria rows",
    "AC_NO_CHECK": "an acceptance-criteria row has no check",
    "AC_NO_EVIDENCE": "an acceptance-criteria row has no evidence",
    "NO_SAFEGUARD": "a risk flag fired but no SG-n safeguard exists",
    "OVER_BUDGET": "the brief is over its word budget",
}

ID_RE = re.compile(r"\b(?:FR|NFR|SG|SC)-\d+\b")
AC_ROW = re.compile(r"^\s*\|\s*(AC-\d+)\s*\|(.*)$")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’_.-]*")
WITHDRAWN = re.compile(r"withdr[ae]wn?|withdraw", re.I)
HTML_TAGS = {
    "a", "abbr", "article", "aside", "audio", "b", "body", "br", "button", "canvas", "code", "dd",
    "details", "dialog", "div", "dl", "dt", "em", "footer", "form", "h1", "h2", "h3", "h4", "h5",
    "h6", "head", "header", "hr", "html", "i", "iframe", "img", "input", "label", "li", "link",
    "main", "meta", "nav", "ol", "option", "p", "pre", "script", "section", "select", "small",
    "source", "span", "strong", "style", "summary", "svg", "table", "tbody", "td", "template",
    "textarea", "tfoot", "th", "thead", "title", "tr", "u", "ul", "video",
}
PLACEHOLDERS = [
    re.compile(r"\b(?:TBD|TODO|FIXME)\b"),
    re.compile(r"(?<![\w$/{])\{[A-Za-z_][\w .-]{0,40}\}(?!\})"),
    re.compile(r"\[\s*(?:insert|your|fill in|add)\b[^\]]*\](?!\()", re.I),
]
ANGLE = re.compile(r"(?<![\w])<(/?)([A-Za-z_][^<>\n]{0,60})>")


def _norm(head: str) -> str:
    h = re.sub(r"^\s*\d+[.)]?\s+", "", head)
    h = re.sub(r"[*_`]", "", h.replace("&", " and "))
    return re.sub(r"\s+", " ", h).strip().rstrip(":").strip().lower()


def _canon(head: str, names: list) -> str | None:
    n = _norm(head)
    for c in names:
        cl = c.lower()
        if n == cl or any(n.startswith(cl + sep) for sep in (" (", " -", " —", ":", " and ")):
            return c
    return None


def _exempt(head: str | None) -> bool:
    return head is not None and any(_norm(head) == e or _norm(head).startswith(e + " ") for e in EXEMPT)


def _sections(text: str) -> list:
    """[(heading or None, [lines])], split at level-2 headings outside code fences."""
    out, head, cur, fence = [], None, [], False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        m = None if fence else re.match(r"^##\s+(?!#)(.+?)\s*#*\s*$", line)
        if m:
            out.append((head, cur))
            head, cur = m.group(1), []
        else:
            cur.append(line)
    out.append((head, cur))
    return out


def _metadata(text: str):
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^\*\*metadata:?\*\*:?\s*(.*)$", s, re.I)
        if not m:
            continue
        body = m.group(1)
        sep = "·" if "·" in body else ("|" if "|" in body else ";")
        meta = {}
        for part in body.split(sep):
            if ":" in part:
                k, v = part.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        return line, meta
    return None, {}


def _empty(cell: str) -> bool:
    return cell.strip().strip("*_`").strip().lower() in EMPTY_CELL


def _placeholders(line: str) -> list:
    hits = []
    for rx in PLACEHOLDERS:
        hits += [m.group(0) for m in rx.finditer(line)]
    for m in ANGLE.finditer(line):
        body = m.group(2)
        tag = re.split(r"[\s/]", body, 1)[0].lower()
        if tag in HTML_TAGS or body.lower().startswith(("http", "mailto:")) or "@" in body:
            continue
        hits.append(m.group(0))
    return hits


def lint_report(text: str, tier: str | None = None) -> dict:
    findings = []

    def add(code, where, message):
        findings.append({"code": code, "where": where, "message": message})

    meta_line, meta = _metadata(text)
    sections = _sections(text)
    heads = [h for h, _ in sections if h is not None]

    if meta_line is None:
        add("NO_METADATA", "metadata", "add the **Metadata:** line under the title "
            "(version, status, date, tier, type, route, pack, risk, self-review).")
    else:
        for key in REQUIRED_META:
            if key not in meta:
                add("META_MISSING_KEY", "metadata", f"'{key}' is missing; add '{key}: <value>' to the metadata line.")
        status = meta.get("status", "").split(" ")[0].strip(",.").lower()
        if "status" in meta and status not in STATUSES:
            add("BAD_STATUS", "metadata", f"status '{meta['status']}' is not one of {', '.join(STATUSES)}.")
    meta_tier = None
    if "tier" in meta:
        m = re.search(r"\bT([0-4])\b", meta["tier"])
        if m:
            meta_tier = "T" + m.group(1)
        else:
            add("BAD_TIER", "metadata", f"tier '{meta['tier']}' is not one of T0-T4.")
    if tier is None:
        tier = meta_tier or ("T1" if any(_canon(h, ["Objective and scenario"]) for h in heads) else "T2")
    compact = tier in ("T0", "T1")
    schema = COMPACT_SECTIONS if compact else FULL_SECTIONS
    if meta_line is not None and not compact and "self-review" not in meta:
        add("META_MISSING_KEY", "metadata", "'self-review' is missing; T2-T4 briefs record it "
            "('self-review: 2 fixed', or 'self-review: skipped (user request)').")
    if meta_line is not None and any(_exempt(h) for h in heads) and "snapshot" not in meta:
        add("META_MISSING_KEY", "metadata", "'snapshot' is missing; a reviewed brief records the evidence "
            "sha256 prefix of the version the co-developers saw.")
    risk = meta.get("risk", "").strip().lower()
    no_risk = risk in NO_RISK

    # Sections: presence and order.
    allowed = schema + [OPTIONAL_LAST]
    found = [c for c in (_canon(h, allowed) for h in heads) if c]
    for name in schema:
        if name in CONDITIONAL and no_risk:
            continue
        if name not in found:
            why = f" (risk '{meta.get('risk')}' fired)" if name in CONDITIONAL else ""
            add("MISSING_SECTION", name, f"add the '## {name}' section{why}; see the "
                f"{'compact' if compact else 'full'} schema in brief-template.md.")
    order = [allowed.index(c) for c in found]
    for i in range(1, len(order)):
        if order[i] < order[i - 1]:
            add("SECTION_ORDER", found[i], f"'{found[i]}' comes after '{found[i - 1]}'; "
                "put the sections in the template order.")
            break

    # Placeholders, IDs, acceptance criteria and words — generated text only.
    mentioned, withdrawn, covered, ac_rows, words = {}, set(), set(), 0, 0
    placeholder_hits = []
    for head, lines in sections:
        if _exempt(head):
            continue
        where = head or "title"
        is_ac = head is not None and _canon(head, ["Acceptance criteria and verification", "Acceptance criteria"])
        in_request = head is not None and _norm(head).startswith(REQUEST)
        fence = False
        if head:
            words += len(WORD_RE.findall(head))
        for line in lines:
            s = line.strip()
            if s.startswith(("```", "~~~")):
                fence = not fence
                if in_request:
                    continue
            if s.startswith(">") or (in_request and fence):
                continue                                  # quoted user material
            if line == meta_line:
                placeholder_hits += [(where, h) for h in _placeholders(line)]
                continue
            if not re.match(r"^\|?\s*:?-{3,}", s):
                words += len(WORD_RE.findall(line))
            placeholder_hits += [(where, h) for h in _placeholders(line)]
            row = AC_ROW.match(line)
            if row:
                ac_rows += 1
                cells = [c.strip() for c in row.group(2).rstrip().rstrip("|").split("|")]
                cells += [""] * (3 - len(cells))
                covered.update(ID_RE.findall(cells[0]))
                if _empty(cells[1]):
                    add("AC_NO_CHECK", row.group(1), "give this row a concrete check (a command, test or observation).")
                if _empty(cells[2]):
                    add("AC_NO_EVIDENCE", row.group(1), "name the evidence this row produces (test output, log, screenshot).")
                continue
            if is_ac or head is None:
                continue
            ids = ID_RE.findall(line)
            if WITHDRAWN.search(line):
                withdrawn.update(ids)
                continue
            for i in ids:
                mentioned.setdefault(i, where)

    for where, hit in placeholder_hits[:10]:
        add("PLACEHOLDER", where, f"'{hit}' is a placeholder; write the real value (paths, numbers and commands included).")
    if len(placeholder_hits) > 10:
        add("PLACEHOLDER", "brief", f"... and {len(placeholder_hits) - 10} more placeholder(s).")
    for i in sorted(set(mentioned) - covered - withdrawn, key=lambda x: (x.split("-")[0], int(x.split("-")[1]))):
        add("UNCOVERED_ID", mentioned[i], f"{i} has no acceptance-criteria row; add one that covers it, or mark it withdrawn.")
    if ac_rows == 0:
        add("NO_AC_ROWS", "Acceptance criteria", "add the table: | AC-n | covers | check | evidence |.")
    if not no_risk and not any(i.startswith("SG-") for i in list(mentioned) + list(covered)):
        add("NO_SAFEGUARD", "Requirements and safeguards" if not compact else "Safeguards",
            f"risk '{meta.get('risk')}' needs at least one SG-n safeguard with a check (see safeguards.md).")
    budget = BUDGETS.get(tier or "T2", 1500)
    if words > budget:
        add("OVER_BUDGET", "brief", f"{words} words against the {tier} budget of {budget}; cut repetition, "
            "move detail into the decision register or tables, or re-check the tier.")
    return {"ok": not findings, "tier": tier, "schema": "compact" if compact else "full",
            "words": words, "budget": budget, "findings": findings}


def lint_text(text: str, tier: str | None = None) -> list:
    return lint_report(text, tier)["findings"]


def main(argv: list | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Self-check a senior-dev-prompt brief.")
    ap.add_argument("brief", help="path to the brief (.md)")
    ap.add_argument("--tier", choices=TIERS, help="override the tier in the metadata line")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)
    path = Path(args.brief)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"lint_brief: cannot read {path}: {e}", file=sys.stderr)
        return 2
    rep = lint_report(text, args.tier)
    if args.json:
        rep["file"] = str(path)
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    else:
        for f in rep["findings"]:
            print(f"{f['code']:<16} {f['where']}: {f['message']}")
        verdict = "PASS" if rep["ok"] else f"FAIL ({len(rep['findings'])} finding(s))"
        print(f"{verdict}: {path.name} -- tier {rep['tier']}, {rep['schema']} schema, "
              f"{rep['words']}/{rep['budget']} words")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
