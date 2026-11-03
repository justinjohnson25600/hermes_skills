#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quality_gate.py — the machine-checkable half of the quality-guard skill.

SKILL.md states: "The footer is the observable proof the gate ran, and it is
what makes this skill testable."  This script is what makes that true.

It checks the parts of the skill a machine can check, and stays out of the way
of the parts it cannot. It does NOT decide whether you actually executed the
code or fetched the docs -- no script can. It checks that the *record* of that
work exists, is filled in, is in the agreed format, is in the right place, and
that the "ready" labels are never applied without one.

Design notes
------------
* Standard library only. No install step, no dependencies, no network.
* Exit code 1 when the gate fails, so it drops straight into CI or a
  pre-commit hook.
* Negation is not a violation: "not yet production-ready" is the guardrail
  working, and a checker that flags it manufactures findings -- which destroys
  the signal value of the real ones.

Usage
-----
    quality_gate.py --response FILE [--artefact FILE ...] [--tier 1|2|3]
    quality_gate.py --response FILE --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

__version__ = "1.0.2"

# --------------------------------------------------------------------------
# The footer, exactly as SKILL.md specifies it.
# --------------------------------------------------------------------------
FOOTER_STRICT = re.compile(
    r"^[ \t]*Verified[ \t]*:.*?\n[ \t]*Unverified[ \t]*:.*?\n[ \t]*Assumptions[ \t]*:",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)

# A footer ATTEMPT: a "Verified:" line however decorated (bold, bullet,
# heading). Used to tell "drifted out of format" apart from "absent entirely",
# because those are different failures with different fixes.
FOOTER_LOOSE = re.compile(
    r"^[ \t]*(?:[*_#>\-]+[ \t]*)*\**[ \t]*Verified[ \t]*:",
    re.IGNORECASE | re.MULTILINE,
)

# An UNFILLED footer. SKILL.md's own template uses <angle-bracket> placeholders,
# so shape alone cannot distinguish a real footer from a copied blank one.
# Anchored to the start of the value so that a genuine footer mentioning "<" in
# prose (e.g. a shell redirect) is not flagged.
FOOTER_PLACEHOLDER = re.compile(
    r"^[ \t]*(?:Verified|Unverified|Assumptions)[ \t]*:[ \t]*"
    r"(<[^>\n]*>|\.\.\.|TBD|TODO|N/?A[ \t]*$|\[[^\]\n]*\])",
    re.IGNORECASE | re.MULTILINE,
)

# --------------------------------------------------------------------------
# Script drift.
#
# A class of [\u4e00-\u9fff] covers CJK Unified Ideographs and nothing else.
# Measured against realistic drift samples it misses 9 of 11: full-width
# punctuation, ideographic space, kana, Hangul, Ext-A and compatibility forms
# all pass clean. The ranges below close that gap.
# --------------------------------------------------------------------------
CJK_NARROW = re.compile(r"[\u4e00-\u9fff]")  # kept to report what a narrow class would miss
CJK_FULL = re.compile(
    "["
    "\u2e80-\u2eff"  # CJK radicals supplement
    "\u3000-\u303f"  # CJK symbols & punctuation (ideographic space, 、 。 「 」)
    "\u3040-\u309f"  # Hiragana
    "\u30a0-\u30ff"  # Katakana
    "\u3100-\u312f"  # Bopomofo
    "\u3130-\u318f"  # Hangul compatibility jamo
    "\u3400-\u4dbf"  # CJK Unified Ext A
    "\u4e00-\u9fff"  # CJK Unified  <- the only range a narrow class covers
    "\ua000-\ua4cf"  # Yi
    "\uac00-\ud7af"  # Hangul syllables
    "\uf900-\ufaff"  # CJK compatibility ideographs
    "\ufe30-\ufe4f"  # CJK compatibility forms
    "\uff00-\uffef"  # Half/full-width forms
    "]"
)

# The three labels the skill refuses to un-gated output.
READY_CLAIM = re.compile(r"(production|client|publication)[- ]ready", re.IGNORECASE)

# Negation anywhere earlier in the SAME sentence means the label is being
# WITHHELD or the rule is being described ("never label the output
# production-ready"). Scanning only the adjacent few words misses these, and a
# checker that reports them manufactures findings -- which destroys the signal
# value of the real ones. Scope is the sentence, so a negation in a PREVIOUS
# sentence cannot license a later claim.
NEGATION_WORDS = re.compile(
    r"\b(not|isn'?t|is ?n'?t|are ?n'?t|aren'?t|wasn'?t|weren'?t|never|no longer|"
    r"cannot|can'?t|won'?t|refuse[sd]?|forbid(?:s|den)?|prohibit(?:s|ed)?|"
    r"far from|nowhere near|yet to be|before it is|until it is|unless|without|"
    r"path to|towards?|make it|becoming|avoid)\b",
    re.IGNORECASE,
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n{2,}|\n(?=[-*#|])")

BLOCKING = ("CRITICAL", "HIGH")

# --------------------------------------------------------------------------
# Quoted regions.
#
# Prose that DESCRIBES the footer format necessarily contains the footer
# format. This skill's own SKILL.md and README are the obvious cases: both
# print the template inside a code fence, and a naive scan reads the example
# as a real (unfilled) footer.
#
# The general trap: when a check asks a question about content, quoted or
# fenced regions routinely contain the exact vocabulary being searched for, so
# they must be excluded before matching -- otherwise documentation about a rule
# is indistinguishable from a violation of it.
# --------------------------------------------------------------------------
FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})[^\n]*\n.*?(?:^\1?\2[^\n]*$|\Z)",
                      re.DOTALL | re.MULTILINE)
INDENTED_BLOCK_RE = re.compile(r"^(?:[ ]{4,}|\t)[^\n]*$", re.MULTILINE)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
# YAML frontmatter is metadata -- trigger phrases listed there are the skill
# declaring what fires it, not a claim about the current deliverable.
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n.*?^---[ \t]*\r?$",
                            re.DOTALL | re.MULTILINE)


def strip_quoted(text: str) -> str:
    """Blank out frontmatter, fenced/indented/inline code, preserving lines.

    Replacement keeps newlines so that reported line numbers still match the
    original document.
    """
    def _blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    text = FRONTMATTER_RE.sub(_blank, text)
    text = FENCE_RE.sub(_blank, text)
    text = INDENTED_BLOCK_RE.sub(_blank, text)
    text = INLINE_CODE_RE.sub(_blank, text)
    return text


def _sentence_containing(text: str, index: int) -> str:
    """Return the sentence enclosing `index`, for negation scoping."""
    start = 0
    for m in SENTENCE_SPLIT.finditer(text, 0, index):
        start = m.end()
    end = len(text)
    m = SENTENCE_SPLIT.search(text, index)
    if m:
        end = m.start()
    return text[start:end]


class Finding:
    """One gate finding. Severity drives the exit code."""

    __slots__ = ("severity", "check", "where", "detail")

    def __init__(self, severity: str, check: str, where: str, detail: str) -> None:
        self.severity = severity
        self.check = check
        self.where = where
        self.detail = detail

    def as_dict(self) -> dict:
        return {
            "severity": self.severity,
            "check": self.check,
            "where": self.where,
            "detail": self.detail,
        }

    def __str__(self) -> str:
        return "[{:<8}] {:<18} {}: {}".format(
            self.severity, self.check, self.where, self.detail)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
def check_footer(prose: str, tier: int) -> list:
    """Tier 3 must carry a filled, correctly-shaped verification footer.

    `prose` is already stripped of quoted regions by the caller.
    """
    out = []
    if tier < 3:
        return out

    if FOOTER_STRICT.search(prose):
        # A strict-shaped footer with a whitespace-only value is a blank footer: the
        # shape matched but no evidence was written (test_blank_verified_fails).
        m = FOOTER_STRICT.search(prose)
        first_line = prose[m.start():prose.find("\n", m.start())]
        if first_line.split(":", 1)[1].strip() == "":
            out.append(Finding(
                "CRITICAL", "footer-unfilled", "response",
                "footer has the correct shape but the Verified line is empty — "
                "a blank footer is not evidence"))
            return out
        ph = FOOTER_PLACEHOLDER.search(prose)
        if ph:
            out.append(Finding(
                "CRITICAL", "footer-unfilled", "response",
                "footer has the correct shape but still contains the template "
                "placeholder {!r} on line {} — a blank footer is not evidence".format(
                    ph.group(1)[:40], _line_of(prose, ph.start()))))
        return out

    if FOOTER_LOOSE.search(prose):
        out.append(Finding(
            "HIGH", "footer-shape", "response",
            "footer attempted but not in the specified three-line form "
            "(Verified:/Unverified:/Assumptions:) — a drifted footer is not "
            "machine-checkable"))
    else:
        out.append(Finding(
            "CRITICAL", "footer-missing", "response",
            "Tier 3 delivery carries no verification footer; the gate left no "
            "evidence that it ran"))
    return out


def check_ready_claim(prose: str, tier: int) -> list:
    """The '*-ready' prohibition is tier-INDEPENDENT.

    SKILL.md calls this "the actual guardrail". Scoping it to Tier 3 would make
    it dead code, because the Tier 3 footer check already fires on the same
    input -- proven by mutation testing, where disabling a tier-scoped version
    left the suite green. A Tier 1 draft may not call itself client-ready.

    `prose` is already stripped of quoted regions by the caller.
    """
    out = []
    if FOOTER_STRICT.search(prose) and not FOOTER_PLACEHOLDER.search(prose):
        return out
    for m in READY_CLAIM.finditer(prose):
        sentence = _sentence_containing(prose, m.start())
        if NEGATION_WORDS.search(sentence):
            continue  # label withheld or rule described -- not a violation
        out.append(Finding(
            "CRITICAL", "unbacked-claim", "response",
            "asserts {!r} on line {} without a filled verification footer; "
            "SKILL.md forbids this label on un-gated output (tier {})".format(
                m.group(0), _line_of(prose, m.start()), tier)))
        break
    return out


def check_artefact(path: Path, max_hits: int = 10) -> list:
    """Client-facing artefacts: no script drift, and no footer leaked in."""
    out = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        out.append(Finding("HIGH", "unreadable", str(path), str(exc)))
        return out

    hits = 0
    for m in CJK_FULL.finditer(text):
        ch = m.group(0)
        narrow_would_miss = not CJK_NARROW.match(ch)
        out.append(Finding(
            "CRITICAL", "cjk-drift", path.name,
            "line {} contains U+{:04X} {!r}{}".format(
                _line_of(text, m.start()), ord(ch), ch,
                "  (a [\\u4e00-\\u9fff] class would MISS this)"
                if narrow_would_miss else "")))
        hits += 1
        if hits >= max_hits:
            out.append(Finding(
                "INFO", "cjk-drift", path.name,
                "further drift hits suppressed after {}".format(max_hits)))
            break

    artefact_prose = strip_quoted(text)
    if FOOTER_STRICT.search(artefact_prose) or FOOTER_LOOSE.search(artefact_prose):
        out.append(Finding(
            "HIGH", "footer-placement", path.name,
            "verification footer found INSIDE a client-facing artefact; "
            "SKILL.md places it in the accompanying chat response only"))
    return out


def run(response_path, artefacts, tier: int) -> list:
    """Run every applicable check. Returns a list of Finding.

    An unreadable input yields a finding rather than an exception: a traceback
    from a gate is indistinguishable from the gate itself being broken, which
    is precisely the ambiguity a gate exists to remove.
    """
    findings = []
    if response_path is not None:
        try:
            response = Path(response_path).read_text(
                encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(Finding(
                "HIGH", "unreadable", str(response_path),
                "could not read the response file: {}".format(exc)))
        else:
            prose = strip_quoted(response)
            findings += check_footer(prose, tier)
            findings += check_ready_claim(prose, tier)
    for a in artefacts or []:
        findings += check_artefact(Path(a))
    return findings


def record_run(log_path, tier: int, findings: list, blocking: list,
               response_path=None, artefacts=None) -> None:
    """Append one JSON line describing this run.

    Deliberately best-effort: recording is observability, not the gate itself.
    A log that cannot be written must never turn a passing deliverable into a
    failing one, so every error here is swallowed.
    """
    try:
        import datetime
        record = {
            "timestamp": datetime.datetime.now(
                datetime.timezone.utc).isoformat(timespec="seconds"),
            "version": __version__,
            "tier": tier,
            "pass": not blocking,
            "blocking": len(blocking),
            "findings": len(findings),
            "checks_failed": sorted({f.check for f in blocking}),
            "response": str(response_path) if response_path else None,
            "artefacts": [str(a) for a in (artefacts or [])],
        }
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - never let logging fail the gate
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="quality_gate.py",
        description="Enforcement gate for the quality-guard skill.",
        epilog="Exit code 1 means the gate FAILED. See docs/how-it-works.md.")
    p.add_argument("--response", type=Path,
                   help="the chat response accompanying delivery")
    p.add_argument("--artefact", type=Path, action="append", default=[],
                   help="a client-facing artefact (repeatable)")
    p.add_argument("--tier", type=int, choices=(1, 2, 3), default=3,
                   help="risk tier of the deliverable (default: 3)")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="emit machine-readable JSON")
    p.add_argument("--log", type=Path, metavar="FILE",
                   help="append a JSON-lines run record to FILE (best-effort; "
                        "a log failure never fails the gate)")
    p.add_argument("--version", action="version",
                   version="quality_gate.py {}".format(__version__))
    args = p.parse_args(argv)

    if not args.response and not args.artefact:
        p.error("need --response and/or --artefact")

    findings = run(args.response, args.artefact, args.tier)
    blocking = [f for f in findings if f.severity in BLOCKING]

    if args.log:
        record_run(args.log, args.tier, findings, blocking,
                   args.response, args.artefact)

    if args.as_json:
        print(json.dumps({
            "version": __version__,
            "tier": args.tier,
            "pass": not blocking,
            "blocking": len(blocking),
            "findings": [f.as_dict() for f in findings],
        }, indent=2, ensure_ascii=False))
    else:
        for f in findings:
            print(f)
        if not findings:
            print("No findings.")
        print("\nGATE {} — {} blocking, {} total".format(
            "FAILED" if blocking else "PASSED", len(blocking), len(findings)))

    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
