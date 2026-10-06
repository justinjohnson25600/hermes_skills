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
import errno
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
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


class LockTimeout(RuntimeError):
    """A lock that exists could not be acquired before the deadline."""


LOCK_DEADLINE_S = 30
_LOCK_BUSY_ERRNOS = {getattr(errno, n) for n in ("EAGAIN", "EWOULDBLOCK", "EACCES", "EDEADLK", "EDEADLOCK")
                     if hasattr(errno, n)}


class _file_lock:
    """Exclusive lock on a side-car lock file.

    Without it the cap is only advisory: two processes both read `used < cap`,
    both append, and both call a backend — a `daily_cap: 1` machine spends
    twice. Uses a separate lock file so the lock survives ledger truncation.
    The same primitive serialises session read-modify-write.

    Degrades honestly: if no locking primitive exists on this platform, the
    caller is told the cap is advisory rather than being given a false promise.
    """

    def __init__(self, lockpath: str | None = None) -> None:
        self.lockpath = lockpath
        self.fh = None
        self.locked = False

    def __enter__(self):
        lockpath = self.lockpath or (str(LEDGER) + ".lock")
        try:
            Path(lockpath).parent.mkdir(parents=True, exist_ok=True)
            self.fh = open(lockpath, "a+")
        except OSError:
            return self
        # Both platforms poll a NON-blocking lock against an explicit deadline.
        # Windows LK_LOCK retries once per second, gives up after 10 tries and
        # used to fall through UNLOCKED; POSIX LOCK_EX blocks forever behind a
        # suspended holder. A lock that exists but cannot be acquired in time
        # raises LockTimeout — proceeding unlocked would silently reintroduce
        # the very race the lock exists to prevent.
        deadline = time.time() + LOCK_DEADLINE_S
        try:
            import fcntl  # POSIX
            acquire = lambda: fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # noqa: E731
        except ImportError:
            try:
                import msvcrt  # Windows

                def acquire():
                    self.fh.seek(0)
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            except ImportError:
                return self  # no primitive at all: caller sees locked=False
        while True:
            try:
                acquire()
                self.locked = True
                return self
            except OSError as e:
                if e.errno not in _LOCK_BUSY_ERRNOS:
                    return self  # locking unsupported here (e.g. ENOLCK): caller sees locked=False
                if time.time() > deadline:
                    try:
                        self.fh.close()
                    except OSError:
                        pass
                    self.fh = None
                    raise LockTimeout(f"{lockpath} is held by another devpair process "
                                      f"(waited {LOCK_DEADLINE_S}s)")
                time.sleep(0.05)

    def __exit__(self, *exc):
        if self.fh:
            try:
                if self.locked:
                    try:
                        import fcntl
                        fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
                    except ImportError:
                        import msvcrt
                        self.fh.seek(0)
                        msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            try:
                self.fh.close()
            except OSError:
                pass
        return False


class _ledger_lock(_file_lock):
    """The ledger's count-and-append lock (kept as its own name: tests and
    callers substitute it to simulate a filesystem without locking)."""

    def __init__(self) -> None:
        super().__init__(None)


def _scan_ledger(days: int = 0) -> tuple[list[dict], int, bool]:
    """Parse the ledger, returning (records, corrupt_line_count, readable).

    Three distinct outcomes, because enforcement must tell them apart:
      - no ledger yet        -> ([], 0, True)   genuinely zero runs
      - readable with junk   -> (recs, n, True) count is an UNDERCOUNT
      - unreadable           -> ([], 0, False)  count is UNKNOWN, not zero

    Collapsing the third into the first is a fail-open: a write-only or
    permission-damaged ledger would report zero usage and reopen a spent cap.
    """
    if not LEDGER.is_file():
        return [], 0, True
    cutoff = time.time() - days * 86400 if days else 0
    out: list[dict] = []
    corrupt = 0
    try:
        raw = LEDGER.read_text(errors="replace")
    except OSError:
        return [], 0, False
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            corrupt += 1
            continue
        if not isinstance(rec, dict):
            corrupt += 1
            continue
        if cutoff and rec.get("epoch", 0) < cutoff:
            continue
        out.append(rec)
    return out, corrupt, True


def read_ledger(days: int = 0) -> list[dict]:
    """Lenient view for `devpair audit` — a corrupt line must not hide the rest
    of the history from the human trying to read it."""
    return _scan_ledger(days)[0]


def runs_today() -> int:
    """Paid backend ATTEMPTS today. Outcome records are bookkeeping, not spend."""
    return _count_attempts(_scan_ledger(days=2)[0])


def _count_attempts(recs: list[dict]) -> int:
    today = _today()
    return sum(1 for r in recs if r.get("day") == today and r.get("kind") != "outcome")


def daily_cap() -> int:
    """0 = unlimited. DISPLAY ONLY — enforcement uses _enforcement(), which
    refuses on an invalid config instead of reading it as 'unlimited'."""
    state, cfg, _ = _cfg_state()
    cap = cfg.get("daily_cap") if state == "valid" else None
    return cap if isinstance(cap, int) and not isinstance(cap, bool) and cap > 0 else 0


def log_invocation(mode: str, reviewer: dict, driver: dict, requested_by: str,
                   context_chars: int, extra: dict | None = None) -> bool:
    """Append one run to the ledger. Returns whether it was durably recorded.

    A crashed writer can leave a line with no trailing newline; appending after
    it would concatenate the two and destroy BOTH records. The newline guard
    heals that instead of compounding it.
    """
    rec = {
        "at": _now(), "epoch": time.time(), "day": _today(), "mode": mode,
        "reviewer": f"{reviewer['provider']}/{reviewer['model']}",
        "driver": f"{driver['provider']}/{driver['model']}",
        "requested_by": requested_by, "context_chars": context_chars,
        "cwd": os.getcwd(), "pid": os.getpid(),
    }
    if extra:
        rec.update(extra)
    return _append_ledger(rec)


def _append_ledger(rec: dict) -> bool:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        prefix = ""
        try:
            if LEDGER.is_file() and LEDGER.stat().st_size:
                with open(LEDGER, "rb") as fh:
                    fh.seek(-1, os.SEEK_END)
                    if fh.read(1) != b"\n":
                        prefix = "\n"
        except OSError:
            pass
        with open(LEDGER, "a", encoding="utf-8") as fh:
            fh.write(prefix + json.dumps(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return True
    except OSError as e:
        print(f"[devpair] note: could not write the invocation ledger ({e})",
              file=sys.stderr)
        return False


def _enforcement() -> tuple[int, bool, bool]:
    """(daily_cap, require_attestation, allow_unlocked_cap) for a PAID path.

    Three config states, kept apart on purpose: ABSENT means no limits (the
    documented default); VALID is enforced; PRESENT-BUT-INVALID refuses. The old
    reader turned a malformed or unreadable file into {} — which silently
    disabled BOTH the cap and required attestation. A broken limit is not an
    absent limit.
    """
    state, cfg, problem = _cfg_state()
    if state == "invalid":
        sys.exit(
            "devpair: refusing a paid run — the enforcement config is invalid.\n"
            f"  {problem}\n"
            "  A broken config must not silently disable the daily cap or required\n"
            f"  attestation. Fix {CONFIG} (or delete it to run with no limits), then retry."
        )
    cap = cfg.get("daily_cap") or 0
    return int(cap), bool(cfg.get("require_attestation")), bool(cfg.get("allow_unlocked_cap"))


def _new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + f"{os.getpid()}-{int(time.time() * 1000) % 100000}"


def _reserve_attempt_locked(args, reviewer: dict, driver: dict, context_chars: int, *,
                    run_id: str, attempt: int) -> tuple[bool, str]:
    """Reserve ONE paid backend attempt: check quota and append the ledger
    record under one lock, before the call. Returns (ok, refusal_message).

    Every attempt is reserved — fallbacks and live doctor probes included. The
    old flow authorised once and then let N fallback calls run uncounted, so
    "1/1 paid runs" could mean three billed calls, and the ledger named a
    reviewer that never answered.
    """
    cap, require, allow_unlocked = _enforcement()
    requested_by = (getattr(args, "requested_by", None)
                    or os.environ.get("DEVPAIR_REQUESTED_BY") or "").strip()
    enforcing = bool(cap) or require

    if require and not requested_by:
        return False, (
            "devpair: this install requires --requested-by on every run.\n"
            "  Name who asked for the review, e.g. --requested-by user\n"
            "  (agents: this is an attestation — do not fill it in unless the\n"
            "  user actually asked).")

    with _ledger_lock() as lock:
        if cap:
            if not lock.locked:
                # A "hard" cap that cannot serialise is not hard. Refuse rather
                # than continue under a guarantee we cannot keep — set
                # allow_unlocked_cap to accept an advisory cap deliberately.
                if not allow_unlocked:
                    return False, (
                        "devpair: a daily cap is set, but no file lock is available "
                        f"for {LEDGER}.\n"
                        "  Without one, two concurrent runs can both pass the same cap,\n"
                        "  so the limit cannot be enforced — refusing rather than\n"
                        "  advertising a hard cap this filesystem cannot provide.\n"
                        "  Note: network filesystems (NFS/SMB) may report a lock while\n"
                        "  not excluding other hosts. Keep the ledger on local disk.\n"
                        "  To accept an advisory cap anyway, set \"allow_unlocked_cap\": true "
                        f"in {CONFIG}.")
                print("[devpair] WARNING: no file lock available — the daily cap is "
                      "advisory here (allow_unlocked_cap is set), and two concurrent "
                      "runs could both pass it.", file=sys.stderr)
            recs, corrupt, readable = _scan_ledger(days=2)
            if not readable:
                # Unreadable is NOT zero. Treating it as zero would reopen a cap
                # that has already been spent.
                return False, (
                    f"devpair: the invocation ledger at {LEDGER} exists but cannot "
                    "be read, so today's usage is unknown.\n"
                    f"  A daily cap is set ({cap}/day) and unknown usage is not zero "
                    "usage — refusing rather than risk overspending.\n"
                    "  Check the file's permissions, then retry.")
            if corrupt:
                return False, (
                    f"devpair: the invocation ledger has {corrupt} unreadable "
                    f"line(s), so today's usage cannot be proven.\n"
                    f"  A daily cap is set ({cap}/day), and an unprovable limit is "
                    "not a limit — refusing rather than risk overspending.\n"
                    f"  Inspect or repair {LEDGER}, then retry.")
            used = _count_attempts(recs)
            if used >= cap:
                return False, (
                    f"devpair: daily cap reached — {used}/{cap} paid attempts today.\n"
                    "  This is a hard stop: no reviewer will be called.\n"
                    f"  Raise or clear it with \"daily_cap\" in {CONFIG}, or wait for tomorrow.\n"
                    "  See what spent it: devpair audit --days 1")

        wrote = log_invocation(getattr(args, "mode", "?"), reviewer, driver,
                               requested_by or "unattributed", context_chars,
                               extra={"kind": "attempt", "run_id": run_id, "attempt": attempt})

    if enforcing and not wrote:
        # The run would proceed unrecorded, which makes the cap uncountable and
        # a required attestation meaningless. Refuse instead of quietly
        # downgrading the guarantee the docs advertise.
        return False, (
            f"devpair: could not record this run in {LEDGER}.\n"
            "  This install enforces a daily cap or required attestation, both of\n"
            "  which depend on the ledger — proceeding would spend tokens that\n"
            "  nothing could account for. Fix the path's permissions and retry.")
    return True, ""


def reserve_attempt(args, reviewer: dict, driver: dict, context_chars: int, **kw) -> tuple[bool, str]:
    """Reserve ONE paid attempt under the ledger lock. A ledger lock held past
    the deadline REFUSES the attempt: spending without the lock would let two
    processes both pass the cap."""
    try:
        return _reserve_attempt_locked(args, reviewer, driver, context_chars, **kw)
    except LockTimeout as e:
        return False, (f"devpair: could not lock the invocation ledger — {e}.\n"
                       "  Refusing the paid call rather than spending outside the cap. "
                       "Retry when the other run finishes.")


def authorize(args, reviewer: dict, driver: dict, context_chars: int,
              *, run_id: str | None = None) -> str:
    """Gate a paid run by reserving its FIRST attempt. Exits non-zero rather
    than spending tokens. Returns the run id that later attempts and outcome
    records share."""
    run_id = run_id or _new_run_id()
    ok, why = reserve_attempt(args, reviewer, driver, context_chars, run_id=run_id, attempt=1)
    if not ok:
        sys.exit(why)
    return run_id


def record_outcome(run_id: str, attempt: int, receipt: dict) -> None:
    """Best-effort outcome record for an attempt (status, reported route,
    usage). Not counted against the cap — the reservation already was."""
    keep = ("status", "transport", "identity", "requested_provider", "requested_model",
            "reported_provider", "reported_model", "api_calls", "input_tokens",
            "output_tokens", "estimated_cost_usd", "cost_status", "elapsed_s", "warnings")
    rec = {"at": _now(), "epoch": time.time(), "day": _today(), "kind": "outcome",
           "run_id": run_id, "attempt": attempt}
    rec.update({k: receipt.get(k) for k in keep if k in receipt})
    try:
        with _ledger_lock():
            _append_ledger(rec)
    except LockTimeout as e:
        # The attempt itself is already counted; only its outcome note is lost.
        print(f"[devpair] WARNING: outcome not recorded — {e}", file=sys.stderr)




def _load_cfg() -> dict:
    """TOLERANT read for roster/order/display. Never use it to decide whether a
    paid call is allowed — that is _enforcement()/_cfg_state()."""
    if CONFIG.is_file():
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
            # Valid JSON of the WRONG SHAPE (a list, a string, a number) would
            # otherwise reach every .get() call site and crash the whole CLI —
            # _load_roster() runs before argparse, so a stray `[]` bricked even
            # `devpair --help`.
            if isinstance(cfg, dict):
                return cfg
            print(f"devpair: ignoring {CONFIG} — expected a JSON object, got "
                  f"{type(cfg).__name__}.", file=sys.stderr)
        except Exception:
            pass
    return {}


def _cfg_state() -> tuple[str, dict, str]:
    """('absent' | 'valid' | 'invalid', cfg, problem) — strict, for enforcement."""
    if not CONFIG.exists():
        return "absent", {}, ""
    try:
        raw = CONFIG.read_text(encoding="utf-8-sig")
    except OSError as e:
        return "invalid", {}, f"cannot read {CONFIG}: {e}"
    try:
        cfg = json.loads(raw)
    except Exception as e:
        return "invalid", {}, f"{CONFIG} is not valid JSON ({e})"
    if not isinstance(cfg, dict):
        return "invalid", {}, f"{CONFIG} must be a JSON object, got {type(cfg).__name__}"
    problems = []
    cap = cfg.get("daily_cap")
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 0):
        problems.append(f"daily_cap must be a non-negative integer (0 = unlimited), got {cap!r}")
    for k in ("require_attestation", "allow_unlocked_cap"):
        if k in cfg and not isinstance(cfg[k], bool):
            problems.append(f"{k} must be true or false, got {cfg[k]!r}")
    if problems:
        return "invalid", cfg, "; ".join(problems)
    return "valid", cfg, ""


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
_SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


_WIN_DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} |     {f"{d}{i}" for d in ("COM", "LPT") for i in range(1, 10)}


def _valid_session_name(name: str | None) -> bool:
    """Letters/digits/._- only, no '..', no trailing dot, and never a Windows
    device name (the device rule applies to the part before the first dot, so
    `NUL.json` IS the null device and the turn would be silently lost)."""
    if not name or not _SESSION_NAME_RE.match(name) or ".." in name or name.endswith("."):
        return False
    return name.split(".", 1)[0].upper() not in _WIN_DEVICES


def _contained_session(name: str) -> Path:
    """SESSIONS/<name>.json, refusing anything that resolves outside SESSIONS.
    `--session ../x` (or an absolute/drive path, which makes `SESSIONS / name`
    discard SESSIONS entirely) used to read and write wherever it pointed."""
    if not _valid_session_name(name):
        sys.exit(f"devpair: invalid session name {name!r} — use letters, digits, '.', '_' "
                 "or '-' (max 100 chars), with no path separators or '..'.")
    p = SESSIONS / f"{name}.json"
    try:
        root = SESSIONS.resolve()
        if not str(p.resolve()).startswith(str(root) + os.sep):
            sys.exit(f"devpair: session {name!r} resolves outside {SESSIONS} — refusing.")
    except OSError:
        pass
    return p


def project_root(cwd: str | None = None) -> str:
    """Identity of the project being reviewed: the git top-level when inside a
    work tree, else the working directory. Normalised for comparison."""
    cwd = cwd or os.getcwd()
    top = sh(["git", "rev-parse", "--show-toplevel"], cwd)
    root = top if top and Path(top).is_dir() else cwd
    return os.path.normcase(os.path.realpath(root))


def _same_project(stored: str | None, root: str) -> bool:
    """A session belongs to `root` if it recorded that root, or (legacy
    sessions recorded the raw cwd) a directory inside it. A session with no
    project recorded is treated as matching — nothing says otherwise."""
    if not stored:
        return True
    s = os.path.normcase(os.path.realpath(stored))
    return s == root or s.startswith(root.rstrip("\\/") + os.sep)


def _read_pointers() -> tuple[str | None, dict]:
    """(legacy_single_name, {project_root: name}) from CURRENT. The pointer used
    to be ONE global name, so a review in project B silently continued — and
    replayed — project A's session."""
    try:
        raw = CURRENT.read_text(encoding="utf-8").strip() if CURRENT.is_file() else ""
    except OSError:
        raw = ""
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return None, {k: v for k, v in data.items() if isinstance(v, str)}
        except Exception:
            pass
        return None, {}
    return (raw or None), {}


def _current_for(root: str) -> str | None:
    legacy, mapping = _read_pointers()
    name = mapping.get(root)
    if name is None and legacy:
        name = legacy
    if name and not _valid_session_name(name):
        print(f"[devpair] note: ignoring invalid current-session pointer {name!r}", file=sys.stderr)
        return None
    if name:
        p = SESSIONS / f"{name}.json"
        if p.is_file() and not _same_project(load_session(p, quarantine=False).get("project"), root):
            # The pointed-to session belongs to another project — never replay it here.
            return None
    return name


def _set_current(root: str, name: str) -> None:
    legacy, mapping = _read_pointers()
    if legacy and _valid_session_name(legacy):
        lp = SESSIONS / f"{legacy}.json"
        owner = load_session(lp, quarantine=False).get("project") if lp.is_file() else None
        if owner:
            mapping.setdefault(os.path.normcase(os.path.realpath(owner)), legacy)
    mapping[root] = name
    CURRENT.parent.mkdir(parents=True, exist_ok=True)
    tmp = CURRENT.with_name(CURRENT.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(mapping, indent=1), encoding="utf-8")
    os.replace(tmp, CURRENT)


def active_session_names() -> set[str]:
    legacy, mapping = _read_pointers()
    return set(mapping.values()) | ({legacy} if legacy else set())


def _new_session_name() -> str:
    """A timestamp name that is not already taken. Callers that pin it hold the
    CURRENT lock across choose-and-pin, so two processes never pick the same
    name; the short random suffix also keeps unpinned names (chosen at the start
    of a run, pinned only after the review) from colliding across processes."""
    base = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(2).hex()
    taken = active_session_names()
    name, n = base, 2
    while (SESSIONS / f"{name}.json").exists() or name in taken:
        name, n = f"{base}-{n}", n + 1
    return name


def session_path(name: str | None = None, create: bool = True) -> Path:
    """Resolve the active session file.

    create=False resolves without side effects (for read-only commands like
    `log`), so merely asking where the session is never invents a new one.
    The default session is per PROJECT: another project's session is never
    picked up implicitly.
    """
    SESSIONS.mkdir(parents=True, exist_ok=True)
    if name:
        return _contained_session(name)
    root = project_root()
    cur = _current_for(root)
    if cur:
        return _contained_session(cur)
    if not create:
        return SESSIONS / f"{_new_session_name()}.json"
    # Choose-and-pin under the ONE pointer lock, like every other CURRENT write.
    try:
        with _file_lock(str(CURRENT) + ".lock"):
            cur = _current_for(root)
            if cur:
                return _contained_session(cur)
            stamp = _new_session_name()
            _set_current(root, stamp)
    except LockTimeout as e:
        sys.exit(f"devpair: the session pointer is locked by another devpair run ({e}). "
                 "Retry when it finishes, or pass --session NAME.")
    return SESSIONS / f"{stamp}.json"


def load_session(path: Path, *, quarantine: bool = True) -> dict:
    """A session, or a fresh one. A session file that exists but cannot be
    parsed is MOVED ASIDE (quarantined) rather than silently replaced: the old
    behaviour returned an empty session and the next save overwrote the whole
    history."""
    if path.is_file():
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            raw = None
        try:
            data = json.loads(raw) if raw is not None else None
            if isinstance(data, dict):
                data.setdefault("turns", [])
                return _redact_session(data)
        except Exception:
            pass
        if quarantine and raw is not None:
            # Only a file we could READ but not PARSE is quarantined; an unreadable
            # one (permissions, sharing violation) is left exactly where it is.
            aside = path.with_name(path.name + f".corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
            try:
                # The quarantined copy is redacted too: legacy sessions saved
                # --ask/--focus verbatim, and a corrupt file is still on disk.
                aside.write_text(redact_secrets(raw or "")[0], encoding="utf-8")
                path.unlink()
                print(f"[devpair] WARNING: session {path.name} was unreadable — kept (redacted) as "
                      f"{aside.name}; starting a fresh session.", file=sys.stderr)
            except OSError:
                pass
    return {"created": _now(), "project": None, "turns": []}


_REDACT_TURN_KEYS = ("ask", "focus", "response")


def _redact_session(data: dict) -> dict:
    """Redact EVERY turn at the load boundary — one choke point. Redacting only
    the newly appended turn left credentials from older turns on disk and
    replayed them to the next reviewer through prior_context."""
    for t in data.get("turns") or []:
        if isinstance(t, dict):
            for k in _REDACT_TURN_KEYS:
                if isinstance(t.get(k), str):
                    t[k] = redact_secrets(t[k])[0]
    return data


def save_session(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)  # transcripts hold review text; owner-only where supported
    except OSError:
        pass
    os.replace(tmp, path)  # atomic on POSIX — a crash never leaves a torn file


def append_turn(path: Path, turn: dict, project: str) -> dict:
    """Reload-append-save under a per-session lock. Atomic replace alone did not
    serialise read-modify-write: two runs that loaded the same session before
    the model call each saved their copy, and the second erased the first."""
    try:
        with _file_lock(str(path) + ".lock"):
            sess = load_session(path)
            sess.setdefault("turns", []).append(turn)
            if not sess.get("project"):
                sess["project"] = project
            save_session(path, sess)
        return sess
    except LockTimeout as e:
        return _rescue_turn(path, turn, project, str(e))


def _rescue_turn(path: Path, turn: dict, project: str, why: str) -> dict:
    """The review was paid for: never lose it, never write it unlocked."""
    rescue = path.with_name(f"{path.stem}.turn-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                            f"-{os.getpid()}.json")
    save_session(rescue, {"created": _now(), "project": project, "turns": [turn],
                          "rescued_from": path.name})
    print(f"[devpair] WARNING: session lock unavailable ({why}); this turn was saved to "
          f"{rescue.name} instead of being written unlocked.", file=sys.stderr)
    return {"turns": [turn], "project": project}


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
    sink = getattr(_TLS, "clips", None)
    if isinstance(sink, list):
        sink.append({"section": label, "chars": len(text), "omitted_chars": omitted})
    return f"{head}\n\n[... {label} truncated: {omitted} chars omitted ...]\n\n{tail}"


def last_manifest() -> dict | None:
    """Harness-side evidence manifest of the most recent gather() on THIS
    thread: what was sent, what was clipped, what was left out and why. The
    gate decides coverage from THIS, never from what the reviewer says."""
    return getattr(_TLS, "manifest", None)


_DIFF_PATH_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.M)


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

# Token COUNTS are not tokens: input_tokens, max_tokens, token_count, num_tokens.
_COUNT_NAME = re.compile(r"(?i)(tokens$|^max_?tokens?|tokens?_(count|limit|budget|used|in|out)$|^num_?tokens?)")


# identifier(...), identifier[...], a.b.c(...) — a call or index, not a credential.
_CODE_EXPR = re.compile(r"^[A-Za-z_][\w.]*\s*[(\[]")


def _CODE_NOT_SECRET(name: str, value: str) -> bool:
    """An `assigned-secret` match that is plainly code, not a credential:
    a call or index expression (`_as_int(u.get(...))`, `cfg["x"]`) or a
    token-COUNT name. Bare numbers are NOT exempt: a numeric PIN is a secret. Redacting those garbled code under review —
    reviewers were sent `"input_tokens": [REDACTED]` and could not read it."""
    if _CODE_EXPR.match(value):
        return True
    return bool(_COUNT_NAME.search(name or ""))


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
            if kind == "assigned-secret" and _CODE_NOT_SECRET(m.group(1), secret):
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
    _TLS.clips = []
    _TLS.manifest = None
    omitted: list[dict] = []    # required evidence that was NOT sent, and why
    failures: list[str] = []    # context commands that failed
    paths: list[str] = []       # repo-relative paths whose content WAS sent
    try:
        context, notes = _gather_parts(args, omitted, failures, paths)
    finally:
        clips = list(getattr(_TLS, "clips", None) or [])
        _TLS.clips = None
    total_clipped = any(c["section"] == "total context" for c in clips)
    gaps = ([f"{c['section']} truncated ({c['omitted_chars']:,} of {c['chars']:,} chars omitted)"
             for c in clips]
            + [f"{o['source']}: {o['reason']}" for o in omitted]
            + [f"context command failed: {f}" for f in failures])
    _TLS.manifest = {
        "complete": not gaps,
        "gaps": gaps,
        "clipped": clips,
        "omitted": omitted,
        "failures": failures,
        "total_clipped": total_clipped,
        "paths": sorted(set(paths)),
        "context_chars": len(context),
        "sha256": hashlib.sha256(context.encode("utf-8", "replace")).hexdigest(),
    }
    return context, notes


def _gather_parts(args, omitted: list, failures: list, paths: list) -> tuple[str, list[str]]:
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
                failures.append(f"{src} ({note})")
        else:
            d, note = sh(["git", "diff", "HEAD"], cwd, want_status=True)
            src = "git diff HEAD (uncommitted)"
            if note:
                notes.append(f"`{src}` failed ({note})")
                failures.append(f"{src} ({note})")
        untracked, lnote = sh(["git", "ls-files", "--others", "--exclude-standard"], cwd, want_status=True)
        if lnote:
            notes.append(f"`git ls-files --others` failed ({lnote}) — untracked files unknown")
            failures.append(f"git ls-files --others ({lnote})")
        if d.strip():
            paths.extend(m.group(2) for m in _DIFF_PATH_RE.finditer(d))
            parts.append(f"## DIFF UNDER REVIEW — {src}\n```diff\n{clip(d, MAX_DIFF_CHARS, 'diff')}\n```")
        elif not note and not untracked.strip():
            notes.append(f"no diff found for '{src}'")
        if ref:
            u, unote = sh(["git", "diff", "HEAD"], cwd, want_status=True)
            if u.strip():
                paths.extend(m.group(2) for m in _DIFF_PATH_RE.finditer(u))
                parts.append(
                    "## UNCOMMITTED CHANGES (not in the branch diff above)\n"
                    f"```diff\n{clip(u, MAX_DIFF_CHARS // 2, 'uncommitted diff')}\n```"
                )
            elif unote:
                notes.append(f"`git diff HEAD` failed ({unote})")
                failures.append(f"git diff HEAD ({unote})")
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
            for idx, f in enumerate(files):
                if shown >= MAX_UNTRACKED_FILES:
                    rest = files[idx:]
                    parts.append(
                        f"## NOTE\n{len(rest)} further untracked file(s) not shown "
                        f"(limit {MAX_UNTRACKED_FILES}). Use --files to include specific ones."
                    )
                    for r in rest:
                        omitted.append({"source": r, "reason": f"untracked file beyond the {MAX_UNTRACKED_FILES}-file limit"})
                    break
                p = Path(cwd) / f
                try:
                    if not p.is_file():
                        continue
                    if p.stat().st_size > MAX_UNTRACKED_BYTES:
                        omitted.append({"source": f, "reason": f"untracked file larger than {MAX_UNTRACKED_BYTES:,} bytes"})
                        continue
                    body = p.read_text(errors="replace")
                except Exception as e:
                    omitted.append({"source": f, "reason": f"unreadable ({type(e).__name__})"})
                    continue
                if not body.strip():
                    continue  # empty: nothing to review
                if "\x00" in body[:1024]:
                    omitted.append({"source": f, "reason": "binary untracked file not shown"})
                    continue
                numbered = "\n".join(
                    f"{i:>5}| {ln}" for i, ln in enumerate(body.splitlines(), 1)
                )
                parts.append(
                    f"## NEW FILE (untracked): {f}\n```\n"
                    f"{clip(numbered, MAX_UNTRACKED_CHARS, f)}\n```"
                )
                paths.append(f)
                shown += 1

    for f in args.files or []:
        p = Path(f).expanduser()
        if not p.is_file():
            notes.append(f"file not found: {f}")
            omitted.append({"source": f, "reason": "requested --files entry not found"})
            continue
        try:
            body = p.read_text(errors="replace")
        except Exception as e:
            notes.append(f"unreadable {f}: {e}")
            omitted.append({"source": f, "reason": f"requested --files entry unreadable ({type(e).__name__})"})
            continue
        numbered = "\n".join(f"{i:>5}| {ln}" for i, ln in enumerate(body.splitlines(), 1))
        parts.append(
            f"## FILE: {p}\n```\n{clip(numbered, MAX_FILE_CHARS, p.name)}\n```"
        )
        try:
            paths.append(os.path.relpath(p.resolve(), cwd))
        except ValueError:  # different drive on Windows
            paths.append(str(p))

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

TOOLS: you have none. You cannot run commands, open files, browse, or check
anything against a live system — the evidence below is everything you can see.
Do not announce checks you are about to run: write the whole review now, and put
any check you would want run into the testing section as a recommendation.

FRAMING: their question is a hypothesis, not a premise. If it rests on a wrong
premise, or offers a choice between options that are both wrong, say that first.
Judge against an explicit decision rule — what "good enough" means here — and
state it in one line when it is not obvious.

STAKES: every [BLOCKER] or [MAJOR] must name the decision it changes (ship or
not, this design or another). A finding that changes no decision is [MINOR] at most.
"""

CONFIDENCE_TAIL = """
## CONFIDENCE
High / Medium / Low — then one line: what you saw versus what you had to assume.

## WHAT WOULD CHANGE MY MIND
Flip condition: the one concrete fact that, if shown to you, would change your verdict.
Falsifier: the cheapest observation that would prove your most serious finding wrong."""

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

    # Mirrors the verify-results skill's six passes and label vocabulary.
    # Pinned to the canonical SKILL.md by
    # test_verify_template_matches_the_verify_results_skill — edit both together.
    # EXACTLY. The labels are shared with quality-guard, so a flag raised here
    # must stay legible there — do not substitute devpair's own
    # [BLOCKER|MAJOR|MINOR] severity words in this shape.
    "verify": """Respond in EXACTLY this shape, using these labels where relevant:
[VERIFIED ERROR] — contradicted by supplied material or reliable evidence
[UNSUPPORTED CLAIM] — may be true, but no evidence is provided
[LIKELY ISSUE] — appears problematic but needs confirmation
[ASSUMPTION] — relies on something not stated
[STYLE/CLARITY] — wording, flow, or presentation issue
[SAFETY/COMPLIANCE] — risk of harm, legal, medical, financial, or reputational

## EVIDENCE BASIS
One or two lines naming exactly what you were given and what you could NOT check.
Name the artefact (path, line count, commit SHA or version) so the verdict says
which revision it covers, and quote any command output verbatim rather than
paraphrasing it. If you saw only part of the work, say so — and then cap your
verdict at REVISE BEFORE USE. An APPROVE issued on a partial view launders a
guess as an assurance.

## PASS 1 — ERRORS & PROBLEMS
What is factually wrong, logically flawed, technically broken, misleading, unsafe,
non-compliant, or likely to fail in the real world. For each:
- Severity: [CRITICAL] / [MAJOR] / [MINOR]
- Label: one of the labels above
- Quoted text or exact section
- What is wrong
- Evidence, reasoning, or source basis
- Confidence: High / Medium / Low
- Corrected version or recommended fix

Severity guide: [CRITICAL] will break, mislead, cause harm, create serious
legal/compliance risk, or make the work unusable. [MAJOR] should be fixed before
use. [MINOR] acceptable but should be improved.

## PASS 2 — HALLUCINATION & VERIFICATION CHECK
Invented facts, sources, names, dates, numbers, studies, products, APIs,
specifications or capabilities; authoritative-sounding but unevidenced claims;
false precision; exaggerated certainty; unsupported statistics; outdated or
time-sensitive information; missing citations or weak source grounding.
Mark each [VERIFIED ERROR], [UNSUPPORTED CLAIM], [LIKELY ISSUE], or [ASSUMPTION],
and state which ones you could NOT check — an unchecked claim must not look like a
cleared one. Anything here that is an actual defect also belongs in PASS 1 where it
carries a severity; PASS 2 records check status only. Do not list it twice as
though it were two problems.

## PASS 3 — GAPS & OMISSIONS
What a competent professional would expect to find and cannot: missing evidence,
safety warnings, edge cases, implementation detail, stated assumptions, audience
context, compliance checks, practical instructions, limitations, test cases, or
failure modes. Do not list things absent because they are irrelevant.

## PASS 4 — IMPROVEMENT RECOMMENDATIONS
Up to five improvements ranked by impact, highest first — or "None." if the work
does not warrant any; do not pad to reach a count. For each: what to change,
where, why it materially matters, and a concrete rewrite/example/checklist if
applicable. Prioritise fixes preventing factual error, user harm, broken
functionality, compliance risk, reputational damage, or serious misunderstanding.

## PASS 5 — CHECKS THAT WOULD SETTLE THIS
List the specific commands, lookups, or sources that would confirm or refute your
findings above — the evidence you could not gather yourself. Prefer runnable
commands over vague advice. If none are needed, write "None." This section is the
point of running a second model: name what the first one should go and check.

## PASS 6 — VERDICT & WHAT HAPPENS NEXT
One of: APPROVE / APPROVE WITH MINOR EDITS / REVISE BEFORE USE / DO NOT USE
(APPROVE WITH MINOR EDITS requires only [MINOR] findings AND a full evidence basis.)
Then one short paragraph covering: overall assessment; the primary risk if used
as-is; the single highest-leverage fix; and whether further external verification
is required.""",
}

VERIFY_ROLE = """You are an independent verifier performing a post-hoc critique of work
that ALREADY EXISTS, running on a different model than the one that produced it.

Apply the standard of a senior professional reviewing this before it goes live, is
merged, deployed, published, or relied upon. The work is most often CODE — a diff, a
pull request, a script, a config, a schema, a migration, a test suite — but it may
equally be a document, an analysis, a report, or a plain answer. Critique what is
actually in front of you, and do not assume a domain that was not stated.

Your value is that you did not write it. You have different blind spots, and you are
not attached to any of its conclusions.

RULES
  - Do not invent missing context, and do not assume requirements that were not
    stated unless they are essential for this type of work.
  - Separate confirmed errors from unsupported claims, assumptions, and subjective
    improvements. These are different things and must not be blurred.
  - Where verification is possible, prefer the supplied source material first, then
    official documentation, primary research, recognised standards, or authoritative
    references.
  - If you are uncertain, say so, and mark confidence High, Medium, or Low.
  - Flag false precision, overclaiming, invented detail, and unsupported certainty.
  - You cannot run commands or open files. Anything you could not check yourself is a
    CLAIM about the work, not a finding — say which checks would settle it.
  - Do not pad, and do not praise structure while ignoring substance. If something is
    good, move on. "No material issues" is a valid answer when it is true.

Use British English."""

ASK_HINT = {
    "critique": "Critique this direction before effort is sunk into it.",
    "review": "Review this work.",
    "debug": "Help me find this bug.",
    "alt": "Challenge this approach and give me the alternatives.",
    "followup": "Here is how I responded to your review.",
    "verify": "Verify this finished work before it is used.",
}


def build_prompt(mode: str, ask: str, context: str, sess: dict, focus: str | None,
                 notes: list[str] | None = None, manifest: dict | None = None) -> str:
    # `verify` critiques a finished deliverable that may not be code at all, so
    # it carries its own role. Every other mode is the software-supervision one.
    blocks = [VERIFY_ROLE if mode == "verify" else ROLE]
    if focus:
        blocks.append(f"\n## FOCUS DIRECTIVE\nThe colleague specifically wants your attention on: {focus}\nStill report anything critical you find outside that focus.")
    blocks.append(prior_context(sess))
    blocks.append(f"\n## WHAT THEY ARE ASKING\n{ask or ASK_HINT.get(mode, '')}")
    if isinstance(manifest, dict) and manifest.get("gaps"):
        # The harness — not the reviewer — knows what was left out. Saying so
        # lets the reviewer calibrate instead of approving what it never saw.
        gaps = "\n".join(f"- {g}" for g in manifest["gaps"][:12])
        blocks.append(
            "\n## EVIDENCE SCOPE (reported by the harness, not a guess)\n"
            "You are NOT seeing everything in scope. Missing or truncated:\n"
            f"{gaps}\n"
            "Any approval you give covers only what is shown — say what the gaps could hide."
        )
    if context.strip():
        blocks.append(f"\n## CONTEXT / EVIDENCE\n{context}")
    else:
        blocks.append(
            "\n## CONTEXT / EVIDENCE\n(none supplied — if you cannot review responsibly "
            "without seeing code, say exactly what you need and stop.)"
        )
    shape = SHAPES[mode] + ("" if mode == "verify" else CONFIDENCE_TAIL)
    blocks.append("\n## REQUIRED OUTPUT SHAPE\n" + shape)
    blocks.append(
        "\nBe dense. Every line must earn its place. A short sharp review beats a "
        "long thorough-looking one. Do not restate the context back to them."
    )
    prompt = "\n".join(b for b in blocks if b)
    # FINAL chokepoint. gather() scrubs the evidence, but it is only ONE of the
    # blocks above: --ask, --focus and the replayed prior turns never passed
    # through it, so a credential typed into a question — or quoted back by the
    # reviewer in turn 1 and replayed on every turn after — went to the API in
    # clear. Redacting the assembled prompt is the only placement that covers
    # every block, including any added later. Already-scrubbed context is not
    # double-counted: the patterns skip existing [REDACTED:...] markers.
    prompt, late = redact_secrets(prompt)
    if late and notes is not None:
        notes.append(
            f"redacted {late} credential-shaped value(s) from the question, focus, "
            "or replayed session history — check what you are pasting into --ask"
        )
    return prompt


# ---------------------------------------------------------------------------
# Verdict parsing, gating, and claim verification. The reviewer's output is
# prose, but two things in it are machine-actionable: the verdict line, and any
# file:line it cites. Both are extracted here so a caller can gate on the first
# and distrust the second.
# ---------------------------------------------------------------------------
BAD_VERDICTS = {"DO NOT SHIP", "STOP", "NEEDS WORK", "RECONSIDER",
                # verify mode's vocabulary (verify-results / quality-guard)
                "DO NOT USE", "REVISE BEFORE USE"}
_VERDICT_RE = re.compile(
    # Tolerates the forms a model actually emits: with or without heading
    # hashes, "PASS 5 — VERDICT", "PASS 6 — VERDICT & WHAT HAPPENS NEXT", and
    # an inline "VERDICT: APPROVE". Being strict here does not fail safe — an
    # unparseable verdict fails the gate, so a well-formed review would be
    # rejected on punctuation. The heading may carry trailing words; the
    # verdict itself is then on the next line.
    r"^\s*#*\s*(?:PASS\s*\d+\s*[—\-–:]\s*)?(?:REMAINING\s+)?VERDICT"
    r"(?:\s*[&/][^\n]*|\s+(?:AND|WHAT)[^\n]*)?"
    r"\s*(?:[:：—\-–]\s*|$)\s*(.+?)$",
    re.M | re.I,
)


def parse_verdict(response: str) -> str | None:
    """Extract the verdict token from a review. None if absent/unparseable."""
    tokens = _all_verdicts(response)
    return tokens[0] if tokens else None


def _all_verdicts(response: str) -> list[str]:
    """Every distinct verdict token in the response, in order of appearance.

    More than one DIFFERENT token means the review contradicts itself (or quotes
    an example verdict), and the gate cannot know which is meant — see
    gate_failed, which refuses rather than picking.
    """
    out: list[str] = []
    for m in _VERDICT_RE.finditer(response or ""):
        line = m.group(1).strip().strip("*_` ").upper()
        # Longest-first so "DO NOT SHIP" wins over "SHIP", and
        # "PROCEED WITH CHANGES" over "PROCEED".
        known = ["DO NOT SHIP", "SHIP AFTER FIXES", "PROCEED WITH CHANGES",
                 "NEEDS WORK", "RECONSIDER", "PROCEED", "SHIP", "STOP",
                 # verify mode. "APPROVE WITH MINOR EDITS" must beat "APPROVE",
                 # and "DO NOT USE" must beat nothing else — both handled by the
                 # longest-first sort below.
                 "APPROVE WITH MINOR EDITS", "REVISE BEFORE USE", "DO NOT USE",
                 "APPROVE"]
        for tok in sorted(known, key=len, reverse=True):
            if line.startswith(tok):
                if tok not in out:
                    out.append(tok)
                break
    return out


def count_blockers(response: str) -> int:
    """Highest-severity findings, in EITHER vocabulary.

    devpair's own modes emit [BLOCKER]; `verify` mirrors verify-results and
    emits [CRITICAL]. Counting only one would let --gate pass a review full of
    critical findings.
    """
    return len(re.findall(r"\[(?:BLOCKER|CRITICAL)\]", response or "", re.I))


def gate_failed(response: str) -> tuple[bool, str]:
    """Should a --gate run exit non-zero? Returns (failed, reason).

    Fails closed on an unparseable verdict: a gate that cannot read the answer
    must not report success. Also fails closed on CONFLICTING verdicts — a
    review that says SHIP and later DO NOT SHIP was previously gated on
    whichever came first, which is a fail-OPEN in the one component whose job
    is to fail closed. An identical verdict restated is not a conflict.
    """
    verdicts = _all_verdicts(response)
    blockers = count_blockers(response)
    if not verdicts:
        return True, "no parseable VERDICT line in the review"
    if len(verdicts) > 1:
        return True, ("conflicting verdicts in one review: "
                      + ", ".join(verdicts)
                      + " — cannot tell which is meant")
    verdict = verdicts[0]
    if verdict in BAD_VERDICTS:
        return True, f"verdict: {verdict}"
    if blockers:
        return True, f"verdict {verdict} but {blockers} [BLOCKER] finding(s) present"
    return False, f"verdict: {verdict}"


def coverage_status(manifest: dict | None) -> tuple[str, list[str]]:
    """complete | partial | unknown, from the HARNESS manifest only."""
    if not isinstance(manifest, dict):
        return "unknown", ["no evidence manifest — coverage cannot be established"]
    gaps = [str(g) for g in (manifest.get("gaps") or [])]
    return ("complete" if manifest.get("complete") and not gaps else "partial"), gaps


def gate_decision(response: str, manifest: dict | None, *, allow_partial: bool = False,
                  claim_problems: list[str] | None = None,
                  strict_citations: bool = False) -> tuple[bool, str, str]:
    """(failed, reason, coverage). Verdict checks first (gate_failed), then
    COVERAGE: an approval is only as good as the evidence behind it, and that
    is decided by what the harness sent — the reviewer saying "I saw
    everything" cannot override a clipped or incomplete packet."""
    failed, reason = gate_failed(response)
    coverage, gaps = coverage_status(manifest)
    if failed:
        return True, reason, coverage
    if coverage != "complete":
        gap_txt = "; ".join(gaps[:4]) + (f"; +{len(gaps) - 4} more" if len(gaps) > 4 else "")
        if allow_partial and coverage == "partial":
            reason = f"{reason} — PARTIAL evidence accepted by --allow-partial ({gap_txt})"
        else:
            return True, (f"{reason}, but the evidence was {coverage}: {gap_txt} — narrow the "
                          "scope or pass --allow-partial to accept a PARTIAL approval"), coverage
    if strict_citations and claim_problems:
        return True, (f"{reason}, but {len(claim_problems)} cited anchor(s) could not be verified "
                      f"(--strict-citations): {claim_problems[0]}"), coverage
    return False, reason, coverage


def _in_packet(raw: str, packet_paths: list[str]) -> bool:
    """Was this cited path part of the evidence actually sent? Matched on path
    suffix (a reviewer may cite `devpair.py` for `tools/devpair.py`), never on
    mere existence in the working tree."""
    r = raw.replace("\\", "/").lstrip("./").lower()
    for p in packet_paths:
        q = p.replace("\\", "/").lstrip("./").lower()
        if q == r or q.endswith("/" + r) or r.endswith("/" + q):
            return True
    return False


def _located_in_text(name: str, text: str | None) -> bool:
    """The basename appears in the packet AS A LOCATION — `name:12`,
    `File ".../name", line 12`, `name line 12` — i.e. a traceback or compiler
    message the reviewer was shown. A bare mention (comment, import, prose)
    does not count, or --strict-citations would excuse almost anything."""
    if not text or not name:
        return False
    pat = (r"(?:^|[\s/\\\"'(])" + re.escape(name)
           + r"(?:\"?,?\s*line\s+\d+|:\d+)")
    return re.search(pat, text, re.I | re.M) is not None


def verify_claims(response: str, cwd: str | None = None,
                  packet_paths: list[str] | None = None,
                  packet_text: str | None = None) -> list[str]:
    """Check every `path:line` the reviewer cited.

    It reasons from pasted text and cannot open files, so its anchors are
    claims, not facts. Returns human-readable problems (missing file, line past
    EOF, or — when the packet is known — a file it was never sent). Files
    outside the working tree are ignored rather than guessed at.
    """
    root = Path(cwd or os.getcwd())
    problems: list[str] = []
    seen: set[tuple[str, int]] = set()
    # Two anchor styles, because models use both and only one was checked.
    # Reviewers routinely cite in prose ("README.md line 438"), and the
    # colon-only pattern matched none of those — so an anchor to a file the
    # reviewer was never sent went unflagged, which is the one thing this
    # function exists to catch.
    anchors = re.findall(r"\b([\w./\-]+\.[A-Za-z]\w{0,9}):(\d+)\b", response or "")
    anchors += re.findall(r"\b([\w./\-]+\.[A-Za-z]\w{0,9})\s+(?:on\s+)?lines?\s+(\d+)",
                          response or "", re.I)
    for raw, lineno in anchors:
        try:
            n = int(lineno)
        except ValueError:
            continue
        if (raw, n) in seen:
            continue
        seen.add((raw, n))
        if packet_paths is not None and not _in_packet(raw, packet_paths) \
                and not _located_in_text(Path(raw).name, packet_text):
            problems.append(f"{raw}:{n} — not in the evidence sent to the reviewer")
            continue
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


def _hermes_command() -> list[str]:
    """The command prefix that launches the reviewer backend.

    Two portability problems, one answer:

    * A bare "hermes" in a subprocess list reaches CreateProcess on Windows,
      which only ever appends `.exe` and never consults `PATHEXT` — so the
      `.cmd`/`.bat` shim this skill's own manual-install section tells you to
      create was invisible. `shutil.which` walks PATHEXT properly.
    * Some installs put Hermes somewhere PATH does not reach, or behind a
      wrapper (a venv launcher, a container shim). `DEVPAIR_HERMES_CMD` takes a
      full command prefix — e.g. `/usr/bin/python3 /opt/hermes/cli.py` — and the
      reviewer arguments are appended to it.

    Falls back to the bare name so a genuinely missing binary still produces the
    existing soft failure rather than a new error here.
    """
    override = os.environ.get("DEVPAIR_HERMES_CMD", "").strip()
    if override:
        # Neither shlex mode is correct on its own for a Windows path:
        #   posix=True  treats "\\" as an escape, so C:\\Users\\x loses its separators;
        #   posix=False keeps the quote characters INSIDE the token, so a quoted
        #               path arrives as  'C:\\...\\python.exe'  and will not launch.
        # Split with backslashes preserved, then strip one balanced pair of
        # surrounding quotes per token. Both quoting styles then work on every
        # platform, which is what a documented env var has to promise.
        parts = []
        for tok in shlex.split(override, posix=False):
            if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
                tok = tok[1:-1]
            if tok:
                parts.append(tok)
        return parts or [shutil.which("hermes") or "hermes"]
    return [shutil.which("hermes") or "hermes"]


# ---------------------------------------------------------------------------
# Reviewer launch. Three guarantees live here, and each was broken before:
#
#  1. READ-ONLY. `hermes -z ... -t ""` does NOT mean "no tools": Hermes
#     normalises an empty toolset to None and then loads the config's full CLI
#     toolset (terminal, write_file, patch, execute_code, delegate_task, ...)
#     with approvals bypassed (oneshot sets HERMES_YOLO_MODE). The reviewer is
#     now launched with an explicit toolset that resolves to ZERO tools
#     (default `context_engine`; override with `reviewer_toolset`), plus
#     --ignore-rules so the operator's SOUL/memory/AGENTS.md are neither sent
#     to a third-party model nor allowed to steer the review.
#  2. TRANSPORT. Windows CreateProcess caps the whole command line at 32,767
#     chars; a bigger prompt raised FileNotFoundError(winerror 206), which was
#     reported as "hermes not found". Large prompts now travel through a
#     private temp file (`hermes chat -Q --query-file`), never through argv.
#  3. RECEIPTS. Every attempt records what was REQUESTED and what the backend
#     REPORTED (provider/model/completion/usage), read from Hermes' own
#     --usage-file. A selection banner is not evidence of who answered.
# ---------------------------------------------------------------------------
REVIEWER_TOOLSET_DEFAULT = "context_engine"
_WIN_CMDLINE_SAFE = 30_000      # CreateProcess hard limit is 32,767 UTF-16 units
_POSIX_ARG_SAFE = 100_000       # Linux MAX_ARG_STRLEN is 131,072 bytes per arg
_TLS = threading.local()


def last_receipt() -> dict | None:
    """Receipt of the most recent run_reviewer() call made on THIS thread."""
    return getattr(_TLS, "receipt", None)


def _reviewer_toolset() -> str:
    env = os.environ.get("DEVPAIR_REVIEWER_TOOLSET", "").strip()
    if env:
        return env
    v = _load_cfg().get("reviewer_toolset")
    return v.strip() if isinstance(v, str) and v.strip() else REVIEWER_TOOLSET_DEFAULT


def _prompt_transport() -> str:
    v = os.environ.get("DEVPAIR_PROMPT_TRANSPORT") or _load_cfg().get("prompt_transport") or "auto"
    v = str(v).strip().lower()
    return v if v in ("auto", "inline", "file") else "auto"


def _fits_inline(cmd: list[str]) -> bool:
    if os.name == "nt":
        return len(subprocess.list2cmdline(cmd)) < _WIN_CMDLINE_SAFE
    return all(len(a.encode("utf-8", "replace")) < _POSIX_ARG_SAFE for a in cmd)


def _norm_model(m: str) -> str:
    m = (m or "").lower().rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", m)


def _route_identity(req_provider: str, req_model: str,
                    rep_provider: str | None, rep_model: str | None) -> str:
    """reported-match | reported-mismatch | unknown. A match is what the backend
    REPORTED — useful evidence, never cryptographic proof of the upstream model."""
    if not rep_provider or not rep_model:
        return "unknown"
    same = ((rep_provider or "").strip().lower() == (req_provider or "").strip().lower()
            and _norm_model(rep_model) == _norm_model(req_model))
    return "reported-match" if same else "reported-mismatch"


def _kill_tree(p: subprocess.Popen) -> None:
    """Kill the reviewer AND its children. subprocess.run's timeout kills only
    the direct child; hermes.exe launches a Python child that kept billing."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)],
                           capture_output=True, timeout=15)
        else:
            import signal
            os.killpg(p.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        p.kill()
    except Exception:
        pass


def _launch(cmd: list[str], timeout: int, env: dict) -> tuple[int, str, str]:
    kw: dict = {}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                         errors="replace", env=env, **kw)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        try:
            p.communicate(timeout=10)
        except Exception:
            pass
        raise
    return p.returncode, out or "", err or ""


def _parse_stream_json(stdout: str) -> tuple[str | None, dict]:
    """(final_text, result_event) from `--format stream-json` JSONL output."""
    texts: list[str] = []
    result: dict = {}
    seen = False
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if not isinstance(ev, dict):
            continue
        seen = True
        if ev.get("type") == "text" and isinstance(ev.get("text"), str):
            texts.append(ev["text"])
        elif ev.get("type") == "result":
            result = ev
    if not seen:
        return None, {}
    final = result.get("text") if isinstance(result.get("text"), str) and result.get("text") else "".join(texts)
    return final, result


def _hermes_home() -> Path:
    h = os.environ.get("HERMES_HOME", "").strip()
    if h:
        return Path(h)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


def _session_store_receipt(session_id: str | None) -> dict | None:
    """What Hermes' own session store recorded for this run (read-only):
    model, billing provider and base URL. The chat/stream-json transport has no
    --usage-file, but it returns a session_id — so large-prompt reviews get the
    same strength of identity evidence as inline ones, instead of 'unknown'."""
    if not session_id or not re.match(r"^[A-Za-z0-9_.:-]{1,128}$", str(session_id)):
        return None
    db = _hermes_home() / "state.db"
    prof = os.environ.get("HERMES_PROFILE", "").strip()
    if prof and re.match(r"^[A-Za-z0-9_-]{1,64}$", prof):
        # Profile store first whenever a profile is named — HERMES_HOME may be
        # the root (profiles/<p>/state.db) or already the profile dir itself.
        cand = _hermes_home() / "profiles" / prof / "state.db"
        db = cand if cand.is_file() else db
    if not db.is_file():
        return None
    try:
        import sqlite3
        q = "SELECT model, billing_provider, billing_base_url FROM sessions WHERE id = ?"
        row = None
        for opener in ("ro", "query_only"):
            con = None
            try:
                if opener == "ro":
                    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
                else:
                    # A WAL database whose -shm cannot be created read-only:
                    # open normally but forbid writes on this connection.
                    con = sqlite3.connect(str(db), timeout=5)
                    con.execute("PRAGMA query_only = 1")
                row = con.execute(q, (str(session_id),)).fetchone()
                break
            except sqlite3.OperationalError:
                continue
            finally:
                if con is not None:
                    con.close()
    except Exception:
        return None
    if not row:
        return None
    return {"model": row[0], "provider": row[1], "base_url": row[2]}


def _as_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# Operator-session state that must not follow the reviewer into its own run.
_SCRUB_ENV = ("HERMES_YOLO_MODE", "HERMES_RESUME", "HERMES_SESSION_ID", "HERMES_CONTINUE",
              "HERMES_SESSION_SOURCE", "HERMES_SESSION_SOURCE_EXPLICIT", "HERMES_INFERENCE_MODEL",
              "HERMES_INFERENCE_PROVIDER")


def run_reviewer(reviewer: dict, prompt: str, timeout: int, verbose: bool) -> tuple[bool, str]:
    receipt: dict = {
        "requested_provider": reviewer["provider"], "requested_model": reviewer["model"],
        "transport": None, "status": "not-started", "toolset": _reviewer_toolset(),
        "reported_provider": None, "reported_model": None, "identity": "unknown",
        "identity_source": None,
        "completed": None, "api_calls": None, "input_tokens": None, "output_tokens": None,
        "estimated_cost_usd": None, "cost_status": None, "warnings": [],
    }
    _TLS.receipt = receipt
    t0 = time.time()

    def done(ok: bool, text: str, status: str) -> tuple[bool, str]:
        receipt["status"] = status
        receipt["elapsed_s"] = round(time.time() - t0, 1)
        return ok, text

    base = _hermes_command()
    # No --max-turns on the inline path: `hermes -z` rejects the flag (verified),
    # and it is unnecessary — the toolset has zero tools, and Hermes refuses an
    # unknown toolset name outright (rc 2, "did not contain any valid toolsets")
    # rather than falling back to the full set. The receipt's api_calls is the
    # after-the-fact check.
    common = ["-m", reviewer["model"], "--provider", reviewer["provider"],
              "-t", receipt["toolset"], "--ignore-rules"]
    env = {k: v for k, v in os.environ.items() if k.upper() not in _SCRUB_ENV}
    env["HERMES_NONINTERACTIVE"] = "1"
    # Hermes writes UTF-8; make any Python child (incl. test stubs) do the same,
    # and decode as UTF-8 — the locale code page mangled em-dashes in verdicts.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    tmpdir = tempfile.mkdtemp(prefix="devpair-")  # 0700 on POSIX
    try:
        usage_path = os.path.join(tmpdir, "usage.json")
        inline = base + ["-z", prompt] + common + ["--usage-file", usage_path]
        mode = _prompt_transport()
        if mode == "inline" or (mode == "auto" and _fits_inline(inline)):
            cmd, transport = inline, "inline"
        else:
            qpath = os.path.join(tmpdir, "prompt.txt")
            fd = os.open(qpath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(prompt)
            cmd = base + ["chat", "-Q", "--query-file", qpath, "--format", "stream-json"] \
                + common + ["--max-turns", "1"]
            transport = "file"
        receipt["transport"] = transport
        if verbose:
            print(f"[devpair] invoking {reviewer['label']} ({reviewer['provider']}/{reviewer['model']}) "
                  f"with {len(prompt):,} chars via {transport} transport, toolset "
                  f"{receipt['toolset']!r}", file=sys.stderr)
        try:
            rc, out, err = _launch(cmd, timeout, env)
        except subprocess.TimeoutExpired:
            return done(False, f"reviewer timed out after {timeout}s (process tree killed)", "timeout")
        except OSError as e:
            if getattr(e, "winerror", None) == 206 or e.errno == errno.E2BIG:
                return done(False, (
                    f"the prompt ({len(prompt):,} chars) is too large for this platform's "
                    "command line — set DEVPAIR_PROMPT_TRANSPORT=file (or prompt_transport "
                    "in config.json) or narrow the evidence"), "too-large")
            if isinstance(e, FileNotFoundError):
                # `hermes` really is missing. Soft failure: the retry loop moves
                # on (and doctor reports it) rather than dying on a traceback.
                return done(False, f"the `hermes` CLI was not found on PATH (tried {cmd[0]!r}) "
                                   "— is Hermes installed?", "launch-error")
            return done(False, f"could not launch reviewer: {type(e).__name__}: {e}", "launch-error")
        finally:
            if transport == "file":
                try:
                    os.unlink(os.path.join(tmpdir, "prompt.txt"))
                except OSError:
                    pass

        out_s, err_s = out.strip(), err.strip()
        if transport == "file":
            text, result = _parse_stream_json(out_s)
            if text is None:
                text = out_s  # a backend that ignored --format; take raw text
            if result:
                tok = result.get("tokens") if isinstance(result.get("tokens"), dict) else {}
                receipt["input_tokens"] = _as_int(tok.get("input"))
                receipt["output_tokens"] = _as_int(tok.get("output"))
                if result.get("error"):
                    receipt["warnings"].append(f"backend error: {str(result['error'])[:200]}")
                code = result.get("exit_code")
                if code not in (None, 0, "0", False):
                    rc = rc or (_as_int(code) or 1)
            store = _session_store_receipt(result.get("session_id") if result else None)
            if store:
                receipt["reported_provider"] = store.get("provider")
                receipt["reported_model"] = store.get("model")
                receipt["reported_base_url"] = store.get("base_url")
                receipt["identity_source"] = "session-store"
            else:
                receipt["warnings"].append("file transport: no session record found — identity unknown")
            out_s = (text or "").strip()
        else:
            try:
                u = json.loads(Path(usage_path).read_text(encoding="utf-8"))
            except Exception:
                u = None
            if isinstance(u, dict):
                receipt.update({
                    "reported_provider": u.get("provider"), "reported_model": u.get("model"),
                    "completed": u.get("completed"), "api_calls": _as_int(u.get("api_calls")),
                    "input_tokens": _as_int(u.get("input_tokens")),
                    "output_tokens": _as_int(u.get("output_tokens")),
                    "estimated_cost_usd": u.get("estimated_cost_usd"),
                    "cost_status": u.get("cost_status"),
                    "turn_exit_reason": u.get("turn_exit_reason"),
                })
                receipt["identity_source"] = "usage-file"
                if u.get("failed") or u.get("partial") or u.get("interrupted"):
                    receipt["warnings"].append("backend reported failed/partial/interrupted")
        receipt["identity"] = _route_identity(reviewer["provider"], reviewer["model"],
                                              receipt["reported_provider"], receipt["reported_model"])
        if isinstance(receipt["api_calls"], int) and receipt["api_calls"] > 1:
            receipt["warnings"].append(
                f"reviewer made {receipt['api_calls']} model calls — a tool-less review "
                "needs 1; retries or tool use. Read-only is not independently proven.")
        if rc != 0:
            detail = err_s or out_s or f"exit {rc} with no output"
            return done(False, f"exit {rc}: {detail[:400]}", "failed")
        if not out_s or "agent failed" in out_s.lower()[:200]:
            return done(False, out_s or err_s or "no output from reviewer", "failed")
        if receipt["completed"] is False:
            return done(False, "backend reported the turn as not completed: "
                               f"{receipt.get('turn_exit_reason') or 'no reason given'}", "failed")
        return done(True, out_s, "ok")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


NON_REVIEW_MAX_CHARS = 600


def _is_non_review(mode: str, response: str) -> bool:
    """True for a verdict-bearing mode whose reply has no verdict AND is too
    short to be a review. Long verdict-less reviews are kept (the gate fails
    them closed); only obvious non-answers are treated as a failed attempt."""
    if mode == "debug":
        return False
    return not _all_verdicts(response) and len((response or "").strip()) < NON_REVIEW_MAX_CHARS


def _attempt_record(cand: dict, ok: bool, response: str) -> dict:
    """The receipt for one backend attempt. A backend wrapper that sets no
    receipt (a test stub, an old fork) yields identity "unknown" — never a
    claim about which model answered."""
    rec = dict(last_receipt() or {
        "requested_provider": cand["provider"], "requested_model": cand["model"],
        "transport": None, "status": "ok" if ok else "failed",
        "reported_provider": None, "reported_model": None, "identity": "unknown",
        "warnings": ["no backend receipt"],
    })
    if not ok:
        rec["error"] = (response or "")[:300]
    return rec


# ---------------------------------------------------------------------------
def cmd_pair(args) -> int:
    mode = args.mode
    # Resolve the session WITHOUT creating one — a --dry-run (or an early exit)
    # must not leave a stale CURRENT pointer behind.
    spath = session_path(args.session, create=False)
    sess = load_session(spath)
    if args.session and sess.get("turns") and not _same_project(sess.get("project"), project_root()):
        print(f"[devpair] WARNING: session '{spath.stem}' belongs to {sess.get('project')}, not this "
              "project — its earlier turns will be replayed here. Use a different --session "
              "if that is not what you want.", file=sys.stderr)

    _TLS.manifest = None   # never inherit a previous run's manifest on this thread
    context, notes = gather(args)
    manifest = last_manifest()
    for n in notes:
        print(f"[devpair] note: {n}", file=sys.stderr)
    # Remember what has already been printed, so the late-redaction pass below
    # reports only what IT found rather than repeating gather()'s notes.
    printed_notes = list(notes)

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
        cov, gaps = coverage_status(manifest)
        print(f"evidence : {cov}" + (f" — {len(gaps)} gap(s): " + "; ".join(gaps[:3]) if cov != "complete" else ""))
        print(f"session  : {spath.stem} (turn {len(sess.get('turns', [])) + 1})")
        cstate, _, cproblem = _cfg_state()
        if cstate == "invalid":
            print(f"config   : INVALID — a real run would be refused ({cproblem})")
        cap = daily_cap()
        if cap:
            used = runs_today()
            state = "AT CAP — a real run would be refused" if used >= cap else "ok"
            print(f"cap      : {used}/{cap} paid attempts today ({state})")
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

    prompt = build_prompt(mode, args.ask or "", context, sess, args.focus, notes, manifest=manifest)
    # Redactions found in the question/focus/history are reported here, after
    # --dry-run's free path, so the user learns what was scrubbed before a paid
    # call goes out — not silently.
    for n in notes[len(printed_notes):]:
        print(f"[devpair] note: {n}", file=sys.stderr)

    # Gate + record the paid run. Placed AFTER --dry-run (which is free and must
    # stay free) and BEFORE the first backend call, so nothing is spent without
    # a ledger entry and nothing exceeds the cap.
    authorize_ctx = len(context)
    run_id = authorize(args, reviewer, driver, authorize_ctx)

    t0 = time.time()
    ok, response, used = False, "", reviewer
    attempts: list[dict] = []
    budget = args.budget if args.budget and args.budget > 0 else None
    for i, cand in enumerate(order):
        remaining = None
        if budget is not None:
            remaining = budget - (time.time() - t0)
            if remaining <= 5:
                print(f"[devpair] wall-clock budget ({budget}s) exhausted — "
                      f"{len(order) - i} backend(s) not tried", file=sys.stderr)
                break
        if i > 0:
            # Every fallback is its own paid attempt: reserved and counted.
            reserved, why = reserve_attempt(args, cand, driver, authorize_ctx,
                                            run_id=run_id, attempt=i + 1)
            if not reserved:
                print(f"[devpair] fallback to {cand['label']} not attempted — "
                      f"{why.splitlines()[0]}", file=sys.stderr)
                break
        this_timeout = int(min(args.timeout, remaining)) if remaining else args.timeout
        _TLS.receipt = None  # a stale receipt must never be attributed to this attempt
        ok, response = run_reviewer(cand, prompt, this_timeout, args.verbose)
        used = cand
        attempts.append(_attempt_record(cand, ok, response))
        if ok and _is_non_review(mode, response):
            # A reply with no verdict that is too short to be a review (e.g. "I'll
            # verify a few claims first..." from a model that expected tools) is
            # not a review. Saving it as one would replay junk into the session.
            ok = False
            attempts[-1]["status"] = "malformed"
            attempts[-1]["error"] = f"no review produced ({len(response)} chars, no verdict)"
            response = f"{cand['label']} returned no review ({len(response)} chars, no verdict): {response[:200]}"
        record_outcome(run_id, i + 1, attempts[-1])
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

    # The reviewer cites file:line from pasted text it cannot open — verify,
    # including that the cited file was in the packet it was actually sent.
    claim_problems = verify_claims(response, os.getcwd(),
                                   packet_paths=(manifest or {}).get("paths") if manifest else None,
                                   packet_text=context if manifest else None)

    gate_fail, gate_reason, coverage = gate_decision(
        response, manifest, allow_partial=getattr(args, "allow_partial", False),
        claim_problems=claim_problems, strict_citations=getattr(args, "strict_citations", False))
    coverage_gaps = coverage_status(manifest)[1]
    manifest_summary = None if not manifest else {
        k: manifest.get(k) for k in ("complete", "gaps", "paths", "context_chars", "sha256", "total_clipped")}

    # A real review happened — now it is correct to pin the session pointer.
    project = project_root()
    pin_failed = None
    if not args.session:
        try:
            with _file_lock(str(CURRENT) + ".lock"):
                cur = _current_for(project)
                if cur:
                    if cur != spath.stem and not spath.is_file():
                        # Another run in THIS project pinned a session while we were
                        # reviewing — join it rather than orphan a file nobody points at.
                        spath = _contained_session(cur)
                else:
                    if spath.exists() or spath.stem in active_session_names():
                        # Our provisional name was taken (by another project) during
                        # the review. Never share it: allocate a fresh one.
                        spath = SESSIONS / f"{_new_session_name()}.json"
                    _set_current(project, spath.stem)
        except LockTimeout as e:
            pin_failed = str(e)   # paid already: rescue the turn below, never crash

    # Stored state is redacted too: outbound redaction alone left a credential
    # typed into --ask/--focus sitting in the session JSON on disk.
    turn = {
        "at": _now(),
        "mode": mode,
        "ask": redact_secrets(args.ask or "")[0],
        "focus": redact_secrets(args.focus or "")[0],
        "reviewer": f"{used['provider']}/{used['model']}",
        "driver": f"{driver['provider']}/{driver['model']}",
        "context_chars": len(context),
        "elapsed_s": round(elapsed, 1),
        "tokens_in_est": tokens_in,
        "tokens_out_est": tokens_out,
        "verdict": parse_verdict(response),
        "blockers": count_blockers(response),
        "unverified_claims": claim_problems,
        "coverage": coverage,
        "coverage_gaps": coverage_gaps,
        "evidence": manifest_summary,
        "independence": (("same-family" if used.get("same_family_as_driver")
                          else "unverified" if used.get("unverifiable")
                          else "verified")),
        "route": attempts[-1] if attempts else None,
        "attempts": attempts,
        "response": redact_secrets(response)[0],
    }
    sess = (_rescue_turn(spath, turn, project, pin_failed) if pin_failed
            else append_turn(spath, turn, project))

    rt0 = attempts[-1] if attempts else {}
    if rt0.get("identity") == "reported-mismatch":
        # Always on stderr — a --json consumer must not be able to miss it.
        print(f"[devpair] ROUTE MISMATCH: requested {rt0.get('requested_provider')}/"
              f"{rt0.get('requested_model')}, backend reported {rt0.get('reported_provider')}/"
              f"{rt0.get('reported_model')}", file=sys.stderr)

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
            "coverage": coverage,
            "coverage_gaps": coverage_gaps,
            "evidence": manifest_summary,
            "independence": ("same-family" if used.get("same_family_as_driver")
                             else "unverified" if used.get("unverifiable")
                             else "verified"),
            "gate_failed": gate_fail,
            "gate_reason": gate_reason,
            "route": attempts[-1] if attempts else None,
            "attempts": attempts,
            "response": response,
        }, indent=2))
    else:
        bar = "─" * 66
        print(f"\n{bar}")
        print(f"  DEV PAIR · {mode.upper()} · reviewed by {used['label']}")
        print(f"  driver: {driver['model']}   session: {spath.stem} (turn {len(sess['turns'])})   {elapsed:.0f}s")
        print(f"  ~{tokens_in:,} tokens in / ~{tokens_out:,} out")
        rt = attempts[-1] if attempts else {}
        if rt.get("identity") == "reported-match":
            print(f"  route: backend reported {rt.get('reported_provider')}/{rt.get('reported_model')} "
                  f"(matches request; {rt.get('transport')} transport)")
        elif rt.get("identity") == "reported-mismatch":
            print(f"  ROUTE MISMATCH: requested {rt.get('requested_provider')}/{rt.get('requested_model')}, "
                  f"backend reported {rt.get('reported_provider')}/{rt.get('reported_model')}")
        else:
            print("  route: backend did not report which model answered (identity unknown)")
        for w in rt.get("warnings") or []:
            print(f"  WARNING: {w}")
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
        if coverage != "complete":
            print(f"  EVIDENCE {coverage.upper()} — the reviewer did not see everything in scope:")
            for g in coverage_gaps[:8]:
                print(f"    · {g}")
            print("  An approval here covers only what was sent.")
            print(bar)
        print(f"  reply with: devpair followup --ask \"...\"")
        print(bar)

    if args.gate and gate_fail:
        print(f"\n[devpair] GATE FAILED — {gate_reason}", file=sys.stderr)
        return 2
    if args.gate and coverage == "partial":
        print(f"\n[devpair] GATE PASSED (PARTIAL) — {gate_reason}", file=sys.stderr)
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
    try:
        with _file_lock(str(CURRENT) + ".lock"):
            stamp = _new_session_name()
            _set_current(project_root(), stamp)
    except LockTimeout as e:
        print(f"devpair: could not reset — the session pointer is locked ({e}).", file=sys.stderr)
        return 1
    print(f"devpair: new pairing session {stamp} (for this project)")
    return 0


def cmd_doctor(args) -> int:
    """Static by default: zero model calls. `--live` probes each backend, and
    every probe is a reserved, counted, attested paid attempt — the old doctor
    fanned out to every reviewer in parallel with no cap and no ledger entry."""
    driver = driver_identity(getattr(args, "driver", None))
    print(f"driver (being supervised): {driver['provider']}/{driver['model']}  family={driver['family']}")
    if driver["family"] == "unknown":
        print("  WARNING: driver family unidentified — independence cannot be proven.")
        print("  Pass --driver PROVIDER/MODEL for an accurate same-family column.")
    print(f"state: {BASE}")
    rc = 0
    cstate, _, cproblem = _cfg_state()
    if cstate == "invalid":
        print(f"config: INVALID — every paid run will be refused: {cproblem}")
        rc = 1
    else:
        print(f"config: {cstate}" + (f" (daily cap {daily_cap()}/day)" if daily_cap() else ""))
    cmd = _hermes_command()
    found = shutil.which(cmd[0]) or (cmd[0] if Path(cmd[0]).exists() else None)
    print(f"backend command: {' '.join(cmd)}" + ("" if found else "   <-- NOT FOUND"))
    if not found:
        rc = 1
    print(f"reviewer toolset: {_reviewer_toolset()!r} (must resolve to ZERO tools; "
          "`-t \"\"` would load the full CLI toolset)")
    print(f"prompt transport: {_prompt_transport()}\n")

    live = bool(getattr(args, "live", False))
    print(f"{'reviewer':<10} {'provider/model':<34} {'family':<8} status")
    print("-" * 78)
    if not live:
        for key, r in REVIEWERS.items():
            same = " (SAME FAMILY AS DRIVER — not independent)" if r["family"] == driver["family"] else ""
            print(f"{key:<10} {r['provider'] + '/' + r['model']:<34} {r['family']:<8} "
                  f"not probed{same}")
        print("\nStatic check only — no model was called. `devpair doctor --live "
              "--requested-by user` probes each backend (one paid attempt per reviewer).")
        return rc

    args.mode = "doctor"
    run_id = _new_run_id()
    reserved: list[tuple[str, dict, int]] = []
    skipped: list[tuple[str, dict, str]] = []
    for n, (key, r) in enumerate(REVIEWERS.items(), 1):
        ok, why = reserve_attempt(args, r, driver, 0, run_id=run_id, attempt=n)
        if ok:
            reserved.append((key, r, n))
        else:
            skipped.append((key, r, why.splitlines()[0]))

    def _probe(item):
        key, r, n = item
        # Small local reasoning models emit a long trace even for a trivial
        # probe (~2min), so they get a longer leash than hosted backends.
        probe_timeout = 300 if r["provider"].startswith("lmstudio") else 90
        _TLS.receipt = None
        ok, out = run_reviewer(r, "Reply with exactly: OK", probe_timeout, False)
        return key, r, ok, out, _attempt_record(r, ok, out), n

    # Probed in parallel: serially this is 4 x up-to-300s of dead waiting.
    from concurrent.futures import ThreadPoolExecutor

    results = []
    if reserved:
        with ThreadPoolExecutor(max_workers=max(1, len(reserved))) as pool:
            results = list(pool.map(_probe, reserved))
    # Outcomes are written from THIS thread, after the pool: on Windows
    # msvcrt.locking retries only once per second, so threads finishing together
    # and contending for the ledger lock serialised the whole doctor run.
    for _key, _r, _ok, _out, rec, n in results:
        record_outcome(run_id, n, rec)

    any_ok = False
    for key, r, ok, out, rec, _n in results:
        same = " (SAME FAMILY AS DRIVER — not independent)" if r["family"] == driver["family"] else ""
        status = "OK" if ok and "OK" in out.upper()[:40] else f"FAIL: {out[:60]}"
        if ok:
            any_ok = True
            status += f" [route {rec.get('identity')}]"
        print(f"{key:<10} {r['provider'] + '/' + r['model']:<34} {r['family']:<8} {status}{same}")
    for key, r, why in skipped:
        print(f"{key:<10} {r['provider'] + '/' + r['model']:<34} {r['family']:<8} NOT PROBED: {why}")
    if not any_ok:
        print("\nNo reviewer backend answered a live probe — devpair cannot run.")
        rc = 1
    return rc


def cmd_audit(args) -> int:
    """Who has been spending your tokens, and did anyone claim you asked?

    This is the accountability half of the manual-invocation policy: the skill
    tells an agent not to self-initiate, and this shows whether it obeyed.
    """
    recs = read_ledger(days=args.days)
    outcomes = {(r.get("run_id"), r.get("attempt")): r for r in recs if r.get("kind") == "outcome"}
    recs = [r for r in recs if r.get("kind") != "outcome"]
    if not recs:
        where = "no runs recorded" if LEDGER.is_file() else f"no ledger yet at {LEDGER}"
        print(f"devpair: {where}"
              + (f" in the last {args.days}d." if args.days else "."))
        return 0

    if args.json:
        for r in recs:
            o = outcomes.get((r.get("run_id"), r.get("attempt")))
            if o:
                r["outcome"] = {k: v for k, v in o.items() if k not in ("kind", "run_id", "attempt", "day", "epoch")}
        print(json.dumps({"days": args.days, "count": len(recs),
                          "runs_today": runs_today(), "daily_cap": daily_cap(),
                          "runs": recs}, indent=2))
        return 0

    print(f"{'when':<22} {'mode':<9} {'requested by':<14} {'reviewer':<30} {'outcome':<14} ctx")
    print("─" * 100)
    for r in recs:
        o = outcomes.get((r.get("run_id"), r.get("attempt"))) or {}
        oc = o.get("status") or ("—" if r.get("kind") == "attempt" else "(legacy)")
        if o.get("identity") == "reported-mismatch":
            oc += " MISMATCH"
        print(f"{r.get('at','?')[:19]:<22} {r.get('mode','?'):<9} "
              f"{r.get('requested_by','?')[:13]:<14} {r.get('reviewer','?')[:29]:<30} "
              f"{oc[:13]:<14} {r.get('context_chars',0):,}")

    unattributed = [r for r in recs if r.get("requested_by") in ("", "unattributed", None)]
    cap = daily_cap()
    state, _c, problem = _cfg_state()
    print("─" * 100)
    print(f"{len(recs)} paid attempt(s)"
          + (f" in the last {args.days}d" if args.days else "")
          + f"; {runs_today()} today"
          + (f" — CONFIG INVALID, every paid run is being refused ({problem})" if state == "invalid"
             else f" of a {cap}/day cap" if cap else " (no daily cap set)"))
    if unattributed:
        print(f"\n  {len(unattributed)} run(s) named nobody as the requester.")
        print("  Unattributed runs are the ones to check — the skill forbids an")
        print("  agent from self-initiating, and this is where that would show.")
    return 0


def _mtime(p: Path) -> float | None:
    try:
        return p.stat().st_mtime
    except OSError:  # deleted concurrently
        return None


def cmd_prune(args) -> int:
    """Housekeeping: sessions — and their lock/tmp/quarantine/rescue sidecars —
    accumulate forever otherwise. --redact rewrites every kept session through
    the redactor (legacy sessions stored --ask/--focus verbatim)."""
    if not SESSIONS.is_dir():
        print("devpair: no sessions to prune.")
        return 0
    cutoff = time.time() - (args.days * 86400)
    active = active_session_names()
    files = [(p, m) for p in SESSIONS.glob("*.json")
             if ".turn-" not in p.name and (m := _mtime(p)) is not None]
    files.sort(key=lambda x: x[1])
    doomed = [p for p, m in files if m < cutoff and p.stem not in active]
    doomed_names = {p.name for p in doomed}

    def _sidecar_ok(p: Path) -> bool:
        if p.name.endswith(".json.lock"):
            # A lock is never aged out on its own: it is opened, never written, so
            # its mtime is its creation time. Unlinking a lock a live holder owns
            # lets the next writer lock a NEW inode — two "locked" writers.
            owner = p.name[: -len(".lock")]
            return owner in doomed_names or not (SESSIONS / owner).exists()
        return True

    side = [p for pat in ("*.json.lock", "*.json.tmp-*", "*.json.corrupt-*", "*.turn-*.json")
            for p in SESSIONS.glob(pat)
            if (m := _mtime(p)) is not None and m < cutoff and p not in doomed and _sidecar_ok(p)]
    for p in doomed + side:
        if args.dry_run:
            print(f"would delete {p.name}")
        else:
            try:
                p.unlink()
                print(f"deleted {p.name}")
            except OSError as e:
                print(f"could not delete {p.name}: {e}")
    if getattr(args, "redact", False):
        changed = 0
        for p, _m in files:
            if p in doomed or not p.exists():
                continue
            try:
                with _file_lock(str(p) + ".lock"):
                    raw = p.read_text(encoding="utf-8")
                    try:
                        if not isinstance(json.loads(raw), dict):
                            raise ValueError("not a session object")
                    except ValueError:
                        print(f"skipped {p.name}: unparseable — not rewritten (would lose content)")
                        continue
                    data = load_session(p, quarantine=False)
                    if redact_secrets(raw)[1]:
                        if not args.dry_run:
                            save_session(p, data)
                        changed += 1
            except (OSError, LockTimeout) as e:
                print(f"could not redact {p.name}: {e}")
        print(f"devpair: {'would redact' if args.dry_run else 'redacted'} {changed} stored session(s).")
    verb = "would free" if args.dry_run else "freed"
    print(f"devpair: {verb} {len(doomed)} session(s) and {len(side)} sidecar file(s) older than "
          f"{args.days}d; {len(files) - len(doomed)} session(s) kept (active sessions never pruned).")
    return 0


def _force_utf8_output() -> None:
    """Make stdout/stderr UTF-8 wherever Python let the console choose.

    Windows consoles default to a legacy code page (cp1252 here), which cannot
    encode the box-drawing characters used in every banner. The failure mode was
    the worst kind: the reviewer answered, the paid call was already spent and
    ledgered, and THEN devpair died with a UnicodeEncodeError while printing the
    result — so the user paid for a review they never saw. Replacing unencodable
    characters is strictly better than losing the report.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            # Python < 3.7, or a stream that is not a TextIOWrapper (pytest
            # capture, a pipe wrapper). Never fatal: this is cosmetic.
            pass


def main() -> int:
    _force_utf8_output()
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
              verify     post-hoc six-pass critique of finished work (verify-results)

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

    for mode in ("critique", "review", "debug", "alt", "followup", "verify"):
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
                            "if any [BLOCKER] is found, if the verdict cannot be parsed, or if "
                            "an approval rests on evidence the harness clipped or left out "
                            "(fails closed). Default: advisory, always exit 0.")
        p.add_argument("--allow-partial", dest="allow_partial", action="store_true",
                       help="with --gate: accept an approval on PARTIAL evidence (clipped or "
                            "omitted sections). The result is labelled PARTIAL, never complete.")
        p.add_argument("--strict-citations", dest="strict_citations", action="store_true",
                       help="with --gate: fail when the reviewer cites a file:line that does not "
                            "exist or was not in the evidence sent (default: advisory).")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        p.add_argument("--dry-run", action="store_true", help="show who would review and why, without calling them")
        p.add_argument("--verbose", "-v", action="store_true")

    pl = sub.add_parser("log", help="what the pair has said this session")
    pl.set_defaults(func=cmd_log)
    pl.add_argument("--session", "-s")
    pl.add_argument("--full", action="store_true")

    pr = sub.add_parser("reset", help="start a fresh pairing session")
    pr.set_defaults(func=cmd_reset)

    pd = sub.add_parser("doctor", help="check reviewer setup (static; --live probes backends)")
    pd.set_defaults(func=cmd_doctor)
    pd.add_argument("--driver", metavar="[PROVIDER/]MODEL",
                    help="the live session model, for an accurate same-family column")
    pd.add_argument("--live", action="store_true",
                    help="actually call each reviewer (one PAID, capped, ledgered attempt each)")
    pd.add_argument("--requested-by", dest="requested_by", metavar="WHO",
                    help="who asked for the live probe (required when attestation is enforced)")

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
    pp.add_argument("--redact", action="store_true",
                    help="also rewrite every kept session through the secret redactor "
                         "(one-time cleanup for sessions saved before redaction-at-rest)")

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
