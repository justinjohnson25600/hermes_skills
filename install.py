#!/usr/bin/env python3
"""
hermes_skills installer — install any skill from this repo onto this machine.

    # from a clone
    python3 install.py dev-pair

    # or straight from GitHub, no clone needed
    curl -fsSL https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/install.py \\
      | python3 - dev-pair

    python3 install.py --list             # what's available
    python3 install.py dev-pair --dry-run # show every action, change nothing

Piping a remote script into an interpreter means trusting the source. Read it
first if that matters to you — it is short on purpose.

What it does:
  1. Finds THIS machine's Hermes home (HERMES_HOME, %LOCALAPPDATA%\\hermes,
     ~/.hermes, or a dotted dir that actually looks like one).
  2. Installs SKILL.md into <home>/skills/<category>/<name>/.
  3. If the skill ships code (declared in skill.json), installs it and writes a
     CLI shim onto PATH — a .cmd on Windows, a shebang script on POSIX.
  4. Runs the skill's own verify command and reports the result honestly.

Idempotent: re-running upgrades in place. Python 3.8+, stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

RAW_BASE = "https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main"
IS_WIN = os.name == "nt"


def log(msg: str) -> None:
    print(f"[install] {msg}")


# --------------------------------------------------------------------------
def resolve_hermes_home() -> Path:
    """Same resolution order the installed tools use — keep these in step."""
    env = os.environ.get("HERMES_HOME")
    if env and Path(env).is_dir():
        return Path(env)

    home = Path(os.path.expanduser("~"))
    candidates: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "hermes")
    candidates.append(home / ".hermes")
    try:
        candidates.extend(sorted(p for p in home.glob(".*") if p.is_dir()))
    except OSError:
        pass

    for c in candidates:
        try:
            if c.is_dir() and ((c / "config.yaml").is_file() or (c / "skills").is_dir()):
                return c
        except OSError:
            continue
    return home / ".hermes"


def bin_dir() -> Path:
    """Where a user-level CLI belongs on this platform."""
    if IS_WIN:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(local) / "hermes" / "bin"
    return Path.home() / ".local" / "bin"


def fetch(relpath: str, quiet: bool = False) -> str | None:
    """Read a repo file — from the local clone if we're in one, else GitHub."""
    local = Path(__file__).resolve().parent / relpath
    if local.is_file():
        return local.read_text(encoding="utf-8")
    url = f"{RAW_BASE}/{relpath}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310
            return r.read().decode("utf-8")
    except Exception as e:
        # quiet=True for optional files (a missing index is not an error the
        # user needs to see while installing a skill by name).
        if not quiet:
            log(f"could not fetch {relpath}: {e}")
        return None


def list_skills() -> list[str]:
    here = Path(__file__).resolve().parent
    local = sorted(p.name for p in here.iterdir()
                   if p.is_dir() and (p / "SKILL.md").is_file())
    if local:
        return local
    idx = fetch("skills.json", quiet=True)
    if idx:
        try:
            return list(json.loads(idx))
        except Exception:
            pass
    return ["dev-pair"]


# --------------------------------------------------------------------------
def write_shim(name: str, target: Path, py: str, dry: bool) -> Path:
    """Create a CLI entry point that survives interpreter breakage."""
    dest_dir = bin_dir()
    dest = dest_dir / (f"{name}.cmd" if IS_WIN else name)
    if IS_WIN:
        body = f'@echo off\r\n"{py}" "{target}" %*\r\n'
    else:
        body = (
            "#!/bin/bash\n"
            f"# {name} — installed by hermes_skills/install.py\n"
            "set -u\n"
            f'TARGET="{target}"\n'
            f'for py in "{py}" python3.11 python3; do\n'
            '  if command -v "$py" >/dev/null 2>&1 && "$py" -c "import encodings" 2>/dev/null; then\n'
            '    exec "$py" "$TARGET" "$@"\n'
            "  fi\n"
            "done\n"
            f'echo "{name}: no working python found" >&2\n'
            "exit 127\n"
        )
    if dry:
        log(f"DRY-RUN would write shim {dest}")
        return dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    if not IS_WIN:
        dest.chmod(0o755)
    log(f"CLI installed: {dest}")
    if str(dest_dir) not in os.environ.get("PATH", ""):
        log(f"NOTE: {dest_dir} is not on PATH — add it to use `{name}` directly.")
    return dest


def _families_from_config(home: Path) -> dict[str, dict]:
    """Derive real reviewer entries from this machine's config.yaml.

    Two shapes matter and both appear in the wild:
      providers:            <- a map of configured provider IDs
        anthropic: {...}
      fallback_providers:   <- a list of provider/model pairs already proven
        - provider: zai-indirect
          model: glm-5.3
    The fallback list is the better source when present: those pairs are known
    to work on this box, so we prefer them over guessed model names.
    """
    known_family = [
        ("claude", ("anthropic", "claude")),
        ("kimi", ("kimi-coding", "kimi", "moonshot")),
        ("glm", ("zai-indirect", "zai", "zhipu", "glm")),
        ("gpt", ("openai-codex", "openai", "azure")),
        ("qwen", ("qwen", "dashscope", "unsloth", "lmstudio")),
        ("gemini", ("gemini", "google", "vertex")),
    ]
    default_model = {"claude": "claude-sonnet-4.6", "kimi": "kimi-k3",
                     "glm": "glm-5.3", "gpt": "gpt-5.6-luna",
                     "qwen": "qwen3.8-9b", "gemini": "gemini-2.5-pro"}

    def family_of(provider: str) -> str | None:
        p = (provider or "").lower()
        for fam, names in known_family:
            if any(n in p for n in names):
                return fam
        return None

    roster: dict[str, dict] = {}
    yml = home / "config.yaml"
    if not yml.is_file():
        return roster
    try:
        lines = yml.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return roster

    # Pass 1 — fallback_providers / model: real provider+model pairs.
    pending_provider = None
    in_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if line and not line[0].isspace():
            in_list = stripped.startswith(("fallback_providers:", "model:"))
            pending_provider = None
            continue
        if not in_list:
            continue
        if "provider:" in stripped:
            pending_provider = stripped.split("provider:", 1)[1].strip().strip("\"'")
        elif "model:" in stripped and pending_provider:
            model = stripped.split("model:", 1)[1].strip().strip("\"'")
            fam = family_of(pending_provider)
            if fam and fam not in roster and model:
                roster[fam] = {"model": model, "provider": pending_provider,
                               "family": fam, "label": f"{pending_provider}/{model}"}
            pending_provider = None

    # Pass 2 — a providers: map, for families the fallback list didn't cover.
    in_providers = False
    for line in lines:
        if line.startswith("#"):
            continue
        if line.startswith("providers:"):
            in_providers = True
            continue
        if in_providers:
            if line and not line[0].isspace():
                break
            if line.startswith("  ") and not line.startswith("    ") \
                    and line.strip().endswith(":"):
                prov = line.strip().rstrip(":")
                fam = family_of(prov)
                if fam and fam not in roster:
                    roster[fam] = {"model": default_model.get(fam, "unknown"),
                                   "provider": prov, "family": fam,
                                   "label": f"{prov}/{default_model.get(fam, '')}"}
    return roster


def build_reviewer_config(home: Path, state_dir: Path, dry: bool) -> None:
    """Seed dev-pair's roster from THIS machine's configured providers.

    A roster copied from another box names providers that may not exist here,
    so the reviewers are derived from the local config.yaml where possible.
    """
    cfg_file = state_dir / "config.json"
    if cfg_file.is_file():
        log("roster: config.json already present, leaving it alone")
        return

    roster = _families_from_config(home)

    if len(roster) < 2:
        log("roster: fewer than 2 provider families detected — writing a TEMPLATE.")
        log("        Edit config.json and set real models, then run `devpair doctor`.")
        payload = {
            "_comment": "EDIT ME: reviewers must be real providers from your config.yaml. "
                        "At least two DIFFERENT model families are required.",
            "reviewers": roster or {
                "claude": {"model": "claude-sonnet-4.6", "provider": "anthropic",
                           "family": "claude", "label": "Claude"},
            },
            "order": list(roster) or ["claude"],
        }
    else:
        payload = {"reviewers": roster, "order": list(roster)}
        log(f"roster: detected {len(roster)} independent families "
            f"({', '.join(roster)})")
        for k, v in roster.items():
            log(f"        {k:8s} -> {v['provider']}/{v['model']}")

    if dry:
        log(f"DRY-RUN would write {cfg_file}")
        return
    state_dir.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log(f"roster written: {cfg_file}")


# --------------------------------------------------------------------------
def install(skill: str, dry: bool, run_verify: bool) -> int:
    manifest_raw = fetch(f"{skill}/skill.json")
    manifest = {}
    if manifest_raw:
        try:
            manifest = json.loads(manifest_raw)
        except Exception as e:
            log(f"skill.json is not valid JSON: {e}")
            return 1

    skill_md = fetch(f"{skill}/SKILL.md")
    if not skill_md:
        log(f"no such skill: {skill}  (try --list)")
        return 1

    home = resolve_hermes_home()
    category = manifest.get("category", "software-development")
    skills_dir = home / "skills" / category / skill
    log(f"hermes home : {home}")
    log(f"skill target: {skills_dir}")

    if dry:
        log(f"DRY-RUN would write {skills_dir / 'SKILL.md'}")
    else:
        skills_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
        log(f"skill installed: {skills_dir / 'SKILL.md'}")

    files = manifest.get("files", [])
    if not files:
        log("markdown-only skill — nothing else to install.")
        return 0

    state_dir = home / manifest.get("state_dir", skill)
    py = sys.executable or ("python" if IS_WIN else "python3")
    for f in files:
        body = fetch(f"{skill}/{f}")
        if body is None:
            log(f"MISSING file declared in skill.json: {f}")
            return 1
        dest = state_dir / f
        if dry:
            log(f"DRY-RUN would write {dest}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        log(f"installed: {dest}")

    entry = manifest.get("entrypoint")
    if entry:
        write_shim(manifest.get("command", skill), state_dir / entry, py, dry)

    if manifest.get("needs_reviewer_config"):
        build_reviewer_config(home, state_dir, dry)

    verify = manifest.get("verify")
    if verify and run_verify and not dry:
        log(f"verifying: {verify}")
        target = state_dir / verify.replace("{entry}", entry or "")
        try:
            r = subprocess.run([py, str(target)], capture_output=True,
                               text=True, timeout=300)
            tail = (r.stdout or r.stderr or "").strip().splitlines()[-3:]
            for line in tail:
                log(f"  {line}")
            if r.returncode != 0:
                log("VERIFY FAILED — the skill is installed but not proven working.")
                return 1
            log("verify passed.")
        except Exception as e:
            log(f"verify could not run: {e}")

    log("")
    log(f"Done. Next: {manifest.get('next_step', 'see the skill README')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="install.py",
        description="Install a skill from the hermes_skills repo onto this machine.")
    ap.add_argument("skill", nargs="?", help="skill name, e.g. dev-pair")
    ap.add_argument("--list", action="store_true", help="list available skills")
    ap.add_argument("--dry-run", action="store_true", help="show actions, change nothing")
    ap.add_argument("--no-verify", action="store_true", help="skip the post-install check")
    a = ap.parse_args()

    if a.list or not a.skill:
        print("available skills:")
        for s in list_skills():
            print(f"  {s}")
        print("\ninstall with:  python3 install.py <skill>")
        return 0
    return install(a.skill, a.dry_run, not a.no_verify)


if __name__ == "__main__":
    sys.exit(main())
