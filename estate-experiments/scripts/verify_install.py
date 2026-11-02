#!/usr/bin/env python3
"""Install verifier for estate-experiments (run by install.py via `python`).

Proves the skill is installed AND working on this machine:
  1. both skills' entry scripts are present
  2. the harness falsifier suite passes (guard / no-guard / noise logic)
  3. the harness end-to-end on a synthetic experiment returns keep
  4. the client monitor exposes the two-phase --confirm-delivered interface
Exit 0 = proven; 1 = a check failed. Stdlib only.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent


def monitor_path() -> Path:
    # repo layout (sibling skill) first, then deployed layout (<home>/skills/<cat>/<skill>)
    sibling = SKILL_DIR.parent / "client-literature-monitor" / "scripts" / "theorem_literature_monitor.py"
    if sibling.is_file():
        return sibling
    return SKILL_DIR.parent.parent / "devops" / "client-literature-monitor" / "scripts" / "theorem_literature_monitor.py"


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(("PASS " if ok else "FAIL ") + label + (f": {detail}" if detail else ""))
    return ok


def main() -> int:
    results = []
    harness = HERE / "experiment_harness.py"
    tests = HERE / "test_experiment_harness.py"
    mon = monitor_path()
    results.append(check("harness present", harness.is_file()))
    results.append(check("monitor present", mon.is_file(), str(mon)))

    t = subprocess.run([sys.executable, str(tests)], capture_output=True, text=True, timeout=300)
    results.append(check("harness falsifier suite", t.returncode == 0,
                         (t.stderr.strip().splitlines() or [""])[-1]))

    with tempfile.TemporaryDirectory() as tmp:
        exp = Path(tmp) / "exp"
        exp.mkdir()
        (exp / "intent.md").write_text("# t\nimprove x\n")
        (exp / "baseline.sh").write_text('#!/usr/bin/env bash\necho "WORK_DONE n=10"\nsleep 0.30\n')
        (exp / "trial.sh").write_text('#!/usr/bin/env bash\necho "WORK_DONE n=10"\nsleep 0.05\n')
        (exp / "metric.py").write_text(
            "import re\n\ndef parse(o):\n    return float(re.findall(r'real ([0-9.]+)', o)[-1])\n")
        (exp / "guard.sh").write_text('#!/usr/bin/env bash\no="$(cat)"; echo "$o" | grep -q WORK_DONE\n')
        r = subprocess.run([sys.executable, str(harness), "run", str(exp), "--runs", "2"],
                           capture_output=True, text=True, timeout=300)
        results.append(check("harness end-to-end -> keep", '"verdict": "keep"' in r.stdout,
                             "" if '"verdict": "keep"' in r.stdout else r.stdout[-200:]))

    m = subprocess.run([sys.executable, str(mon), "--help"], capture_output=True, text=True, timeout=60)
    results.append(check("monitor two-phase interface", "--confirm-delivered" in m.stdout))

    ok = all(results)
    print("VERIFY OK — estate-experiments installed and working" if ok else "VERIFY FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
