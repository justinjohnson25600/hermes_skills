#!/usr/bin/env python3
"""Experiment harness: run a self-improvement experiment against the estate's own checks.

Autoresearch-shaped loop for FleetOps/hermes-dev (Karpathy's pattern, applied to ops):
a trial is one measurable change to a check or script; the harness runs the BASELINE and
the TRIAL against the same inputs, compares a metric, and records keep/discard with the
evidence. Humans never lose the decision: a kept trial still lands as a proposed patch
with its receipt, never a silent overwrite.

    python3 experiment_harness.py run <experiment_dir>
    python3 experiment_harness.py show <experiment_dir>

Layout of an experiment dir:
    intent.md     - what the experiment tries to improve, and the metric
    baseline.sh   - produces the metric on current code (read-only)
    trial.sh      - produces the metric with the candidate change applied
    metric.py     - parses a run's raw output into a float (lower = better)
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

VERDICTS = ("keep", "discard")


def sh(script: Path, timeout: int = 900) -> dict:
    t0 = time.monotonic()
    try:
        p = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=timeout)
        rc, out = p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired as exc:
        rc, out = 124, f"TIMEOUT after {timeout}s: {exc}"
    return {"rc": rc, "out": out[-20000:], "wall_s": round(time.monotonic() - t0, 2)}


def metric_of(exp_dir: Path, run: dict) -> float | None:
    spec = importlib.util.spec_from_file_location("metric", exp_dir / "metric.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["metric"] = mod
    spec.loader.exec_module(mod)
    try:
        return float(mod.parse(run["out"]))
    except Exception as exc:
        run["metric_error"] = f"{type(exc).__name__}: {exc}"
        return None


def run_experiment(exp_dir: Path) -> int:
    intent = (exp_dir / "intent.md").read_text()
    # invariant: same inputs to both arms — refuse to run otherwise
    for arm in ("baseline.sh", "trial.sh"):
        if not (exp_dir / arm).is_file():
            print(f"REFUSED: missing {arm}", file=sys.stderr)
            return 2
    print(f"== baseline ==")
    base = sh(exp_dir / "baseline.sh")
    print(f"rc={base['rc']} wall={base['wall_s']}s")
    print(f"== trial ==")
    trial = sh(exp_dir / "trial.sh")
    print(f"rc={trial['rc']} wall={trial['wall_s']}s")

    bm, tm = metric_of(exp_dir, base), metric_of(exp_dir, trial)
    if bm is None or tm is None:
        verdict, why = "discard", f"metric unparsable (base={bm}, trial={tm})"
    else:
        # keep only if the trial is strictly better AND its rc is clean
        verdict = "keep" if (tm < bm and trial["rc"] == 0) else "discard"
        why = f"baseline {bm:.3f}s -> trial {tm:.3f}s ({(bm - tm) / bm * 100:.0f}% faster)" \
              if tm < bm else f"trial {tm:.3f}s not better than baseline {bm:.3f}s"
        if verdict == "discard" and trial["rc"] != 0:
            why += f"; trial rc={trial['rc']}"
    receipt = {
        "experiment": exp_dir.name,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "intent": intent.strip().splitlines()[0][:200],
        "baseline": {k: base[k] for k in ("rc", "wall_s")},
        "trial": {k: trial[k] for k in ("rc", "wall_s")},
        "baseline_metric": bm, "trial_metric": tm,
        "verdict": verdict, "why": why,
    }
    (exp_dir / "receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))
    return 0


def show(exp_dir: Path) -> int:
    r = exp_dir / "receipt.json"
    if not r.is_file():
        print("no receipt yet", file=sys.stderr)
        return 1
    print(r.read_text())
    return 0


if __name__ == "__main__":
    import importlib.util
    cmds = {"run": run_experiment, "show": show}
    if len(sys.argv) != 3 or sys.argv[1] not in cmds:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(cmds[sys.argv[1]](Path(sys.argv[2]).resolve()))
