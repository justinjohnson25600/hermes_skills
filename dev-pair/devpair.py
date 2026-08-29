#!/usr/bin/env python3.11
"""
DEV PAIR — the second pair of eyes.

A supervisory review partner that runs on a DIFFERENT LLM than the agent doing
the work. It critiques direction, challenges approach, finds the bug you can't
see, and asks the questions that expose gaps.

It does NOT write the implementation. It never does the work twice.

Usage:
    devpair critique  --plan  PLAN.md            # before you build
    devpair review    --diff                     # after you build
    devpair debug     --error err.txt --files a.py b.py
    devpair alt       --ask "should this be a cron job or a daemon?"
    devpair followup  --ask "I fixed #1 and #3 by X. #2 I disagree because Y."

    devpair log                                  # what the pair has said so far
    devpair reset                                # start a fresh pairing session
    devpair doctor                               # check reviewer backends
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.path.expanduser("~"))


def _resolve_hermes_home() -> Path:
    """Find THIS machine's Hermes home. Layouts differ per platform/install:
    ~/.hermes on most POSIX boxes, %LOCALAPPDATA%\\hermes on Windows, and some
    installs mask or relocate it. Guessing wrong means writing state into a
    directory the agent never reads, silently.

    Order: HERMES_HOME env > a dotted/known dir that actually looks like a
    Hermes home > ~/.hermes as a last resort.
    """
    env = os.environ.get("HERMES_HOME")
    if env and Path(env).is_dir():
        return Path(env)

    candidates: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "hermes")
    candidates.append(HOME / ".hermes")
    # Some installs display-mask the config home; find it by shape, not name.
    try:
        candidates.extend(sorted(p for p in HOME.glob(".*") if p.is_dir()))
    except OSError:
        pass

    for c in candidates:
        try:
            if c.is_dir() and ((c / "config.yaml").is_file() or (c / "skills").is_dir()):
                return c
        except OSError:
            continue
    return HOME / ".hermes"


BASE = _resolve_hermes_home() / "devpair"
SESSIONS = BASE / "sessions"
CONFIG = BASE / "config.json"
CURRENT = BASE / "current_session"
LEDGER = BASE / "invocations.jsonl"

MAX_CONTEXT_CHARS = 90_000
MAX_FILE_CHARS = 24_000
MAX_DIFF_CHARS = 60_000
MAX_UNTRACKED_FILES = 5
MAX_UNTRACKED_CHARS = 8_000
MAX_UNTRACKED_BYTES = 256_000

# ---------------------------------------------------------------------------
# Reviewer roster. Ordered by preference. Each MUST be a different model family
# from the driver so the critique is genuinely independent.
# ---------------------------------------------------------------------------
REVIEWERS = {
    "kimi": {
        "model": "kimi-k3",
        "provider": "kimi-coding",
        "family": "kimi",
        "label": "Kimi K3",
    },
    "claude": {
        "model": "claude-sonnet-4.6",
        "provider": "anthropic",
        "family": "claude",
        "label": "Claude Sonnet 4.6",
    },
    "glm": {
        "model": "glm-5.3",
        "provider": "zai",
        "family": "glm",
        "label": "GLM-5.3",
    },
    "local": {
        "model": "qwen3.8-9b",
        "provider": "lmstudio",
        "family": "qwen",
        "label": "Qwen3.8-9B (local)",
    },
}
DEFAULT_ORDER = ["kimi", "claude", "local"]


def _load_roster() -> None:
    """Let each machine declare its OWN reviewers in config.json.

    Providers differ per install, so a hardcoded roster is wrong the moment the
    tool leaves the box it was written on. `reviewers` REPLACES the defaults;
    the shipped dict is only a starting example.

    config.json:
      {"reviewers": {"claude": {"model": "...", "provider": "...",
                                "family": "claude", "label": "..."}},
       "order": ["claude", "kimi"]}
    """
    cfg = _load_cfg()
    custom = cfg.get("reviewers")
    if not isinstance(custom, dict) or not custom:
        return
    valid: dict[str, dict] = {}
    for key, r in custom.items():
        if not isinstance(r, dict):
            continue
        if not r.get("model") or not r.get("provider"):
            continue
        valid[key] = {
            "model": r["model"],
            "provider": r["provider"],
            # Infer the family when not declared, so a roster entry cannot
            # accidentally claim independence it does not have. NOTE: _family_of
            # returns the STRING "unknown", which is truthy — an `or` chain here
            # would stop at it and hand back a reviewer of unprovable family.
            "family": (r.get("family")
                       or _resolve_family(r["model"], r["provider"])),
            "label": r.get("label") or f"{r['provider']}/{r['model']}",
        }
    if valid:
        REVIEWERS.clear()
        REVIEWERS.update(valid)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


# ---------------------------------------------------------------------------
# Invocation control. v1.1.5 said "USER-INVOKED ONLY" in SKILL.md prose, which
# a misbehaving agent simply ignores. Prose is not a control. These are:
#
#   ledger  — every paid run is appended to an append-only file BEFORE the
#             backend is called, so an unasked-for run is visible after the
#             fact even if the agent never mentions it.
#   cap     — a hard daily ceiling on paid runs. This is the only mechanism
#             here that an agent cannot talk its way past: the process refuses
#             to make the call, regardless of what it believes it was told.
#   attest  — the caller must state WHO asked. Defeatable by a lying agent,
#             so it is a record, not a lock; the cap is what actually bites.
# ---------------------------------------------------------------------------
def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def read_ledger(days: int = 0) -> list[dict]:
    """Parse the invocation ledger. A corrupt line is skipped, never fatal —
    losing the audit trail must not take the tool down with it."""
    if not LEDGER.is_file():
        return []
    cutoff = time.time() - days * 86400 if days else 0
    out = []
    try:
        for line in LEDGER.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if cutoff and rec.get("epoch", 0) < cutoff:
                continue
            out.append(rec)
    except OSError:
        return []
    return out


def runs_today() -> int:
    today = _today()
    return sum(1 for r in read_ledger(days=2) if r.get("day") == today)


def daily_cap() -> int:
    """0 = unlimited. Config-driven so a machine can set its own ceiling."""
    try:
        return int(_load_cfg().get("daily_cap", 0) or 0)
    except (TypeError, ValueError):
        return 0


def log_invocation(mode: str, reviewer: dict, driver: dict, requested_by: str,
                   context_chars: int) -> None:
    """Append BEFORE the paid call, so a run that crashes mid-review is still
    on the record. Best-effort: a failure to log must not block the review."""
    rec = {
        "at": _now(), "epoch": time.time(), "day": _today(), "mode": mode,
        "reviewer": f"{reviewer['provider']}/{reviewer['model']}",
        "driver": f"{driver['provider']}/{driver['model']}",
        "requested_by": requested_by, "context_chars": context_chars,
        "cwd": os.getcwd(), "pid": os.getpid(),
    }
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError as e:
        print(f"[devpair] note: could not write the invocation ledger ({e})",
              file=sys.stderr)


def authorize(args, reviewer: dict, driver: dict, context_chars: int) -> None:
    """Gate a paid run. Exits non-zero rather than spending tokens."""
    cap = daily_cap()
    if cap:
        used = runs_today()
        if used >= cap:
            sys.exit(
                f"devpair: daily cap reached — {used}/{cap} paid runs today.\n"
                "  This is a hard stop: no reviewer will be called.\n"
                f"  Raise or clear it with \"daily_cap\" in {CONFIG}, or wait for tomorrow.\n"
                "  See what spent it: devpair audit --days 1"
            )

    requested_by = (getattr(args, "requested_by", None)
                    or os.environ.get("DEVPAIR_REQUESTED_BY") or "").strip()
    require = bool(_load_cfg().get("require_attestation"))
    if require and not requested_by:
        sys.exit(
            "devpair: this install requires --requested-by on every run.\n"
            "  Name who asked for the review, e.g. --requested-by user\n"
            "  (agents: this is an attestation — do not fill it in unless the\n"
            "  user actually asked)."
        )
    log_invocation(args.mode, reviewer, driver, requested_by or "unattributed",
                   context_chars)



def _load_cfg() -> dict:
    if CONFIG.is_file():
        try:
            return json.loads(CONFIG.read_text())
        except Exception:
            pass
    return {}


def driver_identity(explicit: str | None = None) -> dict:
    """Which model is doing the actual work (the one being supervised).

    Precedence: explicit --driver flag > DEVPAIR_DRIVER_* env vars > config.yaml
    default. The config default is only a guess — the live session model is what
    must be passed in, or the same-family guard silently protects the wrong model.
    """
    cfg_path = _resolve_hermes_home() / "config.yaml"
    model, provider = "unknown", "unknown"
    try:
        import yaml  # type: ignore

        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        m = cfg.get("model")
        if isinstance(m, dict):
            model = m.get("default") or model
            provider = m.get("provider") or provider
        elif isinstance(m, str):
            model = m
    except Exception:
        pass
    # A live agent can be overridden per-session; honour an explicit hint.
    model = os.environ.get("DEVPAIR_DRIVER_MODEL", model)
    provider = os.environ.get("DEVPAIR_DRIVER_PROVIDER", provider)
    if explicit:
        if "/" in explicit:
            provider, model = explicit.split("/", 1)
        else:
            model = explicit
    family = _family_of(model)
    if family == "unknown":
        # A model alias we don't recognise (e.g. "my-fast-coder") would make
        # every reviewer look independent, which is exactly the failure this
        # tool exists to prevent. Fall back to inferring from the PROVIDER,
        # which aliases cannot disguise.
        family = _family_of_provider(provider)
    return {"model": model, "provider": provider, "family": family}


def _resolve_family(model: str, provider: str) -> str:
    """Model name first, then provider. Returns "unknown" only when neither
    identifies a family — callers must treat that as unproven, never as
    independent."""
    fam = _family_of(model)
    if fam == "unknown":
        fam = _family_of_provider(provider)
    return fam


def _family_of_provider(provider: str) -> str:
    """Infer a model family from the provider ID when the model name is opaque."""
    p = (provider or "").lower()
    for key, pat in (
        ("claude", r"anthropic|claude"),
        ("kimi", r"kimi|moonshot"),
        ("glm", r"zai|zhipu|glm"),
        ("gpt", r"openai|azure"),
        ("qwen", r"qwen|dashscope"),
        ("gemini", r"gemini|google|vertex"),
    ):
        if re.search(pat, p):
            return key
    return "unknown"


def _family_of(model: str) -> str:
    m = (model or "").lower()
    for key, pat in (
        ("glm", r"glm"),
        ("kimi", r"kimi|moonshot"),
        ("claude", r"claude|sonnet|opus|haiku"),
        ("gpt", r"gpt|luna|o[13]"),
        ("qwen", r"qwen"),
        ("gemini", r"gemini"),
    ):
        if re.search(pat, m):
            return key
    return "unknown"


def reviewer_candidates(explicit: str | None, driver_spec: str | None = None,
                        ad_hoc: str | None = None) -> list[dict]:
    """Full ordered candidate list. Used for BOTH the initial pick and retries,
    so a failing first choice always falls through to every other independent
    reviewer, not just the ones named in config order."""
    driver = driver_identity(driver_spec)
    cfg = _load_cfg()
    order = cfg.get("order") or DEFAULT_ORDER

    if ad_hoc and explicit:
        # Two contradictory reviewer choices. Silently honouring one means the
        # user watches a model they did not pick answer their review, so refuse
        # and make them say which they meant.
        sys.exit(
            f"devpair: --with '{ad_hoc}' and --reviewer '{explicit}' both name a "
            "reviewer.\n  Pick one: --with for any PROVIDER/MODEL, --reviewer for a "
            "roster entry."
        )

    if ad_hoc:
        # The user named a model directly: `--with anthropic/claude-opus-5`.
        # No roster entry needed — this is the "use THIS as my pair" path.
        if "/" in ad_hoc:
            provider, model = ad_hoc.split("/", 1)
        else:
            provider, model = "", ad_hoc
        if not model:
            sys.exit("devpair: --with needs a model, e.g. --with anthropic/claude-sonnet-4.6")
        if not provider:
            # Try to find the provider from the roster; a bare model name is
            # ambiguous otherwise and `hermes -z` needs both.
            for r in REVIEWERS.values():
                if r["model"] == model:
                    provider = r["provider"]
                    break
        if not provider:
            sys.exit(
                f"devpair: --with '{ad_hoc}' has no provider and '{model}' is not in "
                "your roster.\n  Use PROVIDER/MODEL, e.g. --with anthropic/claude-sonnet-4.6"
            )
        family = _resolve_family(model, provider)
        cand = {
            "key": "adhoc", "model": model, "provider": provider,
            "family": family, "label": f"{provider}/{model}",
            "same_family_as_driver": family != "unknown" and family == driver["family"],
            # Neither the model nor the provider identifies a family, so this
            # reviewer's independence is UNPROVEN. The user asked for it by
            # name so we proceed, but we must not imply a guarantee.
            "unverifiable": family == "unknown",
        }
        return [cand]

    if explicit:
        if explicit not in REVIEWERS:
            sys.exit(f"devpair: unknown reviewer '{explicit}'. Options: {', '.join(REVIEWERS)}")
        r = dict(REVIEWERS[explicit], key=explicit)
        r["same_family_as_driver"] = (r["family"] != "unknown"
                                      and r["family"] == driver["family"])
        # A forced roster entry gets the same honesty as a forced --with target:
        # an opaque family is UNPROVEN, not independent.
        r["unverifiable"] = r["family"] == "unknown"
        return [r]

    out: list[dict] = []
    skipped: list[str] = []

    if driver["family"] == "unknown":
        # Fail CLOSED. With an unidentifiable driver, every reviewer compares
        # as "different" and the independence guarantee silently evaporates.
        sys.exit(
            "devpair: cannot identify the driver's model family.\n"
            f"  driver resolved to {driver['provider']}/{driver['model']}\n"
            "  Neither the model name nor the provider matched a known family, so a\n"
            "  reviewer cannot be proven independent — and an unprovable guarantee is\n"
            "  worse than none. Pass --driver PROVIDER/MODEL naming the real model\n"
            "  (e.g. --driver anthropic/claude-sonnet-4.6), or force a reviewer with\n"
            "  --reviewer <name> if you accept an unverified review."
        )

    for key in list(order) + [k for k in REVIEWERS if k not in order]:
        r = REVIEWERS.get(key)
        if not r:
            skipped.append(f"{key} (not a known reviewer)")
            continue
        if r["family"] == driver["family"]:
            skipped.append(f"{key} (same family as driver: {r['family']})")
            continue
        cand = dict(r, key=key)
        cand["same_family_as_driver"] = False
        # An opaque roster entry compares as "different family" against every
        # driver, so it would otherwise be auto-selected as PROVEN independent.
        # It is not proven — mark it, and sort it behind anything that is.
        cand["unverifiable"] = r["family"] == "unknown"
        out.append(cand)

    # Stable sort: proven-independent reviewers first, config order preserved
    # within each group. A user whose roster mixes known and opaque models
    # always gets the provable one as first choice, without losing the opaque
    # one as a fallback.
    out.sort(key=lambda c: c["unverifiable"])

    if not out:
        # Every candidate shares the driver's family. Refuse rather than pretend:
        # a model reviewing itself shares its own blind spots, which is the one
        # thing this tool exists to avoid.
        sys.exit(
            "devpair: no independent reviewer available.\n"
            f"  driver is {driver['provider']}/{driver['model']} (family: {driver['family']})\n"
            "  skipped: " + "; ".join(skipped) + "\n"
            "  A model peer-reviewing itself shares its own blind spots, so this is\n"
            "  refused rather than silently downgraded. Either switch the driver model,\n"
            "  or force it anyway with --reviewer <name> if you accept the weaker review."
        )
    return out


def pick_reviewer(explicit: str | None, driver_spec: str | None = None,
                  ad_hoc: str | None = None) -> dict:
    """Choose a reviewer that is NOT the same family as the driver."""
    return reviewer_candidates(explicit, driver_spec, ad_hoc)[0]


# ---------------------------------------------------------------------------
# Session state — this is what makes it a PAIR and not a one-shot reviewer.
# ---------------------------------------------------------------------------
def session_path(name: str | None = None, create: bool = True) -> Path:
    """Resolve the active session file.

    create=False resolves without side effects (for read-only commands like
    `log`), so merely asking where the session is never invents a new one.
    """
    SESSIONS.mkdir(parents=True, exist_ok=True)
    if name:
        return SESSIONS / f"{name}.json"
    if CURRENT.is_file():
        cur = CURRENT.read_text().strip()
        if cur:
            return SESSIONS / f"{cur}.json"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if create:
        CURRENT.write_text(stamp)
    return SESSIONS / f"{stamp}.json"


def load_session(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"created": _now(), "project": os.getcwd(), "turns": []}


def save_session(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)  # atomic on POSIX — a crash never leaves a torn file


def prior_context(sess: dict, limit: int = 4) -> str:
    turns = sess.get("turns", [])[-limit:]
    if not turns:
        return ""
    out = ["", "## WHAT YOU (the pair) ALREADY SAID THIS SESSION", ""]
    out.append(
        "You have reviewed this work before. Do NOT repeat concerns you already "
        "raised unless they were ignored — in that case say so plainly and "
        "escalate. Build on your earlier read; note where the work has moved."
    )
    for i, t in enumerate(turns, 1):
        out.append(f"\n### Earlier turn {i} — mode={t.get('mode')} @ {t.get('at')}")
        if t.get("ask"):
            out.append(f"They asked: {t['ask'][:400]}")
        resp = (t.get("response") or "").strip()
        out.append("Your response was:")
        out.append(resp[:2500] + ("\n[...truncated]" if len(resp) > 2500 else ""))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Context gathering — done HERE, in the harness. The REVIEWER subprocess is
# launched with `-t ""` (no toolset), so it cannot read, write, or execute
# anything: it only ever sees the text we hand it. That read-only guarantee
# covers the reviewer, NOT this gathering step — `--cmd` deliberately runs a
# user-supplied shell command locally, with the user's own privileges.
# ---------------------------------------------------------------------------
def sh(cmd: list[str], cwd: str | None = None, *, want_status: bool = False):
    """Run a command. Returns stdout, or (stdout, note) when want_status.

    `note` is a human-readable failure description (non-zero exit + stderr,
    timeout, or launch failure) so a failing context command is never silently
    reported as 'no output'.
    """
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=45)
        out = (p.stdout or "").strip()
        if not want_status:
            return out
        note = ""
        if p.returncode != 0:
            err = (p.stderr or "").strip()
            note = f"exit {p.returncode}" + (f": {err[:300]}" if err else "")
        return out, note
    except subprocess.TimeoutExpired:
        return ("", "timed out after 45s") if want_status else ""
    except Exception as e:
        return ("", f"{type(e).__name__}: {e}") if want_status else ""


def clip(text: str, limit: int, label: str = "") -> str:
    if len(text) <= limit:
        return text
    head_n, tail_n = int(limit * 0.7), int(limit * 0.25)
    head, tail = text[:head_n], text[-tail_n:]
    omitted = len(text) - head_n - tail_n
    return f"{head}\n\n[... {label} truncated: {omitted} chars omitted ...]\n\n{tail}"


# ---------------------------------------------------------------------------
# Secret redaction. EVERYTHING gathered here is posted to a third-party model
# API, so credentials must never survive the trip. This is defence in depth,
# not a guarantee: it catches the common shapes, and the note tells the user
# something was caught so they can judge whether to send at all.
# ---------------------------------------------------------------------------
# Each entry: (regex, kind, secret_group). secret_group is the capture group
# holding the SECRET itself — 0 means the whole match. Everything outside that
# group is preserved, so the reviewer still sees structure (key names, URL
# hosts, header names) and can reason about the code.
SECRET_PATTERNS: list[tuple[str, str, int]] = [
    # --- high-confidence vendor token shapes (prefix + entropy) --------------
    (r"sk-[A-Za-z0-9_\-]{16,}", "openai-key", 0),
    (r"gh[pousr]_[A-Za-z0-9]{16,}", "github-token", 0),
    (r"github_pat_[A-Za-z0-9_]{20,}", "github-pat", 0),
    (r"xox[abprs]-[A-Za-z0-9\-]{10,}", "slack-token", 0),
    (r"AKIA[0-9A-Z]{16}", "aws-key-id", 0),
    (r"ya29\.[A-Za-z0-9_\-]{20,}", "google-oauth", 0),
    (r"AIza[A-Za-z0-9_\-]{30,}", "google-api-key", 0),
    (r"GOCSPX-[A-Za-z0-9_\-]{10,}", "google-client-secret", 0),
    (r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}", "jwt", 0),
    (r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----",
     "private-key", 0),
    # --- structural: the secret is a middle/last group ----------------------
    # Authorization: Bearer <token>   (must precede the generic assignment rule,
    # or "AUTH...:" would match and redact the scheme word instead of the token)
    (r"(?i)(authorization\s*[:=]\s*(?:bearer|basic|token)\s+)"
     r"((?!\[REDACTED)[A-Za-z0-9._\-+/=]{8,})", "auth-header", 2),
    # scheme://user:secret@host
    (r"([a-zA-Z][a-zA-Z0-9+.\-]*://[^\s:/@]+:)((?!\[REDACTED)[^\s@]{3,})(@)",
     "url-password", 2),
    # KEY=value / "key": "value" / key: value  — where the NAME looks secret.
    (r"(?i)\b([A-Z0-9_]*(?:SECRET|PASSWORD|PASSWD|TOKEN|API[_-]?KEY|ACCESS[_-]?KEY"
     r"|PRIVATE[_-]?KEY|CLIENT[_-]?SECRET|CREDENTIAL)[A-Z0-9_]*)"
     r"([\"']?\s*[:=]\s*[\"']?)"
     r"((?!\[REDACTED)[^\s\"',;]{4,})", "assigned-secret", 3),
]

_PLACEHOLDERISH = re.compile(
    r"(?i)^(x{3,}|\*{3,}|\.{3,}|<[^>]*>|\$\{?[a-z_]+\}?|change[_-]?me|your[_-]?[\w\-]+"
    r"|redacted|placeholder|example|dummy|none|null|true|false|test|localhost)$"
)


def redact_secrets(text: str) -> tuple[str, int]:
    """Strip credential-shaped strings. Returns (clean_text, count_redacted).

    Only the secret itself is replaced, never the surrounding structure, so a
    reviewer can still reason about config shape without reading the values.
    """
    if not text:
        return text, 0
    hits = 0

    def _make_sub(kind: str, group: int):
        def _sub(m: re.Match) -> str:
            nonlocal hits
            secret = m.group(group)
            if not secret or _PLACEHOLDERISH.match(secret):
                return m.group(0)
            hits += 1
            whole, start = m.group(0), m.start()
            # Splice the placeholder into the match, preserving everything else.
            return (whole[: m.start(group) - start]
                    + f"[REDACTED:{kind}]"
                    + whole[m.end(group) - start:])
        return _sub

    out = text
    for pat, kind, group in SECRET_PATTERNS:
        out = re.sub(pat, _make_sub(kind, group), out)
    return out, hits


def gather(args) -> tuple[str, list[str]]:
    parts: list[str] = []
    notes: list[str] = []
    cwd = os.getcwd()

    is_repo = sh(["git", "rev-parse", "--is-inside-work-tree"], cwd) == "true"
    if is_repo:
        branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
        status = sh(["git", "status", "--short"], cwd)
        parts.append(f"## REPO\n{cwd}\nbranch: {branch}\n\nstatus:\n{status or '(clean)'}")

    if args.diff or args.diff_ref:
        ref = args.diff_ref
        if ref:
            # Merge-base semantics: what THIS branch changed, not everything
            # that moved on the ref since. Uncommitted work is not in this
            # diff, so it is appended separately below.
            d, note = sh(["git", "diff", f"{ref}...HEAD"], cwd, want_status=True)
            src = f"git diff {ref}...HEAD"
            if note:
                notes.append(f"`{src}` failed ({note}) — the ref may not exist locally")
        else:
            d, note = sh(["git", "diff", "HEAD"], cwd, want_status=True)
            src = "git diff HEAD (uncommitted)"
            if note:
                notes.append(f"`{src}` failed ({note})")
        untracked = sh(["git", "ls-files", "--others", "--exclude-standard"], cwd)
        if d.strip():
            parts.append(f"## DIFF UNDER REVIEW — {src}\n```diff\n{clip(d, MAX_DIFF_CHARS, 'diff')}\n```")
        elif not note and not untracked.strip():
            notes.append(f"no diff found for '{src}'")
        if ref:
            u, unote = sh(["git", "diff", "HEAD"], cwd, want_status=True)
            if u.strip():
                parts.append(
                    "## UNCOMMITTED CHANGES (not in the branch diff above)\n"
                    f"```diff\n{clip(u, MAX_DIFF_CHARS // 2, 'uncommitted diff')}\n```"
                )
            elif unote:
                notes.append(f"`git diff HEAD` failed ({unote})")
        if untracked.strip():
            files = [f for f in untracked.splitlines() if f.strip()]
            parts.append(
                "## UNTRACKED FILES (git diff does NOT show these — new code hides here)\n"
                + "\n".join(files)
            )
            # Naming them is not enough: brand-new code is invisible to
            # `git diff`, so a review of a new-file-only change would see
            # nothing but a filename. Read a bounded number of them.
            shown = 0
            for f in files:
                if shown >= MAX_UNTRACKED_FILES:
                    parts.append(
                        f"## NOTE\n{len(files) - shown} further untracked file(s) not shown "
                        f"(limit {MAX_UNTRACKED_FILES}). Use --files to include specific ones."
                    )
                    break
                p = Path(cwd) / f
                try:
                    if not p.is_file() or p.stat().st_size > MAX_UNTRACKED_BYTES:
                        continue
                    body = p.read_text(errors="replace")
                except Exception:
                    continue
                if not body.strip() or "\x00" in body[:1024]:
                    continue
                numbered = "\n".join(
                    f"{i:>5}| {ln}" for i, ln in enumerate(body.splitlines(), 1)
                )
                parts.append(
                    f"## NEW FILE (untracked): {f}\n```\n"
                    f"{clip(numbered, MAX_UNTRACKED_CHARS, f)}\n```"
                )
                shown += 1

    for f in args.files or []:
        p = Path(f).expanduser()
        if not p.is_file():
            notes.append(f"file not found: {f}")
            continue
        try:
            body = p.read_text(errors="replace")
        except Exception as e:
            notes.append(f"unreadable {f}: {e}")
            continue
        numbered = "\n".join(f"{i:>5}| {ln}" for i, ln in enumerate(body.splitlines(), 1))
        parts.append(
            f"## FILE: {p}\n```\n{clip(numbered, MAX_FILE_CHARS, p.name)}\n```"
        )

    if args.plan:
        p = Path(args.plan).expanduser()
        if p.is_file():
            parts.append(f"## THE PROPOSED PLAN / DIRECTION ({p})\n{clip(p.read_text(errors='replace'), 30000, 'plan')}")
        else:
            parts.append(f"## THE PROPOSED PLAN / DIRECTION\n{args.plan}")

    if args.error:
        p = Path(args.error).expanduser()
        body = p.read_text(errors="replace") if p.is_file() else args.error
        parts.append(f"## THE FAILURE / ERROR OUTPUT\n```\n{clip(body, 20000, 'error')}\n```")

    if args.cmd:
        # No bash on a stock Windows box; use the native shell there.
        shell_cmd = (["cmd", "/c", args.cmd] if os.name == "nt"
                     else ["bash", "-lc", args.cmd])
        out, note = sh(shell_cmd, cwd, want_status=True)
        body = out or "(no stdout)"
        if note:
            body += f"\n\n[command FAILED — {note}]"
            notes.append(f"`{args.cmd}` failed: {note}")
        parts.append(f"## OUTPUT OF `{args.cmd}`\n```\n{clip(body, 15000, 'cmd output')}\n```")

    if not sys.stdin.isatty():
        # Only drain stdin when data is actually waiting; an inherited-but-idle
        # pipe would otherwise block forever with no timeout.
        try:
            import select

            ready = select.select([sys.stdin], [], [], 0.4)[0]
        except Exception:
            ready = []
        if ready:
            piped = sys.stdin.read()
            if piped.strip():
                parts.append(f"## PIPED CONTEXT\n```\n{clip(piped, 30000, 'stdin')}\n```")

    blob = "\n\n".join(parts)
    # Single chokepoint: everything leaving this function is bound for a
    # third-party API, so redaction happens HERE and cannot be bypassed by a
    # future context source that forgets to call it.
    blob, redacted = redact_secrets(blob)
    if redacted:
        notes.append(
            f"redacted {redacted} credential-shaped value(s) before sending — "
            "review the evidence yourself if the code under review handles secrets"
        )
    return clip(blob, MAX_CONTEXT_CHARS, "total context"), notes


# ---------------------------------------------------------------------------
# The supervisory contract. This is the whole product.
# ---------------------------------------------------------------------------
ROLE = """You are the DEV PAIR — the second pair of eyes on a piece of software work.

You are a senior engineer sitting beside a competent colleague who is doing the
actual building. Your value is that you are NOT them, you did not fall in love
with their approach, and you are running on a different model with different
blind spots. You catch what they cannot see precisely because they wrote it.

WHAT YOU DO
  - Pressure-test the direction before effort is sunk into it.
  - Name specific, concrete risks — with file:line or exact function names.
  - Offer a genuinely better alternative WHEN one exists, with its trade-off stated.
  - Ask the questions whose answers would change the design.
  - Help find bugs by reasoning about the evidence, not by guessing.

WHAT YOU NEVER DO
  - You never rewrite the implementation. No full files, no "here's my version".
  - You do not redo their work in parallel. This is supervision, not duplication.
  - You do not restate their plan back to them as if it were analysis.
  - You do not pad. No preamble, no "great question", no summary of what you just said.
  - You do not invent problems to look useful. "This is sound" is a valid, valuable
    answer and you should give it when it is true — then shut up.
  - You do not soften a real blocker to be agreeable. Being liked is not the job.

CODE SNIPPETS: allowed only as a ≤5 line illustration of a specific fix direction,
and only when prose cannot convey it. Never a full function, never a full file.

CALIBRATION: distinguish what you KNOW from the evidence given, from what you
SUSPECT, from what you cannot see. If context is missing that would change your
verdict, say exactly what you'd need. Never bluff certainty you don't have.
Ground every concern in the evidence actually shown to you — if you are reasoning
from a general pattern rather than from their code, label it as such.
"""

SHAPES = {
    "critique": """Respond in EXACTLY this shape:

## VERDICT
One of: PROCEED / PROCEED WITH CHANGES / RECONSIDER / STOP
Then one sentence — the real reason.

## CONCERNS
Ranked, worst first. Each: `[BLOCKER|MAJOR|MINOR] area or file:line` then at most
three lines — what breaks, when it bites, the smallest correct fix direction.
If there are no real concerns, write "None material." and do not manufacture any.

## ALTERNATIVE WORTH CONSIDERING
Only if genuinely better. State what it buys and what it costs.
If their approach is right, write "None — the chosen approach is sound" and stop.

## QUESTIONS THAT EXPOSE GAPS
2-4 questions whose answers would actually change the design. Not comprehension
questions — questions that probe the load-bearing assumptions.

## WHAT I'D TEST FIRST
The single cheapest check that would falsify the riskiest assumption.""",
    "review": """Respond in EXACTLY this shape:

## VERDICT
One of: SHIP / SHIP AFTER FIXES / NEEDS WORK / DO NOT SHIP
Then one sentence — the real reason.

## DEFECTS
Ranked, worst first. Each: `[BLOCKER|MAJOR|MINOR] file:line` then at most three
lines — the defect, the condition that triggers it, the fix direction.
Look hard at: error paths, the unhappy case, concurrency, resource cleanup,
partial failure, silent fallbacks, off-by-one, and anything the tests do not touch.
If a change is correct but the surrounding code makes it wrong, say so.

## WHAT THE TESTS DO NOT PROVE
Name the behaviour a reader would ASSUME is covered but is not. A green suite is
evidence, not a verdict.

## ALTERNATIVE WORTH CONSIDERING
Only if a materially simpler or safer shape exists. Otherwise "None."

## WHAT I'D TEST FIRST
The single cheapest check most likely to expose a real problem.""",
    "debug": """Respond in EXACTLY this shape:

## MOST LIKELY CAUSE
One paragraph. Commit to a position — name the mechanism, not a category.

## RANKED HYPOTHESES
Worst-first by probability × cost-if-true. Each: the hypothesis, the specific
evidence FOR it, and the specific evidence that would kill it.

## CHEAPEST DISCRIMINATING TEST
The one command, print, or probe that splits the hypothesis space fastest.
Say what each possible outcome would prove. This is the most important section.

## WHAT THE EVIDENCE ALREADY RULES OUT
Be explicit — this is where a stuck colleague reclaims the most time.

## WHAT I CANNOT SEE
The context that would let you answer properly, if any.""",
    "alt": """Respond in EXACTLY this shape:

## THE HONEST READ
Is the current direction actually a problem, or does it just feel wrong?
Say which. Do not invent a problem to justify the question.

## ALTERNATIVES
Two or three at most. For each: the shape in 2-3 lines, what it buys,
what it costs, and the condition under which it becomes the right call.

## WHAT I'D DO
Commit to one recommendation and defend it in a sentence. No fence-sitting.

## THE ASSUMPTION TO CHECK FIRST
The one belief that, if wrong, flips the recommendation.""",
    "followup": """They have responded to your earlier review. Respond in EXACTLY this shape:

## RESOLVED
Concerns you now consider genuinely closed, and why the response satisfies you.

## NOT RESOLVED
Concerns their response did not actually address, or addressed in a way that
moves the problem rather than fixing it. Be specific and do not let it slide.

## WHERE THEY ARE RIGHT AND I WAS WRONG
Concede properly and explicitly where their reasoning beat yours. Being right
matters more than looking right.

## REMAINING VERDICT
One of: PROCEED / PROCEED WITH CHANGES / RECONSIDER / STOP, plus one sentence.""",
}

ASK_HINT = {
    "critique": "Critique this direction before effort is sunk into it.",
    "review": "Review this work.",
    "debug": "Help me find this bug.",
    "alt": "Challenge this approach and give me the alternatives.",
    "followup": "Here is how I responded to your review.",
}


def build_prompt(mode: str, ask: str, context: str, sess: dict, focus: str | None) -> str:
    blocks = [ROLE]
    if focus:
        blocks.append(f"\n## FOCUS DIRECTIVE\nThe colleague specifically wants your attention on: {focus}\nStill report anything critical you find outside that focus.")
    blocks.append(prior_context(sess))
    blocks.append(f"\n## WHAT THEY ARE ASKING\n{ask or ASK_HINT.get(mode, '')}")
    if context.strip():
        blocks.append(f"\n## CONTEXT / EVIDENCE\n{context}")
    else:
        blocks.append(
            "\n## CONTEXT / EVIDENCE\n(none supplied — if you cannot review responsibly "
            "without seeing code, say exactly what you need and stop.)"
        )
    blocks.append("\n## REQUIRED OUTPUT SHAPE\n" + SHAPES[mode])
    blocks.append(
        "\nBe dense. Every line must earn its place. A short sharp review beats a "
        "long thorough-looking one. Do not restate the context back to them."
    )
    return "\n".join(b for b in blocks if b)


# ---------------------------------------------------------------------------
# Verdict parsing, gating, and claim verification. The reviewer's output is
# prose, but two things in it are machine-actionable: the verdict line, and any
# file:line it cites. Both are extracted here so a caller can gate on the first
# and distrust the second.
# ---------------------------------------------------------------------------
BAD_VERDICTS = {"DO NOT SHIP", "STOP", "NEEDS WORK", "RECONSIDER"}
_VERDICT_RE = re.compile(
    r"^#+\s*(?:REMAINING\s+)?VERDICT\s*$\s*(.+?)$", re.M | re.I
)


def parse_verdict(response: str) -> str | None:
    """Extract the verdict token from a review. None if absent/unparseable."""
    m = _VERDICT_RE.search(response or "")
    if not m:
        return None
    line = m.group(1).strip().strip("*_` ").upper()
    # Longest-first so "DO NOT SHIP" wins over "SHIP", and
    # "PROCEED WITH CHANGES" over "PROCEED".
    known = ["DO NOT SHIP", "SHIP AFTER FIXES", "PROCEED WITH CHANGES",
             "NEEDS WORK", "RECONSIDER", "PROCEED", "SHIP", "STOP"]
    for tok in sorted(known, key=len, reverse=True):
        if line.startswith(tok):
            return tok
    return None


def count_blockers(response: str) -> int:
    return len(re.findall(r"\[BLOCKER\]", response or "", re.I))


def gate_failed(response: str) -> tuple[bool, str]:
    """Should a --gate run exit non-zero? Returns (failed, reason).

    Fails closed on an unparseable verdict: a gate that cannot read the answer
    must not report success.
    """
    verdict = parse_verdict(response)
    blockers = count_blockers(response)
    if verdict is None:
        return True, "no parseable VERDICT line in the review"
    if verdict in BAD_VERDICTS:
        return True, f"verdict: {verdict}"
    if blockers:
        return True, f"verdict {verdict} but {blockers} [BLOCKER] finding(s) present"
    return False, f"verdict: {verdict}"


def verify_claims(response: str, cwd: str | None = None) -> list[str]:
    """Check every `path:line` the reviewer cited.

    It reasons from pasted text and cannot open files, so its anchors are
    claims, not facts. Returns human-readable problems (missing file, line past
    EOF). Files outside the working tree are ignored rather than guessed at.
    """
    root = Path(cwd or os.getcwd())
    problems: list[str] = []
    seen: set[tuple[str, int]] = set()
    for raw, lineno in re.findall(r"\b([\w./\-]+\.[A-Za-z]\w{0,9}):(\d+)\b", response or ""):
        try:
            n = int(lineno)
        except ValueError:
            continue
        if (raw, n) in seen:
            continue
        seen.add((raw, n))
        cand = (root / raw) if not os.path.isabs(raw) else Path(raw)
        if not cand.exists():
            # Try a basename match anywhere shallow in the tree before crying wolf.
            matches = list(root.glob(f"**/{Path(raw).name}"))
            if not matches:
                problems.append(f"{raw}:{n} — no such file in this tree")
                continue
            cand = matches[0]
        try:
            total = len(cand.read_text(errors="replace").splitlines())
        except Exception:
            continue
        if n > total:
            problems.append(f"{raw}:{n} — file has only {total} lines")
    return problems


def estimate_tokens(text: str) -> int:
    """Rough token count (~4 chars/token). Good enough to spot a runaway prompt."""
    return max(1, len(text or "") // 4)


def run_reviewer(reviewer: dict, prompt: str, timeout: int, verbose: bool) -> tuple[bool, str]:
    cmd = [
        "hermes", "-z", prompt,
        "-m", reviewer["model"],
        "--provider", reviewer["provider"],
        "-t", "",
    ]
    env = dict(os.environ)
    env["HERMES_NONINTERACTIVE"] = "1"
    if verbose:
        print(f"[devpair] invoking {reviewer['label']} ({reviewer['provider']}/{reviewer['model']}) "
              f"with {len(prompt):,} chars", file=sys.stderr)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return False, f"reviewer timed out after {timeout}s"
    except FileNotFoundError:
        # `hermes` not on PATH. Must be a soft failure: the retry loop should
        # move on (and doctor should report it) rather than dying on a traceback.
        return False, "the `hermes` CLI was not found on PATH — is Hermes installed?"
    except OSError as e:
        return False, f"could not launch reviewer: {type(e).__name__}: {e}"
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode != 0:
        detail = err or out or f"exit {p.returncode} with no output"
        return False, f"exit {p.returncode}: {detail[:400]}"
    if not out or "agent failed" in out.lower()[:200]:
        return False, out or err or "no output from reviewer"
    return True, out


# ---------------------------------------------------------------------------
def cmd_pair(args) -> int:
    mode = args.mode
    # Resolve the session WITHOUT creating one — a --dry-run (or an early exit)
    # must not leave a stale CURRENT pointer behind.
    spath = session_path(args.session, create=False)
    sess = load_session(spath)

    context, notes = gather(args)
    for n in notes:
        print(f"[devpair] note: {n}", file=sys.stderr)

    order = reviewer_candidates(args.reviewer, args.driver, getattr(args, 'with_model', None))
    reviewer = order[0]
    driver = driver_identity(args.driver)

    if mode == "followup" and not sess.get("turns"):
        print(
            f"[devpair] WARNING: session '{spath.stem}' has no earlier turns — the "
            f"reviewer has no prior review to audit, so this followup will read as a "
            f"fresh critique. Check you're in the right session (devpair log).",
            file=sys.stderr,
        )

    if args.dry_run:
        print(f"driver   : {driver['provider']}/{driver['model']}  (family: {driver['family']})")
        print(f"reviewer : {reviewer['label']}  {reviewer['provider']}/{reviewer['model']}")
        if reviewer.get("same_family_as_driver"):
            print("  WARNING: forced same-family review — not independent.")
        elif reviewer.get("unverifiable"):
            print("  WARNING: independence UNVERIFIED — neither the model name nor "
                  "the provider identifies a family.")
        if len(order) > 1:
            print("fallbacks: " + ", ".join(c["label"] for c in order[1:]))
        print(f"mode     : {mode}")
        print(f"context  : {len(context):,} chars")
        print(f"session  : {spath.stem} (turn {len(sess.get('turns', [])) + 1})")
        cap = daily_cap()
        if cap:
            used = runs_today()
            state = "AT CAP — a real run would be refused" if used >= cap else "ok"
            print(f"cap      : {used}/{cap} paid runs today ({state})")
        return 0

    if reviewer.get("unverifiable"):
        print(
            f"[devpair] WARNING: cannot verify that {reviewer['label']} is independent of "
            f"the driver ({driver['model']}) — neither its model name nor its provider "
            f"maps to a known family. Proceeding because you named it explicitly, but "
            f"this review carries no independence guarantee.",
            file=sys.stderr,
        )

    if reviewer.get("same_family_as_driver"):
        print(
            f"[devpair] WARNING: reviewer ({reviewer['label']}) is the same model family "
            f"as the driver ({driver['model']}). A model peer-reviewing itself shares its "
            f"blind spots — the critique is worth much less. Use --reviewer to pick another.",
            file=sys.stderr,
        )

    prompt = build_prompt(mode, args.ask or "", context, sess, args.focus)

    # Gate + record the paid run. Placed AFTER --dry-run (which is free and must
    # stay free) and BEFORE the first backend call, so nothing is spent without
    # a ledger entry and nothing exceeds the cap.
    authorize(args, reviewer, driver, len(context))

    t0 = time.time()
    ok, response, used = False, "", reviewer
    budget = args.budget if args.budget and args.budget > 0 else None
    for i, cand in enumerate(order):
        remaining = None
        if budget is not None:
            remaining = budget - (time.time() - t0)
            if remaining <= 5:
                print(f"[devpair] wall-clock budget ({budget}s) exhausted — "
                      f"{len(order) - i} backend(s) not tried", file=sys.stderr)
                break
        this_timeout = int(min(args.timeout, remaining)) if remaining else args.timeout
        ok, response = run_reviewer(cand, prompt, this_timeout, args.verbose)
        used = cand
        if ok:
            break
        print(f"[devpair] {cand['label']} unavailable: {response[:160]}", file=sys.stderr)

    if not ok:
        print("\n[devpair] FAILED — no reviewer backend answered.", file=sys.stderr)
        print(f"[devpair] last error: {response[:600]}", file=sys.stderr)
        print("[devpair] run `devpair doctor` to check backends.", file=sys.stderr)
        return 1

    elapsed = time.time() - t0
    tokens_in = estimate_tokens(prompt)
    tokens_out = estimate_tokens(response)

    # The reviewer cites file:line from pasted text it cannot open — verify.
    claim_problems = verify_claims(response, os.getcwd())

    gate_fail, gate_reason = gate_failed(response)

    # A real review happened — now it is correct to pin the session pointer.
    if not args.session:
        if not CURRENT.is_file():
            CURRENT.parent.mkdir(parents=True, exist_ok=True)
            CURRENT.write_text(spath.stem)
        elif CURRENT.read_text().strip() != spath.stem and not spath.is_file():
            # Another concurrent run pinned a different session while we were
            # reviewing. Merge our turn into THAT session rather than orphaning
            # a same-timestamp file nobody points at.
            spath = session_path(create=False)
            sess = load_session(spath)

    sess.setdefault("turns", []).append({
        "at": _now(),
        "mode": mode,
        "ask": args.ask or "",
        "focus": args.focus or "",
        "reviewer": f"{used['provider']}/{used['model']}",
        "driver": f"{driver['provider']}/{driver['model']}",
        "context_chars": len(context),
        "elapsed_s": round(elapsed, 1),
        "tokens_in_est": tokens_in,
        "tokens_out_est": tokens_out,
        "verdict": parse_verdict(response),
        "blockers": count_blockers(response),
        "unverified_claims": claim_problems,
        "independence": ("same-family" if used.get("same_family_as_driver")
                         else "unverified" if used.get("unverifiable")
                         else "verified"),
        "response": response,
    })
    sess["project"] = os.getcwd()
    save_session(spath, sess)

    if args.json:
        print(json.dumps({
            "mode": mode,
            "reviewer": f"{used['provider']}/{used['model']}",
            "reviewer_label": used["label"],
            "driver": f"{driver['provider']}/{driver['model']}",
            "session": spath.stem,
            "turn": len(sess["turns"]),
            "elapsed_s": round(elapsed, 1),
            "tokens_in_est": tokens_in,
            "tokens_out_est": tokens_out,
            "verdict": parse_verdict(response),
            "blockers": count_blockers(response),
            "unverified_claims": claim_problems,
            "independence": ("same-family" if used.get("same_family_as_driver")
                             else "unverified" if used.get("unverifiable")
                             else "verified"),
            "gate_failed": gate_fail,
            "gate_reason": gate_reason,
            "response": response,
        }, indent=2))
    else:
        bar = "─" * 66
        print(f"\n{bar}")
        print(f"  DEV PAIR · {mode.upper()} · reviewed by {used['label']}")
        print(f"  driver: {driver['model']}   session: {spath.stem} (turn {len(sess['turns'])})   {elapsed:.0f}s")
        print(f"  ~{tokens_in:,} tokens in / ~{tokens_out:,} out")
        print(bar + "\n")
        print(response)
        print(f"\n{bar}")
        if used.get("same_family_as_driver"):
            print(f"  NOT INDEPENDENT — {used['label']} shares the driver's model family.")
        elif used.get("unverifiable"):
            print(f"  INDEPENDENCE UNVERIFIED — {used['label']} maps to no known model")
            print("  family, so it cannot be proven different from the driver.")
        if claim_problems:
            print("  UNVERIFIED CLAIMS — the reviewer cited anchors that do not check out:")
            for c in claim_problems[:8]:
                print(f"    · {c}")
            print("  Treat those findings with extra scepticism.")
            print(bar)
        print(f"  reply with: devpair followup --ask \"...\"")
        print(bar)

    if args.gate and gate_fail:
        print(f"\n[devpair] GATE FAILED — {gate_reason}", file=sys.stderr)
        return 2
    return 0


def cmd_log(args) -> int:
    spath = session_path(args.session, create=False)
    if not spath.is_file():
        print("devpair: no session yet.")
        return 0
    sess = load_session(spath)
    print(f"Session {spath.stem} · {sess.get('project','?')} · {len(sess.get('turns',[]))} turns")
    for i, t in enumerate(sess.get("turns", []), 1):
        print(f"\n{'='*66}\n[{i}] {t['mode'].upper()} · {t['reviewer']} · {t['at']}")
        if t.get("ask"):
            print(f"asked: {t['ask'][:200]}")
        print(f"{'-'*66}")
        print(t.get("response", "")[: (None if args.full else 1200)])
    return 0


def cmd_reset(args) -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    CURRENT.parent.mkdir(parents=True, exist_ok=True)
    CURRENT.write_text(stamp)
    print(f"devpair: new pairing session {stamp}")
    return 0


def cmd_doctor(args) -> int:
    driver = driver_identity(getattr(args, "driver", None))
    print(f"driver (being supervised): {driver['provider']}/{driver['model']}  family={driver['family']}")
    if driver["family"] == "unknown":
        print("  WARNING: driver family unidentified — independence cannot be proven.")
        print("  Pass --driver PROVIDER/MODEL for an accurate same-family column.")
    print(f"state: {BASE}\n")
    print(f"{'reviewer':<10} {'provider/model':<34} {'family':<8} status")
    print("-" * 78)
    rc = 0
    any_ok = False

    def _probe(item):
        key, r = item
        # Small local reasoning models emit a long trace even for a trivial
        # probe (~2min), so they get a longer leash than hosted backends.
        probe_timeout = 300 if r["provider"].startswith("lmstudio") else 90
        ok, out = run_reviewer(r, "Reply with exactly: OK", probe_timeout, False)
        return key, r, ok, out

    # Probed in parallel: serially this is 4 x up-to-300s of dead waiting.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=max(1, len(REVIEWERS))) as pool:
        results = list(pool.map(_probe, list(REVIEWERS.items())))

    for key, r, ok, out in results:
        same = " (SAME FAMILY AS DRIVER — not independent)" if r["family"] == driver["family"] else ""
        status = "OK" if ok and "OK" in out.upper()[:40] else f"FAIL: {out[:60]}"
        if ok:
            any_ok = True
        print(f"{key:<10} {r['provider']+'/'+r['model']:<34} {r['family']:<8} {status}{same}")
    if not any_ok:
        print("\nNo reviewer backend is reachable — devpair cannot run.")
        rc = 1
    return rc


def cmd_audit(args) -> int:
    """Who has been spending your tokens, and did anyone claim you asked?

    This is the accountability half of the manual-invocation policy: the skill
    tells an agent not to self-initiate, and this shows whether it obeyed.
    """
    recs = read_ledger(days=args.days)
    if not recs:
        where = "no runs recorded" if LEDGER.is_file() else f"no ledger yet at {LEDGER}"
        print(f"devpair: {where}"
              + (f" in the last {args.days}d." if args.days else "."))
        return 0

    if args.json:
        print(json.dumps({"days": args.days, "count": len(recs),
                          "runs_today": runs_today(), "daily_cap": daily_cap(),
                          "runs": recs}, indent=2))
        return 0

    print(f"{'when':<22} {'mode':<9} {'requested by':<14} {'reviewer':<30} ctx")
    print("─" * 88)
    for r in recs:
        print(f"{r.get('at','?')[:19]:<22} {r.get('mode','?'):<9} "
              f"{r.get('requested_by','?')[:13]:<14} {r.get('reviewer','?')[:29]:<30} "
              f"{r.get('context_chars',0):,}")

    unattributed = [r for r in recs if r.get("requested_by") in ("", "unattributed", None)]
    cap = daily_cap()
    print("─" * 88)
    print(f"{len(recs)} run(s)"
          + (f" in the last {args.days}d" if args.days else "")
          + f"; {runs_today()} today"
          + (f" of a {cap}/day cap" if cap else " (no daily cap set)"))
    if unattributed:
        print(f"\n  {len(unattributed)} run(s) named nobody as the requester.")
        print("  Unattributed runs are the ones to check — the skill forbids an")
        print("  agent from self-initiating, and this is where that would show.")
    return 0


def cmd_prune(args) -> int:
    """Housekeeping: sessions accumulate forever otherwise."""
    if not SESSIONS.is_dir():
        print("devpair: no sessions to prune.")
        return 0
    cutoff = time.time() - (args.days * 86400)
    current = CURRENT.read_text().strip() if CURRENT.is_file() else ""
    files = sorted(SESSIONS.glob("*.json"), key=lambda p: p.stat().st_mtime)
    doomed = [p for p in files if p.stat().st_mtime < cutoff and p.stem != current]
    if not doomed:
        print(f"devpair: nothing older than {args.days}d "
              f"({len(files)} session(s) kept).")
        return 0
    for p in doomed:
        if args.dry_run:
            print(f"would delete {p.stem}")
        else:
            p.unlink()
            print(f"deleted {p.stem}")
    verb = "would free" if args.dry_run else "freed"
    print(f"devpair: {verb} {len(doomed)} session(s); "
          f"{len(files) - len(doomed)} kept (active session never pruned).")
    return 0


def main() -> int:
    # Apply this machine's roster BEFORE argparse reads REVIEWERS for --reviewer
    # choices, or a locally-declared reviewer would be rejected as unknown.
    _load_roster()
    ap = argparse.ArgumentParser(
        prog="devpair",
        description="The second pair of eyes — supervisory review on a different LLM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            modes:
              critique   pressure-test a direction BEFORE effort is sunk into it
              review     review work already done (diff, files)
              debug      help find a bug you're stuck on
              alt        challenge the approach, get real alternatives
              followup   respond to the pair's earlier review

            examples:
              devpair critique --plan PLAN.md
              devpair review --diff
              devpair review --diff-ref main --focus "error paths and cleanup"
              devpair debug --error /tmp/fail.log --files src/router.py
              devpair alt --ask "cron job or long-running daemon for this watcher?"
              devpair followup --ask "Fixed 1 and 3. Disagree with 2 because ..."
              devpair log ; devpair reset ; devpair doctor
        """),
    )
    sub = ap.add_subparsers(dest="subcmd", required=True)

    for mode in ("critique", "review", "debug", "alt", "followup"):
        p = sub.add_parser(mode, help=ASK_HINT[mode])
        # NOTE: the subparser dest must NOT be "cmd" — it would collide with
        # the --cmd/-c shell-command option below, and set_defaults(cmd=...)
        # would leave args.cmd == "pair" whenever -c is absent, making every
        # run execute a phantom `bash -lc pair` context command.
        p.set_defaults(mode=mode, func=cmd_pair)
        p.add_argument("--ask", "-a", help="what you want their eyes on, in your words")
        p.add_argument("--focus", "-F", help="direct their attention (e.g. 'concurrency', 'auth boundary')")
        p.add_argument("--diff", action="store_true", help="include uncommitted git diff + untracked files")
        p.add_argument("--diff-ref", metavar="REF", help="diff against a ref instead (e.g. main)")
        p.add_argument("--files", "-f", nargs="+", help="files to put in front of them")
        p.add_argument("--plan", "-p", help="plan file path, or inline text")
        p.add_argument("--error", "-e", help="error/failure log path, or inline text")
        p.add_argument("--cmd", "-c", help="run this shell command and include its output")
        p.add_argument("--reviewer", "-r", choices=list(REVIEWERS), help="force a reviewer from your roster")
        p.add_argument("--with", dest="with_model", metavar="PROVIDER/MODEL",
                       help="use THIS model as the pair, roster or not "
                            "(e.g. --with anthropic/claude-opus-5). Same-family "
                            "is warned about, not blocked — it is your call.")
        p.add_argument("--driver", metavar="[PROVIDER/]MODEL",
                       help="the model ACTUALLY doing the work (default: config.yaml model.default — "
                            "pass the live session model or the same-family guard protects the wrong model)")
        p.add_argument("--requested-by", dest="requested_by", metavar="WHO",
                       help="who asked for this review (e.g. 'user'). Recorded in "
                            "the invocation ledger; agents must NOT fill this in "
                            "unless the user actually asked. Env: DEVPAIR_REQUESTED_BY")
        p.add_argument("--session", "-s", help="named pairing session")
        p.add_argument("--timeout", type=int, default=420, help="per-backend seconds (default 420)")
        p.add_argument("--budget", type=int, default=0,
                       help="total wall-clock seconds across ALL backend attempts "
                            "(default 0 = unlimited; use for CI so a dead chain "
                            "cannot burn timeout x candidates)")
        p.add_argument("--gate", action="store_true",
                       help="exit 2 if the verdict is DO NOT SHIP/NEEDS WORK/STOP/RECONSIDER, "
                            "if any [BLOCKER] is found, or if the verdict cannot be parsed "
                            "(fails closed). Default: advisory, always exit 0.")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        p.add_argument("--dry-run", action="store_true", help="show who would review and why, without calling them")
        p.add_argument("--verbose", "-v", action="store_true")

    pl = sub.add_parser("log", help="what the pair has said this session")
    pl.set_defaults(func=cmd_log)
    pl.add_argument("--session", "-s")
    pl.add_argument("--full", action="store_true")

    pr = sub.add_parser("reset", help="start a fresh pairing session")
    pr.set_defaults(func=cmd_reset)

    pd = sub.add_parser("doctor", help="check reviewer backends")
    pd.set_defaults(func=cmd_doctor)
    pd.add_argument("--driver", metavar="[PROVIDER/]MODEL",
                    help="the live session model, for an accurate same-family column")

    pa = sub.add_parser("audit", help="who ran the pair, when, and who asked")
    pa.set_defaults(func=cmd_audit)
    pa.add_argument("--days", type=int, default=7,
                    help="look back N days (default 7; 0 = all history)")
    pa.add_argument("--json", action="store_true", help="machine-readable output")

    pp = sub.add_parser("prune", help="delete old pairing sessions")
    pp.set_defaults(func=cmd_prune)
    pp.add_argument("--days", type=int, default=30,
                    help="delete sessions older than N days (default 30)")
    pp.add_argument("--dry-run", action="store_true", help="show what would go, delete nothing")

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
