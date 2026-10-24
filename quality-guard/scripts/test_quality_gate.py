"""Offline release/installation contract tests; Python 3.8+, no third-party packages."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts' / 'quality_gate.py'
GOOD = 'Verified: local fixture executed\nUnverified: none\nAssumptions: none\n'


class QualityGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='quality-guard-test-')
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.response = self.put('response.md', GOOD)
        self.artifact = self.put('client.txt', 'Requested multilingual content: 日本語.\n')
        self.receipt = self.work / 'receipt.json'

    def put(self, name, text, encoding='utf-8'):
        p = self.work / name
        p.write_text(text, encoding=encoding)
        return p

    def cli(self, *args):
        self.assertTrue(HELPER.is_file(), 'Approved bounded helper has not been implemented')
        flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        r = subprocess.run([sys.executable, str(HELPER)] + [str(x) for x in args],
                           capture_output=True, timeout=15, cwd=str(self.work), **flags)
        self.assertNotIn(b'Traceback', r.stderr)
        obj = json.loads(r.stdout.decode('ascii'))
        self.assertEqual(obj['readiness'], 'not_assessed')
        return r.returncode, obj

    def lint(self, text=GOOD, **kwargs):
        self.response.write_text(text, encoding=kwargs.pop('encoding', 'utf-8'))
        args = ['lint', '--response', self.response]
        if kwargs.pop('artifact', False):
            args += ['--artefact', self.artifact]
        return self.cli(*args, *kwargs.pop('extra', []))

    def run_check(self, code='print("fixture success")', **kwargs):
        args = ['run', '--receipt', self.receipt, '--artefact', self.artifact]
        args += kwargs.pop('extra', [])
        return self.cli(*args, '--', sys.executable, '-c', code)

    def verify(self):
        return self.cli('verify', '--receipt', self.receipt, '--artefact', self.artifact)

    def test_valid_record_is_not_readiness(self):
        rc, obj = self.lint()
        self.assertEqual(rc, 0)
        self.assertEqual(obj['status'], 'pass')
        self.assertEqual(obj['scope'], 'record-structure-and-placement')

    def test_empty_fields_fail(self):
        self.assertEqual(self.lint('Verified:\nUnverified:\nAssumptions:\n')[0], 1)

    def test_blank_verified_fails(self):
        self.assertEqual(self.lint(GOOD.replace('local fixture executed', '  '))[0], 1)

    def test_template_fails(self):
        self.assertEqual(self.lint(GOOD.replace('local fixture executed', '<actions taken>'))[0], 1)

    def test_bracket_template_fails(self):
        self.assertEqual(self.lint(GOOD.replace('local fixture executed', '[insert actions]'))[0], 1)

    def test_real_bracket_labels_pass(self):
        self.assertEqual(self.lint(GOOD.replace('Unverified: none', 'Unverified: [UNSUPPORTED CLAIM] SMTP path'))[0], 0)

    def test_label_without_detail_fails(self):
        self.assertEqual(self.lint(GOOD.replace('Unverified: none', 'Unverified: [UNSUPPORTED CLAIM]'))[0], 1)

    def test_footer_must_be_terminal(self):
        self.assertEqual(self.lint(GOOD + 'More delivery content.\n')[0], 1)

    def test_footer_must_be_consecutive(self):
        self.assertEqual(self.lint(GOOD.replace('Unverified:', 'Other paragraph\nUnverified:'))[0], 1)

    def test_fenced_example_is_not_a_record(self):
        self.assertEqual(self.lint('```text\n' + GOOD + '```\n')[0], 1)

    def test_bold_labels_are_not_the_contract(self):
        self.assertEqual(self.lint(GOOD.replace('Verified:', '**Verified:**'))[0], 1)

    def test_internal_tier_does_not_require_footer(self):
        self.assertEqual(self.lint('Internal draft.\n', extra=['--tier', '1'])[0], 0)

    def test_ready_words_are_not_semantically_certified(self):
        rc, obj = self.lint('This is production-ready.\n' + GOOD.replace('Unverified: none', 'Unverified: production writes'))
        self.assertEqual(rc, 0)
        self.assertEqual(obj['readiness'], 'not_assessed')

    def test_low_stakes_tier_permits_no_record(self):
        self.assertEqual(self.lint('Low-stakes copy.\n', extra=['--tier', '2'])[0], 0)

    def test_low_stakes_malformed_record_still_fails(self):
        self.assertEqual(self.lint('Verified:\n', extra=['--tier', '2'])[0], 1)

    def test_oversized_response_is_error(self):
        self.assertEqual(self.lint('x' * (4 * 1024 * 1024 + 1))[0], 2)

    def test_non_utf_input_is_error(self):
        self.response.write_bytes(b'\xffnot-utf8')
        self.assertEqual(self.cli('lint', '--response', self.response)[0], 2)

    def test_multilingual_content_is_not_rejected(self):
        self.assertEqual(self.lint(artifact=True)[0], 0)

    def test_plain_client_footer_is_rejected(self):
        self.artifact.write_text(GOOD, encoding='utf-8')
        self.assertEqual(self.lint(artifact=True)[0], 1)

    def test_html_client_footer_is_rejected(self):
        self.artifact = self.put('client.html', '<p>Verified: tests</p><p>Unverified: none</p><p>Assumptions: none</p>')
        self.assertEqual(self.lint(artifact=True)[0], 1)

    def test_fenced_client_footer_is_rejected(self):
        self.artifact.write_text('```\n' + GOOD + '```', encoding='utf-8')
        self.assertEqual(self.lint(artifact=True)[0], 1)

    def test_utf16_response_supported(self):
        self.assertEqual(self.lint(encoding='utf-16')[0], 0)

    def test_utf16_client_footer_detected(self):
        self.artifact.write_text(GOOD, encoding='utf-16')
        self.assertEqual(self.lint(artifact=True)[0], 1)

    def test_utf8_bom_supported(self):
        self.assertEqual(self.lint(encoding='utf-8-sig')[0], 0)

    def test_nul_input_is_explicit_error(self):
        self.assertEqual(self.lint('V\x00e\x00r\x00')[0], 2)

    def test_unsupported_artifact_is_error(self):
        self.artifact = self.put('client.pdf', 'not a PDF parser')
        self.assertEqual(self.lint(artifact=True)[0], 2)

    def test_missing_response_is_error(self):
        self.response.unlink()
        self.assertEqual(self.cli('lint', '--response', self.response)[0], 2)

    def test_cp1252_pipeline_receives_ascii_json(self):
        self.artifact.write_text(GOOD, encoding='utf-8')
        flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        # This encoding fixture needs OS paths/temp, not the caller's credentials.
        env = {'PYTHONIOENCODING': 'cp1252', 'PYTHONUTF8': '0'}
        for key in ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'TMPDIR'):
            value = os.environ.get(key)
            if value is not None:
                env[key] = value
        self.assertTrue(HELPER.is_file(), 'Approved bounded helper has not been implemented')
        r = subprocess.run([sys.executable, str(HELPER), 'lint', '--response', str(self.response), '--artefact', str(self.artifact)],
                           env=env, capture_output=True, timeout=15, **flags)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(json.loads(r.stdout.decode('ascii'))['readiness'], 'not_assessed')
        self.assertNotIn(b'UnicodeEncodeError', r.stderr)

    def test_run_records_actual_execution_without_raw_secrets(self):
        rc, obj = self.run_check('print("private-fixture-marker")')
        self.assertEqual(rc, 0)
        record = json.loads(self.receipt.read_text())
        self.assertEqual(record['schema_version'], 1)
        self.assertEqual(record['returncode'], 0)
        self.assertTrue(record['complete'])
        self.assertNotIn('private-fixture-marker', self.receipt.read_text())
        self.assertEqual(record['stdout_sha256'], hashlib.sha256(b'private-fixture-marker\r\n' if os.name == 'nt' else b'private-fixture-marker\n').hexdigest())
        self.assertEqual(obj['readiness'], 'not_assessed')

    def test_receipt_permissions(self):
        self.run_check()
        if os.name == 'nt':
            self.assertTrue(self.receipt.is_file())
        else:
            self.assertEqual(self.receipt.stat().st_mode & 0o777, 0o600)

    def test_verify_fresh_receipt(self):
        self.run_check()
        self.assertEqual(self.verify()[0], 0)

    def test_verify_changed_artifact_fails(self):
        self.run_check()
        self.artifact.write_text('changed after checking')
        self.assertEqual(self.verify()[0], 1)

    def test_failed_command_is_not_green(self):
        self.assertEqual(self.run_check('import sys; sys.exit(7)')[0], 1)
        self.assertEqual(self.verify()[0], 1)

    def test_changed_during_check_is_not_green(self):
        code = 'from pathlib import Path; Path(%r).write_text("rewritten")' % str(self.artifact)
        self.assertEqual(self.run_check(code)[0], 1)
        self.assertEqual(self.verify()[0], 1)

    def test_timeout_records_incomplete_execution(self):
        before = time.monotonic()
        self.assertEqual(self.run_check('import time; time.sleep(30)', extra=['--timeout', '0.3'])[0], 2)
        self.assertLess(time.monotonic() - before, 8)
        self.assertFalse(json.loads(self.receipt.read_text())['complete'])
        self.assertEqual(self.verify()[0], 1)

    def test_output_limit_is_not_green(self):
        self.assertEqual(self.run_check('print("x" * 10000)', extra=['--max-output-bytes', '256'])[0], 2)
        self.assertFalse(json.loads(self.receipt.read_text())['complete'])

    def test_existing_receipt_refuses_before_execution(self):
        self.receipt.write_text('preserve this')
        marker = self.work / 'must-not-exist'
        code = 'from pathlib import Path; Path(%r).touch()' % str(marker)
        self.assertEqual(self.run_check(code)[0], 2)
        self.assertFalse(marker.exists())
        self.assertEqual(self.receipt.read_text(), 'preserve this')

    def test_missing_artifact_refuses_before_execution(self):
        self.artifact.unlink()
        marker = self.work / 'must-not-exist'
        code = 'from pathlib import Path; Path(%r).touch()' % str(marker)
        self.assertEqual(self.run_check(code)[0], 2)
        self.assertFalse(marker.exists())

    def test_malformed_receipt_is_error(self):
        self.receipt.write_text('{broken')
        self.assertEqual(self.verify()[0], 2)

    def test_duplicate_json_keys_are_error(self):
        self.receipt.write_text('{"schema_version":1,"schema_version":1}')
        self.assertEqual(self.verify()[0], 2)

    def load_helper(self):
        spec = importlib.util.spec_from_file_location('qg_fixture', str(HELPER))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_deep_json_is_structured_input_error(self):
        self.receipt.write_text('{"unused":' + '[' * 1200 + '0' + ']' * 1200 + '}')
        self.assertEqual(self.verify()[0], 2)

    def test_special_text_inputs_refuse_without_blocking(self):
        module = self.load_helper()
        mode = SimpleNamespace(st_size=0, st_mode=stat.S_IFIFO)
        with mock.patch.object(module.Path, 'stat', return_value=mode), \
             mock.patch.object(module.Path, 'read_bytes', return_value=GOOD.encode()) as read:
            with self.assertRaisesRegex(module.InputError, 'regular'):
                module.read_text(self.response)
            read.assert_not_called()
        # Both platforms exercise the guard above. POSIX additionally uses real FIFOs.
        if hasattr(os, 'mkfifo'):
            for name, args in (('fifo.md', ['lint', '--response']),
                               ('fifo.json', ['verify', '--artefact', self.artifact, '--receipt'])):
                fifo = self.work / name
                os.mkfifo(str(fifo))
                flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
                try:
                    child = subprocess.run([sys.executable, str(HELPER)] + [str(x) for x in args] + [str(fifo)],
                                           capture_output=True, timeout=3, **flags)
                except subprocess.TimeoutExpired:
                    self.fail('FIFO input blocked instead of returning an input error')
                self.assertEqual(child.returncode, 2)
                self.assertEqual(json.loads(child.stdout)['readiness'], 'not_assessed')

    def test_text_read_is_capped_not_just_stat_checked(self):
        module = self.load_helper()
        reads = []
        real_open = module.Path.open
        class TracedRead:
            def __init__(self, file):
                self.file = file
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return self.file.__exit__(*args)
            def fileno(self):
                return self.file.fileno()
            def read(self, size=-1):
                reads.append(size)
                return self.file.read(size)
        def traced(path, *args, **kwargs):
            return TracedRead(real_open(path, *args, **kwargs))
        with mock.patch.object(module.Path, 'open', autospec=True, side_effect=traced):
            self.assertEqual(module.read_text(self.response), GOOD)
        self.assertEqual(reads, [module.LIMIT + 1])

    def test_ordinary_descendant_is_explicitly_outside_completion_scope(self):
        release = self.work / 'release'
        late = self.work / 'late'
        grandchild = ('import time; from pathlib import Path; p=Path(%r); end=time.monotonic()+4; '
                      '\nwhile not p.exists() and time.monotonic()<end: time.sleep(.02)'
                      '\np=Path(%r); t=p.with_suffix(".part"); t.write_text("finished"); '
                      't.replace(p); print("x"*10000)') % (str(release), str(late))
        # The fixture deliberately outlives its parent. Do not keep its CWD/file
        # handles in the disposable test directory (Windows rmdir would race it).
        parent = ('import subprocess,sys; subprocess.Popen([sys.executable,"-c",%r], '
                  'cwd=%r, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))') % (grandchild, str(self.work.parent))
        rc, obj = self.run_check(parent, extra=['--max-output-bytes', '256'])
        data = json.loads(self.receipt.read_text())
        release.touch()
        deadline = time.monotonic() + 6
        while not late.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue(late.is_file(), 'finite ordinary descendant fixture did not finish')
        self.assertEqual(rc, 0)
        self.assertEqual(data.get('completion_scope'), 'direct_child')
        self.assertEqual(obj.get('descendant_completion'), 'not_assessed')

    def test_receipt_requires_explicit_completion_scope(self):
        self.run_check()
        data = json.loads(self.receipt.read_text())
        data.pop('completion_scope', None)
        self.receipt.write_text(json.dumps(data))
        self.assertEqual(self.verify()[0], 2)

    def test_receipt_cannot_supply_unapproved_paths(self):
        self.run_check()
        r = json.loads(self.receipt.read_text())
        r['artifacts'][0]['path'] = str(self.work / 'unapproved')
        self.receipt.write_text(json.dumps(r))
        self.assertEqual(self.verify()[0], 2)

    def test_receipt_missing_required_fields_is_error(self):
        self.receipt.write_text('{}')
        self.assertEqual(self.verify()[0], 2)

    def test_receipt_invalid_run_id_is_error(self):
        self.run_check()
        data = json.loads(self.receipt.read_text())
        data['run_id'] = []
        self.receipt.write_text(json.dumps(data))
        self.assertEqual(self.verify()[0], 2)

    def test_receipt_unknown_status_is_error(self):
        self.run_check()
        data = json.loads(self.receipt.read_text())
        data['status'] = 'invented-status'
        self.receipt.write_text(json.dumps(data))
        self.assertEqual(self.verify()[0], 2)

    def test_multiple_required_receipts_include_failure(self):
        self.run_check()
        good = self.receipt
        self.receipt = self.work / 'failed.json'
        self.run_check('raise SystemExit(9)')
        self.assertEqual(self.cli('verify', '--receipt', good, '--receipt', self.receipt,
                                  '--artefact', self.artifact)[0], 1)

    def test_receipt_parent_missing_refuses_before_execution(self):
        self.receipt = self.work / 'missing' / 'receipt.json'
        marker = self.work / 'must-not-exist'
        code = 'from pathlib import Path; Path(%r).touch()' % str(marker)
        self.assertEqual(self.run_check(code)[0], 2)
        self.assertFalse(marker.exists())

    def test_release_version_and_short_trigger(self):
        text = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
        match = re.search(r'^description: (.*)$', text, re.M)
        self.assertIsNotNone(match)
        assert match is not None
        desc = match.group(1).strip('"')
        self.assertLessEqual(len(desc), 60)
        self.assertIn('version: 0.1.1', text)

    def test_docs_do_not_claim_footer_is_proof(self):
        for name in ('SKILL.md', 'README.md'):
            text = (ROOT / name).read_text(encoding='utf-8').lower()
            self.assertNotIn('footer is the observable proof', text)
            self.assertIn('not proof', text)

    def test_manifest_ships_helper_and_tests(self):
        # Native URL installs do not fetch skill.json; this test's local receipt
        # and schema assertions remain available there, manifest checked in repo installs.
        p = ROOT / 'skill.json'
        if p.is_file():
            data = json.loads(p.read_text())
            self.assertIn('scripts/quality_gate.py', data['skill_files'])
            self.assertIn('scripts/test_quality_gate.py', data['skill_files'])
            self.assertEqual(data['verify_skill'], 'scripts/test_quality_gate.py')
        else:
            self.assertTrue(HELPER.is_file())
            self.assertTrue((ROOT / 'README.md').is_file())


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(QualityGuardTests))
    failed = len(result.failures) + len(result.errors)
    print('%d passed, %d failed' % (result.testsRun - failed - len(result.skipped), failed))
    if result.skipped:
        print('SKIPPED %d: release qualification requires no skipped tests' % len(result.skipped))
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
