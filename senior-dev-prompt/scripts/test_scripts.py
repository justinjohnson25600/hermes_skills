#!/usr/bin/env python3
"""Tests for senior-dev-prompt's helper scripts, plus static checks of the skill.

Run:  python3 scripts/test_scripts.py      (standard library only, no network)
The installer runs this file after every install (skill.json "verify_skill").
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))

import lint_brief  # noqa: E402
import scout  # noqa: E402

PASS, FAIL = [], []


def check(name: str, cond: object, detail: object = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
# lint_brief.py
# --------------------------------------------------------------------------
FULL_T2 = """# Brief: Example task tracker

**Metadata:** version: 1 · status: draft · date: 2026-10-11 · tier: T2 · type: new app · route: superpowers writing-plans then executing-plans then verification-before-completion · pack: web-app · risk: personal data · self-review: 1 fixed

## 1. For you
You get a small web page where you add tasks and tick them off (SC-1). You provide a computer with Python 3.11. Nothing waits for your decision. Effort: one session.

## 2. Operating obligations
Follow the workflow mandate; show evidence before claiming done; stop at the conditions in section 13.

## 3. Original request
> make me a todo app TODO make it nice <whatever> {thing}

## 4. Context
Greenfield: a new folder `task-tracker` under the workspace. Reuse check: no installed skill does this.

## 5. Outcome, users and scenario
- SC-1: the user adds "buy milk" and still sees it after a reload.
- SC-2: with no tasks the page says "No tasks yet".

## 6. Scope and deliverables
In: the page and its storage. Out: accounts, replaced by a single local user.

## 7. Requirements and safeguards
- FR-1: add a task. FR-2: mark a task done.
- NFR-1: works offline on one machine.
- SG-1: tasks are stored only on this machine.

## 8. Approach and design
Flask with SQLite. Rejected: a JavaScript framework (more moving parts).

## 9. Decision register
| Decision | Choice | Status | Why | Override |
|---|---|---|---|---|
| Storage | SQLite file | ASSUMED | no server needed | say "use Postgres" |

## 10. Prerequisites you provide
Python 3.11. No secrets.

## 11. Workflow mandate
Route: superpowers writing-plans, executing-plans, verification-before-completion. First task: encode AC-1 to AC-4 as failing tests.

## 12. Acceptance criteria and verification
| AC | Covers | Check | Evidence |
|---|---|---|---|
| AC-1 | FR-1, SC-1 | add a task, reload, it is listed | pytest output |
| AC-2 | FR-2 | mark done, it shows as done | pytest output |
| AC-3 | NFR-1, SG-1 | run with networking off; data file is local | test log |
| AC-4 | SC-2 | empty store shows "No tasks yet" | pytest output |

## 13. Boundaries and stop conditions
Ask before deleting data. Stop if an AC cannot be met.

## 14. Risks and mitigations
Data loss: back up the SQLite file before any migration.

## 15. Definition of done
Every row in section 12 passes with its evidence.
"""

COMPACT_T1 = """# Brief: Rename photos by date

**Metadata:** version: 1 · status: draft · date: 2026-10-11 · tier: T1 · type: new tool · route: inline test-first then verify · pack: script-cli · risk: user-data mutation

## For you
You get a script that renames photos to the date they were taken (SC-1). Nothing waits for your decision.

## Objective and scenario
- SC-1: IMG_0001.jpg taken 2024-05-01 10:00:00 becomes 2024-05-01_100000.jpg.
- SC-2: a photo with no date is left alone and reported.

## Scope
In: one folder of JPEG files. Out: videos, later.

## Decisions
| Decision | Choice | Status |
|---|---|---|
| Name format | YYYY-MM-DD_HHMMSS | ASSUMED |

## Safeguards
- SG-1: dry-run by default; --apply renames.
- SG-2: never overwrite; add a suffix on collision.

## Route
Inline: failing tests first, then the script, then verify.

## Acceptance criteria
| AC | Covers | Check | Evidence |
|---|---|---|---|
| AC-1 | SC-1, SG-1 | dry-run lists the rename; --apply performs it | test output |
| AC-2 | SC-2 | undated file untouched and reported | test output |
| AC-3 | SG-2 | two photos with the same timestamp both survive | test output |

## Stop conditions
Stop and ask before touching any folder other than the one given.
"""


def codes(text, **kw):
    return sorted({f["code"] for f in lint_brief.lint_text(text, **kw)})


def test_lint():
    print("\n[lint] the self-check catches each defect class and passes clean briefs")
    check("clean full T2 brief passes", codes(FULL_T2) == [], lint_brief.lint_text(FULL_T2))
    check("clean compact T1 brief passes", codes(COMPACT_T1) == [], lint_brief.lint_text(COMPACT_T1))
    check("quoted request is exempt from the placeholder lint", "PLACEHOLDER" not in codes(FULL_T2))
    no_meta = "\n".join(l for l in FULL_T2.splitlines() if not l.startswith("**Metadata:**"))
    check("missing metadata line", "NO_METADATA" in codes(no_meta))
    check("invalid status", "BAD_STATUS" in codes(FULL_T2.replace("status: draft", "status: shipping")))
    check("invalid tier", "BAD_TIER" in codes(FULL_T2.replace("tier: T2", "tier: T9")))
    no_route = FULL_T2.replace(" · route: superpowers writing-plans then executing-plans then verification-before-completion", "")
    check("missing required metadata key", "META_MISSING_KEY" in codes(no_route))
    cut = FULL_T2.split("## 13. Boundaries and stop conditions")
    no_stop = cut[0] + "## 14." + cut[1].split("## 14.", 1)[1]
    check("missing stop-conditions section", "MISSING_SECTION" in codes(no_stop))
    s9 = FULL_T2[FULL_T2.index("## 9. Decision register"):FULL_T2.index("## 10. Prerequisites")]
    s10 = FULL_T2[FULL_T2.index("## 10. Prerequisites"):FULL_T2.index("## 11. Workflow mandate")]
    swapped = FULL_T2.replace(s9 + s10, s10 + s9)
    check("sections out of order", "SECTION_ORDER" in codes(swapped))
    ph = FULL_T2.replace("Route: superpowers writing-plans,", "Route: gsd-plan-phase <N> --prd <brief path>, superpowers writing-plans,")
    check("placeholder in a route is flagged", "PLACEHOLDER" in codes(ph))
    meta_ph = FULL_T2.replace("route: superpowers writing-plans then", "route: gsd-plan-phase <N> then")
    check("placeholder in the metadata route is flagged", "PLACEHOLDER" in codes(meta_ph))
    check("TBD in generated text is flagged", "PLACEHOLDER" in codes(FULL_T2.replace("Python 3.11. No secrets.", "Python TBD.")))
    check("[insert ...] is flagged", "PLACEHOLDER" in codes(FULL_T2.replace("No secrets.", "[insert API key name].")))
    benign = FULL_T2.replace("Flask with SQLite.", "Flask with SQLite; the list is a `<ul>` and items load from `/tasks/{id}`; a todo app.")
    check("HTML tags, URL path parameters and lower-case 'todo' are not placeholders", "PLACEHOLDER" not in codes(benign),
          lint_brief.lint_text(benign))
    uncovered = FULL_T2.replace("- NFR-1: works offline", "- FR-3: export tasks to CSV.\n- NFR-1: works offline")
    check("FR without an AC row", "UNCOVERED_ID" in codes(uncovered))
    withdrawn = FULL_T2.replace("- NFR-1: works offline", "- FR-3: export tasks to CSV (withdrawn in v2).\n- NFR-1: works offline")
    check("a withdrawn ID needs no AC row", "UNCOVERED_ID" not in codes(withdrawn), lint_brief.lint_text(withdrawn))
    no_sc = FULL_T2.replace("| AC-4 | SC-2 |", "| AC-4 | FR-2 |")
    check("scenario without an AC row", "UNCOVERED_ID" in codes(no_sc))
    check("AC row without a check", "AC_NO_CHECK" in codes(FULL_T2.replace("| mark done, it shows as done |", "|  |")))
    check("AC row without evidence", "AC_NO_EVIDENCE" in codes(FULL_T2.replace("| test log |", "| — |")))
    no_rows = "\n".join(l for l in FULL_T2.splitlines() if not l.startswith("| AC-"))
    check("AC section with no rows", "NO_AC_ROWS" in codes(no_rows))
    check("compact brief over its budget", "OVER_BUDGET" in codes(COMPACT_T1 + "\n" + ("word " * 400)))
    check("full brief within budget", "OVER_BUDGET" not in codes(FULL_T2))
    quoted = COMPACT_T1.replace("## Scope", "> " + ("quoted " * 400) + "\n\n## Scope")
    check("quoted material does not count toward the budget", "OVER_BUDGET" not in codes(quoted), lint_brief.lint_text(quoted))
    check("risk flag without a Safeguards section (compact)", "MISSING_SECTION" in codes(
        COMPACT_T1[:COMPACT_T1.index("## Safeguards")] + COMPACT_T1[COMPACT_T1.index("## Route"):]))
    no_sg = FULL_T2.replace("- SG-1: tasks are stored only on this machine.\n", "").replace("NFR-1, SG-1", "NFR-1")
    check("risk flag without any safeguard (full)", "NO_SAFEGUARD" in codes(no_sg))
    no_risk = no_sg.replace("risk: personal data", "risk: none")
    check("risk none needs no safeguard", "NO_SAFEGUARD" not in codes(no_risk), lint_brief.lint_text(no_risk))
    reviewed = FULL_T2.replace("self-review: 1 fixed", "self-review: 1 fixed · snapshot: 3f9a1c2b") + "\n## 16. Co-developer review\n| R1 | suggests FR-9 TBD | REJECT |\n"
    check("co-developer section is exempt (IDs and placeholders)", codes(reviewed) == [], lint_brief.lint_text(reviewed))
    check("a reviewed brief must carry the snapshot hash", "META_MISSING_KEY" in codes(FULL_T2 + "\n## 16. Co-developer review\nnone\n"))
    check("--tier overrides the metadata tier", "OVER_BUDGET" in codes(FULL_T2, tier="T1") or "MISSING_SECTION" in codes(FULL_T2, tier="T1"))
    check("full schema is pinned (15 sections)", lint_brief.FULL_SECTIONS == [
        "For you", "Operating obligations", "Original request", "Context", "Outcome, users and scenario",
        "Scope and deliverables", "Requirements and safeguards", "Approach and design", "Decision register",
        "Prerequisites you provide", "Workflow mandate", "Acceptance criteria and verification",
        "Boundaries and stop conditions", "Risks and mitigations", "Definition of done"], lint_brief.FULL_SECTIONS)
    check("compact schema is pinned (8 sections)", lint_brief.COMPACT_SECTIONS == [
        "For you", "Objective and scenario", "Scope", "Decisions", "Safeguards", "Route", "Acceptance criteria",
        "Stop conditions"], lint_brief.COMPACT_SECTIONS)
    for key in ("status", "date", "pack"):
        cut_meta = re.sub(r" · " + key + r": [^·\n]+", "", FULL_T2)
        check(f"missing '{key}' key is flagged", "META_MISSING_KEY" in codes(cut_meta), lint_brief.lint_text(cut_meta))
    check("T2 without a self-review result is flagged", "META_MISSING_KEY" in codes(FULL_T2.replace(" · self-review: 1 fixed", "")))
    check("T1 needs no self-review key", codes(COMPACT_T1) == [])
    interp = FULL_T2.replace("> make me a todo app TODO make it nice <whatever> {thing}\n",
                             "> make me a todo app TODO make it nice <whatever> {thing}\n\nInterpretation: the app is TBD.\n")
    check("generated text inside the request section is still linted", "PLACEHOLDER" in codes(interp))
    quoted_elsewhere = FULL_T2.replace("## 10. Prerequisites you provide\n", "## 10. Prerequisites you provide\n> user said: key TBD <later>\n\n")
    check("quoted user material elsewhere is exempt", "PLACEHOLDER" not in codes(quoted_elsewhere), lint_brief.lint_text(quoted_elsewhere))
    check("{token} is flagged", "PLACEHOLDER" in codes(FULL_T2.replace("No secrets.", "Store it in {secret store}.")))
    for ok_text in ("see <!-- note -->", "docs at <https://example.org/x>", "line<br>break", "returns Promise<void>", "ask <person@example.org>"):
        t = FULL_T2.replace("No secrets.", f"No secrets; {ok_text}.")
        check(f"not a placeholder: {ok_text}", "PLACEHOLDER" not in codes(t), lint_brief.lint_text(t))
    for tier, base_text in (("T0", COMPACT_T1), ("T1", COMPACT_T1), ("T2", FULL_T2), ("T3", FULL_T2), ("T4", FULL_T2)):
        txt = base_text.replace(re.search(r"tier: T\d", base_text).group(0), "tier: " + tier)
        rep = lint_brief.lint_report(txt)
        room = rep["budget"] - rep["words"]
        under = txt + "\n" + ("word " * (room - 5))
        over = txt + "\n" + ("word " * (room + 5))
        check(f"{tier}: budget {rep['budget']} holds just under", "OVER_BUDGET" not in codes(under), lint_brief.lint_report(under)["words"])
        check(f"{tier}: budget {rep['budget']} fails just over", "OVER_BUDGET" in codes(over), lint_brief.lint_report(over)["words"])
    exact = FULL_T2.replace("| AC-1 | FR-1, SC-1 |", "| AC-1 | FR-10, SC-1 |")
    check("IDs match exactly (FR-10 does not cover FR-1)", "UNCOVERED_ID" in codes(exact))
    amp = FULL_T2.replace("## 6. Scope and deliverables", "## 6. Scope & deliverables")
    check("'&' in a heading reads as 'and'", codes(amp) == [], lint_brief.lint_text(amp))


def _run_script(name, *args, env=None):
    return subprocess.run([sys.executable, str(HERE / name), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=180)


def test_lint_cli():
    print("\n[lint] command line: exit codes and JSON")
    with tempfile.TemporaryDirectory() as td:
        good, bad = Path(td) / "good.md", Path(td) / "bad.md"
        good.write_text(FULL_T2, encoding="utf-8")
        bad.write_text(FULL_T2.replace("status: draft", "status: shipping"), encoding="utf-8")
        r = _run_script("lint_brief.py", str(good))
        check("clean brief exits 0 and says PASS", r.returncode == 0 and "PASS" in r.stdout, r.stdout + r.stderr)
        r = _run_script("lint_brief.py", str(bad))
        check("defective brief exits 1 and names the code", r.returncode == 1 and "BAD_STATUS" in r.stdout, r.stdout + r.stderr)
        r = _run_script("lint_brief.py", str(bad), "--json")
        try:
            data = json.loads(r.stdout)
        except ValueError:
            data = {}
        check("--json is machine-readable", data.get("ok") is False and any(f["code"] == "BAD_STATUS" for f in data.get("findings", [])),
              r.stdout[-200:])
        r = _run_script("lint_brief.py", str(Path(td) / "missing.md"))
        check("missing file exits 2", r.returncode == 2, r.stderr)
        spaced = Path(td) / "with space" / "brief é.md"
        spaced.parent.mkdir()
        spaced.write_text(FULL_T2, encoding="utf-8")
        r = _run_script("lint_brief.py", str(spaced))
        check("a path with spaces and non-ASCII characters works", r.returncode == 0 and "PASS" in r.stdout, r.stdout + r.stderr)
        r = _run_script("lint_brief.py", str(good), "--tier", "T9")
        check("bad --tier is a usage error (exit 2)", r.returncode == 2, r.stderr)


# --------------------------------------------------------------------------
# scout.py — driven through a stub `hermes`, never the real one
# --------------------------------------------------------------------------
STUB = r'''
import json, os, sys, time
a = sys.argv[1:]
def _record(prefix, line):
    # One file per call: concurrent appends to one file lose lines on Windows.
    with open(f"{prefix}.{os.getpid()}.{time.time_ns()}", "w", encoding="utf-8") as fh:
        fh.write(line + "\n")
_record(os.environ["STUB_LOG"], json.dumps(a))
if os.environ.get("STUB_TIMES"):
    t0 = time.time()
    time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
    _record(os.environ["STUB_TIMES"], json.dumps([t0, time.time()]))
if a[:2] == ["skills", "list"]:
    if os.environ.get("STUB_LIST_FAIL"):
        sys.stderr.write("list exploded\n")
        sys.exit(1)
    print("   ┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓")
    print("   ┃ Name ┃ Category ┃ Source ┃ Trust ┃ Status ┃")
    for n in ("brainstorming", "verification-before-completion", "alpha-installed", "gamma-local"):
        print("   │ %s │ x │ local │ local │ enabled │" % n)
    print("   │ off-skill │ x │ local │ local │ disabled │")
    sys.exit(0)
if a[:2] == ["skills", "search"]:
    q = a[2]
    if q == "slow":
        time.sleep(8)
    if q == "boom":
        sys.stderr.write("boom failed\n")
        sys.exit(1)
    if q == "badjson":
        print("this is not json")
        sys.exit(0)
    data = {
        "alpha": [{"name": "unrelated-pro", "identifier": "x/unrelated", "source": "github", "trust_level": "trusted", "description": "does something else"},
                  {"name": "Alpha Tool", "identifier": "x/alpha", "source": "official", "trust_level": "official", "description": "does alpha"},
                  {"name": "alpha-tool", "identifier": "y/alpha-copy", "source": "skills.sh", "trust_level": "community", "description": "Indexed by skills.sh · 5 installs"},
                  {"name": "Dup", "identifier": "x/dup", "source": "skills.sh", "trust_level": "community", "description": "Indexed by skills.sh from x · 1,234 installs"},
                  {"name": "alpha-installed", "identifier": "x/alpha-installed", "source": "clawhub", "trust_level": "community", "description": "already here"}],
        "beta": [{"name": "Dup", "identifier": "x/dup", "source": "skills.sh", "trust_level": "community", "description": "Indexed by skills.sh from x · 1,234 installs"},
                 {"name": "Beta Pro", "identifier": "x/beta", "source": "clawhub", "trust_level": "trusted", "description": "beta things"},
                 {"name": "beta-lite", "identifier": "x/betalite", "source": "skills.sh", "trust_level": "community", "description": "Indexed by skills.sh from z · 10 installs"},
                 {"name": "Beta Pop", "identifier": "x/betapop", "source": "skills.sh", "trust_level": "community", "description": "Indexed by skills.sh from y · 9,999 installs"}],
        "writing-plans": [{"name": "writing-plans-lite", "identifier": "x/lite", "source": "skills.sh", "trust_level": "community", "description": "near miss"},
                          {"name": "writing-plans", "identifier": "x/superpowers/writing-plans", "source": "github", "trust_level": "trusted", "description": "plans"}],
    }.get(q, [])
    print(json.dumps(data))
    sys.exit(0)
if a[:2] == ["plugins", "search"]:
    time.sleep(float(os.environ.get("STUB_SLOW_CATALOG", "0")))
    # The real CLI: no term lists the whole catalog; a term is a case-insensitive substring
    # match over name, description and declared tools.
    q = a[2] if len(a) > 2 and not a[2].startswith("--") else ""
    catalog = [
        {"name": "alpha-plugin", "tier": "community", "maintainer": "m", "description": "plugin for alpha", "platforms": []},
        {"name": "here-plugin", "tier": "community", "maintainer": "m", "description": "alpha helper that runs here",
         "platforms": [os.environ.get("STUB_OS", "x")]},
        {"name": "elsewhere-only", "tier": "official", "maintainer": "m", "description": "beta tool", "platforms": ["no-such-os"]},
        {"name": "tooly-plugin", "tier": "community", "maintainer": "m", "description": "does other things", "platforms": [],
         "capabilities": {"provides_tools": ["beta_lookup"]}},
    ]
    hits = [e for e in catalog if not q or any(q.lower() in h.lower() for h in
            [e["name"], e["description"], *(e.get("capabilities") or {}).get("provides_tools", [])])]
    print(json.dumps({"query": q, "results": hits}))
    sys.exit(0)
sys.exit(3)
'''


def _scout_env(td):
    stub = Path(td) / "stub_hermes.py"
    stub.write_text(STUB, encoding="utf-8")
    log = Path(td) / "stub.log"
    packs = Path(td) / "packs"
    packs.mkdir()
    (packs / "test-pack.md").write_text("# Test pack\n\n## Common pitfalls\n- not a term\n\n## Tool search terms\n- alpha\n- `beta`\n", encoding="utf-8")
    return json.dumps([sys.executable, str(stub)]), log, packs


def _records(prefix: Path) -> str:
    """Every per-call record the stub wrote under this prefix, joined."""
    return "".join(p.read_text(encoding="utf-8") for p in sorted(prefix.parent.glob(prefix.name + ".*")))


def run_scout(td, *args, extra_env=None):
    cmd, log, packs = _scout_env(td)
    env = dict(os.environ, STUB_LOG=str(log), PYTHONIOENCODING="utf-8", STUB_OS=scout._os_name(), **(extra_env or {}))
    r = _run_script("scout.py", "--hermes-cmd", cmd, "--packs-dir", str(packs), *args, env=env)
    return r, _records(log)


def test_scout():
    print("\n[scout] search, dedupe, rank and report; never install")
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--pack", "test-pack", "--want", "writing-plans", "verification-before-completion", "--json", "--max", "12")
        try:
            d = json.loads(r.stdout)
        except ValueError:
            d = {}
        tools = d.get("tools", [])
        ids = [t["id"] for t in tools]
        check("exit 0 and JSON parses", r.returncode == 0 and bool(d), r.stdout[-300:] + r.stderr[-300:])
        check("pack terms become queries (bullets under that heading only)", d.get("queries") == ["alpha", "beta"], d.get("queries"))
        check("duplicates collapse to one entry", ids.count("x/dup") == 1, ids)
        check("installed skills are marked", any(t["id"] == "x/alpha-installed" and t["installed"] for t in tools), tools)
        check("missing workflow skills are listed", d.get("missing") == ["writing-plans"], d.get("missing"))
        ranked = [t["id"] for t in tools if not t["installed"]]
        check("official ranks above trusted above community",
              all(x in ranked for x in ("x/alpha", "x/beta", "x/dup")) and ranked.index("x/alpha") < ranked.index("x/beta") < ranked.index("x/dup"), ranked)
        check("installs parsed from the description", any(t["id"] == "x/dup" and t["installs"] == 1234 for t in tools), tools)
        check("plugins for another OS are dropped", "plugin:elsewhere-only" not in ids, ids)
        check("plugins are included and flagged as code", any(t["id"] == "plugin:alpha-plugin" and t.get("note") for t in tools), tools)
        calls = []
        for line in raw.splitlines():
            try:
                calls.append(tuple(json.loads(line)[:2]))
            except ValueError:
                pass
        allowed = {("skills", "list"), ("skills", "search"), ("plugins", "search")}
        check("the stub was really called (list, skill and plugin searches)",
              {("skills", "list"), ("skills", "search"), ("plugins", "search")} <= set(calls), calls)
        check("every call is read-only (never an install)", bool(calls) and set(calls) <= allowed and '"install"' not in raw, calls)
        check("plugins for this OS are kept", "plugin:here-plugin" in ids, ids)
        check("more installs rank first at equal fit and trust", "x/betapop" in ids and "x/betalite" in ids
              and ids.index("x/betapop") < ids.index("x/betalite"), ids)
        check("a relevant community skill ranks above an irrelevant trusted one (fit first)",
              "x/unrelated" in ids and ids.index("x/betapop") < ids.index("x/unrelated"), ids)
        check("each tool reports its fit score", all(isinstance(t.get("fit"), (int, float)) for t in tools), tools[:2])
        alpha = next((t for t in tools if t["id"] == "x/alpha"), {})
        check("same-name copies from other sources collapse into the best one", "y/alpha-copy" not in ids and alpha.get("also") == 1, (ids, alpha))
        cand = (d.get("missing_candidates") or {}).get("writing-plans") or {}
        check("a missing workflow skill gets its exact-name install candidate", cand.get("id") == "x/superpowers/writing-plans", d.get("missing_candidates"))
        check("candidate lookups do not use the five query terms", d.get("queries") == ["alpha", "beta"], d.get("queries"))
        plugin_calls = [json.loads(l) for l in raw.splitlines() if l.startswith('["plugins", "search"')]
        check("the plugin catalog is fetched once, with no search term",
              len(plugin_calls) == 1 and plugin_calls[0][2:] == ["--json"], plugin_calls)
        check("a plugin matches a term through its declared tools", "plugin:tooly-plugin" in ids, ids)
    with tempfile.TemporaryDirectory() as td:
        times = Path(td) / "times.log"
        r, raw = run_scout(td, "--terms", "alpha,beta,gamma,delta,epsilon", "--want", "writing-plans", "--json",
                           extra_env={"STUB_TIMES": str(times), "STUB_SLEEP": "0.6"})
        spans = [json.loads(l) for l in _records(times).splitlines() if l.strip()]
        edges = sorted([(s, 1) for s, _ in spans] + [(e, -1) for _, e in spans], key=lambda x: (x[0], x[1]))
        live = peak = 0
        for _, step in edges:
            live += step
            peak = max(peak, live)
        check("at most 3 hermes processes run at once", 2 <= peak <= scout.MAX_PARALLEL == 3, (peak, len(spans)))
        check("calls: one list, one plugin catalog, one search per term, one lookup per missing skill",
              len(spans) == 1 + 1 + 5 + 1, len(spans))
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--terms", "alpha", "--timeout", "2", "--json", extra_env={"STUB_SLOW_CATALOG": "3"})
        try:
            d = json.loads(r.stdout)
        except ValueError:
            d = {}
        check("the one plugin-catalog call gets twice the per-search timeout (a 3 s catalog passes at --timeout 2)",
              not any("plugin catalog" in e for e in d.get("errors", [])) and "plugin:alpha-plugin" in [t["id"] for t in d.get("tools", [])],
              d.get("errors"))
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--terms", "alpha,beta", "--max", "2")
        tool_lines = [l for l in r.stdout.splitlines() if l.startswith("TOOL")]
        check("--max caps the tool lines", len(tool_lines) == 2, r.stdout)
        check("each query gets a slot before any query gets a second", any('"alpha"' in l for l in tool_lines)
              and any('"beta"' in l for l in tool_lines), r.stdout)
        check("text output stays short", len(r.stdout.splitlines()) <= 40, len(r.stdout.splitlines()))
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--terms", "alpha,slow,boom", "--timeout", "3")
        errs = [l for l in r.stdout.splitlines() if l.startswith("ERROR")]
        check("a slow and a failing search each give one ERROR line",
              len([e for e in errs if "slow" in e]) == 1 and len([e for e in errs if "boom" in e]) == 1, r.stdout)
        check("...and the other searches still report", any(l.startswith("TOOL") for l in r.stdout.splitlines()), r.stdout)
        check("search errors are not fatal (exit 0)", r.returncode == 0, r.returncode)
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--terms", "a,b,c,d,e,f,g", "--json")
        try:
            q = json.loads(r.stdout).get("queries", [])
        except ValueError:
            q = []
        check("at most five queries", len(q) == 5, q)
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--pack", "no-such-pack")
        check("unknown pack is a usage error (exit 2)", r.returncode == 2, r.stdout + r.stderr)
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--terms", "gamma", "--json")
        try:
            tools = json.loads(r.stdout).get("tools", [])
        except ValueError:
            tools = []
        check("an installed skill whose name matches a term is reported", any(t["name"] == "gamma-local" and t["installed"] for t in tools), tools)
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--terms", "alpha", "--want", "writing-plans", "--json", extra_env={"STUB_LIST_FAIL": "1"})
        try:
            d = json.loads(r.stdout)
        except ValueError:
            d = {}
        check("a failed installed-list is reported, not guessed", d.get("installed_known") is False and d.get("missing") == []
              and any("installed skills unknown" in e for e in d.get("errors", [])), d)
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--terms", "alpha,badjson")
        check("malformed search output is one ERROR line", sum("badjson" in l for l in r.stdout.splitlines() if l.startswith("ERROR")) == 1, r.stdout)
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--terms", "alpha,ALPHA, alpha ", "--json")
        try:
            q = json.loads(r.stdout).get("queries")
        except ValueError:
            q = None
        check("duplicate terms collapse (case-insensitive)", q == ["alpha"], q)
    with tempfile.TemporaryDirectory() as td:
        r, raw = run_scout(td, "--terms", "alpha", "--max", "0")
        check("--max below 1 is a usage error (exit 2)", r.returncode == 2, r.stdout + r.stderr)
    spaced = os.path.join("C:\\Program Files" if os.name == "nt" else "/opt/my tools", "py thon")
    check("a plain-string --hermes-cmd keeps quoted paths with spaces",
          scout._hermes_cmd(f'"{spaced}" "{spaced}2" -X') == [spaced, spaced + "2", "-X"], scout._hermes_cmd(f'"{spaced}" "{spaced}2" -X'))
    installed = scout.parse_installed("│ on │ x │ enabled │\n│ off │ x │ disabled │\n┃ Name ┃ Status ┃\n")
    check("disabled skills do not count as installed", installed == {"on": True, "off": False}, installed)
    check("installs parse with thousands separators", scout.parse_installs("Indexed by skills.sh · 174,820 installs") == 174820)
    check("fit: every query word in the name scores 1", scout.fit("web app testing", "webapp-testing", "") == 1.0)
    check("fit: boilerplate descriptions do not count", scout.fit("authentication", "hf-cli", "Indexed by skills.sh from authentication-co") == 0.0)
    check("fit: description matches count at a discount", 0 < scout.fit("authentication", "aspnet-core", "adds authentication") < 1)


# --------------------------------------------------------------------------
# Static checks of the published skill
# --------------------------------------------------------------------------
PACK_HEADINGS = ["Typical gaps", "NFR candidates", "Safeguards", "Acceptance-criteria patterns", "Common pitfalls", "Tool search terms"]


def test_examples_and_template():
    print("\n[contract] worked examples pass the linter; the template names every heading")
    ex = sorted((SKILL / "references" / "examples").glob("*.md"))
    check("at least two worked examples", len(ex) >= 2, ex)
    for p in ex:
        f = lint_brief.lint_text(p.read_text(encoding="utf-8"))
        check(f"example {p.name} passes the linter", f == [], f)
    tpl_path = SKILL / "references" / "brief-template.md"
    tpl = tpl_path.read_text(encoding="utf-8") if tpl_path.is_file() else ""
    check("brief-template.md exists", bool(tpl))
    for h in lint_brief.FULL_SECTIONS + lint_brief.COMPACT_SECTIONS + [lint_brief.OPTIONAL_LAST]:
        check(f"template documents heading '{h}'", h.lower() in tpl.lower())
    for code in lint_brief.CODES:
        check(f"template explains lint code {code}", code in tpl)


def test_packs():
    print("\n[packs] four packs, six headings each, short, with search terms")
    packs = sorted((SKILL / "references" / "packs").glob("*.md"))
    check("four packs", [p.stem for p in packs] == ["agent-skill", "bot-integration", "script-cli", "web-app"], [p.stem for p in packs])
    for p in packs:
        t = p.read_text(encoding="utf-8")
        heads = re.findall(r"^## (.+?)\s*$", t, re.M)
        check(f"{p.stem}: six headings in order", heads == PACK_HEADINGS, heads)
        check(f"{p.stem}: at most 60 lines", len(t.splitlines()) <= 60, len(t.splitlines()))
        terms = scout.pack_terms(p)
        check(f"{p.stem}: two to five tool search terms", 2 <= len(terms) <= 5, terms)


def test_skill_md():
    print("\n[skill] frontmatter, size limits, links and hard rules")
    p = SKILL / "SKILL.md"
    t = p.read_text(encoding="utf-8") if p.is_file() else ""
    m = re.search(r'^description:\s*"?(.+?)"?\s*$', t, re.M)
    desc = m.group(1) if m else ""
    check("description is the agreed trigger", desc == "Use when a rough build idea needs a senior-dev prompt.", desc)
    check("description at most 60 characters", 0 < len(desc) <= 60, len(desc))
    check("platforms list all three", re.search(r"^platforms:\s*\[macos, linux, windows\]", t, re.M) is not None)
    check("at most 200 lines", 0 < len(t.splitlines()) <= 200, len(t.splitlines()))
    check("at most 12,000 characters", 0 < len(t) <= 12000, len(t))
    refs = set()
    for f in [p] + sorted((SKILL / "references").rglob("*.md")):
        if f.is_file() and "examples" not in f.relative_to(SKILL).parts:   # examples describe other projects
            refs |= set(re.findall(r"`((?:references|scripts)/[^`\s]+\.(?:md|py))`", f.read_text(encoding="utf-8")))
    check("SKILL.md and references link to files", len(refs) >= 5, sorted(refs))
    for ref in sorted(refs):
        check(f"linked file exists: {ref}", (SKILL / ref).exists())
    for rule in ("H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11"):
        check(f"hard rule {rule} stated", re.search(rf"\*\*{rule}\b", t) is not None)


def test_portability():
    print("\n[portability] Python 3.8 syntax; the runner fails loudly")
    import ast
    for f in ("lint_brief.py", "scout.py", "test_scripts.py"):
        src = (HERE / f).read_text(encoding="utf-8")
        try:
            ast.parse(src, feature_version=(3, 8))
            ok, why = True, ""
        except SyntaxError as e:
            ok, why = False, f"{e.msg} at line {e.lineno}"
        check(f"{f} parses as Python 3.8", ok, why)
    r = subprocess.run([sys.executable, str(HERE / "test_scripts.py")], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=dict(os.environ, SDP_TEST_SEED_FAILURE="1"), timeout=120)
    check("a seeded failure makes the runner exit non-zero with a count", r.returncode == 1 and "0 passed, 1 failed" in r.stdout,
          r.stdout[-200:])


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    print("senior-dev-prompt script tests")
    print("=" * 60)
    if os.environ.get("SDP_TEST_SEED_FAILURE"):
        check("seeded failure (runner self-test)", False)
        print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
        return 1
    for t in (
        test_lint,
        test_lint_cli,
        test_scout,
        test_examples_and_template,
        test_packs,
        test_skill_md,
        test_portability,
    ):
        try:
            t()
        except Exception as e:  # a crashing test is a failure, never a silent stop
            check(f"{t.__name__} ran to completion", False, f"{type(e).__name__}: {e}")
    print("\n" + "=" * 60)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
