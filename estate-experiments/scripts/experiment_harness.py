#!/usr/bin/env python3
"""Experiment harness v0.2: measured, guard-checked, noise-aware keep/discard verdicts.

Autoresearch-shaped loop for estate/client-automation work: a trial is one measurable
change to something that runs repeatedly. v0.2 hardens the verdict (council 2026-10-31):

  * GUARD-CHECKED — a keep requires guard.sh proving the arm still did the work.
    No guard, no keep (verdict "unproven"). A faster arm that skipped the work is
    discarded, never kept.
  * INTERLEAVED — both arms run k times, alternating who goes first; the metric is
    the per-arm MEDIAN and a verdict inside the noise band (margin <= spread) is
    refused. Cold/warm cache artifacts cannot decide a keep.
  * LEDGERED — every arm-run appends a JSONL line (wall, metric, rc, guard), giving
    free baselines and a passive record of what actually runs.

Nothing auto-applies: the receipt is the review artifact; the human (or an owner
rule) applies keeps. Receipts name the target's owner so a kept change to a
fleet-managed file goes through the skills repo, not local edit.

    python3 experiment_harness.py run <experiment_dir> [--runs N]
    python3 experiment_harness.py show <experiment_dir>
    python3 experiment_harness.py ledger <experiments_root>

Experiment dir:
    intent.md     goal + metric (lower = better); optional `owner: <who owns the target>`
    baseline.sh   current behaviour (read-only)
    trial.sh      candidate behaviour
    metric.py     parse(run_output) -> float   (harness appends its own "real <s>" line)
    guard.sh      REQUIRED for keep: reads one arm's full output on stdin; exit 0 iff
                  the arm actually did the work (the invariant held)
    receipt.json  written by the harness
    ledger.jsonl  appended per arm-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

VERDICTS = ("keep", "discard", "unproven")


def sh(script: Path, timeout: int = 900) -> dict:
    t0 = time.monotonic()
    try:
        p = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=timeout)
        rc, out = p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired as exc:
        rc, out = 124, f"TIMEOUT after {timeout}s: {exc}"
    return {"rc": rc, "out": out[-20000:], "wall_s": round(time.monotonic() - t0, 3)}


def load_metric(exp_dir: Path):
    spec = importlib.util.spec_from_file_location("metric", exp_dir / "metric.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["metric"] = mod
    spec.loader.exec_module(mod)
    return mod


def guard_ok(guard: Path, arm_output: str) -> bool:
    p = subprocess.run(["bash", str(guard)], input=arm_output,
                       capture_output=True, text=True, timeout=300)
    return p.returncode == 0


def _owner_of(intent: str) -> str:
    for line in intent.splitlines():
        if line.lower().startswith("owner:"):
            return line.split(":", 1)[1].strip()
    return "profile-local"


def run_experiment(exp_dir: Path, runs: int = 3) -> int:
    intent = (exp_dir / "intent.md").read_text()
    for f in ("baseline.sh", "trial.sh"):
        if not (exp_dir / f).is_file():
            print(f"REFUSED: missing {f}", file=sys.stderr)
            return 2
    has_guard = (exp_dir / "guard.sh").is_file()
    metric = load_metric(exp_dir)
    ledger = exp_dir / "ledger.jsonl"

    # Interleaved reps: who runs first alternates, so order effects cancel.
    runs_by_arm: dict[str, list[dict]] = {"baseline": [], "trial": []}
    for rep in range(runs):
        arms = ("baseline", "trial") if rep % 2 == 0 else ("trial", "baseline")
        for arm in arms:
            r = sh(exp_dir / f"{arm}.sh")
            m = None
            try:
                m = float(metric.parse(r["out"] + f"\nreal {r['wall_s']}"))
            except Exception as exc:
                r["metric_error"] = f"{type(exc).__name__}: {exc}"
            g = guard_ok(exp_dir / "guard.sh", r["out"]) if has_guard else None
            rec = {"arm": arm, "rep": rep, "rc": r["rc"], "wall_s": r["wall_s"],
                   "metric": m, "guard": g,
                   "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
            runs_by_arm[arm].append(rec)
            with ledger.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"experiment": exp_dir.name, **rec}) + "\n")
            print(f"  {arm}[{rep}] rc={r['rc']} wall={r['wall_s']}s metric={m} guard={g}")

    base, trial = runs_by_arm["baseline"], runs_by_arm["trial"]
    if not has_guard:
        verdict, why = "unproven", "no guard.sh — a keep requires proof the work still happened"
    elif any(r["rc"] != 0 for r in base + trial):
        verdict, why = "discard", "an arm exited non-zero"
    elif any(r["guard"] is False for r in trial):
        verdict, why = "discard", "guard failed on trial — it skipped the work (or the guard is wrong)"
    elif any(r["guard"] is False for r in base):
        verdict, why = "discard", "guard failed on baseline — fix the guard: it must accept real work"
    elif any(r["metric"] is None for r in base + trial):
        verdict, why = "discard", "metric unparsable for at least one run"
    else:
        mb = [r["metric"] for r in base]
        mt = [r["metric"] for r in trial]
        med_b, med_t = statistics.median(mb), statistics.median(mt)
        spread = max(max(mb) - min(mb), max(mt) - min(mt))
        margin = med_b - med_t
        if margin > spread:
            verdict, why = "keep", (f"median {med_b:.3f} -> {med_t:.3f}; margin {margin:.3f} "
                                    f"exceeds noise spread {spread:.3f} over {runs} interleaved runs")
        else:
            verdict, why = "discard", f"within noise: margin {margin:.3f} <= spread {spread:.3f}"

    receipt = {
        "experiment": exp_dir.name,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "intent": intent.strip().splitlines()[0][:200],
        "owner": _owner_of(intent),
        "runs": runs,
        "baseline": runs_by_arm["baseline"],
        "trial": runs_by_arm["trial"],
        "verdict": verdict, "why": why,
    }
    (exp_dir / "receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps({k: receipt[k] for k in ("experiment", "verdict", "why", "owner")}, indent=2))
    return 0


def show(exp_dir: Path) -> int:
    r = exp_dir / "receipt.json"
    if not r.is_file():
        print("no receipt yet", file=sys.stderr)
        return 1
    print(r.read_text())
    return 0


def ledger_rollup(root: Path) -> int:
    """Passive record: median wall + last rc per arm for every experiment under root."""
    for lj in sorted(root.glob("*/ledger.jsonl")):
        lines = [json.loads(x) for x in lj.read_text().splitlines() if x.strip()]
        if not lines:
            continue
        arms: dict[str, list] = {}
        for ln in lines:
            arms.setdefault(ln["arm"], []).append(ln)
        out = [f"{lj.parent.name}  (last {lines[-1]['at']})"]
        for arm, rs in arms.items():
            walls = sorted(r["wall_s"] for r in rs)
            out.append(f"  {arm:<9} n={len(rs)} median_wall={statistics.median(walls):.3f}s "
                       f"last_rc={rs[-1]['rc']} last_guard={rs[-1].get('guard')}")
        print("\n".join(out))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Guard-checked, interleaved experiment harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("dir"); r.add_argument("--runs", type=int, default=3)
    s = sub.add_parser("show"); s.add_argument("dir")
    l = sub.add_parser("ledger"); l.add_argument("root")
    a = ap.parse_args()
    fn = {"run": lambda: run_experiment(Path(a.dir).resolve(), a.runs),
          "show": lambda: show(Path(a.dir).resolve()),
          "ledger": lambda: ledger_rollup(Path(a.root).resolve())}
    raise SystemExit(fn[a.cmd]())
