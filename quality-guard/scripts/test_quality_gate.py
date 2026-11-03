#!/usr/bin/env python3
"""Offline contract tests for the quality-guard 1.0.x gate (Python 3.8+, stdlib only).

Pins the behaviour contracts of scripts/quality_gate.py as landed in 1.0.7:
  - exit 0 / JSON pass=true only for a well-formed, filled footer
  - blank/placeholder/bold/bracket footers BLOCK (they are not evidence)
  - tier gating: footer required at tier 3, optional below
  - unreadable artefacts block; JSON is valid on every path
The 0.1.x receipt/readiness contracts were retired with the 0.1.x gate.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts' / 'quality_gate.py'
GOOD = 'Verified: local fixture executed\nUnverified: none\nAssumptions: none\n'


def gate(tmp: Path, response_text: str, *extra: str) -> tuple[int, dict]:
    r = tmp / 'response.md'
    r.write_text(response_text, encoding='utf-8')
    args = [sys.executable, str(HELPER), '--response', str(r), '--json', *extra]
    p = subprocess.run(args, capture_output=True, timeout=30, cwd=str(tmp))
    assert b'Traceback' not in p.stderr, p.stderr.decode('utf-8', 'replace')
    return p.returncode, json.loads(p.stdout.decode('utf-8'))


class FooterContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='qg17-'))

    def test_good_footer_passes(self):
        rc, o = gate(self.tmp, GOOD)
        self.assertEqual((rc, o['pass'], o['blocking']), (0, True, 0))

    def test_blank_verified_blocks(self):
        rc, o = gate(self.tmp, GOOD.replace('local fixture executed', '   '))
        self.assertEqual((rc, o['pass']), (1, False))
        self.assertIn('footer-unfilled', [f['check'] for f in o['findings']])

    def test_placeholder_blocks(self):
        rc, o = gate(self.tmp, GOOD.replace('local fixture executed', '<actions taken>'))
        self.assertEqual((rc, o['pass']), (1, False))

    def test_bracket_template_blocks(self):
        rc, o = gate(self.tmp, GOOD.replace('local fixture executed', '[insert actions]'))
        self.assertEqual((rc, o['pass']), (1, False))

    def test_bold_labels_block(self):
        rc, o = gate(self.tmp, GOOD.replace('Verified:', '**Verified:**'))
        self.assertEqual((rc, o['pass']), (1, False))

    def test_missing_footer_blocks_at_tier3(self):
        rc, o = gate(self.tmp, 'no footer at all\n')
        self.assertEqual((rc, o['pass']), (1, False))
        self.assertIn('footer-missing', [f['check'] for f in o['findings']])

    def test_footer_optional_below_tier3(self):
        rc, o = gate(self.tmp, 'no footer at all\n', '--tier', '2')
        self.assertEqual((rc, o['pass'], o['blocking']), (0, True, 0))

    def test_unreadable_artifact_blocks(self):
        rc, o = gate(self.tmp, GOOD, '--artefact', str(self.tmp / 'nope.txt'))
        self.assertEqual((rc, o['pass']), (1, False))
        self.assertIn('unreadable', [f['check'] for f in o['findings']])


if __name__ == '__main__':
    unittest.main(verbosity=1)
