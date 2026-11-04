"""Real installer and fresh Hermes consumer tests for the unreleased skill.

Run with HERMES_SOURCE_ROOT pointing to a Hermes source checkout and an
interpreter that has that checkout's dependencies. No network is needed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
NAME = "failure-is-not-an-option"
SOURCE = Path(os.environ["HERMES_SOURCE_ROOT"]).resolve()


class SkillInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="failure-skill-tests-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "profile-a"
        self.other = Path(self.temp.name) / "profile-b"
        self.home.mkdir()
        self.other.mkdir()
        self.env = {k: v for k, v in os.environ.items() if k.upper() in {
            "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
            "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA",
            "APPDATA", "LANG", "LC_ALL", "TZ",
        }}
        self.env.update(HERMES_HOME=str(self.home), PYTHONPATH=str(SOURCE), PYTHONDONTWRITEBYTECODE="1")

    def run_process(self, *args, env=None):
        completed = subprocess.run(
            [sys.executable, *map(str, args)], cwd=ROOT, env=env or self.env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return completed.stdout

    def install(self, dry=False):
        args = [ROOT / "install.py", NAME]
        if dry:
            args.append("--dry-run")
        return self.run_process(*args)

    def test_missing_explicit_home_never_falls_back_to_default(self):
        intended = Path(self.temp.name) / "not-yet-created"
        account = Path(self.temp.name) / "account"
        account.mkdir()
        default = account / ("AppData/Local/hermes" if os.name == "nt" else ".hermes")
        default.mkdir(parents=True)
        (default / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        self.env.update(HERMES_HOME=str(intended), HOME=str(account), USERPROFILE=str(account),
                        LOCALAPPDATA=str(account / "AppData" / "Local"))
        result = subprocess.run([sys.executable, str(ROOT / "install.py"), NAME], cwd=ROOT,
                                env=self.env, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=60)
        target = intended / "skills" / "autonomous-ai-agents" / NAME / "SKILL.md"
        self.assertFalse((default / "skills").exists(), result.stdout + result.stderr)
        if result.returncode == 0:
            self.assertTrue(target.is_file(), result.stdout + result.stderr)
        else:
            self.assertIn("HERMES_HOME", result.stdout + result.stderr)
            self.assertFalse(target.exists())

    def test_explicit_file_home_is_refused_without_other_writes(self):
        file_home = Path(self.temp.name) / "not-a-directory"
        file_home.write_text("protected", encoding="utf-8")
        self.env["HERMES_HOME"] = str(file_home)
        result = subprocess.run([sys.executable, str(ROOT / "install.py"), NAME], cwd=ROOT,
                                env=self.env, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=60)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("HERMES_HOME", result.stdout + result.stderr)
        self.assertEqual(file_home.read_text(encoding="utf-8"), "protected")
        self.assertEqual(list(self.other.iterdir()), [])

    def test_default_resolution_agrees_with_real_consumer(self):
        account = Path(self.temp.name) / "account"
        account.mkdir()
        decoy = account / ".other-hermes"
        (decoy / "skills").mkdir(parents=True)
        env = dict(self.env, HOME=str(account), USERPROFILE=str(account),
                   LOCALAPPDATA=str(account / "AppData" / "Local"), HERMES_DATA_DIR_SUFFIX="-test")
        env.pop("HERMES_HOME")
        actual = self.run_process("-c", "from hermes_constants import get_hermes_home; print(get_hermes_home())", env=env).strip()
        output = self.run_process(ROOT / "install.py", NAME, "--dry-run", env=env)
        self.assertIn("hermes home : " + actual, output)
        self.assertNotIn("hermes home : " + str(decoy), output)
        self.assertEqual(list(decoy.iterdir()), [decoy / "skills"])

    def test_expanded_explicit_home_matches_real_consumer(self):
        env = dict(self.env, HERMES_TEST_TARGET=str(self.home), HERMES_HOME="$HERMES_TEST_TARGET")
        expected = self.run_process("-c", "from hermes_constants import get_hermes_home; print(get_hermes_home())", env=env).strip()
        output = self.run_process(ROOT / "install.py", NAME, "--dry-run", env=env)
        self.assertIn("hermes home : " + expected, output)

    def test_dry_run_does_not_install(self):
        self.assertIn("DRY-RUN", self.install(dry=True))
        self.assertFalse((self.home / "skills").exists())
        self.assertEqual(list(self.other.iterdir()), [])

    def test_installer_copies_exact_candidate_only_into_active_profile(self):
        self.install()
        target = self.home / "skills" / "autonomous-ai-agents" / NAME / "SKILL.md"
        self.assertEqual(target.read_text(encoding="utf-8"), (ROOT / NAME / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(list(self.other.iterdir()), [])
        self.assertFalse((self.home / "SOUL.md").exists())

    def test_piped_installer_fetches_from_loopback_and_respects_profile(self):
        requested = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                requested.append(self.path)
                allowed = {f"/{NAME}/skill.json", f"/{NAME}/SKILL.md"}
                if self.path not in allowed:
                    self.send_error(404)
                    return
                content = (ROOT / self.path.lstrip("/")).read_bytes()
                self.send_response(200)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 10)
        self.addCleanup(server.shutdown)

        # Rewrite only the fixture's known repository URL; real traffic stays on loopback.
        shim = Path(self.temp.name) / "sitecustomize.py"
        shim.write_text(
            "import os, urllib.request\n"
            "_open = urllib.request.urlopen\n"
            "def local_only(url, *a, **kw):\n"
            "    base = 'https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/'\n"
            "    if not isinstance(url, str) or not url.startswith(base): raise ValueError('unexpected URL')\n"
            "    return _open(os.environ['FIXTURE_ORIGIN'] + '/' + url[len(base):], *a, **kw)\n"
            "urllib.request.urlopen = local_only\n", encoding="utf-8")
        account = Path(self.temp.name) / "account"
        account.mkdir()
        env = dict(self.env, PYTHONPATH=str(shim.parent) + os.pathsep + str(SOURCE),
                   HOME=str(account), USERPROFILE=str(account), LOCALAPPDATA=str(account / "AppData" / "Local"),
                   FIXTURE_ORIGIN=f"http://127.0.0.1:{server.server_port}")
        result = subprocess.run([sys.executable, "-", NAME], input=(ROOT / "install.py").read_text(encoding="utf-8"),
                                cwd=self.temp.name, env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = self.home / "skills" / "autonomous-ai-agents" / NAME / "SKILL.md"
        self.assertEqual(target.read_text(encoding="utf-8"), (ROOT / NAME / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn(b"Failure is not an option.", target.read_bytes())
        self.assertEqual(set(requested), {f"/{NAME}/skill.json", f"/{NAME}/SKILL.md"})
        self.assertEqual(list(self.other.iterdir()), [])
        self.assertFalse((self.home / "SOUL.md").exists())
        missing = Path(self.temp.name) / "missing-profile"
        refused = subprocess.run([sys.executable, "-", NAME], input=(ROOT / "install.py").read_text(encoding="utf-8"),
                                 cwd=self.temp.name, env=dict(env, HERMES_HOME=str(missing)),
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
        self.assertIn("HERMES_HOME", refused.stdout + refused.stderr)
        self.assertFalse(missing.exists())
        self.assertEqual(list(account.iterdir()), [])

    def test_fresh_consumer_discovers_and_views_installed_skill(self):
        self.install()
        code = (
            "import json; from tools.skills_tool import skills_list,skill_view; "
            "from tools.skill_manager_tool import _validate_frontmatter; "
            "from tools.skill_linter import lint_skill; from pathlib import Path; "
            "r=json.loads(skill_view('failure-is-not-an-option')); "
            "print(json.dumps({'listed': 'failure-is-not-an-option' in skills_list(), "
            "'result':r, 'frontmatter_error':_validate_frontmatter(r.get('content','')), "
            "'lint':[(x.severity,x.rule) for x in lint_skill(Path(r['skill_dir'])/'SKILL.md')]}))"
        )
        result = json.loads(self.run_process("-c", code))
        self.assertTrue(result["listed"])
        self.assertTrue(result["result"]["success"])
        self.assertIn("Failure is not an option.", result["result"]["content"])
        self.assertIsNone(result["frontmatter_error"])
        self.assertEqual(result["lint"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
