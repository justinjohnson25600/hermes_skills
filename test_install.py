#!/usr/bin/env python3
"""Regression tests for install.py's shared CLI launcher (shim).

The launcher in ~/.local/bin (Windows: %LOCALAPPDATA%\\hermes\\bin) is shared by every Hermes
home on the account. An install into a non-default home (a profile, a test's temporary home) once
repointed it at that home; when the home was deleted the CLI died. These tests drive the real
write_shim() in child processes whose HOME, USERPROFILE, LOCALAPPDATA and HERMES_HOME point into
a temporary directory, then run the launchers they write. Nothing outside that directory is touched.

Usage: python test_install.py [--installer PATH]   (exit 0 all pass, 1 any failure)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IS_WIN = os.name == "nt"
HERE = Path(__file__).resolve().parent
PASS: list[str] = []
FAIL: list[str] = []

CHILD = r"""
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("installer_under_test", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
dest = m.write_shim("toolx", Path(sys.argv[2]), sys.executable, False)
print("RESULT " + json.dumps({"dest": str(dest)}))
"""


def check(name: str, ok: bool, detail: object = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {detail}"))


class Box:
    """A fake account: its own home, default Hermes home and launcher directory."""

    def __init__(self, root: Path, installer: Path):
        self.root, self.installer = root, installer
        self.home = root / "home"
        self.local = self.home / "AppData" / "Local"
        self.default_home = (self.local / "hermes") if IS_WIN else (self.home / ".hermes")
        self.other_home = root / "other-home"
        self.bin = (self.local / "hermes" / "bin") if IS_WIN else (self.home / ".local" / "bin")
        self.launcher = self.bin / ("toolx.cmd" if IS_WIN else "toolx")
        for h, label in ((self.default_home, "default-copy"), (self.other_home, "other-copy")):
            (h / "tool").mkdir(parents=True, exist_ok=True)
            (h / "config.yaml").write_text("model: {}\n", encoding="utf-8")
            (h / "tool" / "toolx.py").write_text(f"print({label!r})\n", encoding="utf-8")

    def env(self, hermes_home: Path | None) -> dict:
        e = {k: v for k, v in os.environ.items() if k not in ("HERMES_HOME", "LOCALAPPDATA")}
        e["HOME"] = str(self.home)
        e["USERPROFILE"] = str(self.home)
        if IS_WIN:
            e["LOCALAPPDATA"] = str(self.local)
        if hermes_home is not None:
            e["HERMES_HOME"] = str(hermes_home)
        return e

    def install(self, hermes_home: Path | None, target: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-c", CHILD, str(self.installer), str(target)],
                              capture_output=True, text=True, env=self.env(hermes_home), timeout=60)

    def target_in_launcher(self) -> str | None:
        if not self.launcher.is_file():
            return None
        for line in self.launcher.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            for prefix in ('set "TARGET=', 'TARGET="'):
                if s.startswith(prefix):
                    return s[len(prefix):].rstrip('"')
        return None

    def run_launcher(self) -> str:
        cmd = ["cmd", "/c", str(self.launcher)] if IS_WIN else [str(self.launcher)]
        r = subprocess.run(cmd, capture_output=True, text=True, env=self.env(None), timeout=60)
        return (r.stdout + r.stderr).strip()


def scenario(installer: Path, fn) -> None:
    root = Path(tempfile.mkdtemp(prefix="install-shim-"))
    try:
        fn(Box(root, installer))
    except Exception as e:  # a crashing scenario is a failure, never a silent stop
        check(f"{fn.__name__} ran without crashing", False, repr(e))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_default_install_writes_launcher(b: Box) -> None:
    r = b.install(None, b.default_home / "tool" / "toolx.py")
    check("default install exits 0", r.returncode == 0, r.stderr[-300:])
    check("default install writes the launcher at the platform bin dir", b.launcher.is_file(), b.launcher)
    check("launcher points at the default home's copy",
          b.target_in_launcher() == str(b.default_home / "tool" / "toolx.py"), b.target_in_launcher())
    check("launcher runs the default copy", b.run_launcher() == "default-copy", b.run_launcher())


def test_profile_install_keeps_working_launcher(b: Box) -> None:
    b.install(None, b.default_home / "tool" / "toolx.py")
    r = b.install(b.other_home, b.other_home / "tool" / "toolx.py")
    check("non-default install exits 0", r.returncode == 0, r.stderr[-300:])
    check("non-default install does not repoint a working launcher",
          b.target_in_launcher() == str(b.default_home / "tool" / "toolx.py"), b.target_in_launcher())
    check("non-default install says it kept the launcher", "kept the existing toolx launcher" in r.stdout,
          r.stdout[-300:])
    shutil.rmtree(b.other_home)
    check("deleting the non-default home leaves the CLI working", b.run_launcher() == "default-copy",
          b.run_launcher())


def test_dead_launcher_is_repaired(b: Box) -> None:
    b.install(b.root / "gone-home", b.root / "gone-home" / "tool" / "toolx.py")  # target never existed
    r = b.install(b.other_home, b.other_home / "tool" / "toolx.py")
    check("a dead launcher is rewritten", b.target_in_launcher() == str(b.other_home / "tool" / "toolx.py"),
          (b.target_in_launcher(), r.stdout[-300:]))
    check("the repaired launcher runs", b.run_launcher() == "other-copy", b.run_launcher())


def test_launcher_falls_back_to_default_copy(b: Box) -> None:
    b.install(b.other_home, b.other_home / "tool" / "toolx.py")  # no launcher yet: written for other home
    check("first install from a non-default home writes the launcher",
          b.target_in_launcher() == str(b.other_home / "tool" / "toolx.py"), b.target_in_launcher())
    shutil.rmtree(b.other_home)
    check("when its home is deleted the launcher falls back to the default home's copy",
          b.run_launcher() == "default-copy", b.run_launcher())


def test_default_install_repoints_from_profile(b: Box) -> None:
    b.install(b.other_home, b.other_home / "tool" / "toolx.py")
    b.install(None, b.default_home / "tool" / "toolx.py")
    check("a default-home install always owns the launcher",
          b.target_in_launcher() == str(b.default_home / "tool" / "toolx.py"), b.target_in_launcher())


def main() -> int:
    ap = argparse.ArgumentParser(description="install.py launcher regression tests")
    ap.add_argument("--installer", default=str(HERE / "install.py"), help="install.py to test")
    args = ap.parse_args()
    installer = Path(args.installer).resolve()
    print(f"install.py launcher tests ({'windows' if IS_WIN else 'posix'}): {installer}")
    for fn in (
        test_default_install_writes_launcher,
        test_profile_install_keeps_working_launcher,
        test_dead_launcher_is_repaired,
        test_launcher_falls_back_to_default_copy,
        test_default_install_repoints_from_profile,
    ):
        scenario(installer, fn)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
