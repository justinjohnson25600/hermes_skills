#!/usr/bin/env python3
"""Release consistency gate for hermes_skills.

Exists because a version bump touched SKILL.md and skill.json but left both
READMEs a version behind, and that shipped to a public repo. Twice in one day
the docs disagreed with the code. Remembering to check is not a control; this
is.

Checks, per skill:
  1. Every version string agrees (skill.json, SKILL.md frontmatter, the skill's
     own README, the repo-root table, and the newest CHANGELOG heading).
  2. Test-count claims in the docs match what the suite actually reports.
  3. `platforms:` frontmatter is a plausible list and matches any shim the
     installer writes for that platform.
  4. The live install under the Hermes home (if present on this machine) is
     byte-identical for code, and differs from the repo SKILL.md ONLY by the
     known machine-local deltas.
  5. The local branch is not behind origin — a claim about remote state made
     from a stale ref is worthless.

Exit 0 = consistent. Exit 1 = drift (details printed). Use as a pre-push hook.

    python3 check_consistency.py            # check everything
    python3 check_consistency.py --fix      # repair what is safely repairable
    python3 check_consistency.py --no-fetch # skip the network check
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# SKILL.md lines that are DELIBERATELY different in a live install: absolute
# machine paths and the local interpreter. Anything else differing is drift.
LIVE_ONLY_MARKERS = ("~/.hermes/", "~/.hv/", "author:")

problems: list[str] = []
fixes: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def note(msg: str) -> None:
    notes.append(msg)


def sh(*args: str, cwd: Path | None = None) -> str:
    try:
        p = subprocess.run(args, cwd=cwd or ROOT, capture_output=True, text=True,
                           timeout=60)
        return (p.stdout or "").strip()
    except Exception:
        return ""


def skills() -> list[str]:
    return sorted(p.name for p in ROOT.iterdir()
                  if p.is_dir() and (p / "SKILL.md").is_file())


def hermes_home() -> Path | None:
    env = os.environ.get("HERMES_HOME")
    if env and Path(env).is_dir():
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    cands = ([Path(local) / "hermes"] if local else []) + [Path.home() / ".hermes"]
    try:
        cands += sorted(p for p in Path.home().glob(".*") if p.is_dir())
    except OSError:
        pass
    for c in cands:
        try:
            if c.is_dir() and ((c / "config.yaml").is_file() or (c / "skills").is_dir()):
                return c
        except OSError:
            continue
    return None


# ---------------------------------------------------------------------------
def check_versions(skill: str, fix: bool) -> str | None:
    """All five version strings must agree. skill.json is the source of truth."""
    d = ROOT / skill
    sj = json.loads((d / "skill.json").read_text(encoding="utf-8"))
    truth = sj["version"]
    found: dict[str, tuple[str, Path, str]] = {}

    sk = (d / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\S+)", sk, re.M)
    if m:
        found["SKILL.md frontmatter"] = (m.group(1), d / "SKILL.md",
                                         f"version: {m.group(1)}")

    rd_path = d / "README.md"
    if rd_path.is_file():
        rd = rd_path.read_text(encoding="utf-8")
        m = re.search(r"Current:\s*\*\*(\S+?)\*\*", rd)
        if m:
            found["skill README 'Current:'"] = (m.group(1), rd_path,
                                                f"Current: **{m.group(1)}**")

    root_readme = ROOT / "README.md"
    if root_readme.is_file():
        rr = root_readme.read_text(encoding="utf-8")
        m = re.search(rf"\[{re.escape(skill)}\]\({re.escape(skill)}/\)\s*\|\s*(\S+?)\s*\|", rr)
        if m:
            found["repo-root table"] = (m.group(1), root_readme,
                                        f"| [{skill}]({skill}/) | {m.group(1)} |")

    cl = d / "CHANGELOG.md"
    if cl.is_file():
        heads = re.findall(r"^##\s*(\d+\.\d+\.\d+)", cl.read_text(encoding="utf-8"), re.M)
        if heads and heads[0] != truth:
            fail(f"[{skill}] newest CHANGELOG entry is {heads[0]} but "
                 f"skill.json says {truth} — the release is undocumented")
        # This repo's rule: skills increment by +0.0.1 per published change.
        # A wrong bump is invisible to every other check here, because all five
        # version strings agree with each other — they are just agreeing on the
        # wrong number.
        if len(heads) >= 2:
            try:
                new_v = tuple(int(x) for x in heads[0].split("."))
                prev = tuple(int(x) for x in heads[1].split("."))
            except ValueError:
                new_v = prev = None
            if new_v and prev:
                expected = (prev[0], prev[1], prev[2] + 1)
                if new_v != expected and new_v <= prev:
                    fail(f"[{skill}] CHANGELOG goes {heads[1]} -> {heads[0]}, "
                         f"which is not an increase")
                elif new_v != expected:
                    note(f"[{skill}] CHANGELOG jumps {heads[1]} -> {heads[0]}; "
                         f"this repo increments +0.0.1 per change "
                         f"(expected {'.'.join(map(str, expected))}) — "
                         f"deliberate major/minor bumps are fine, confirm it was one")

    for where, (ver, path, needle) in found.items():
        if ver == truth:
            continue
        if fix:
            txt = path.read_text(encoding="utf-8")
            txt = txt.replace(needle, needle.replace(ver, truth), 1)
            path.write_text(txt, encoding="utf-8")
            fixes.append(f"[{skill}] {where}: {ver} -> {truth}")
        else:
            fail(f"[{skill}] {where} says {ver}, skill.json says {truth}")
    return truth


def check_test_counts(skill: str, fix: bool) -> None:
    """Docs claim 'N regression tests (M checks)'. Run the suite and compare."""
    d = ROOT / skill
    verify = json.loads((d / "skill.json").read_text(encoding="utf-8")).get("verify")
    if not verify or not (d / verify).is_file():
        return
    out = sh(sys.executable, str(d / verify), cwd=d)
    m = re.search(r"(\d+)\s+passed,\s+(\d+)\s+failed", out)
    if not m:
        note(f"[{skill}] could not read a pass/fail line from {verify}")
        return
    checks, failed = int(m.group(1)), int(m.group(2))
    if failed:
        fail(f"[{skill}] its own suite reports {failed} FAILED check(s)")
    tests = len(re.findall(r"^\s*test_\w+,\s*$", (d / verify).read_text(encoding="utf-8"), re.M))

    for path in (d / "SKILL.md", d / "README.md"):
        if not path.is_file():
            continue
        txt = path.read_text(encoding="utf-8")
        for claim_t, claim_c in re.findall(r"(\d+)\s+regression tests?\s*\((\d+)\s+checks?\)", txt):
            if int(claim_c) != checks:
                if fix:
                    txt = txt.replace(f"{claim_t} regression tests ({claim_c} checks)",
                                      f"{tests} regression tests ({checks} checks)")
                    path.write_text(txt, encoding="utf-8")
                    fixes.append(f"[{skill}] {path.name}: {claim_c} -> {checks} checks")
                else:
                    fail(f"[{skill}] {path.name} claims {claim_c} checks, "
                         f"the suite reports {checks}")
        for claim_c in re.findall(r"#\s*(\d+)\s+checks,\s*no network", txt):
            if int(claim_c) != checks:
                if fix:
                    path.write_text(txt.replace(f"# {claim_c} checks, no network",
                                                f"# {checks} checks, no network"),
                                    encoding="utf-8")
                    fixes.append(f"[{skill}] {path.name}: inline count -> {checks}")
                else:
                    fail(f"[{skill}] {path.name} inline comment claims {claim_c} checks, "
                         f"the suite reports {checks}")


def check_platforms(skill: str) -> None:
    sk = (ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^platforms:\s*\[([^\]]*)\]", sk, re.M)
    if not m:
        fail(f"[{skill}] SKILL.md has no `platforms:` frontmatter — Hermes filters "
             f"on it, so the skill would be invisible everywhere")
        return
    declared = {p.strip() for p in m.group(1).split(",") if p.strip()}
    known = {"macos", "linux", "windows"}
    if bad := declared - known:
        fail(f"[{skill}] unknown platform(s) in frontmatter: {sorted(bad)}")
    # If the code ships a Windows codepath, the frontmatter must admit it.
    src = " ".join((ROOT / skill / f).read_text(encoding="utf-8", errors="replace")
                   for f in os.listdir(ROOT / skill) if f.endswith(".py"))
    if ("msvcrt" in src or "LOCALAPPDATA" in src) and "windows" not in declared:
        fail(f"[{skill}] code has Windows support (msvcrt/LOCALAPPDATA) but "
             f"`platforms:` omits windows — it would install and stay invisible")


def check_live_install(skill: str, fix: bool) -> None:
    """The published copy and the copy actually running must not diverge."""
    home = hermes_home()
    if not home:
        note("no Hermes home on this machine — skipped the live-install check")
        return
    sj = json.loads((ROOT / skill / "skill.json").read_text(encoding="utf-8"))
    state = home / (sj.get("state_dir") or skill)
    live_skill = home / "skills" / sj.get("category", "") / skill / "SKILL.md"

    for f in sj.get("files", []):
        repo_f, live_f = ROOT / skill / f, state / f
        if not live_f.is_file():
            note(f"[{skill}] {f} not installed live — skipped")
            continue
        if repo_f.read_bytes() != live_f.read_bytes():
            if fix:
                live_f.write_bytes(repo_f.read_bytes())
                fixes.append(f"[{skill}] live {f} resynced from repo")
            else:
                fail(f"[{skill}] live {f} differs from the repo copy")

    if not live_skill.is_file():
        note(f"[{skill}] no live SKILL.md at {live_skill} — skipped")
        return
    repo_lines = (ROOT / skill / "SKILL.md").read_text(encoding="utf-8").splitlines()
    live_lines = live_skill.read_text(encoding="utf-8").splitlines()
    if len(repo_lines) != len(live_lines):
        fail(f"[{skill}] live SKILL.md has {len(live_lines)} lines, repo has "
             f"{len(repo_lines)} — structural drift, resync it")
        return
    for i, (r, l) in enumerate(zip(repo_lines, live_lines), 1):
        if r == l:
            continue
        if any(mk in l for mk in LIVE_ONLY_MARKERS):
            continue  # a deliberate machine-local path/author difference
        fail(f"[{skill}] live SKILL.md line {i} drifted (not a known local delta):\n"
             f"      repo: {r.strip()[:80]}\n      live: {l.strip()[:80]}")


def check_remote(no_fetch: bool) -> None:
    """A claim about the remote made from an unfetched ref is worthless."""
    if no_fetch:
        note("--no-fetch: did not compare against origin")
        return
    if not sh("git", "remote"):
        return
    subprocess.run(["git", "fetch", "--quiet", "origin"], cwd=ROOT,
                   capture_output=True, timeout=120)
    counts = sh("git", "rev-list", "--left-right", "--count", "origin/main...HEAD")
    if not counts:
        return
    try:
        behind, ahead = (int(x) for x in counts.split())
    except ValueError:
        return
    if behind:
        fail(f"local is {behind} commit(s) BEHIND origin/main — pull before "
             f"asserting anything about the published state")
    if ahead:
        note(f"local is {ahead} commit(s) ahead of origin/main (unpushed)")


def check_index() -> None:
    """skills.json backs the installer's remote --list; a stale one lies."""
    idx = ROOT / "skills.json"
    if not idx.is_file():
        note("no skills.json — the installer's remote --list will fall back")
        return
    listed = set(json.loads(idx.read_text(encoding="utf-8")))
    actual = set(skills())
    if listed != actual:
        fail(f"skills.json is stale: lists {sorted(listed)}, repo has {sorted(actual)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="repair what is safely repairable")
    ap.add_argument("--no-fetch", action="store_true", help="skip the origin comparison")
    a = ap.parse_args()

    check_remote(a.no_fetch)
    check_index()
    for s in skills():
        v = check_versions(s, a.fix)
        check_test_counts(s, a.fix)
        check_platforms(s)
        check_live_install(s, a.fix)
        if v:
            print(f"  {s}: {v}")

    for f in fixes:
        print(f"  FIXED   {f}")
    for n in notes:
        print(f"  note    {n}")
    if problems:
        print(f"\n{len(problems)} consistency problem(s):")
        for p in problems:
            print(f"  DRIFT   {p}")
        if not a.fix:
            print("\nRun with --fix to repair the mechanical ones.")
        return 1
    print("\nconsistent." + (" (after fixes)" if fixes else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
