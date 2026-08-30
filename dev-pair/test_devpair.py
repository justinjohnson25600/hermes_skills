#!/usr/bin/env python3.11
"""Regression tests for devpair. Pins the defects the pair found.

Run: python3.11 test_devpair.py   (or: python3.11 -m pytest test_devpair.py)
No network: every test targets selection, side-effect, and error-propagation
logic. The one reviewer-invocation test uses a deliberately invalid provider.
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import devpair  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))


def isolated(fn):
    """Run fn with devpair's state redirected into a temp dir."""
    def wrapper():
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            orig = (devpair.BASE, devpair.SESSIONS, devpair.CONFIG,
                    devpair.CURRENT, devpair.LEDGER)
            devpair.BASE = base
            devpair.SESSIONS = base / "sessions"
            devpair.CONFIG = base / "config.json"
            devpair.CURRENT = base / "current_session"
            # Without this the ledger tests would append to the REAL Hermes
            # home and pollute the user's audit trail.
            devpair.LEDGER = base / "invocations.jsonl"
            try:
                fn(base)
            finally:
                (devpair.BASE, devpair.SESSIONS, devpair.CONFIG,
                 devpair.CURRENT, devpair.LEDGER) = orig
    return wrapper


def set_driver(model, provider="zai"):
    os.environ["DEVPAIR_DRIVER_MODEL"] = model
    os.environ["DEVPAIR_DRIVER_PROVIDER"] = provider


# --- selection -------------------------------------------------------------
@isolated
def test_never_self_reviews(base):
    print("\n[selection] never lets a model peer-review itself")
    devpair.CONFIG.write_text(json.dumps({"order": ["claude"]}))
    set_driver("claude-sonnet-4.6", "anthropic")
    r = devpair.pick_reviewer(None)
    check("claude driver + order=[claude] -> non-claude reviewer",
          r["family"] != "claude", f"got {r['family']}")

    set_driver("glm-5.3", "zai")
    devpair.CONFIG.write_text(json.dumps({"order": ["glm"]}))
    r = devpair.pick_reviewer(None)
    check("glm driver + order=[glm] -> non-glm reviewer",
          r["family"] != "glm", f"got {r['family']}")


@isolated
def test_refuses_when_no_independent(base):
    print("\n[selection] refuses rather than silently self-reviewing")
    saved = dict(devpair.REVIEWERS)
    devpair.REVIEWERS.clear()
    devpair.REVIEWERS["claude"] = dict(saved["claude"])
    set_driver("claude-sonnet-4.6", "anthropic")
    try:
        devpair.pick_reviewer(None)
        check("all-same-family -> SystemExit", False, "returned a self-reviewer")
    except SystemExit as e:
        check("all-same-family -> SystemExit", "no independent reviewer" in str(e))
        check("refusal names why each was skipped", "same family as driver" in str(e))
    finally:
        devpair.REVIEWERS.clear()
        devpair.REVIEWERS.update(saved)


@isolated
def test_explicit_override_allowed(base):
    print("\n[selection] --reviewer is a deliberate override, still flagged")
    set_driver("claude-sonnet-4.6", "anthropic")
    r = devpair.pick_reviewer("claude")
    check("forced same-family returns", r["key"] == "claude")
    check("forced same-family sets warning flag", r["same_family_as_driver"] is True)
    try:
        devpair.pick_reviewer("nonexistent")
        check("unknown reviewer -> SystemExit", False)
    except SystemExit:
        check("unknown reviewer -> SystemExit", True)


@isolated
def test_empty_order_falls_back(base):
    print("\n[selection] empty config order is safe (no IndexError)")
    devpair.CONFIG.write_text(json.dumps({"order": []}))
    set_driver("glm-5.3", "zai")
    try:
        r = devpair.pick_reviewer(None)
        check("order=[] falls back to DEFAULT_ORDER", r["family"] != "glm")
    except IndexError as e:
        check("order=[] falls back to DEFAULT_ORDER", False, f"IndexError: {e}")


@isolated
def test_candidates_shared_between_pick_and_retry(base):
    print("\n[selection] retry list covers ALL independent reviewers")
    devpair.CONFIG.write_text(json.dumps({"order": ["kimi"]}))
    set_driver("glm-5.3", "zai")
    cands = devpair.reviewer_candidates(None)
    fams = [c["family"] for c in cands]
    check("narrow order still yields >1 candidate", len(cands) > 1, f"got {fams}")
    check("first honours config order", cands[0]["key"] == "kimi", f"got {cands[0]['key']}")
    check("no driver-family candidate in retry list", "glm" not in fams, f"got {fams}")


# --- side effects ----------------------------------------------------------
@isolated
def test_session_path_no_side_effect(base):
    print("\n[side effects] resolving a session never invents one")
    p = devpair.session_path(None, create=False)
    check("create=False leaves CURRENT absent", not devpair.CURRENT.is_file())
    check("still returns a usable path", p.suffix == ".json")
    devpair.session_path(None, create=True)
    check("create=True writes CURRENT", devpair.CURRENT.is_file())


@isolated
def test_dry_run_creates_nothing(base):
    print("\n[side effects] --dry-run leaves no state behind")
    set_driver("glm-5.3", "zai")
    args = argparse.Namespace(
        mode="review", session=None, ask="", focus=None, diff=False, diff_ref=None,
        files=None, plan=None, error=None, cmd=None, reviewer=None, driver=None,
        timeout=10, json=False, dry_run=True, verbose=False,
    )
    rc = devpair.cmd_pair(args)
    check("dry-run exits 0", rc == 0)
    check("no CURRENT pointer created", not devpair.CURRENT.is_file())
    sessions = list(devpair.SESSIONS.glob("*.json")) if devpair.SESSIONS.exists() else []
    check("no session file created", not sessions, f"got {sessions}")


# --- error propagation -----------------------------------------------------
@isolated
def test_sh_surfaces_failure(base):
    print("\n[errors] context commands never fail silently")
    out, note = devpair.sh(["bash", "-lc", "printf out; printf BOOM >&2; exit 7"], want_status=True)
    check("stdout still captured", out == "out", f"got {out!r}")
    check("non-zero exit reported", "exit 7" in note, f"got {note!r}")
    check("stderr included in note", "BOOM" in note, f"got {note!r}")
    out2, note2 = devpair.sh(["bash", "-lc", "echo fine"], want_status=True)
    check("success -> empty note", note2 == "" and out2 == "fine")
    check("legacy single-return form still works",
          devpair.sh(["bash", "-lc", "echo x"]) == "x")


@isolated
def test_bad_diff_ref_not_reported_as_no_diff(base):
    print("\n[errors] a bad --diff-ref is not disguised as 'no diff'")
    with tempfile.TemporaryDirectory() as repo:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        cwd = os.getcwd()
        os.chdir(repo)
        try:
            args = argparse.Namespace(
                diff=False, diff_ref="no-such-ref-xyz", files=None, plan=None,
                error=None, cmd=None,
            )
            _, notes = devpair.gather(args)
            joined = " ".join(notes)
            check("failure surfaced to user", "failed" in joined, f"notes={notes}")
            check("not mislabelled 'no diff found'", "no diff found" not in joined, f"notes={notes}")
        finally:
            os.chdir(cwd)


@isolated
def test_run_reviewer_reports_exit_code(base):
    print("\n[errors] reviewer subprocess failure surfaces the real error")
    ok, msg = devpair.run_reviewer(
        {"model": "no-such-model", "provider": "definitely-not-a-provider", "label": "x"},
        "hi", 60, False,
    )
    check("failure reported as not-ok", ok is False)
    check("message carries exit code", "exit" in msg.lower(), f"got {msg[:80]}")
    check("message is non-empty", len(msg.strip()) > 10, f"got {msg!r}")


# --- context handling ------------------------------------------------------
@isolated
def test_clip_omitted_count_accurate(base):
    print("\n[context] truncation reports the true omitted count")
    text = "x" * 1000
    out = devpair.clip(text, 100, "t")
    head_n, tail_n = int(100 * 0.7), int(100 * 0.25)
    true_omitted = 1000 - head_n - tail_n
    check(f"reports {true_omitted}, not 900", f"{true_omitted} chars omitted" in out, out[70:130])
    body = out.replace("x", "")
    check("marker present", "truncated" in body)
    check("short text untouched", devpair.clip("abc", 100) == "abc")


@isolated
def test_reviewer_gets_no_tools(base):
    print("\n[safety] reviewer is launched read-only (no toolset)")
    import inspect
    src = inspect.getsource(devpair.run_reviewer)
    check("passes -t '' to disable all tools", '"-t", ""' in src)
    check("no shell=True in reviewer invocation", "shell=True" not in src)


# --- driver identity (fix: same-family guard must use the LIVE model) -------
@isolated
def test_driver_flag_overrides_config_and_env(base):
    print("\n[driver] explicit --driver beats env vars and config default")
    set_driver("glm-5.3", "zai")  # env says glm
    d = devpair.driver_identity("kimi-coding/kimi-k3")
    check("provider/model parsed from PROVIDER/MODEL",
          d["provider"] == "kimi-coding" and d["model"] == "kimi-k3", f"got {d}")
    check("family derived from explicit model", d["family"] == "kimi", f"got {d['family']}")
    d2 = devpair.driver_identity("claude-opus-5")
    check("bare MODEL keeps env provider", d2["provider"] == "zai", f"got {d2}")
    check("bare MODEL sets family", d2["family"] == "claude", f"got {d2['family']}")


@isolated
def test_same_family_guard_uses_explicit_driver(base):
    print("\n[driver] the live hole: config says glm, session runs kimi -> kimi excluded")
    set_driver("glm-5.3", "zai")  # config/env default driver is glm
    cands = devpair.reviewer_candidates(None, "kimi-coding/kimi-k3")
    fams = [c["family"] for c in cands]
    check("kimi NOT offered when the real driver is kimi", "kimi" not in fams, f"got {fams}")
    check("other independents still offered", "claude" in fams, f"got {fams}")
    cands2 = devpair.reviewer_candidates(None)  # no explicit -> env driver (glm)
    check("without --driver, kimi IS allowed (driver is glm)",
          "kimi" in [c["family"] for c in cands2])


# --- followup against an empty session --------------------------------------
@isolated
def test_followup_empty_session_warns(base):
    print("\n[followup] warns instead of silently behaving like critique")
    import contextlib, io
    set_driver("glm-5.3", "zai")
    args = argparse.Namespace(
        mode="followup", session=None, ask="I fixed it", focus=None, diff=False,
        diff_ref=None, files=None, plan=None, error=None, cmd=None, reviewer=None,
        driver=None, timeout=10, json=False, dry_run=True, verbose=False,
    )
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        rc = devpair.cmd_pair(args)
    check("dry-run followup still exits 0", rc == 0)
    check("warns about missing prior turns", "no earlier turns" in buf.getvalue(),
          f"stderr={buf.getvalue()[:120]}")


# --- atomic session writes ---------------------------------------------------
@isolated
def test_save_session_atomic_no_litter(base):
    print("\n[sessions] save is atomic and leaves no tmp files")
    p = base / "sessions" / "s1.json"
    devpair.save_session(p, {"turns": [{"mode": "review"}]})
    devpair.save_session(p, {"turns": [{"mode": "review"}, {"mode": "followup"}]})
    data = json.loads(p.read_text())
    check("second save intact", len(data["turns"]) == 2)
    litter = list((base / "sessions").glob("*.tmp-*"))
    check("no tmp files left behind", not litter, f"got {litter}")


# --- merge-base diff semantics ------------------------------------------------
@isolated
def test_diff_ref_uses_merge_base(base):
    print("\n[diff] --diff-ref shows THIS branch's changes, not the ref's")
    with tempfile.TemporaryDirectory() as repo:
        def git(*a, **kw):
            subprocess.run(["git", *a], cwd=repo, check=True,
                           capture_output=True, **kw)
        git("init", "-q", "-b", "main")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base")
        (Path(repo) / "feature.py").write_text("FEATURE = 1\n")
        git("add", ".")
        git("checkout", "-q", "-b", "feature")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "feature work")
        git("checkout", "-q", "main")
        (Path(repo) / "unrelated.py").write_text("UNRELATED = 1\n")
        git("add", ".")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "main moved on")
        git("checkout", "-q", "feature")
        (Path(repo) / "wip.py").write_text("WIP = 1\n")  # uncommitted, untracked
        (Path(repo) / "feature.py").write_text("FEATURE = 2\n")  # uncommitted, tracked
        cwd = os.getcwd()
        os.chdir(repo)
        try:
            args = argparse.Namespace(diff=False, diff_ref="main", files=None,
                                      plan=None, error=None, cmd=None)
            ctx, notes = devpair.gather(args)
            check("feature change IS in the diff", "FEATURE = 1" in ctx, ctx[:200])
            check("main's unrelated move is NOT", "UNRELATED" not in ctx)
            check("uncommitted tracked change captured", "FEATURE = 2" in ctx)
            check("uncommitted section labelled", "UNCOMMITTED CHANGES" in ctx)
            check("untracked file still listed", "wip.py" in ctx)
            check("no false failure notes", not notes, f"notes={notes}")
        finally:
            os.chdir(cwd)


# --- argparse collision (subcommand dest vs --cmd) ----------------------------
def test_no_phantom_cmd_from_subcommand():
    print("\n[argparse] subcommand selection never leaks into --cmd")
    # The subparser dest used to be 'cmd' with set_defaults(cmd="pair"), so
    # every run without -c executed a phantom `bash -lc pair`. Pin it via the
    # real CLI: a dry-run must not produce a 'pair failed' note.
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(
            [sys.executable, str(Path(devpair.__file__)), "review",
             "--driver", "kimi-coding/kimi-k3", "--dry-run"],
            capture_output=True, text=True, cwd=td, timeout=60,
        )
    check("dry-run exits 0", r.returncode == 0, r.stderr[:200])
    check("no phantom `pair` context command", "`pair` failed" not in r.stderr,
          r.stderr[:200])
    check("dry-run prints reviewer choice", "reviewer :" in r.stdout, r.stdout[:200])


# --- SECRETS: nothing credential-shaped may reach a third-party API ----------
@isolated
def test_secrets_never_reach_the_prompt(base):
    print("\n[secrets] credentials are redacted before leaving the machine")
    with tempfile.TemporaryDirectory() as repo:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True,
                       capture_output=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-q", "--allow-empty", "-m", "base"],
                       cwd=repo, check=True, capture_output=True)
        (Path(repo) / ".env").write_text(
            "OPENAI_API_KEY=sk-proj-REALSECRETVALUE123456789\n"
            "DATABASE_URL=postgres://admin:hunter2@prod.db/main\n"
            "GITHUB_TOKEN=ghp_LIVETOKEN9999999999999999\n"
            "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
            "DEBUG=true\n"
        )
        cwd = os.getcwd()
        os.chdir(repo)
        try:
            args = argparse.Namespace(diff=True, diff_ref=None, files=None,
                                      plan=None, error=None, cmd=None)
            ctx, notes = devpair.gather(args)
        finally:
            os.chdir(cwd)
    for probe, label in (
        ("sk-proj-REALSECRETVALUE", "openai key"),
        ("hunter2", "db password"),
        ("ghp_LIVETOKEN", "github token"),
        ("AKIAIOSFODNN7EXAMPLE", "aws key id"),
    ):
        check(f"{label} NOT in outbound context", probe not in ctx,
              "LEAKED — this goes to a third-party API")
    check("redaction is reported to the user",
          any("redacted" in n for n in notes), f"notes={notes}")
    check("non-secret values survive", "DEBUG" in ctx)
    check("key NAMES survive so the reviewer can still reason",
          "OPENAI_API_KEY" in ctx)


@isolated
def test_ask_focus_and_history_are_redacted_too(base):
    print("\n[secrets] --ask/--focus/replayed history are redacted, not just gathered evidence")
    # GPT-5.6 Terra found this: redact_secrets() ran only inside gather(), so the
    # OTHER four blocks build_prompt assembles — ask, focus, and up to four
    # replayed prior turns — reached the third-party API unscrubbed. The replay
    # path is the nasty one: a reviewer that quoted a credential back at you in
    # turn 1 re-sent it verbatim on every later turn of the session.
    # Literals are assembled from parts so no scanner trips on this file.
    key = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2m3"
    tok = "ghp_" + "9zYxWvUtSrQpOnMlKjIhGfEdCbA0"
    pw = "postgres://admin:" + "h4nter2secret" + "@prod.db/main"
    aws = "AKIA" + "IOSFODNN7EXAMPLE"

    sess = {"turns": [{
        "mode": "review", "at": "2026-08-30",
        "ask": f"here is the token {tok}",
        "response": f"Your config has {pw} hard-coded on line 4.",
    }]}
    prompt = devpair.build_prompt(
        "verify", f"is {key} safe to commit?", "some clean evidence",
        sess, f"the {aws} credential path",
    )
    for probe, where in ((key, "--ask"), (aws, "--focus"),
                         (tok, "replayed prior ask"), (pw, "replayed prior response")):
        check(f"secret in {where} is redacted", probe not in prompt,
              "LEAKED — this string is posted to a third-party API")

    # Redaction must not eat the prompt around it, or reviews become unreadable.
    check("the question itself survives", "safe to commit?" in prompt)
    check("the role block survives", "independent verifier" in prompt)
    check("the output shape survives", "PASS 6" in prompt)
    check("prior-turn framing survives", "ALREADY SAID THIS SESSION" in prompt)

    # And the caller must be TOLD, or a silent redaction looks like clean input.
    notes = []
    devpair.build_prompt("review", f"token {tok}", "", {}, None, notes)
    check("late redaction is reported to the caller",
          any("redact" in n.lower() for n in notes), f"notes={notes}")

    # Clean input must not manufacture a note.
    quiet = []
    devpair.build_prompt("review", "no secrets here", "plain code", {}, None, quiet)
    check("clean prompt produces no redaction note", quiet == [], f"got {quiet}")


def test_prompt_templates_survive_the_redactor():
    print("\n[secrets] redacting the whole prompt must not corrupt devpair's own templates")
    # Redacting late means the ROLE/SHAPES text passes through the redactor on
    # every run. devpair's own docs were once mangled by exactly this (the
    # auth-header pattern matching prose ABOUT auth headers), so pin it.
    for name, text in ([("ROLE", devpair.ROLE), ("VERIFY_ROLE", devpair.VERIFY_ROLE)]
                       + [(f"SHAPES[{k}]", v) for k, v in devpair.SHAPES.items()]):
        _, n = devpair.redact_secrets(text)
        check(f"{name} is not self-redacted", n == 0, f"{n} false positives")


def test_redact_secrets_unit():
    print("\n[secrets] redactor: shapes, placeholders, and value-only replacement")
    cases = [
        ("token = sk-abcdefghij1234567890", "sk-abcdefghij"),
        ("Authorization: Bearer abcdef1234567890", "abcdef1234567890"),
        ("url = mysql://root:s3cr3tpw@db:3306/x", "s3cr3tpw"),
        ('{"client_secret": "GOCSPX-abcdefghijklmnop"}', "GOCSPX-abcdefghijklmnop"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIEow==\n-----END RSA PRIVATE KEY-----",
         "MIIEow=="),
    ]
    for text, secret in cases:
        out, n = devpair.redact_secrets(text)
        check(f"redacts {secret[:18]!r}", secret not in out and n > 0, f"got {out!r}")
    # Must NOT destroy placeholders — that would make reviews of config
    # templates useless and train users to distrust the redactor.
    keep, n = devpair.redact_secrets("API_KEY=<your-key-here>\nPASSWORD=changeme")
    check("leaves obvious placeholders alone", "<your-key-here>" in keep, f"got {keep!r}")
    clean, n2 = devpair.redact_secrets("def add(a, b):\n    return a + b\n")
    check("ordinary code is untouched", n2 == 0 and "return a + b" in clean)


# --- same-family guard must FAIL CLOSED --------------------------------------
@isolated
def test_unknown_family_fails_closed(base):
    print("\n[selection] an unidentifiable driver refuses instead of faking independence")
    set_driver("my-custom-alias", "some-unknown-gateway")
    try:
        devpair.reviewer_candidates(None)
        check("unknown driver family -> SystemExit", False,
              "offered reviewers as 'independent' without proof")
    except SystemExit as e:
        check("unknown driver family -> SystemExit", True)
        check("refusal explains the fix", "--driver" in str(e), f"got {str(e)[:120]}")


@isolated
def test_family_inferred_from_provider(base):
    print("\n[selection] an opaque model name still resolves via its provider")
    set_driver("my-fast-coder", "anthropic")
    d = devpair.driver_identity()
    check("anthropic provider -> claude family", d["family"] == "claude", f"got {d}")
    cands = devpair.reviewer_candidates(None)
    fams = [c["family"] for c in cands]
    check("claude NOT offered to review a claude-backed alias", "claude" not in fams,
          f"got {fams}")
    check("independent reviewers still offered", len(cands) >= 2, f"got {fams}")
    for prov, fam in (("kimi-coding", "kimi"), ("zai", "glm"),
                      ("openai", "gpt"), ("mystery-gw", "unknown")):
        set_driver("opaque-name", prov)
        check(f"provider {prov} -> {fam}", devpair.driver_identity()["family"] == fam,
              f"got {devpair.driver_identity()['family']}")


@isolated
def test_pick_reviewer_honours_driver(base):
    print("\n[selection] pick_reviewer respects an explicit driver")
    set_driver("glm-5.3", "zai")
    r = devpair.pick_reviewer(None, "kimi-coding/kimi-k3")
    check("kimi driver -> non-kimi reviewer", r["family"] != "kimi", f"got {r['family']}")


# --- new code must actually be visible to the reviewer ------------------------
@isolated
def test_untracked_files_are_read_not_just_named(base):
    print("\n[context] brand-new files reach the reviewer as CODE, not just a filename")
    with tempfile.TemporaryDirectory() as repo:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True,
                       capture_output=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-q", "--allow-empty", "-m", "base"],
                       cwd=repo, check=True, capture_output=True)
        (Path(repo) / "brandnew.py").write_text(
            "def withdraw(acct, amount):\n"
            "    acct.balance -= amount   # no overdraft check\n"
            "    return acct.balance\n"
        )
        (Path(repo) / "ignored.bin").write_bytes(b"\x00\x01\x02binary")
        cwd = os.getcwd()
        os.chdir(repo)
        try:
            args = argparse.Namespace(diff=True, diff_ref=None, files=None,
                                      plan=None, error=None, cmd=None)
            ctx, notes = devpair.gather(args)
        finally:
            os.chdir(cwd)
    check("filename listed", "brandnew.py" in ctx)
    check("ACTUAL CODE present", "acct.balance -= amount" in ctx,
          "reviewer would be reviewing a filename only")
    check("code is line-numbered for file:line citations", "    1| def withdraw" in ctx,
          ctx[:200])
    check("binary content not dumped", "\x00" not in ctx)
    check("no misleading 'no diff found' when new code exists",
          not any("no diff found" in n for n in notes), f"notes={notes}")


# --- a missing hermes binary must degrade, not crash --------------------------
def test_missing_hermes_binary_is_soft_failure():
    print("\n[errors] a missing `hermes` CLI falls through instead of crashing")
    env = dict(os.environ, PATH="/nonexistent")
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import devpair; "
         "print(devpair.run_reviewer({'model':'m','provider':'p','label':'L'},'hi',5,False))"
         % str(Path(devpair.__file__).parent)],
        capture_output=True, text=True, env=env, timeout=60,
    )
    check("no traceback", "Traceback" not in r.stderr, r.stderr[-200:])
    check("returns a failure tuple", "False" in r.stdout, r.stdout[:120])
    check("names the real cause", "hermes" in r.stdout.lower() and "path" in r.stdout.lower(),
          r.stdout[:160])


# --- F1: gating on the verdict ------------------------------------------------
def test_parse_verdict_and_gate():
    print("\n[gate] verdict parsing is exact and the gate fails CLOSED")
    cases = [
        ("## VERDICT\nSHIP\nLooks good.", "SHIP", False),
        ("## VERDICT\nDO NOT SHIP\nBroken.", "DO NOT SHIP", True),
        ("## VERDICT\nSHIP AFTER FIXES\nMinor.", "SHIP AFTER FIXES", False),
        ("## VERDICT\nNEEDS WORK", "NEEDS WORK", True),
        ("## VERDICT\nPROCEED WITH CHANGES\nok", "PROCEED WITH CHANGES", False),
        ("## VERDICT\nSTOP\nno", "STOP", True),
        ("## REMAINING VERDICT\nPROCEED\nfine", "PROCEED", False),
    ]
    for text, expect, should_fail in cases:
        got = devpair.parse_verdict(text)
        check(f"parses {expect!r}", got == expect, f"got {got!r}")
        failed, _ = devpair.gate_failed(text)
        check(f"gate {'blocks' if should_fail else 'passes'} on {expect!r}",
              failed is should_fail)
    # "DO NOT SHIP" must not be read as "SHIP"
    check("longest-match wins (not SHIP)",
          devpair.parse_verdict("## VERDICT\nDO NOT SHIP") == "DO NOT SHIP")
    # A BLOCKER overrides a good-looking verdict.
    failed, reason = devpair.gate_failed(
        "## VERDICT\nSHIP\n## DEFECTS\n[BLOCKER] a.py:1 — boom")
    check("BLOCKER overrides a SHIP verdict", failed, reason)
    check("reason names the blocker count", "BLOCKER" in reason, reason)
    # Unparseable output must NOT silently pass a gate.
    failed, reason = devpair.gate_failed("the model rambled and forgot the format")
    check("unparseable verdict fails closed", failed, reason)
    check("counts blockers case-insensitively",
          devpair.count_blockers("[blocker] x\n[BLOCKER] y") == 2)


@isolated
def test_conflicting_verdicts_fail_closed(base):
    print("\n[gate] a response carrying two DIFFERENT verdicts cannot pass the gate")
    # GPT-5.6 Luna found this: parse_verdict() takes the FIRST match, so a review
    # that says SHIP and later DO NOT SHIP was gated on the SHIP. A gate that
    # cannot tell which verdict is the real one must refuse, not pick the
    # convenient one — the same fail-closed rule already applied to an
    # unparseable verdict.
    conflicts = [
        ("SHIP then DO NOT SHIP",
         "## VERDICT\nSHIP\n\nlooks fine\n\n## VERDICT\nDO NOT SHIP\n\nbroken after all"),
        ("APPROVE then DO NOT USE",
         "## PASS 6 — VERDICT\nAPPROVE\n\n## PASS 6 — VERDICT\nDO NOT USE"),
        ("quoted example then the real one",
         "A review might say:\n## VERDICT\nAPPROVE\n\nMine:\n## VERDICT\nREVISE BEFORE USE"),
        ("failing verdict FIRST is still a conflict",
         "## VERDICT\nDO NOT USE\n\n## VERDICT\nAPPROVE"),
    ]
    for name, resp in conflicts:
        failed, reason = devpair.gate_failed(resp)
        check(f"gate blocks: {name}", failed is True, f"reason={reason!r}")
        check(f"reason names the conflict: {name}", "conflict" in reason.lower(),
              f"got {reason!r}")

    # A verdict RESTATED identically is not a conflict — models summarise, and
    # failing that would be a nuisance failure that teaches people to drop --gate.
    same = "## VERDICT\nSHIP\n\nDetail...\n\n## VERDICT\nSHIP"
    failed, reason = devpair.gate_failed(same)
    check("an identically repeated verdict still passes", failed is False, reason)
    check("repeated verdict still parses", devpair.parse_verdict(same) == "SHIP")

    # And the single-verdict behaviour is unchanged.
    for verdict, should_fail in (("SHIP", False), ("APPROVE", False),
                                 ("DO NOT USE", True), ("NEEDS WORK", True)):
        failed, _ = devpair.gate_failed(f"## VERDICT\n{verdict}\n\nreasoning")
        check(f"single {verdict!r} unchanged", failed is should_fail)


@isolated
def test_gate_exit_code_end_to_end(base):
    print("\n[gate] --gate really exits 2 from the CLI; default stays advisory (exit 0)")
    # This test used to be `"return 2" in inspect.getsource(cmd_pair)`. It would
    # have passed on a commented-out branch and failed on a harmless refactor to
    # a named constant — the exact "green that proves nothing" this tool exists
    # to catch. It now drives the real CLI with a stubbed reviewer.
    # The backend is invoked as `hermes` from PATH, so the stub MUST be named
    # `hermes` — naming it anything else silently calls the real binary and the
    # test hangs on a live model call. On Windows an extensionless shebang file
    # is NOT executable via PATH (PATHEXT governs that), so the stub is a .cmd
    # shim delegating to a .py payload. Getting this wrong made all 8 gate
    # assertions fail on every Windows box while passing on macOS — and the
    # 9th ("backend failure is exit 1") passed for the WRONG reason, because a
    # missing stub is itself a backend failure.
    # The stub is delivered via DEVPAIR_HERMES_CMD rather than a shim on PATH.
    # A PATH shim has to be executable BY THE OS, and the rules differ per
    # platform (PATHEXT on Windows, +x and a shebang elsewhere) — that
    # difference made this test pass on macOS and fail on every Windows box.
    # The override runs the current interpreter directly, which works anywhere
    # Python does, and exercises a real documented feature.
    impl = base / "_stub_impl.py"
    log = base / "hermes_calls.log"
    # Double quotes: the style the docs show, and the one that survives Windows
    # paths. shlex.quote() would emit POSIX single quotes here and hide a bug.
    stub_cmd = f'"{sys.executable}" "{impl}"'

    def write_stub(reply: str):
        # encoding="utf-8" is load-bearing: Path.write_text() uses the locale
        # encoding, which is cp1252 on the Windows agents. A reply containing an
        # em-dash was then written as a cp1252 byte, and Python refused to
        # import its own stub ("Non-UTF-8 code ... no encoding declared"). The
        # stub silently never ran and every gate assertion failed.
        impl.write_text(
            "import sys, pathlib\n"
            f"pathlib.Path({str(log)!r}).write_text(' '.join(sys.argv[1:])[:200], encoding='utf-8')\n"
            f"sys.stdout.write({reply!r})\n",
            encoding="utf-8",
        )

    def write_failing_stub(code: int):
        """A backend that exits non-zero without answering."""
        impl.write_text(f"import sys\nsys.exit({code})\n", encoding="utf-8")

    env = dict(os.environ)
    env["DEVPAIR_HERMES_CMD"] = stub_cmd
    env["DEVPAIR_DRIVER_MODEL"] = "claude-opus-5"
    env["DEVPAIR_DRIVER_PROVIDER"] = "anthropic"

    def run(reply, *extra):
        write_stub(reply)
        ev = base / "evidence.txt"
        ev.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(Path(devpair.__file__)), "verify",
             "--with", "kimi-coding/kimi-k3", "--files", str(ev),
             "--ask", "check this", *extra],
            capture_output=True, text=True, env=env, cwd=str(base),
            # DEVNULL, not inherit: devpair drains a non-tty stdin, and an
            # inherited pipe would block the child forever.
            stdin=subprocess.DEVNULL, timeout=120)

    bad = "## PASS 6 — VERDICT & WHAT HAPPENS NEXT\nDO NOT USE\n\nIt is broken."
    good = "## PASS 6 — VERDICT & WHAT HAPPENS NEXT\nAPPROVE\n\nFine."
    unparseable = "I have thoughts about this code but will not state a verdict."
    crit = ("## PASS 6 — VERDICT & WHAT HAPPENS NEXT\nAPPROVE\n\n"
            "[CRITICAL] it will delete the database")

    r = run(bad, "--gate")
    check("stub reviewer was actually invoked", log.exists(),
          f"backend never called — rc={r.returncode} stderr={(r.stderr or '')[-400:]!r}")
    if not log.exists():
        # Everything below assumes the stub answered. Without that, each case is
        # a backend failure and the whole test degrades into vacuous passes —
        # which is exactly how this test shipped broken on Windows. Say so once
        # and stop, rather than printing a wall of misleading results.
        check("gate assertions are meaningful (stub on PATH)", False,
              f"stub via DEVPAIR_HERMES_CMD was never executed — remaining checks skipped")
        return
    check("DO NOT USE + --gate -> exit 2", r.returncode == 2,
          f"got {r.returncode}: {r.stderr[-300:]}")
    check("gate says why", "GATE FAILED" in r.stderr, r.stderr[-200:])

    r = run(bad)
    check("DO NOT USE without --gate stays advisory (exit 0)", r.returncode == 0,
          f"got {r.returncode}: {r.stderr[-300:]}")

    r = run(good, "--gate")
    check("APPROVE + --gate -> exit 0", r.returncode == 0,
          f"got {r.returncode}: {r.stderr[-300:]}")

    r = run(unparseable, "--gate")
    check("unparseable verdict fails CLOSED -> exit 2", r.returncode == 2,
          f"got {r.returncode}: {r.stderr[-300:]}")

    r = run(crit, "--gate")
    check("APPROVE carrying a [CRITICAL] -> exit 2", r.returncode == 2,
          f"got {r.returncode}: {r.stderr[-300:]}")

    # Luna's case, driven through the real CLI: a review that says SHIP and then
    # DO NOT SHIP used to be gated on the SHIP.
    conflict = ("## VERDICT\nSHIP\n\nlooks fine\n\n"
                "## VERDICT\nDO NOT SHIP\n\nbroken after all")
    r = run(conflict, "--gate")
    check("conflicting verdicts -> exit 2", r.returncode == 2,
          f"got {r.returncode}: {r.stderr[-300:]}")

    # Exit 2 must stay distinguishable from exit 1 (backend failure), or CI
    # cannot tell "the reviewer rejected it" from "the reviewer never answered".
    # NOTE: this check is only meaningful because the stub above WAS found and
    # invoked — a stub that never runs makes every case a backend failure and
    # this assertion passes vacuously.
    write_failing_stub(3)
    ev = base / "evidence.txt"
    ev.write_text("x = 1\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(Path(devpair.__file__)), "verify",
         "--with", "kimi-coding/kimi-k3", "--files", str(ev), "--gate"],
        capture_output=True, text=True, env=env, cwd=str(base),
        stdin=subprocess.DEVNULL, timeout=120)
    check("backend failure is exit 1, not the gate's 2", r.returncode == 1,
          f"got {r.returncode}: {r.stderr[-300:]}")


# --- F2: the reviewer's file:line claims are checked ---------------------------
@isolated
def test_verify_claims_catches_hallucinated_anchors(base):
    print("\n[claims] hallucinated file:line anchors are flagged")
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "real.py").write_text("a = 1\nb = 2\nc = 3\n")
        resp = ("[BLOCKER] real.py:2 — fine\n"
                "[MAJOR] real.py:999 — past EOF\n"
                "[MINOR] imaginary.py:5 — does not exist\n")
        problems = devpair.verify_claims(resp, td)
        joined = " | ".join(problems)
        check("valid anchor NOT flagged", "real.py:2 " not in joined, joined)
        check("past-EOF anchor flagged", "real.py:999" in joined, joined)
        check("missing file flagged", "imaginary.py:5" in joined, joined)
        check("says how many lines the file has", "only 3 lines" in joined, joined)
        clean = devpair.verify_claims("no anchors here at all", td)
        check("no false positives on prose", clean == [], f"got {clean}")

        # Models cite in prose too — "README.md line 438", not "README.md:438".
        # A Kimi review once produced fifteen findings against files it had never
        # been sent, every anchor in this style, and the colon-only pattern
        # cleared all of them. Both forms must be checked.
        for style in ("real.py line 999", "real.py on line 999", "real.py lines 999"):
            got = " | ".join(devpair.verify_claims(f"[MAJOR] {style} — past EOF", td))
            check(f"prose anchor caught: {style!r}", "real.py" in got and "999" in got,
                  f"got {got!r} — a fabricated citation would pass unflagged")
        got = " | ".join(devpair.verify_claims("[MINOR] ghost.py line 5 — invented", td))
        check("prose anchor to a missing file is flagged", "ghost.py" in got, f"got {got!r}")
        ok = devpair.verify_claims("[MINOR] real.py line 2 — fine", td)
        check("a VALID prose anchor is not flagged", ok == [], f"got {ok}")
        # Ordinary prose containing a filename must not trip it.
        quiet = devpair.verify_claims("see notes.md for the release lines", td)
        check("prose without a line number is ignored", quiet == [], f"got {quiet}")


# --- F3: doctor probes in parallel --------------------------------------------
def test_doctor_probes_in_parallel():
    print("\n[doctor] backends are probed concurrently, not serially")
    import inspect
    src = inspect.getsource(devpair.cmd_doctor)
    check("uses a thread pool", "ThreadPoolExecutor" in src)
    check("no serial for-loop over REVIEWERS.items() calling run_reviewer",
          "for key, r in REVIEWERS.items():" not in src)


# --- F4: total wall-clock budget ----------------------------------------------
@isolated
def test_budget_caps_total_walltime(base):
    print("\n[budget] a dead backend chain cannot burn timeout x candidates")
    import inspect
    src = inspect.getsource(devpair.cmd_pair)
    check("budget consulted before each attempt", "budget - (time.time() - t0)" in src)
    check("per-attempt timeout is clamped to what remains",
          "min(args.timeout, remaining)" in src)
    check("reports how many backends went untried", "not tried" in src)


# --- F5: token/cost accounting -------------------------------------------------
@isolated
def test_token_estimates_recorded(base):
    print("\n[cost] each turn records an input/output token estimate")
    check("estimator is roughly 4 chars/token",
          900 <= devpair.estimate_tokens("x" * 4000) <= 1100,
          f"got {devpair.estimate_tokens('x' * 4000)}")
    check("never returns 0 for non-empty text", devpair.estimate_tokens("hi") >= 1)
    check("empty text is still >= 1", devpair.estimate_tokens("") >= 1)
    import inspect
    src = inspect.getsource(devpair.cmd_pair)
    check("stored on the session turn", '"tokens_in_est"' in src)
    check("shown in the human footer", "tokens in /" in src)


# --- F6: session pruning -------------------------------------------------------
@isolated
def test_prune_respects_age_and_active_session(base):
    print("\n[prune] old sessions go; the active one never does")
    devpair.SESSIONS.mkdir(parents=True, exist_ok=True)
    old = devpair.SESSIONS / "20200101-000000.json"
    new = devpair.SESSIONS / "20991231-000000.json"
    active = devpair.SESSIONS / "active-one.json"
    for p in (old, new, active):
        p.write_text('{"turns": []}')
    ancient = time.time() - (90 * 86400)
    os.utime(old, (ancient, ancient))
    os.utime(active, (ancient, ancient))   # old BUT active
    devpair.CURRENT.write_text("active-one")

    args = argparse.Namespace(days=30, dry_run=True)
    devpair.cmd_prune(args)
    check("dry-run deletes nothing", old.is_file())

    args = argparse.Namespace(days=30, dry_run=False)
    rc = devpair.cmd_prune(args)
    check("prune exits 0", rc == 0)
    check("old session deleted", not old.is_file())
    check("recent session kept", new.is_file())
    check("ACTIVE session never pruned even when old", active.is_file(),
          "deleted the session the user is mid-conversation with")


def test_banner_survives_a_legacy_console_encoding():
    print("\n[portable] a cp1252 console must not destroy a review that was paid for")
    # Found on the Windows agents: every banner uses box-drawing characters, a
    # Windows console defaults to a legacy code page, and printing the result
    # raised UnicodeEncodeError *after* the reviewer had answered and the ledger
    # entry was written. The user paid for a review and received a traceback.
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "emit.py"
        # cp1252 cannot represent U+2500; the guard must downgrade, not die.
        script.write_text(
            "import sys, pathlib\n"
            f"sys.path.insert(0, {str(Path(devpair.__file__).parent)!r})\n"
            "import devpair\n"
            "devpair._force_utf8_output()\n"
            "print('\\u2500' * 20)\n"
            "print('done')\n"
        )
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        p = subprocess.run([sys.executable, str(script)], capture_output=True,
                           text=True, env=env, timeout=60)
        check("printing a box-drawn banner under cp1252 does not crash",
              p.returncode == 0, f"rc={p.returncode}: {(p.stderr or '')[-200:]}")
        check("output still arrives", "done" in (p.stdout or ""),
              f"stdout={(p.stdout or '')[:120]!r}")
        check("no UnicodeEncodeError", "UnicodeEncodeError" not in (p.stderr or ""),
              (p.stderr or "")[-200:])


# --- PORTABILITY: the tool must find the right home on any machine ----------
def test_hermes_binary_resolves_through_pathext():
    print("\n[portable] a .cmd/.bat shim on PATH is found, not just hermes.exe")
    # Found by deploying to Windows: a bare "hermes" in a subprocess list goes to
    # CreateProcess, which only appends .exe — so the shim the manual-install
    # instructions tell people to create was invisible. shutil.which walks
    # PATHEXT properly.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        ext = ".cmd" if os.name == "nt" else ""
        shim = d / f"hermes{ext}"
        shim.write_text("@echo off\r\nexit /b 0\r\n" if os.name == "nt" else "#!/bin/sh\nexit 0\n")
        if os.name != "nt":
            shim.chmod(0o755)
        orig = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{d}{os.pathsep}{orig}"
        try:
            got = devpair._hermes_command()
            check("returns a command list", isinstance(got, list) and len(got) == 1, f"got {got!r}")
            check("resolves the shim rather than the bare name", got[0] != "hermes",
                  f"got {got!r} — a .cmd shim would be unreachable on Windows")
            check("resolved path is the one we planted", Path(got[0]).parent == d,
                  f"got {got!r}")
        finally:
            os.environ["PATH"] = orig

    # With nothing on PATH it must fall back to the bare name, so the existing
    # soft-failure path still handles a missing binary.
    orig = os.environ.get("PATH", "")
    os.environ["PATH"] = ""
    try:
        check("falls back to the bare name when absent",
              devpair._hermes_command() == ["hermes"], "would raise instead of soft-failing")
    finally:
        os.environ["PATH"] = orig

    # DEVPAIR_HERMES_CMD takes a full prefix, for installs where Hermes is not a
    # bare executable on PATH (venv launcher, container shim, wrapper script).
    prev = os.environ.get("DEVPAIR_HERMES_CMD")
    os.environ["DEVPAIR_HERMES_CMD"] = f"{sys.executable} /opt/hermes/cli.py"
    try:
        got = devpair._hermes_command()
        check("override is split into a command prefix", len(got) == 2, f"got {got!r}")
        check("override keeps the interpreter", got[0] == sys.executable, f"got {got!r}")
        check("override keeps the script argument", got[1].endswith("cli.py"), f"got {got!r}")

        # The bug that cost two releases: shlex.quote writes POSIX single quotes,
        # and shlex.split(posix=False) leaves them INSIDE the token, so a quoted
        # Windows path arrived as "'C:\\...\\python.exe'" and would not launch.
        # A quoted path must round-trip to the bare path on every platform.
        # Both quoting styles must round-trip to the bare path, on every
        # platform. This is the check that caught two bad releases: a Windows
        # path is full of backslashes (POSIX shlex eats them as escapes) and may
        # be quoted (non-POSIX shlex keeps the quotes inside the token).
        for style, q in (("single", "'"), ("double", '"')):
            os.environ["DEVPAIR_HERMES_CMD"] = f"{q}{sys.executable}{q} {q}/opt/a b/cli.py{q}"
            got = devpair._hermes_command()
            check(f"{style}-quoted interpreter path round-trips exactly",
                  got and got[0] == sys.executable,
                  f"got {got!r} — must equal {sys.executable!r}")
            check(f"{style}-quoted path with a space stays one token",
                  len(got) == 2 and got[1] == "/opt/a b/cli.py", f"got {got!r}")
        # Unquoted, with native separators, must survive too.
        os.environ["DEVPAIR_HERMES_CMD"] = sys.executable
        check("an unquoted native path survives intact",
              devpair._hermes_command() == [sys.executable],
              f"got {devpair._hermes_command()!r}")

        # An override of only whitespace must not produce an empty command list.
        os.environ["DEVPAIR_HERMES_CMD"] = "   "
        check("a blank override falls back rather than emptying the command",
              devpair._hermes_command() == [shutil.which("hermes") or "hermes"],
              f"got {devpair._hermes_command()!r}")
    finally:
        if prev is None:
            os.environ.pop("DEVPAIR_HERMES_CMD", None)
        else:
            os.environ["DEVPAIR_HERMES_CMD"] = prev


def test_hermes_home_resolution_is_portable():
    print("\n[portable] state lands in THIS machine's hermes home, not a guess")
    import importlib
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "custom-home"
        (fake / "skills").mkdir(parents=True)
        old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(fake)
        try:
            got = devpair._resolve_hermes_home()
            check("HERMES_HOME wins when set", got == fake, f"got {got}")
        finally:
            if old is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = old
        # A bogus HERMES_HOME must not be trusted blindly.
        os.environ["HERMES_HOME"] = str(Path(td) / "does-not-exist")
        try:
            got = devpair._resolve_hermes_home()
            check("nonexistent HERMES_HOME falls back", got != Path(td) / "does-not-exist")
        finally:
            if old is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = old
    src = inspect_source(devpair)
    check("no hardcoded ~/.hermes for the config path",
          'HOME / ".hermes" / "config.yaml"' not in src,
          "config.yaml path is still hardcoded")
    check("--cmd picks a shell per platform", 'os.name == "nt"' in src,
          "still assumes bash exists")


def inspect_source(mod):
    import inspect as _i
    return _i.getsource(mod)


@isolated
def test_roster_is_machine_local(base):
    print("\n[portable] each machine declares its own reviewers")
    saved = dict(devpair.REVIEWERS)
    try:
        devpair.CONFIG.write_text(json.dumps({
            "reviewers": {
                "mine": {"model": "some-model", "provider": "my-provider",
                         "family": "claude", "label": "Mine"},
                "other": {"model": "kimi-k3", "provider": "kimi-coding"},
                "junk": {"provider": "no-model-key"},
            },
            "order": ["mine", "other"],
        }))
        devpair._load_roster()
        check("config roster REPLACES the shipped defaults",
              set(devpair.REVIEWERS) == {"mine", "other"}, f"got {set(devpair.REVIEWERS)}")
        check("entries missing model/provider are dropped",
              "junk" not in devpair.REVIEWERS)
        check("family inferred when not declared",
              devpair.REVIEWERS["other"]["family"] == "kimi",
              f"got {devpair.REVIEWERS['other'].get('family')}")
        check("label defaults to provider/model",
              devpair.REVIEWERS["other"]["label"] == "kimi-coding/kimi-k3")
        set_driver("glm-5.3", "zai")
        cands = devpair.reviewer_candidates(None)
        check("local roster is used for selection",
              {c["key"] for c in cands} <= {"mine", "other"},
              f"got {[c['key'] for c in cands]}")
    finally:
        devpair.REVIEWERS.clear()
        devpair.REVIEWERS.update(saved)


@isolated
def test_roster_ignores_empty_or_broken_config(base):
    print("\n[portable] a broken roster falls back to defaults, never to nothing")
    saved = dict(devpair.REVIEWERS)
    try:
        for payload in ('{"reviewers": {}}', '{"reviewers": "nonsense"}', "{ not json"):
            devpair.REVIEWERS.clear()
            devpair.REVIEWERS.update(saved)
            devpair.CONFIG.write_text(payload)
            devpair._load_roster()
            check(f"defaults survive {payload[:18]!r}",
                  len(devpair.REVIEWERS) == len(saved))
    finally:
        devpair.REVIEWERS.clear()
        devpair.REVIEWERS.update(saved)


# --- user-chosen reviewer (--with) -------------------------------------------
@isolated
def test_with_model_is_user_choice(base):
    print("\n[--with] the user can name any model as the pair")
    set_driver("glm-5.3", "zai")
    c = devpair.reviewer_candidates(None, None, "anthropic/claude-opus-5")
    check("single candidate, exactly what was asked for", len(c) == 1)
    check("provider parsed", c[0]["provider"] == "anthropic", f"got {c[0]}")
    check("model parsed", c[0]["model"] == "claude-opus-5", f"got {c[0]}")
    check("family inferred", c[0]["family"] == "claude", f"got {c[0]['family']}")
    check("works for a model NOT in the roster",
          c[0]["model"] not in [r["model"] for r in devpair.REVIEWERS.values()])

    # Same-family must WARN, not block — the user's explicit instruction wins.
    set_driver("claude-opus-5", "anthropic")
    c2 = devpair.reviewer_candidates(None, None, "anthropic/claude-sonnet-4.6")
    check("same-family --with is allowed", len(c2) == 1)
    check("but it is flagged as not independent",
          c2[0]["same_family_as_driver"] is True)

    # An opaque provider still resolves rather than silently claiming independence.
    c3 = devpair.reviewer_candidates(None, None, "kimi-coding/some-new-kimi")
    check("family falls back to the provider", c3[0]["family"] == "kimi",
          f"got {c3[0]['family']}")


@isolated
def test_with_model_bad_input_refuses_clearly(base):
    print("\n[--with] a bare unknown model refuses with a usable message")
    set_driver("glm-5.3", "zai")
    try:
        devpair.reviewer_candidates(None, None, "not-a-real-model")
        check("bare unknown model -> SystemExit", False, "accepted it silently")
    except SystemExit as e:
        check("bare unknown model -> SystemExit", True)
        check("message shows the PROVIDER/MODEL form", "PROVIDER/MODEL" in str(e),
              str(e)[:120])
    # A bare model that IS in the roster resolves its provider for convenience.
    c = devpair.reviewer_candidates(None, None, "kimi-k3")
    check("bare roster model resolves its provider",
          c[0]["provider"] == "kimi-coding", f"got {c[0]}")


# --- Luna's findings: unknown family must never read as independent ---------
@isolated
def test_opaque_roster_entry_cannot_fake_independence(base):
    print("\n[luna-1] a roster alias with no family infers from its provider")
    saved = dict(devpair.REVIEWERS)
    try:
        devpair.CONFIG.write_text(json.dumps({
            "reviewers": {
                # opaque model, Claude-backed provider, family NOT declared
                "sneaky": {"model": "my-fast-coder", "provider": "anthropic"},
                "kimi": {"model": "kimi-k3", "provider": "kimi-coding"},
            },
            "order": ["sneaky", "kimi"],
        }))
        devpair._load_roster()
        check("family inferred from provider, not left 'unknown'",
              devpair.REVIEWERS["sneaky"]["family"] == "claude",
              f"got {devpair.REVIEWERS['sneaky']['family']!r}")
        set_driver("claude-opus-5", "anthropic")
        keys = [c["key"] for c in devpair.reviewer_candidates(None)]
        check("claude-backed alias NOT offered to a claude driver",
              "sneaky" not in keys, f"got {keys}")
        check("the genuinely independent reviewer still is", "kimi" in keys)
    finally:
        devpair.REVIEWERS.clear()
        devpair.REVIEWERS.update(saved)


@isolated
def test_resolve_family_never_stops_on_unknown(base):
    print("\n[luna-1] _resolve_family falls through 'unknown' (it is a truthy string)")
    check("opaque model + known provider -> provider family",
          devpair._resolve_family("some-alias", "anthropic") == "claude")
    check("known model wins over provider",
          devpair._resolve_family("kimi-k3", "anthropic") == "kimi")
    check("both opaque -> unknown", devpair._resolve_family("x", "y") == "unknown")


@isolated
def test_with_unverifiable_target_is_flagged(base):
    print("\n[luna-2] --with an unidentifiable model is flagged, not assumed safe")
    set_driver("claude-opus-5", "anthropic")
    c = devpair.reviewer_candidates(None, None, "mystery-gateway/new-model")[0]
    check("family is honestly 'unknown'", c["family"] == "unknown")
    check("flagged unverifiable", c.get("unverifiable") is True,
          "silently presented as independent")
    known = devpair.reviewer_candidates(None, None, "kimi-coding/kimi-k3")[0]
    check("a known-family target is NOT flagged",
          not known.get("unverifiable"), "false positive")
    same = devpair.reviewer_candidates(None, None, "anthropic/claude-sonnet-4.6")[0]
    check("same-family still flagged separately",
          same["same_family_as_driver"] is True and not same.get("unverifiable"))


@isolated
def test_unverifiable_flag_covers_every_selection_path(base):
    print("\n[luna-2b] an opaque reviewer is flagged on ALL paths, not just --with")
    saved = dict(devpair.REVIEWERS)
    try:
        devpair.CONFIG.write_text(json.dumps({
            "reviewers": {
                # Neither the model name nor the provider maps to a family.
                "mystery": {"model": "opaque-model-x", "provider": "mystery-gw"},
                "kimi": {"model": "kimi-k3", "provider": "kimi-coding"},
            },
            "order": ["mystery", "kimi"],
        }))
        devpair._load_roster()
        check("opaque roster entry stays honestly 'unknown'",
              devpair.REVIEWERS["mystery"]["family"] == "unknown",
              f"got {devpair.REVIEWERS['mystery']['family']!r}")
        set_driver("claude-opus-5", "anthropic")

        # AUTOMATIC path: the bug was that an unknown family compares as
        # "different" against every driver and so reads as PROVEN independent.
        auto = devpair.reviewer_candidates(None)
        by_key = {c["key"]: c for c in auto}
        check("auto-selected opaque reviewer is flagged unverifiable",
              by_key["mystery"].get("unverifiable") is True,
              "silently offered as independent")
        check("a provable reviewer is NOT flagged",
              not by_key["kimi"].get("unverifiable"), "false positive")
        check("provable reviewer is preferred over the unprovable one",
              auto[0]["key"] == "kimi", f"first was {auto[0]['key']}")
        check("the opaque one survives as a fallback, not dropped",
              "mystery" in by_key, "silently discarded")

        # --reviewer path: forcing it must be just as honest.
        forced = devpair.reviewer_candidates("mystery")[0]
        check("--reviewer opaque entry flagged unverifiable",
              forced.get("unverifiable") is True, "forced pick claimed independent")
        check("--reviewer known entry not flagged",
              not devpair.reviewer_candidates("kimi")[0].get("unverifiable"))
    finally:
        devpair.REVIEWERS.clear()
        devpair.REVIEWERS.update(saved)


@isolated
def test_unknown_family_is_never_called_same_family(base):
    print("\n[luna-2b] 'unknown' must not collide into the same-family branch")
    saved = dict(devpair.REVIEWERS)
    try:
        devpair.CONFIG.write_text(json.dumps({
            "reviewers": {"mystery": {"model": "opaque-x", "provider": "mystery-gw"}},
            "order": ["mystery"],
        }))
        devpair._load_roster()
        # Driver family is ALSO unknown here, so a naive `==` would report the
        # two as the same family and print the wrong warning entirely.
        set_driver("opaque-x", "mystery-gw")
        forced = devpair.reviewer_candidates("mystery")[0]
        check("not mislabelled as same-family",
              forced["same_family_as_driver"] is False,
              "unknown == unknown leaked into the same-family branch")
        check("correctly labelled unverifiable",
              forced.get("unverifiable") is True)
    finally:
        devpair.REVIEWERS.clear()
        devpair.REVIEWERS.update(saved)


@isolated
def test_independence_state_is_reported_to_callers(base):
    print("\n[luna-2b] the independence state reaches the human footer and --json")
    src = Path(devpair.__file__).read_text()
    check("human footer reports an unverified reviewer",
          "INDEPENDENCE UNVERIFIED" in src,
          "user reads the review with no independence caveat")
    check("human footer reports a same-family reviewer",
          "NOT INDEPENDENT" in src)
    check("machine-readable independence field exists",
          '"independence"' in src, "--json callers cannot tell")
    # The warning must describe the model that ACTUALLY answered, not the
    # first choice, because backend fallthrough can change the reviewer.
    footer = src.split("bar = ")[-1]
    check("footer keys off `used`, not the original pick",
          'used.get("unverifiable")' in footer and 'used.get("same_family_as_driver")' in footer,
          "a fallthrough would report the wrong model's independence")


@isolated
def test_with_and_reviewer_together_refuses(base):
    print("\n[--with] two contradictory reviewer flags refuse instead of silently picking")
    set_driver("glm-5.3", "zai")
    try:
        devpair.reviewer_candidates("kimi", None, "anthropic/claude-opus-5")
        check("--with + --reviewer -> SystemExit", False,
              "silently discarded one of the two choices")
    except SystemExit as e:
        check("--with + --reviewer -> SystemExit", True)
        check("message names both flags",
              "--with" in str(e) and "--reviewer" in str(e), str(e)[:140])
    # Each alone still works.
    check("--with alone still works",
          devpair.reviewer_candidates(None, None, "anthropic/claude-opus-5")[0]["key"] == "adhoc")
    check("--reviewer alone still works",
          devpair.reviewer_candidates("kimi", None, None)[0]["key"] == "kimi")


# --- v1.1.6: invocation control (the enforcement the policy prose lacked) ----
@isolated
def test_ledger_records_every_paid_run(base):
    print("\n[audit] every paid run lands in an append-only ledger")
    rev = {"provider": "kimi-coding", "model": "kimi-k3"}
    drv = {"provider": "zai", "model": "glm-5.3"}
    check("no ledger before the first run", devpair.read_ledger() == [])
    devpair.log_invocation("review", rev, drv, "user", 1234)
    devpair.log_invocation("critique", rev, drv, "unattributed", 99)
    recs = devpair.read_ledger()
    check("both runs recorded", len(recs) == 2, f"got {len(recs)}")
    check("requester preserved", recs[0]["requested_by"] == "user", f"got {recs[0]}")
    check("mode preserved", recs[1]["mode"] == "critique")
    check("reviewer recorded", recs[0]["reviewer"] == "kimi-coding/kimi-k3")
    check("context size recorded", recs[0]["context_chars"] == 1234)
    check("today's runs counted", devpair.runs_today() == 2, f"got {devpair.runs_today()}")

    # A corrupt line must not take the tool down with the audit trail.
    with open(devpair.LEDGER, "a", encoding="utf-8") as fh:
        fh.write("{not json at all\n\n")
    check("corrupt ledger line is skipped, not fatal",
          len(devpair.read_ledger()) == 2, "a bad line broke the reader")


@isolated
def test_daily_cap_is_a_hard_stop(base):
    print("\n[audit] the daily cap REFUSES a run instead of spending tokens")
    rev = {"provider": "kimi-coding", "model": "kimi-k3"}
    drv = {"provider": "zai", "model": "glm-5.3"}
    args = argparse.Namespace(mode="review", requested_by="user")

    check("no cap by default (0 = unlimited)", devpair.daily_cap() == 0)
    devpair.CONFIG.write_text(json.dumps({"daily_cap": 2}))
    check("cap read from config", devpair.daily_cap() == 2)

    devpair.authorize(args, rev, drv, 10)
    devpair.authorize(args, rev, drv, 10)
    check("runs under the cap are allowed and logged", devpair.runs_today() == 2)

    try:
        devpair.authorize(args, rev, drv, 10)
        check("exceeding the cap -> SystemExit", False, "the run was allowed")
    except SystemExit as e:
        check("exceeding the cap -> SystemExit", True)
        check("refusal names the cap", "2/2" in str(e), str(e)[:120])
        check("refusal says it is a hard stop", "hard stop" in str(e).lower())
    check("the refused run was NOT logged", devpair.runs_today() == 2,
          "a refused run still burned a ledger slot")

    # A malformed cap must not brick the tool.
    devpair.CONFIG.write_text(json.dumps({"daily_cap": "not-a-number"}))
    check("garbage cap falls back to unlimited", devpair.daily_cap() == 0)


@isolated
def test_attestation_is_optional_then_enforced(base):
    print("\n[audit] --requested-by is recorded always, required only if configured")
    rev = {"provider": "kimi-coding", "model": "kimi-k3"}
    drv = {"provider": "zai", "model": "glm-5.3"}

    # Default: no attestation demanded, but its absence is RECORDED as such.
    devpair.authorize(argparse.Namespace(mode="review", requested_by=None), rev, drv, 5)
    check("unattributed run still allowed by default", devpair.runs_today() == 1)
    check("and is marked 'unattributed', not silently blank",
          devpair.read_ledger()[0]["requested_by"] == "unattributed",
          f"got {devpair.read_ledger()[0]['requested_by']!r}")

    devpair.CONFIG.write_text(json.dumps({"require_attestation": True}))
    try:
        devpair.authorize(argparse.Namespace(mode="review", requested_by=None), rev, drv, 5)
        check("required attestation missing -> SystemExit", False, "ran anyway")
    except SystemExit as e:
        check("required attestation missing -> SystemExit", True)
        check("message tells the caller the flag", "--requested-by" in str(e))
    check("the refused run was not logged", devpair.runs_today() == 1)

    devpair.authorize(argparse.Namespace(mode="review", requested_by="user"), rev, drv, 5)
    check("supplying the attestation lets it through", devpair.runs_today() == 2)

    # The env var is an equally valid source (for wrappers/CI).
    os.environ["DEVPAIR_REQUESTED_BY"] = "ci"
    try:
        devpair.authorize(argparse.Namespace(mode="review", requested_by=None), rev, drv, 5)
        check("env var satisfies attestation", devpair.runs_today() == 3)
        check("env var value is what gets recorded",
              devpair.read_ledger()[-1]["requested_by"] == "ci")
    finally:
        os.environ.pop("DEVPAIR_REQUESTED_BY", None)


@isolated
def test_dry_run_is_free_and_never_logs(base):
    print("\n[audit] --dry-run must stay free: no ledger entry, no cap spend")
    devpair.CONFIG.write_text(json.dumps({"daily_cap": 1}))
    set_driver("glm-5.3", "zai")
    args = argparse.Namespace(
        mode="review", ask=None, focus=None, diff=False, diff_ref=None,
        files=None, plan=None, error=None, cmd=None, reviewer=None,
        with_model=None, driver="zai/glm-5.3", requested_by=None, session=None,
        timeout=5, budget=0, gate=False, json=False, dry_run=True, verbose=False)
    rc = devpair.cmd_pair(args)
    check("dry-run exits 0", rc == 0)
    check("dry-run wrote NO ledger entry", devpair.runs_today() == 0,
          "a free preflight consumed the daily cap")
    check("so the cap is still spendable", devpair.daily_cap() == 1)


@isolated
def test_authorize_gates_before_the_paid_call(base):
    print("\n[audit] the gate is wired BEFORE the backend, not after")
    src = Path(devpair.__file__).read_text()
    body = src[src.index("def cmd_pair("):src.index("def cmd_log(")]
    check("cmd_pair calls authorize()", "authorize(args, reviewer, driver" in body)
    gate_at = body.index("authorize(args, reviewer, driver")
    call_at = body.index("run_reviewer(cand")
    check("authorize() runs BEFORE run_reviewer()", gate_at < call_at,
          "tokens would already be spent by the time the cap is checked")
    dry_at = body.index("if args.dry_run:")
    check("and AFTER the dry-run short-circuit", dry_at < gate_at,
          "--dry-run would be gated/logged despite being free")


@isolated
def test_audit_command_surfaces_unattributed_runs(base):
    print("\n[audit] `devpair audit` reports history and flags unattributed runs")
    rev = {"provider": "kimi-coding", "model": "kimi-k3"}
    drv = {"provider": "zai", "model": "glm-5.3"}
    rc = devpair.cmd_audit(argparse.Namespace(days=7, json=False))
    check("empty ledger is not an error", rc == 0)

    devpair.log_invocation("review", rev, drv, "user", 10)
    devpair.log_invocation("review", rev, drv, "unattributed", 10)
    out = json.loads(_capture(devpair.cmd_audit,
                              argparse.Namespace(days=7, json=True)))
    check("json reports both runs", out["count"] == 2, f"got {out}")
    check("json exposes today's count", out["runs_today"] == 2)
    check("json exposes the cap", "daily_cap" in out)
    text = _capture(devpair.cmd_audit, argparse.Namespace(days=7, json=False))
    check("human output flags the unattributed run",
          "named nobody" in text, text[-200:])
    check("human output names the requester of the attributed one",
          "user" in text)


def _capture(fn, args) -> str:
    """Run a command function and return everything it printed."""
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(args)
    return buf.getvalue()


# --- Luna's v1.1.6 review: the cap must be hard, not advisory ---------------
@isolated
def test_cap_survives_concurrent_runs(base):
    print("\n[audit] the cap holds under concurrency (check-then-append was racy)")
    import threading
    devpair.CONFIG.write_text(json.dumps({"daily_cap": 1}))
    rev = {"provider": "p", "model": "m"}
    drv = {"provider": "zai", "model": "glm-5.3"}
    gate, out = threading.Barrier(4), []

    def run():
        a = argparse.Namespace(mode="review", requested_by="user")
        gate.wait()  # line all four up ON the quota check
        try:
            devpair.authorize(a, rev, drv, 10)
            out.append("allowed")
        except SystemExit:
            out.append("refused")

    ts = [threading.Thread(target=run) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    check("exactly one of four concurrent runs is allowed",
          out.count("allowed") == 1, f"got {out}")
    check("and exactly one ledger entry exists",
          len(devpair.read_ledger()) == 1, f"got {len(devpair.read_ledger())}")


@isolated
def test_unwritable_ledger_fails_closed_only_when_enforcing(base):
    print("\n[audit] an unrecordable run is refused under a cap, allowed without one")
    rev = {"provider": "p", "model": "m"}
    drv = {"provider": "zai", "model": "glm-5.3"}
    devpair.LEDGER = base / "blocked"
    devpair.LEDGER.mkdir()  # a directory: every append will fail

    devpair.CONFIG.write_text(json.dumps({"daily_cap": 1}))
    try:
        devpair.authorize(argparse.Namespace(mode="review", requested_by="user"),
                          rev, drv, 10)
        check("capped + unwritable ledger -> SystemExit", False,
              "spent tokens nothing could account for")
    except SystemExit as e:
        check("capped + unwritable ledger -> SystemExit", True)
        check("refusal explains why", "could not record" in str(e), str(e)[:120])

    devpair.CONFIG.write_text(json.dumps({"require_attestation": True}))
    try:
        devpair.authorize(argparse.Namespace(mode="review", requested_by="user"),
                          rev, drv, 10)
        check("required attestation + unwritable ledger -> SystemExit", False)
    except SystemExit:
        check("required attestation + unwritable ledger -> SystemExit", True)

    # But with nothing being enforced, the audit trail is best-effort: it must
    # never be the thing that blocks a review nobody limited.
    devpair.CONFIG.write_text(json.dumps({}))
    try:
        devpair.authorize(argparse.Namespace(mode="review", requested_by=None),
                          rev, drv, 10)
        check("uncapped run still proceeds when logging fails", True)
    except SystemExit as e:
        check("uncapped run still proceeds when logging fails", False,
              f"blocked an unlimited install: {str(e)[:80]}")


@isolated
def test_corrupt_ledger_cannot_undercount_a_cap(base):
    print("\n[audit] an unprovable count refuses instead of silently undercounting")
    rev = {"provider": "p", "model": "m"}
    drv = {"provider": "zai", "model": "glm-5.3"}
    devpair.CONFIG.write_text(json.dumps({"daily_cap": 2}))
    devpair.log_invocation("review", rev, drv, "user", 10)
    with open(devpair.LEDGER, "a", encoding="utf-8") as fh:
        fh.write('{"day":"')          # a torn write from a crashed run

    try:
        devpair.authorize(argparse.Namespace(mode="review", requested_by="user"),
                          rev, drv, 10)
        check("corrupt ledger under a cap -> SystemExit", False,
              "counted a partial ledger as authoritative")
    except SystemExit as e:
        check("corrupt ledger under a cap -> SystemExit", True)
        check("refusal names the unreadable lines", "unreadable" in str(e), str(e)[:120])

    # `audit` must stay lenient — a human reading history should still see it.
    check("audit still shows the readable records",
          len(devpair.read_ledger()) == 1, "a corrupt line hid the whole history")
    recs, corrupt, readable = devpair._scan_ledger()
    check("the scanner reports corruption rather than hiding it", corrupt == 1,
          f"got {corrupt}")
    check("and reports the ledger as readable", readable is True)


@isolated
def test_torn_line_does_not_eat_the_next_record(base):
    print("\n[audit] appending after a newline-less crash heals instead of compounding")
    rev = {"provider": "p", "model": "m"}
    drv = {"provider": "zai", "model": "glm-5.3"}
    devpair.log_invocation("review", rev, drv, "first", 10)
    with open(devpair.LEDGER, "a", encoding="utf-8") as fh:
        fh.write('{"partial')         # no trailing newline
    devpair.log_invocation("review", rev, drv, "second", 10)
    who = [r["requested_by"] for r in devpair.read_ledger()]
    check("the record written after the torn line survives", "second" in who, f"got {who}")
    check("and the record before it survives too", "first" in who, f"got {who}")
    check("only the torn fragment is unreadable", devpair._scan_ledger()[1] == 1)
    check("the ledger itself is still readable", devpair._scan_ledger()[2] is True)


@isolated
def test_wrong_shaped_config_does_not_brick_the_cli(base):
    print("\n[config] valid JSON of the wrong TYPE is ignored, not fatal")
    for blob in ("[]", '"a string"', "42", "null"):
        devpair.CONFIG.write_text(blob)
        try:
            devpair._load_cfg()
            devpair.daily_cap()
            devpair._load_roster()          # runs before argparse — must not raise
            devpair.reviewer_candidates(None, "zai/glm-5.3")
            check(f"config {blob!r} is survivable", True)
        except AttributeError as e:
            check(f"config {blob!r} is survivable", False, f"AttributeError: {e}")
        except SystemExit:
            check(f"config {blob!r} is survivable", True)  # a clean refusal is fine


@isolated
def test_cap_holds_across_real_processes(base):
    print("\n[audit] the cap holds across separate INTERPRETERS, not just threads")
    # The thread test shares one interpreter; the real race is two `devpair`
    # processes. This spawns actual subprocesses against a shared ledger.
    devpair.CONFIG.write_text(json.dumps({"daily_cap": 1}))
    mod = str(Path(devpair.__file__).parent)
    driver = f"""
import sys, json, argparse
sys.path.insert(0, {mod!r})
import devpair
from pathlib import Path
b = Path({str(base)!r})
devpair.BASE = b
devpair.CONFIG = b / "config.json"
devpair.LEDGER = b / "invocations.jsonl"
rev = {{"provider": "p", "model": "m"}}
drv = {{"provider": "zai", "model": "glm-5.3"}}
import time
time.sleep(float(sys.argv[1]))          # crude barrier: line the processes up
try:
    devpair.authorize(argparse.Namespace(mode="review", requested_by="user"),
                      rev, drv, 10)
    print("allowed")
except SystemExit:
    print("refused")
"""
    script = base / "racer.py"
    script.write_text(driver)
    start = time.time() + 1.5
    procs = [subprocess.Popen([sys.executable, str(script), str(max(0, start - time.time()))],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
             for _ in range(4)]
    outs = [p.communicate()[0].strip() for p in procs]
    check("exactly one of four real processes is allowed",
          outs.count("allowed") == 1, f"got {outs}")
    check("and the ledger holds exactly one entry",
          len(devpair.read_ledger()) == 1, f"got {len(devpair.read_ledger())}")


@isolated
def test_unreadable_ledger_is_not_treated_as_zero(base):
    print("\n[audit] an unreadable ledger means UNKNOWN usage, never zero usage")
    rev = {"provider": "p", "model": "m"}
    drv = {"provider": "zai", "model": "glm-5.3"}
    devpair.CONFIG.write_text(json.dumps({"daily_cap": 1}))
    devpair.log_invocation("review", rev, drv, "user", 10)   # cap now spent
    check("cap is spent", devpair.runs_today() == 1)

    # Make the ledger unreadable for the scan. chmod 0o222 achieves that
    # on POSIX only — on Windows the read-only bit blocks writes, never
    # reads — so on Windows the same seam production code depends on
    # (read_text raising OSError) is simulated instead.
    if os.name == "nt":
        class _UnreadablePath:
            def __init__(self, real):
                self._real = real
            def is_file(self):
                return True
            def read_text(self, *a, **k):
                raise OSError("simulated unreadable ledger")
            def __str__(self):
                return str(self._real)
            def __fspath__(self):
                return str(self._real)
            def __getattr__(self, name):
                return getattr(self._real, name)
        devpair.LEDGER = _UnreadablePath(devpair.LEDGER)

        def _restore_ledger():
            devpair.LEDGER = devpair.LEDGER._real
    else:
        os.chmod(devpair.LEDGER, 0o222)                      # write-only

        def _restore_ledger():
            os.chmod(devpair.LEDGER, 0o644)
    try:
        recs, corrupt, readable = devpair._scan_ledger(days=2)
        check("scanner reports the ledger as unreadable", readable is False,
              "an unreadable ledger looked like an empty one")
        try:
            devpair.authorize(argparse.Namespace(mode="review", requested_by="user"),
                              rev, drv, 10)
            check("unreadable ledger under a cap -> SystemExit", False,
                  "a spent cap reopened because usage read as zero")
        except SystemExit as e:
            check("unreadable ledger under a cap -> SystemExit", True)
            check("refusal says usage is unknown", "unknown" in str(e).lower(),
                  str(e)[:120])
    finally:
        _restore_ledger()

    # A ledger that does not exist yet is genuinely zero, and must still work.
    devpair.LEDGER.unlink()
    check("a missing ledger still reads as a real zero",
          devpair._scan_ledger()[2] is True and devpair.runs_today() == 0)
    devpair.authorize(argparse.Namespace(mode="review", requested_by="user"),
                      rev, drv, 10)
    check("and the first run on a fresh ledger is allowed", devpair.runs_today() == 1)


@isolated
def test_cap_refuses_when_it_cannot_lock(base):
    print("\n[audit] an unlockable cap refuses rather than pretending to be hard")
    rev = {"provider": "p", "model": "m"}
    drv = {"provider": "zai", "model": "glm-5.3"}
    devpair.CONFIG.write_text(json.dumps({"daily_cap": 5}))

    real = devpair._ledger_lock

    class NoLock(real):           # simulate a filesystem with no locking
        def __enter__(self):
            super().__enter__()
            self.locked = False
            return self

    devpair._ledger_lock = NoLock
    try:
        try:
            devpair.authorize(argparse.Namespace(mode="review", requested_by="user"),
                              rev, drv, 10)
            check("unlockable + capped -> SystemExit", False,
                  "advertised a hard cap it could not enforce")
        except SystemExit as e:
            check("unlockable + capped -> SystemExit", True)
            check("refusal names the escape hatch", "allow_unlocked_cap" in str(e),
                  str(e)[:160])
            check("refusal warns about network filesystems", "NFS" in str(e))

        # Opting in explicitly is allowed — the user accepts an advisory cap.
        devpair.CONFIG.write_text(json.dumps({"daily_cap": 5, "allow_unlocked_cap": True}))
        devpair.authorize(argparse.Namespace(mode="review", requested_by="user"),
                          rev, drv, 10)
        check("allow_unlocked_cap lets it proceed deliberately",
              devpair.runs_today() == 1)

        # And with no cap at all, locking is irrelevant.
        devpair.CONFIG.write_text(json.dumps({}))
        devpair.authorize(argparse.Namespace(mode="review", requested_by=None),
                          rev, drv, 10)
        check("uncapped runs are unaffected by locking", devpair.runs_today() == 2)
    finally:
        devpair._ledger_lock = real


@isolated
def test_verify_mode_speaks_verify_results_vocabulary(base):
    print("\n[verify] the verify mode mirrors verify-results, not devpair's own shape")
    shape = devpair.SHAPES["verify"]
    for label in ("[VERIFIED ERROR]", "[UNSUPPORTED CLAIM]", "[LIKELY ISSUE]",
                  "[ASSUMPTION]", "[STYLE/CLARITY]", "[SAFETY/COMPLIANCE]"):
        check(f"shape carries {label}", label in shape)
    for p in ("PASS 1", "PASS 2", "PASS 3", "PASS 4", "PASS 5"):
        check(f"shape has {p}", p in shape)
    check("shape asks for the settling checks", "CHECKS THAT WOULD SETTLE THIS" in shape)
    # The labels are shared with quality-guard; devpair's own severity words
    # would make the output illegible to it.
    check("shape does NOT use devpair's [BLOCKER]", "[BLOCKER]" not in shape)

    # verify critiques any deliverable, so it must NOT claim to be a code review.
    prompt = devpair.build_prompt("verify", "check this report", "SOME WORK", {}, None)
    check("verify uses the verifier role", "independent verifier" in prompt)
    check("verify does not use the dev-pair software role",
          "DEV PAIR" not in prompt, "a report review would be told it is code")
    check("British English is required", "British English" in prompt)
    check("the reviewer is told it cannot run commands",
          "cannot run commands" in prompt)
    other = devpair.build_prompt("review", "x", "y", {}, None)
    check("other modes keep the dev-pair role", "DEV PAIR" in other)


@isolated
def test_verify_verdicts_parse_and_gate(base):
    print("\n[verify] APPROVE/REVISE/DO NOT USE parse, and the bad ones fail the gate")
    cases = {
        "APPROVE": False,
        "APPROVE WITH MINOR EDITS": False,
        "REVISE BEFORE USE": True,
        "DO NOT USE": True,
    }
    for verdict, should_fail in cases.items():
        resp = f"## PASS 5 — VERDICT\n{verdict}\n\nSome reasoning."
        got = devpair.parse_verdict(resp)
        check(f"parses {verdict!r}", got == verdict, f"got {got!r}")
        failed, _ = devpair.gate_failed(resp)
        check(f"gate {'blocks' if should_fail else 'passes'} on {verdict!r}",
              failed is should_fail)
    # Longest-match: "APPROVE WITH MINOR EDITS" must not degrade to "APPROVE".
    check("longest verdict wins",
          devpair.parse_verdict("## VERDICT\nAPPROVE WITH MINOR EDITS")
          == "APPROVE WITH MINOR EDITS")
    # verify uses [CRITICAL] where devpair uses [BLOCKER]; the gate must count both
    # or a review full of critical findings would pass.
    crit = "## PASS 5 — VERDICT\nAPPROVE\n\n[CRITICAL] something will break"
    check("[CRITICAL] is counted as a blocking finding",
          devpair.count_blockers(crit) == 1, f"got {devpair.count_blockers(crit)}")
    failed, reason = devpair.gate_failed(crit)
    check("an APPROVE with a [CRITICAL] finding still fails the gate", failed is True,
          "a critical finding passed the gate")
    check("[BLOCKER] still counted too", devpair.count_blockers("[BLOCKER] x") == 1)


@isolated
def test_verify_mode_is_wired_into_the_cli(base):
    print("\n[verify] verify is a real subcommand with the same guards as the rest")
    src = Path(devpair.__file__).read_text()
    check("registered in the mode loop", '"followup", "verify"' in src)
    check("has an ASK_HINT", "verify" in devpair.ASK_HINT)
    check("documented in the CLI epilog", "post-hoc six-pass critique" in src,
          "epilog must state the same pass count as the canonical skill")
    # It is a paid call like any other: same family guard, same ledger, same cap.
    set_driver("glm-5.3", "zai")
    args = argparse.Namespace(
        mode="verify", ask="check this", focus=None, diff=False, diff_ref=None,
        files=None, plan=None, error=None, cmd=None, reviewer=None,
        with_model="kimi-coding/kimi-k3", driver="zai/glm-5.3", requested_by="user",
        session=None, timeout=5, budget=0, gate=False, json=False, dry_run=True,
        verbose=False)
    rc = devpair.cmd_pair(args)
    check("verify --dry-run exits 0", rc == 0)
    check("and stays free (no ledger entry)", devpair.runs_today() == 0)


@isolated
def test_verdict_regex_tolerates_real_model_formatting(base):
    print("\n[verify] the verdict parser accepts the forms models actually emit")
    # Being strict here does NOT fail safe: an unparseable verdict fails the
    # gate, so a well-formed review gets rejected for its punctuation.
    cases = {
        "## VERDICT\nSHIP AFTER FIXES": "SHIP AFTER FIXES",
        "## PASS 5 — VERDICT\nAPPROVE": "APPROVE",
        "PASS 5 — VERDICT\nAPPROVE": "APPROVE",          # no heading hashes
        "## VERDICT: APPROVE": "APPROVE",                 # inline, colon
        "VERDICT: DO NOT USE": "DO NOT USE",              # bare inline
        "VERDICT — REVISE BEFORE USE": "REVISE BEFORE USE",
        "## REMAINING VERDICT\nPROCEED WITH CHANGES": "PROCEED WITH CHANGES",
    }
    for text, want in cases.items():
        got = devpair.parse_verdict(text)
        check(f"parses {text.splitlines()[0][:30]!r}", got == want, f"got {got!r}")
    # ...but prose that merely mentions the word must NOT match.
    check("prose mentioning 'verdict' is not a verdict",
          devpair.parse_verdict("I gave my verdict earlier.\nIt was fine.") is None,
          "a false positive would silently mis-gate")
    check("no verdict at all -> None", devpair.parse_verdict("no verdict here") is None)


def _canonical_skill_path():
    """Locate verify-results/SKILL.md — repo sibling, then this machine's Hermes
    home. HERMES_HOME/LOCALAPPDATA must be honoured: hardcoding ~/.hermes made
    the pin silently degrade to its weak fallback on every Windows install."""
    import pathlib
    here = pathlib.Path(__file__).resolve().parent
    homes = []
    env = os.environ.get("HERMES_HOME")
    if env:
        homes.append(pathlib.Path(env))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        homes.append(pathlib.Path(local) / "hermes")
    homes.append(pathlib.Path.home() / ".hermes")
    # devpair.py lives in <home>/devpair/, so its parent IS the home when installed
    homes.append(pathlib.Path(devpair.__file__).resolve().parent.parent)

    cands = [here.parent / "verify-results" / "SKILL.md"]
    for h in homes:
        cands.append(h / "skills" / "productivity" / "verify-results" / "SKILL.md")
    for c in cands:
        if c.is_file():
            return c
    for h in homes:
        if (h / "skills").is_dir():
            for c in (h / "skills").rglob("verify-results/SKILL.md"):
                return c
    return None



@isolated
def test_verify_template_matches_the_verify_results_skill(base):
    print("\n[verify] the routed template is pinned to the CANONICAL skill file")
    # devpair's SHAPES["verify"] and verify-results/SKILL.md are two copies of one
    # contract. GLM-5.3 caught them drifting (5 passes vs 6); the first version of
    # this test then compared the template against hardcoded strings — editing the
    # SKILL still passed green. GPT-5.6 Luna called that theatre and was right.
    # This reads the real file.
    import re as _re
    shape = devpair.SHAPES["verify"]
    tmpl = _re.findall(r"## (PASS \d+) — ([^\n]+)", shape)

    canon_path = _canonical_skill_path()
    if canon_path is None:
        # Not installed (CI, fresh clone). Pin the template's own shape so the
        # test still has teeth, and say plainly what was not compared.
        check("canonical SKILL.md not found — template shape checked alone",
              len(tmpl) == 6, f"got {len(tmpl)}: {tmpl}")
        return

    canon = canon_path.read_text(encoding="utf-8")
    skill = _re.findall(r"### (PASS \d+) — ([^\n]+)", canon)
    check(f"canonical skill found at {canon_path.name}", bool(skill), "no PASS headings")
    check("same number of passes", len(tmpl) == len(skill),
          f"template {len(tmpl)} vs skill {len(skill)}")
    for (tn, tt), (sn, st) in zip(tmpl, skill):
        norm = lambda s: " ".join(s.split()).rstrip(".").upper()
        check(f"{tn} title matches the skill", norm(tt) == norm(st),
              f"template {tt!r} vs skill {st!r}")

    # Normative clauses that must exist on BOTH sides, or the routed reviewer is
    # held to a weaker contract than the inline one.
    for clause, tkey, skey in (
        ("evidence basis demanded", "EVIDENCE BASIS", "EVIDENCE BASIS"),
        ("partial view caps the verdict", "REVISE BEFORE USE", "cap the verdict at REVISE BEFORE USE"),
        ("PASS 2 not double-counted", "PASS 2 records check status only", "PASS 2 records *check status*"),
    ):
        check(f"{clause} (template)", tkey in " ".join(shape.split()), clause)
        check(f"{clause} (skill)", skey in " ".join(canon.split()), clause)

    # Every verdict the skill defines must be one the gate can actually read.
    for v in _re.findall(r"^\| `([A-Z][A-Z ]+)` \|", canon, _re.M):
        parsed = devpair.parse_verdict(f"## PASS 6 — VERDICT & WHAT HAPPENS NEXT\n{v}\nx")
        check(f"gate can parse verdict {v!r}", parsed == v, f"got {parsed!r}")


def main():
    print("devpair regression tests")
    print("=" * 60)
    for t in (
        test_never_self_reviews,
        test_refuses_when_no_independent,
        test_explicit_override_allowed,
        test_empty_order_falls_back,
        test_candidates_shared_between_pick_and_retry,
        test_session_path_no_side_effect,
        test_dry_run_creates_nothing,
        test_sh_surfaces_failure,
        test_bad_diff_ref_not_reported_as_no_diff,
        test_run_reviewer_reports_exit_code,
        test_clip_omitted_count_accurate,
        test_reviewer_gets_no_tools,
        test_driver_flag_overrides_config_and_env,
        test_same_family_guard_uses_explicit_driver,
        test_followup_empty_session_warns,
        test_save_session_atomic_no_litter,
        test_diff_ref_uses_merge_base,
        test_no_phantom_cmd_from_subcommand,
        test_secrets_never_reach_the_prompt,
        test_ask_focus_and_history_are_redacted_too,
        test_prompt_templates_survive_the_redactor,
        test_redact_secrets_unit,
        test_unknown_family_fails_closed,
        test_family_inferred_from_provider,
        test_pick_reviewer_honours_driver,
        test_untracked_files_are_read_not_just_named,
        test_missing_hermes_binary_is_soft_failure,
        test_parse_verdict_and_gate,
        test_conflicting_verdicts_fail_closed,
        test_gate_exit_code_end_to_end,
        test_verify_claims_catches_hallucinated_anchors,
        test_doctor_probes_in_parallel,
        test_budget_caps_total_walltime,
        test_token_estimates_recorded,
        test_prune_respects_age_and_active_session,
        test_banner_survives_a_legacy_console_encoding,
        test_hermes_binary_resolves_through_pathext,
        test_hermes_home_resolution_is_portable,
        test_roster_is_machine_local,
        test_roster_ignores_empty_or_broken_config,
        test_with_model_is_user_choice,
        test_with_model_bad_input_refuses_clearly,
        test_opaque_roster_entry_cannot_fake_independence,
        test_resolve_family_never_stops_on_unknown,
        test_with_unverifiable_target_is_flagged,
        test_unverifiable_flag_covers_every_selection_path,
        test_unknown_family_is_never_called_same_family,
        test_independence_state_is_reported_to_callers,
        test_with_and_reviewer_together_refuses,
        test_ledger_records_every_paid_run,
        test_daily_cap_is_a_hard_stop,
        test_attestation_is_optional_then_enforced,
        test_dry_run_is_free_and_never_logs,
        test_authorize_gates_before_the_paid_call,
        test_audit_command_surfaces_unattributed_runs,
        test_cap_survives_concurrent_runs,
        test_unwritable_ledger_fails_closed_only_when_enforcing,
        test_corrupt_ledger_cannot_undercount_a_cap,
        test_torn_line_does_not_eat_the_next_record,
        test_wrong_shaped_config_does_not_brick_the_cli,
        test_cap_holds_across_real_processes,
        test_unreadable_ledger_is_not_treated_as_zero,
        test_cap_refuses_when_it_cannot_lock,
        test_verify_mode_speaks_verify_results_vocabulary,
        test_verify_verdicts_parse_and_gate,
        test_verify_mode_is_wired_into_the_cli,
        test_verdict_regex_tolerates_real_model_formatting,
        test_verify_template_matches_the_verify_results_skill,
    ):
        t()
    print("\n" + "=" * 60)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"  FAILED: {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
