#!/usr/bin/env python3
"""Behavior contracts for the real review handoff CLI; stdlib, no network."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import review_gate as gate


class ReviewHandoff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.brief = self.root / "brief.md"
        self.brief.write_text("# Brief\nDo /Users/fixture/work safely.\n\n## Co-developer review\nAudit only.\n", encoding="utf-8")
        body = gate.execution_bytes(self.brief)
        clean = body.decode().replace("/Users/fixture", "/example/operator").encode()
        (self.root / "part.md").write_bytes(clean)
        self.out = {"verdict": "PROCEED", "coverage": "complete", "run_id": "fixture-run", "response": "I agree.",
                    "route": {"identity": "reported-match", "requested_provider": "fixture", "reported_provider": "fixture",
                              "requested_model": "test", "reported_model": "test", "completed": True},
                    "evidence": {"context_chars": len(clean)}, "blockers": [], "gate_failed": False}
        self.m = {"execution_sha256": gate.digest(body), "operator_home": "/Users/fixture", "driver_agrees": True,
                  "sanitized_sha256": gate.digest(clean), "parts": {"part.md": gate.digest(clean)}, "expected_provider": "fixture",
                  "expected_model": "test", "expected_context_chars": len(clean), "output_file": "output.json", "call_exit": 0}
        self.manifest = self.root / "manifest.json"

    def run_gate(self):
        raw = json.dumps(self.out).encode()
        (self.root / "output.json").write_bytes(raw)
        self.m["output_sha256"] = gate.digest(raw)
        self.manifest.write_text(json.dumps(self.m), encoding="utf-8")
        return subprocess.run([sys.executable, "-B", str(Path(gate.__file__)), str(self.brief), str(self.manifest)],
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), capture_output=True, text=True, timeout=20)

    def test_complete_agreement_passes_and_audit_append_does_not_invalidate(self):
        self.assertEqual(self.run_gate().returncode, 0)
        with self.brief.open("a", encoding="utf-8") as f:
            f.write("\n## Change log\nReceipt added, no execution changes.\n")
        self.assertEqual(self.run_gate().returncode, 0)

    def test_post_review_execution_edit_fails(self):
        self.brief.write_text(self.brief.read_text().replace("safely", "differently"), encoding="utf-8")
        r = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("changed after review", r.stdout)

    def test_conditional_rejected_and_blocker_verdicts_fail(self):
        for verdict in ("PROCEED WITH CHANGES", "SHIP AFTER FIXES", "STOP", "RECONSIDER", "UNKNOWN", ""):
            with self.subTest(verdict=verdict):
                self.out["verdict"] = verdict
                self.assertEqual(self.run_gate().returncode, 1)

    def test_partial_wrong_model_unverified_context_or_failed_call_fail(self):
        original = copy.deepcopy(self.out)
        cases = [("coverage", "partial"), ("route.reported_model", "other"), ("route.identity", "unknown"),
                 ("route.completed", False), ("evidence.context_chars", -1), ("gate_failed", True),
                 ("blockers", ["real finding"]), ("run_id", ""), ("response", "")]
        for key, value in cases:
            with self.subTest(key=key):
                self.out = copy.deepcopy(original)
                target = self.out
                steps = key.split(".")
                for step in steps[:-1]:
                    target = target[step]
                target[steps[-1]] = value
                self.assertEqual(self.run_gate().returncode, 1)
        self.out = original
        self.m["call_exit"] = 2
        self.assertEqual(self.run_gate().returncode, 1)

    def test_part_corruption_and_missing_parts_fail(self):
        (self.root / "part.md").write_bytes(b"not the approved brief")
        self.assertEqual(self.run_gate().returncode, 1)
        (self.root / "part.md").unlink()
        self.assertEqual(self.run_gate().returncode, 1)

    def test_arbitrary_content_sanitization_or_path_escape_fails(self):
        self.m["operator_home"] = "safely"
        self.assertEqual(self.run_gate().returncode, 1)
        self.m["operator_home"] = "/Users/fixture"
        self.m["output_file"] = "../outside.json"
        self.assertEqual(self.run_gate().returncode, 1)

    def test_duplicate_audit_or_hidden_execution_section_fails(self):
        original = self.brief.read_text()
        for extra in ("\n## Co-developer review\nmore", "\n## Requirements\nnew effects"):
            self.brief.write_text(original + extra, encoding="utf-8")
            self.assertEqual(self.run_gate().returncode, 1)

    def test_saved_output_tamper_and_part_reordering_fail(self):
        self.assertEqual(self.run_gate().returncode, 0)
        with (self.root / "output.json").open("a", encoding="utf-8") as f:
            f.write(" ")
        with self.assertRaisesRegex(ValueError, "output hash mismatch"):
            gate.verify(self.brief, self.manifest)
        clean = (self.root / "part.md").read_bytes()
        for name, chunk in (("first.md", clean[:5]), ("second.md", clean[5:])):
            (self.root / name).write_bytes(chunk)
        self.m["parts"] = {"second.md": gate.digest(clean[5:]), "first.md": gate.digest(clean[:5])}
        r = self.run_gate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("reordered", r.stdout)

    def test_driver_must_agree(self):
        self.m["driver_agrees"] = False
        self.assertEqual(self.run_gate().returncode, 1)

    def test_malformed_manifest_is_a_loud_cli_failure(self):
        self.manifest.write_text("{", encoding="utf-8")
        r = subprocess.run([sys.executable, "-B", str(Path(gate.__file__)), str(self.brief), str(self.manifest)],
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL:", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
