#!/usr/bin/env python3
"""Falsifier tests for experiment_harness v0.2 (council 2026-10-31).

The falsifier every seat proposed: a trial that SKIPS the work but prints
metric-shaped output must never receive `keep`. Proven three ways:

1. work-skipping trial  -> discard (guard catches it)
2. no guard at all      -> unproven (no keep without proof)
3. honest trial, guard passing, margin > noise -> keep

Plus the noise rule: a verdict inside the spread is refused even when the
median looks better. Runs against HARNRESS_TARGET (default: shipped harness),
so the same suite runs red against a saved v0.1 copy.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TARGET = Path(os.environ.get(
    "HARNESS_TARGET",
    str(Path(__file__).resolve().parent.parent / "scripts" / "experiment_harness.py")))


def load(target: Path):
    spec = importlib.util.spec_from_file_location("harness_under_test", target)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["harness_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def fake_sh(outputs_by_call):
    """Return a run() substitute yielding pre-built run dicts in order."""
    it = iter(outputs_by_call)
    def _sh(script, timeout=900):
        return next(it)
    return _sh


def make_exp(tmp: Path, *, guard: str | None, base_out="did the work\nresult_ok\n",
             trial_out="did the work\nresult_ok\n", metric_gap=True):
    d = tmp / "exp"
    d.mkdir()
    (d / "intent.md").write_text("# intent\nimprove X\nowner: profile-local\n")
    (d / "metric.py").write_text(
        "import re\n\ndef parse(run_output):\n"
        "    ts = re.findall(r'real (\\d+\\.\\d+)', run_output)\n"
        "    return float(ts[-1])\n")
    if guard is not None:
        (d / "guard.sh").write_text(guard)
    outs = []
    for arm, out in (("baseline", base_out), ("trial", trial_out)):
        pass
    return d


class GuardRule(unittest.TestCase):
    def setUp(self):
        self.mod = load(TARGET)
        self.tmp = tempfile.TemporaryDirectory()
        self.exp = Path(self.tmp.name) / "exp"
        self.exp.mkdir()
        (self.exp / "intent.md").write_text("# intent\nimprove X\n")
        (self.exp / "metric.py").write_text(
            "def parse(run_output):\n"
            "    import re\n"
            "    ts = re.findall(r'real (\\d+\\.\\d+)', run_output)\n"
            "    return float(ts[-1])\n")
        (self.exp / "baseline.sh").write_text("# baseline\n")
        (self.exp / "trial.sh").write_text("# trial\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _arms(self, n, base_wall, trial_wall, base_out="WORK_DONE ok=4\n", trial_out="WORK_DONE ok=4\n"):
        seq = []
        for rep in range(n):
            first, second = (("baseline", base_wall, base_out), ("trial", trial_wall, trial_out)) \
                if rep % 2 == 0 else (("trial", trial_wall, trial_out), ("baseline", base_wall, base_out))
            seq.append(first, ); seq.append(second)
        return seq

    def _run(self, seq, guard_body):
        (self.exp / "guard.sh").write_text(guard_body)
        outputs = [{"rc": 0, "out": out, "wall_s": wall} for (_arm, wall, out) in seq]
        # guard.sh exists on disk, so guard_ok really executes; feed it via stdin from out
        with mock.patch.object(self.mod, "sh", side_effect=fake_sh(outputs)), \
             mock.patch.object(self.mod, "guard_ok", side_effect=lambda g, out: "WORK_DONE" in out):
            rc = self.mod.run_experiment(self.exp, runs=len(seq) // 2)
        self.assertEqual(rc, 0)
        return json.loads((self.exp / "receipt.json").read_text())

    def test_falsifier_work_skipping_trial_is_discarded(self):
        """THE falsifier: trial prints metric-shaped output but never does the work."""
        seq = self._arms(3, base_wall=5.0, trial_wall=0.1,
                         trial_out="real 0.1\n")  # metric-shaped, no WORK_DONE
        r = self._run(seq, "grep -q WORK_DONE")
        self.assertEqual(r["verdict"], "discard")
        self.assertIn("guard failed on trial", r["why"])

    def test_no_guard_is_unproven_never_keep(self):
        (self.exp / "guard.sh").unlink(missing_ok=True)
        outputs = [{"rc": 0, "out": "x\n", "wall_s": w} for w in
                   (5.0, 0.1, 5.0, 0.1, 5.0, 0.1)]
        with mock.patch.object(self.mod, "sh", side_effect=fake_sh(outputs)):
            rc = self.mod.run_experiment(self.exp, runs=3)
        self.assertEqual(rc, 0)
        r = json.loads((self.exp / "receipt.json").read_text())
        self.assertEqual(r["verdict"], "unproven")

    def test_honest_improvement_keeps(self):
        seq = self._arms(3, base_wall=5.0, trial_wall=1.0)
        r = self._run(seq, "grep -q WORK_DONE")
        self.assertEqual(r["verdict"], "keep")

    def test_within_noise_is_refused(self):
        # margin 0.05 <= spread 0.2: refused even though median looks better
        seq = [
            ("baseline", 5.00, "WORK_DONE ok=4\n"), ("trial", 4.90, "WORK_DONE ok=4\n"),
            ("trial", 4.95, "WORK_DONE ok=4\n"), ("baseline", 5.10, "WORK_DONE ok=4\n"),
            ("baseline", 5.05, "WORK_DONE ok=4\n"), ("trial", 5.00, "WORK_DONE ok=4\n"),
        ]
        r = self._run(seq, "grep -q WORK_DONE")
        self.assertEqual(r["verdict"], "discard")
        self.assertIn("within noise", r["why"])

    def test_baseline_guard_failure_is_discarded_not_kept(self):
        # a guard that rejects even real work must not hand the trial a keep
        seq = self._arms(2, base_wall=5.0, trial_wall=1.0, base_out="DIFFERENT_FORMAT\n")
        r = self._run(seq, "grep -q WORK_DONE")
        self.assertEqual(r["verdict"], "discard")


if __name__ == "__main__":
    unittest.main(verbosity=2)
