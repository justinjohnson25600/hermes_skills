#!/usr/bin/env python3
"""Deliver skills to every enabled Hermes agent in agents.json.

    python3 deploy.py --list                 # who would receive, and their state
    python3 deploy.py dev-pair verify-results
    python3 deploy.py --all                  # every skill in skills.json
    python3 deploy.py dev-pair --dry-run     # show the plan, change nothing

Replaces hand-rolled one-off SSH loops: the target list lives in agents.json, so
adding a box is a data edit, not a code edit.

Deliberate behaviours, each earned from a real failure:
  * Waits for raw.githubusercontent to actually serve the version in the repo.
    The CDN lags a push by minutes and boxes silently install the OLD release.
  * Ships the payload as base64 to a temp file rather than inline `python -c`:
    long inline commands are truncated by cmd.exe.
  * Cleans stale per-profile copies under <home>/profiles/*/skills/.
  * Compares each agent's check COUNT against the highest seen. A lower count
    means checks are silently skipping, which a green "0 failed" will hide.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = "https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main"

REMOTE = r'''import json, os, pathlib, re, shutil, subprocess, sys, time, urllib.request
RAW = "%(raw)s"
SKILLS = %(skills)r
DRY = %(dry)s
h = os.environ.get("HERMES_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes")
HOME = pathlib.Path(h) if h and pathlib.Path(h).is_dir() else pathlib.Path.home() / ".hermes"
rep = {"host": os.environ.get("COMPUTERNAME") or os.uname().nodename, "home": str(HOME), "skills": {}}
if not HOME.is_dir():
    rep["error"] = "no Hermes home found"
    print(json.dumps(rep)); raise SystemExit(0)

tmp = pathlib.Path(os.environ.get("TEMP") or "/tmp") / ("inst%%d.py" %% time.time())
try:
    with urllib.request.urlopen(RAW + "/install.py?cb=" + str(time.time()), timeout=90) as r:
        tmp.write_bytes(r.read())
except Exception as e:
    rep["error"] = "installer fetch failed: %%s" %% e
    print(json.dumps(rep)); raise SystemExit(0)

def _walk(root, pattern):
    """rglob that survives Windows junctions.

    pathlib.rglob raises OSError 448 on an untraversable reparse point, and npm
    workspace installs create exactly those under node_modules. One junction
    aborts the whole walk, so the scan is done manually with the unreadable and
    irrelevant branches pruned.
    """
    hits = []
    skip = {"node_modules", ".git", "__pycache__", "backups", "venv"}
    for dirpath, dirnames, filenames in os.walk(str(root), onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            p = pathlib.Path(dirpath) / fn
            if p.match(pattern):
                hits.append(p)
    return hits


def ver(f):
    try:
        m = re.search(r"^version:\s*([0-9.]+)", f.read_text(encoding="utf-8", errors="replace"), re.M)
        return m.group(1) if m else None
    except Exception:
        return None

for s in SKILLS:
    if DRY:
        rep["skills"][s] = {"dry_run": True}
        continue
    p = subprocess.run([sys.executable, str(tmp), s], capture_output=True, text=True, timeout=900)
    rep["skills"][s] = {"rc": p.returncode, "err": (p.stderr or "").strip()[-200:] if p.returncode else ""}

# stale copies: anything outside the canonical category dir (and the stray state dir)
cleaned = []
if not DRY:
    for s in SKILLS:
        canon = list(HOME.glob("skills/*/%%s/SKILL.md" %% s))
        canon = canon[0] if canon else None
        stray = HOME / s / "SKILL.md"
        if stray.is_file() and canon and stray != canon:
            shutil.rmtree(HOME / s, ignore_errors=True); cleaned.append(str(stray))
        for f in list(_walk(HOME, "%%s/SKILL.md" %% s)):
            if "backups" in str(f) or f == canon:
                continue
            shutil.rmtree(f.parent, ignore_errors=True); cleaned.append(str(f))
rep["cleaned"] = cleaned

for s in SKILLS:
    hits = [f for f in _walk(HOME, "%%s/SKILL.md" %% s) if "backups" not in str(f)]
    rep["skills"].setdefault(s, {})["version"] = ver(hits[0]) if hits else None
    rep["skills"][s]["copies"] = len(hits)

t = HOME / "devpair" / "test_devpair.py"
if t.is_file() and not DRY:
    p = subprocess.run([sys.executable, str(t)], capture_output=True, text=True, timeout=1200, cwd=str(t.parent))
    m = re.search(r"(\d+) passed, (\d+) failed", p.stdout or "")
    rep["tests"] = {"passed": int(m.group(1)), "failed": int(m.group(2))} if m else {"raw": (p.stdout or "")[-120:]}
try:
    tmp.unlink()
except Exception:
    pass
print(json.dumps(rep))
'''


def load_agents() -> dict:
    return json.loads((ROOT / "agents.json").read_text(encoding="utf-8"))


def wait_for_cdn(skills: list[str], timeout: int = 420) -> dict:
    """Block until the CDN serves the versions this repo has. A push is not a
    release: raw.githubusercontent caches, and boxes install the previous one."""
    want = {}
    for s in skills:
        f = ROOT / s / "skill.json"
        if f.is_file():
            want[s] = json.loads(f.read_text(encoding="utf-8"))["version"]
    if not want:
        return {}
    deadline = time.time() + timeout
    while True:
        seen, ok = {}, True
        for s, v in want.items():
            try:
                with urllib.request.urlopen(f"{RAW}/{s}/skill.json?cb={time.time()}", timeout=30) as r:
                    seen[s] = json.loads(r.read().decode())["version"]
            except Exception as e:
                seen[s] = f"ERR {e}"
            if seen[s] != v:
                ok = False
        if ok or time.time() > deadline:
            return {"want": want, "serving": seen, "current": ok}
        time.sleep(20)


def deliver(agent: dict, skills: list[str], dry: bool) -> tuple[str, dict]:
    name, host = agent["name"], agent["host"]
    code = REMOTE % {"raw": RAW, "skills": skills, "dry": dry}
    # Not every Windows box has a usable `python` on PATH. Some have only the
    # Microsoft Store alias stub, which prints an install advert and exits 9009
    # instead of running anything. An agent may therefore pin its interpreter.
    py = agent.get("python") or "python"
    if host == "local":
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=1800)
        out = p.stdout
    else:
        b64 = base64.b64encode(code.encode()).decode()
        writer = (f'"{py}" -c "import base64,os,sys;'
                  "open(os.environ['TEMP']+chr(92)+'_hsdeploy.py','wb')"
                  '.write(base64.b64decode(sys.stdin.read()))"')
        w = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, writer],
                           input=b64, capture_output=True, text=True, timeout=180)
        if w.returncode:
            return name, {"error": f"payload write failed: {(w.stderr or '').strip()[:200]}"}
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", host, f'"{py}" %TEMP%\\_hsdeploy.py'],
                           capture_output=True, text=True, timeout=1800)
        out = p.stdout
    try:
        return name, json.loads(out)
    except Exception:
        return name, {"error": (out or p.stderr or "no output")[-300:]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Deliver skills to the Hermes agent fleet.")
    ap.add_argument("skills", nargs="*", help="skill names (default: every skill in skills.json)")
    ap.add_argument("--all", action="store_true", help="every skill in skills.json")
    ap.add_argument("--list", action="store_true", help="show agents and exit")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-wait", action="store_true", help="skip the CDN freshness wait")
    args = ap.parse_args()

    cfg = load_agents()
    agents = cfg["agents"]

    if args.list:
        print(f"{'AGENT':<20} {'ROLE':<9} {'PLATFORM':<8} {'ENABLED':<8} HOST")
        for a in agents:
            print(f"{a['name']:<20} {a.get('role',''):<9} {a['platform']:<8} "
                  f"{str(a['enabled']):<8} {a['host']}")
            if not a["enabled"] and a.get("blocked_reason"):
                print(f"{'':<20} BLOCKED: {a['blocked_reason'][:150]}")
        print(f"\nnot enrolled: {', '.join(x['name'] for x in cfg.get('unreachable_not_enrolled', []))}")
        return 0

    skills = args.skills
    if args.all or not skills:
        skills = json.loads((ROOT / "skills.json").read_text(encoding="utf-8"))
    for s in skills:
        if not (ROOT / s).is_dir():
            print(f"no such skill in this repo: {s}")
            return 1

    targets = [a for a in agents if a["enabled"]]
    skipped = [a for a in agents if not a["enabled"]]
    print(f"delivering {', '.join(skills)} to {len(targets)} agent(s)"
          f"{' [DRY RUN]' if args.dry_run else ''}")
    for a in skipped:
        print(f"  SKIP {a['name']}: {a.get('blocked_reason', 'disabled')[:110]}")

    if not args.dry_run and not args.no_wait:
        cdn = wait_for_cdn(skills)
        if cdn and not cdn["current"]:
            print(f"  WARNING: CDN still stale after wait: {cdn['serving']} (want {cdn['want']})")
            print("  Boxes may install the previous release. Re-run later, or pass --no-wait to force.")
        elif cdn:
            print(f"  CDN serving current: {cdn['want']}")

    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as ex:
        results = list(ex.map(lambda a: deliver(a, skills, args.dry_run), targets))

    print()
    counts, failed = [], []
    for name, r in results:
        if r.get("error"):
            print(f"  FAIL {name}: {r['error'][:160]}")
            failed.append(name)
            continue
        vers = " ".join(f"{s}={d.get('version')}" for s, d in r.get("skills", {}).items())
        t = r.get("tests") or {}
        tt = f"{t.get('passed')}/{t.get('passed', 0) + t.get('failed', 0)}" if "passed" in t else "-"
        extra = f" cleaned={len(r['cleaned'])}" if r.get("cleaned") else ""
        print(f"  OK   {name:<18} {vers}  tests={tt}{extra}")
        if t.get("failed"):
            failed.append(name)
        if "passed" in t:
            counts.append((name, t["passed"]))

    # A lower check count than the best agent means checks are SKIPPING there.
    if counts:
        best = max(c for _, c in counts)
        for name, c in counts:
            if c < best:
                print(f"  WARN {name}: {c} checks vs {best} elsewhere — checks are being "
                      f"skipped, not passing. Investigate before trusting this install.")
                failed.append(name)

    if failed:
        print(f"\n{len(set(failed))} agent(s) need attention: {', '.join(sorted(set(failed)))}")
        return 1
    print(f"\nall {len(results)} agent(s) current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
