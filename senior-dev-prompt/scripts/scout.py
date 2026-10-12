#!/usr/bin/env python3
"""Read-only tooling scout for senior-dev-prompt (Step 1, reuse check and tools).

Usage:
  python3 scout.py [--type TYPE] [--pack PACK] [--terms "a,b"] [--want SKILL ...]
                   [--max 5] [--timeout 60] [--json] [--hermes-cmd CMD] [--packs-dir DIR]

Runs at most 5 queries (the pack's "Tool search terms" plus --terms) against
`hermes skills search` and `hermes plugins search`, reads `hermes skills list`,
reports which --want workflow skills are missing (with an exact-name install
candidate, one lookup each, at most 3), dedupes, ranks by fit (query words in the
name, or in the description at 0.6), then installed > official > trusted >
community, then installs, then query order, and prints at most --max TOOL lines
(about 40 lines in all). It never installs anything. Measured: the hub's own
result order is trust-first, not relevance, so fit is computed here.

Exit: 0 = ran (search failures are reported as ERROR lines), 1 = every search
failed, 2 = usage error. Standard library only, Python 3.8+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MAX_QUERIES = 5
MAX_LOOKUPS = 3      # install-candidate lookups for missing workflow skills
MAX_PARALLEL = 3     # hermes processes at once: each is a cold Python start, and bursts timed out
DEFAULT_PACKS = Path(__file__).resolve().parent.parent / "references" / "packs"
TRUST_RANK = {"builtin": 0, "official": 0, "trusted": 1, "community": 2}
TYPE_TO_PACK = [
    (("skill", "agent", "plugin", "prompt"), "agent-skill"),
    (("web", "site", "app", "dashboard"), "web-app"),
    (("script", "cli", "command", "tool"), "script-cli"),
    (("bot", "integration", "automation", "webhook", "scheduled"), "bot-integration"),
]
PLUGIN_NOTE = "plugin: runs code, may install Python packages, needs a restart"


def pack_terms(path: Path) -> list:
    """Bullets under the pack's '## Tool search terms' heading, in order."""
    text = Path(path).read_text(encoding="utf-8")
    m = re.search(r"^##\s+Tool search terms\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    terms = []
    for line in (m.group(1).splitlines() if m else []):
        s = line.strip()
        if s.startswith(("- ", "* ")):
            t = s[2:].strip().strip("`").strip()
            if t:
                terms.append(t)
    return terms


STOPWORDS = {"the", "and", "for", "with", "from", "into", "that", "this", "your"}


def fit(query: str, name: str, desc: str) -> float:
    """Share of the query's words found in the name; description matches count at 0.6.
    Registry boilerplate ("Indexed by ...") is not a description. Deterministic, so the
    ranking is testable; the agent still judges real fit when it picks recommendations."""
    words = [w for w in re.split(r"[^a-z0-9]+", query.lower()) if len(w) >= 3 and w not in STOPWORDS]
    if not words:
        return 0.0
    n = (name or "").lower()
    d = "" if (desc or "").startswith("Indexed by") else (desc or "").lower()
    by_name = sum(w in n for w in words) / len(words)
    by_desc = sum(w in d for w in words) / len(words)
    return round(max(by_name, 0.6 * by_desc), 2)


def parse_installs(desc: str):
    m = re.search(r"([\d][\d,]*)\s+installs?\b", desc or "")
    return int(m.group(1).replace(",", "")) if m else None


def parse_installed(table: str) -> dict:
    """{name: enabled} from the table `hermes skills list` prints."""
    out = {}
    for line in table.splitlines():
        s = line.strip()
        if not s or s[0] not in "│|":
            continue
        cells = [c.strip() for c in s.strip("│|").split("│" if "│" in s else "|")]
        if not cells or not cells[0] or cells[0].lower() == "name" or set(cells[0]) <= set("-:━ "):
            continue
        out[cells[0]] = "disabled" not in (cells[-1].lower() if len(cells) > 1 else "")
    return out


def _os_name() -> str:
    return {"darwin": "macos", "win32": "windows", "cygwin": "windows"}.get(sys.platform, "linux")


def _hermes_cmd(raw: str | None) -> list:
    if not raw:
        return [shutil.which("hermes") or "hermes"]
    raw = raw.strip()
    if raw.startswith("["):
        return [str(x) for x in json.loads(raw)]
    parts = shlex.split(raw, posix=(os.name != "nt"))
    return [p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p for p in parts]


def _run(cmd: list, args: list, timeout: float):
    env = dict(os.environ, COLUMNS="400", PYTHONIOENCODING="utf-8", NO_COLOR="1")
    try:
        r = subprocess.run(cmd + args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout:g}s"
    except OSError as e:
        return None, f"could not run hermes: {e}"
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip().splitlines()
        return None, f"exit {r.returncode}" + (f": {err[-1][:120]}" if err else "")
    return r.stdout, ""


def _json(text: str):
    try:
        return json.loads(text)
    except ValueError:
        start = min([i for i in (text.find("["), text.find("{")) if i >= 0] or [0])
        return json.loads(text[start:])


def _plugin_hits(catalog: list, q: str) -> list:
    """The CLI's own plugin match, applied locally to the catalog fetched once:
    case-insensitive substring over name, description and declared tools."""
    ql = q.strip().lower()
    hits = []
    for e in catalog:
        if not isinstance(e, dict) or not e.get("name"):
            continue
        tools = (e.get("capabilities") or {}).get("provides_tools") or []
        if any(ql in str(h).lower() for h in [e["name"], e.get("description") or "", *tools]):
            hits.append(e)
    return hits


def scout(terms: list, want: list, max_tools: int, hermes_cmd: list, timeout: float) -> dict:
    queries = []
    for t in terms:
        t = t.strip()
        if t and t.lower() not in [q.lower() for q in queries]:
            queries.append(t)
    queries = queries[:MAX_QUERIES]
    # One call for the installed list, one for the whole plugin catalog (matched locally per
    # term), one hub search per term; never more than MAX_PARALLEL processes at once.
    jobs = [("list", None), ("catalog", None)] + [("skills", q) for q in queries]

    def work(job):
        kind, q = job
        if kind == "list":
            return job, _run(hermes_cmd, ["skills", "list", "--source", "all"], timeout)
        if kind == "catalog":
            # One call returns all ~550 entries (~0.9 MB), so it gets a longer leash; it
            # runs alongside the searches and only lengthens the run when it is slow.
            return job, _run(hermes_cmd, ["plugins", "search", "--json"], timeout * 2)
        return job, _run(hermes_cmd, ["skills", "search", q, "--json", "--limit", "10"], timeout)

    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(jobs))) as ex:
        results = dict(ex.map(work, jobs))

    errors, installed, installed_known = [], {}, False
    out, err = results[("list", None)]
    if out is not None:
        installed, installed_known = parse_installed(out), True
    else:
        errors.append(f'installed skills unknown: {err}')
    enabled = {n for n, on in installed.items() if on}

    catalog, catalog_ok = [], False
    out, err = results[("catalog", None)]
    if out is None:
        errors.append(f"plugin catalog: {err}")
    else:
        try:
            data = _json(out)
            catalog = data if isinstance(data, list) else (data.get("results") or [])
            catalog_ok = True
        except ValueError:
            errors.append("plugin catalog: output was not JSON")

    tools, seen, failed = {}, set(), 0
    for qi, q in enumerate(queries):
        for kind in ("skills", "plugins"):
            if kind == "plugins":
                if not catalog_ok:
                    failed += 1
                    continue
                items = _plugin_hits(catalog, q)
            else:
                out, err = results[(kind, q)]
                if out is None:
                    failed += 1
                    errors.append(f'query "{q}" ({kind}): {err}')
                    continue
                try:
                    data = _json(out)
                except ValueError:
                    failed += 1
                    errors.append(f'query "{q}" ({kind}): output was not JSON')
                    continue
                items = data if isinstance(data, list) else (data.get("results") or [])
            for it in items:
                if not isinstance(it, dict) or not it.get("name"):
                    continue
                if kind == "skills":
                    tid = it.get("identifier") or it["name"]
                    desc = it.get("description") or ""
                    rec = {"kind": "skill", "name": it["name"], "id": tid, "source": it.get("source") or "?",
                           "trust": (it.get("trust_level") or "unknown").lower(), "installs": parse_installs(desc),
                           "installed": it["name"] in enabled, "matched": q,
                           "why": "" if desc.startswith("Indexed by") else desc[:90]}
                else:
                    plats = it.get("platforms") or []
                    if plats and _os_name() not in [str(p).lower() for p in plats]:
                        continue
                    tid = "plugin:" + it["name"]
                    rec = {"kind": "plugin", "name": it["name"], "id": tid, "source": "plugin catalog",
                           "trust": (it.get("tier") or "unknown").lower(), "installs": None, "installed": False,
                           "matched": q, "why": (it.get("description") or "")[:90], "note": PLUGIN_NOTE}
                if tid in seen:
                    continue
                seen.add(tid)
                rec["fit"] = fit(q, rec["name"], it.get("description") or "")
                rec["_order"] = (qi, len(tools))
                tools[tid] = rec
        # Installed skills whose names share a word with the query.
        words = [w for w in re.split(r"[^a-z0-9]+", q.lower()) if len(w) >= 4]
        for name in sorted(enabled):
            parts = name.lower().split("-")
            if any(w in parts or w in name.lower() for w in words) and not any(t["name"] == name for t in tools.values()):
                tid = "installed:" + name
                tools[tid] = {"kind": "skill", "name": name, "id": tid, "source": "installed", "trust": "installed",
                              "installs": None, "installed": True, "matched": q, "why": "",
                              "fit": fit(q, name, ""), "_order": (qi, len(tools))}
    def rank(t):  # fit first (tenths), then installed, trust, installs, query order
        return (-round(t["fit"], 1), 0 if t["installed"] else 1, TRUST_RANK.get(t["trust"], 3),
                -(t["installs"] or 0), t["_order"])

    # One entry per name: copies of a skill on several registries collapse into the best-ranked one.
    best, uniq = {}, []
    for t in sorted(tools.values(), key=rank):
        key = (t["kind"], re.sub(r"[^a-z0-9]", "", t["name"].lower()))
        if key in best:
            best[key]["also"] = best[key].get("also", 0) + 1
            continue
        best[key] = t
        uniq.append(t)
    # Every query gets its best tool before any query gets a second slot.
    picked = []
    for q in queries:
        top = next((t for t in uniq if t["matched"] == q and t not in picked), None)
        if top and len(picked) < max_tools:
            picked.append(top)
    picked += [t for t in uniq if t not in picked][:max(0, max_tools - len(picked))]
    ranked = sorted(picked, key=rank)
    for t in ranked:
        t.pop("_order", None)
    missing = [w for w in want if installed_known and w not in enabled]
    return {"queries": queries, "installed_known": installed_known, "missing": missing,
            "missing_candidates": _candidates(missing[:MAX_LOOKUPS], hermes_cmd, timeout, errors),
            "tools": ranked, "errors": errors,
            "all_failed": bool(queries) and failed == 2 * len(queries)}


def _candidates(names: list, hermes_cmd: list, timeout: float, errors: list) -> dict:
    """An install candidate for each missing workflow skill: an exact-name hub match,
    best trust first. One lookup per name, outside the five query terms."""
    if not names:
        return {}

    def look(name):
        return name, _run(hermes_cmd, ["skills", "search", name, "--json", "--limit", "10"], timeout)

    out = {}
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(names))) as ex:
        for name, (text, err) in ex.map(look, names):
            out[name] = None
            if text is None:
                errors.append(f'lookup "{name}": {err}')
                continue
            try:
                data = _json(text)
            except ValueError:
                errors.append(f'lookup "{name}": output was not JSON')
                continue
            items = data if isinstance(data, list) else (data.get("results") or [])
            exact = [i for i in items if isinstance(i, dict) and str(i.get("name", "")).lower() == name.lower()]
            exact.sort(key=lambda i: (TRUST_RANK.get(str(i.get("trust_level", "")).lower(), 3),
                                      -(parse_installs(i.get("description", "")) or 0)))
            if exact:
                i = exact[0]
                out[name] = {"id": i.get("identifier") or i["name"], "source": i.get("source") or "?",
                             "trust": str(i.get("trust_level") or "unknown").lower(),
                             "installs": parse_installs(i.get("description", ""))}
    return out


def _pick_pack(args) -> str | None:
    if args.pack:
        return args.pack
    t = (args.type or "").lower()
    for keys, pack in TYPE_TO_PACK:
        if any(k in t for k in keys):
            return pack
    return None


def main(argv: list | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Find installed and installable tools for a build. Never installs.")
    ap.add_argument("--type", help="build type, used to choose a pack when --pack is not given")
    ap.add_argument("--pack", help="domain pack name, e.g. web-app")
    ap.add_argument("--terms", default="", help="extra comma-separated search terms")
    ap.add_argument("--want", nargs="*", default=[], help="workflow skills the route needs")
    ap.add_argument("--max", type=int, default=5, help="most tools to print (default 5)")
    ap.add_argument("--timeout", type=float, default=60,
                    help="seconds per search (default 60; the single plugin-catalog call gets twice this)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hermes-cmd", help="command prefix for hermes (JSON array or string)")
    ap.add_argument("--packs-dir", default=str(DEFAULT_PACKS))
    args = ap.parse_args(argv)
    if args.max < 1:
        print("scout: --max must be at least 1", file=sys.stderr)
        return 2

    terms = []
    pack = _pick_pack(args)
    if pack:
        p = Path(args.packs_dir) / f"{pack}.md"
        if not p.is_file():
            print(f"scout: no pack named '{pack}' in {args.packs_dir}", file=sys.stderr)
            return 2
        terms += pack_terms(p)
    terms += [t for t in args.terms.split(",") if t.strip()]
    if not terms and not args.want:
        print("scout: nothing to do; give --pack, --type, --terms or --want", file=sys.stderr)
        return 2
    rep = scout(terms, args.want, args.max, _hermes_cmd(args.hermes_cmd), args.timeout)
    rep["pack"] = pack
    if args.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    else:
        print("QUERIES  " + (", ".join(rep["queries"]) or "(none)") + (f"  [pack: {pack}]" if pack else ""))
        for m in rep["missing"]:
            c = rep["missing_candidates"].get(m)
            where = (f"candidate: {c['id']} | {c['source']} | {c['trust']}" if c else "no install candidate found")
            print(f"MISSING  {m}  (workflow skill the route uses; not installed) {where}")
        for i, t in enumerate(rep["tools"], 1):
            bits = [t["name"], t["kind"], t["source"], t["trust"], f"fit {t['fit']:.1f}",
                    f"{t['installs']:,} installs" if t["installs"] else "-", t["id"], f'matched "{t["matched"]}"']
            if t["installed"]:
                bits.append("INSTALLED")
            if t.get("also"):
                bits.append(f"+{t['also']} same-name copies elsewhere")
            if t.get("why"):
                bits.append("why: " + t["why"])
            if t.get("note"):
                bits.append(t["note"])
            print(f"TOOL  {i}. " + " | ".join(bits))
        if not rep["tools"]:
            print("TOOLS  none found")
        for e in rep["errors"]:
            print("ERROR  " + e)
    return 1 if rep["all_failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
