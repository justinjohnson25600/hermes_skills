#!/usr/bin/env python3
"""Collect skill edits made on a remote agent and land them in this repo.

    python3 contribute.py --scan                    # what differs, everywhere
    python3 contribute.py --from hermes-windows     # pull that box's changes in
    python3 contribute.py --from gmtek-m8 dev-pair  # just one skill

The fleet is deploy-one-way by default: `deploy.py` overwrites a box's copy with
the repo's, so an edit made on a worker is destroyed by the next deploy. This is
the way back. Develop a skill on whichever machine you are sitting at, pull it
here, review the diff, then commit and deploy it out to everyone.

WHY NOT `git push` FROM THE BOX: the Windows agents have no working git
credential store (wincredman fails, and non-interactive HTTPS has no tty to read
a username from), so a push from there needs credentials those boxes should not
hold. Pulling over the SSH channel that already works avoids handing five
machines push rights to a public repo.

Nothing here writes to git. It stages files and prints the diff; you decide.
"""
from __future__ import annotations

import argparse
import base64
import difflib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Runs ON the agent. Returns every tracked skill file it holds, base64'd so
# Windows console encoding cannot corrupt the payload in transit.
COLLECT = r'''import base64, json, os, pathlib
SKILLS = %(skills)r
h = os.environ.get("HERMES_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes")
HOME = pathlib.Path(h) if h and pathlib.Path(h).is_dir() else pathlib.Path.home() / ".hermes"
out = {"host": os.environ.get("COMPUTERNAME") or os.uname().nodename, "files": {}}
if not HOME.is_dir():
    out["error"] = "no Hermes home"
    print(json.dumps(out)); raise SystemExit(0)
for s in SKILLS:
    for f in HOME.glob("skills/*/%%s/SKILL.md" %% s):
        out["files"]["%%s/SKILL.md" %% s] = base64.b64encode(f.read_bytes()).decode()
    d = HOME / "devpair"
    if s == "dev-pair" and d.is_dir():
        for name in ("devpair.py", "test_devpair.py"):
            p = d / name
            if p.is_file():
                out["files"]["dev-pair/%%s" %% name] = base64.b64encode(p.read_bytes()).decode()
print(json.dumps(out))
'''


def agents() -> list[dict]:
    return json.loads((ROOT / "agents.json").read_text(encoding="utf-8"))["agents"]


def collect(agent: dict, skills: list[str]) -> dict:
    code = COLLECT % {"skills": skills}
    host = agent["host"]
    if host == "local":
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
        out = p.stdout
    else:
        b64 = base64.b64encode(code.encode()).decode()
        writer = ('python -c "import base64,os,sys;'
                  "open(os.environ['TEMP']+chr(92)+'_hscollect.py','wb')"
                  '.write(base64.b64decode(sys.stdin.read()))"')
        w = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, writer],
                           input=b64, capture_output=True, text=True, timeout=180)
        if w.returncode:
            return {"error": f"payload write failed: {(w.stderr or '').strip()[:200]}"}
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", host, "python %TEMP%\\_hscollect.py"],
                           capture_output=True, text=True, timeout=600)
        out = p.stdout
    try:
        return json.loads(out)
    except Exception:
        return {"error": (out or p.stderr or "no output")[-300:]}


def compare(payload: dict) -> dict[str, tuple[bytes, bytes]]:
    """Return {relpath: (repo_bytes, agent_bytes)} for files that differ."""
    diffs = {}
    for rel, b64 in payload.get("files", {}).items():
        theirs = base64.b64decode(b64)
        local = ROOT / rel
        ours = local.read_bytes() if local.is_file() else b""
        if ours != theirs:
            diffs[rel] = (ours, theirs)
    return diffs


def show(rel: str, ours: bytes, theirs: bytes, name: str) -> None:
    a = ours.decode("utf-8", "replace").splitlines()
    b = theirs.decode("utf-8", "replace").splitlines()
    print(f"\n--- {rel} (repo) vs {name} ---")
    shown = 0
    for line in difflib.unified_diff(a, b, lineterm="", n=2):
        if line.startswith(("---", "+++")):
            continue
        print("   " + line[:160])
        shown += 1
        if shown > 80:
            print("   ... (truncated; the full file is staged, review it in git)")
            break
    if not shown:
        print("   (binary or whitespace-only difference)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Pull skill edits from an agent into this repo.")
    ap.add_argument("skills", nargs="*", help="skills to collect (default: skills.json)")
    ap.add_argument("--from", dest="source", help="agent name to pull from")
    ap.add_argument("--scan", action="store_true", help="report differences on every enabled agent")
    ap.add_argument("--apply", action="store_true", help="write the agent's version into the repo")
    args = ap.parse_args()

    skills = args.skills or json.loads((ROOT / "skills.json").read_text(encoding="utf-8"))

    if args.scan:
        rc = 0
        for a in agents():
            if not a["enabled"]:
                print(f"SKIP {a['name']}: {a.get('blocked_reason', 'disabled')[:90]}")
                continue
            r = collect(a, skills)
            if r.get("error"):
                print(f"FAIL {a['name']}: {r['error'][:140]}")
                rc = 1
                continue
            d = compare(r)
            if not d:
                print(f"OK   {a['name']}: identical to repo")
            else:
                print(f"DIFF {a['name']}: {', '.join(sorted(d))}")
                if not a.get("authoring"):
                    print(f"     note: {a['name']} is install-only (authoring=false). These edits "
                          f"will be OVERWRITTEN by the next deploy — pull them with "
                          f"`--from {a['name']} --apply` if they are wanted.")
        return rc

    if not args.source:
        ap.error("give --from AGENT, or --scan")

    match = [a for a in agents() if a["name"] == args.source]
    if not match:
        print(f"no such agent: {args.source}")
        return 1
    agent = match[0]
    if not agent["enabled"]:
        print(f"{agent['name']} is not reachable: {agent.get('blocked_reason', 'disabled')}")
        return 1

    r = collect(agent, skills)
    if r.get("error"):
        print(f"collect failed: {r['error']}")
        return 1
    d = compare(r)
    if not d:
        print(f"{agent['name']} is identical to the repo — nothing to contribute.")
        return 0

    for rel, (ours, theirs) in sorted(d.items()):
        show(rel, ours, theirs, agent["name"])

    if not args.apply:
        print(f"\n{len(d)} file(s) differ. Re-run with --apply to write them into the repo.")
        return 0

    for rel, (_, theirs) in sorted(d.items()):
        (ROOT / rel).write_bytes(theirs)
        print(f"applied: {rel}")
    print("\nStaged in the working tree, NOT committed. Now:")
    print("  1. review:            git diff")
    print("  2. bump the version:  <skill>/skill.json, SKILL.md frontmatter, README, CHANGELOG")
    print("  3. run the tests:     python3 <hermes-home>/devpair/test_devpair.py")
    print("  4. check + push:      python3 check_consistency.py --fix && git commit && git push")
    print("  5. deploy outward:    python3 deploy.py " + " ".join(skills))
    return 0


if __name__ == "__main__":
    sys.exit(main())
