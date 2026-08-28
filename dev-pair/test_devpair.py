#!/usr/bin/env python3.11
"""Regression tests for devpair. Pins the defects the pair found.

Run: python3.11 test_devpair.py   (or: python3.11 -m pytest test_devpair.py)
No network: every test targets selection, side-effect, and error-propagation
logic. The one reviewer-invocation test uses a deliberately invalid provider.
"""
import argparse
import json
import os
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
            orig = (devpair.BASE, devpair.SESSIONS, devpair.CONFIG, devpair.CURRENT)
            devpair.BASE = base
            devpair.SESSIONS = base / "sessions"
            devpair.CONFIG = base / "config.json"
            devpair.CURRENT = base / "current_session"
            try:
                fn(base)
            finally:
                devpair.BASE, devpair.SESSIONS, devpair.CONFIG, devpair.CURRENT = orig
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
def test_gate_exit_code_end_to_end(base):
    print("\n[gate] --gate is opt-in; default stays advisory (exit 0)")
    import inspect
    src = inspect.getsource(devpair.cmd_pair)
    check("gate returns exit 2, distinct from 1 (backend failure)",
          "return 2" in src, "no distinct gate exit code")
    check("gate is conditional on args.gate", "args.gate and gate_fail" in src)


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


# --- PORTABILITY: the tool must find the right home on any machine ----------
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
        test_redact_secrets_unit,
        test_unknown_family_fails_closed,
        test_family_inferred_from_provider,
        test_pick_reviewer_honours_driver,
        test_untracked_files_are_read_not_just_named,
        test_missing_hermes_binary_is_soft_failure,
        test_parse_verdict_and_gate,
        test_gate_exit_code_end_to_end,
        test_verify_claims_catches_hallucinated_anchors,
        test_doctor_probes_in_parallel,
        test_budget_caps_total_walltime,
        test_token_estimates_recorded,
        test_prune_respects_age_and_active_session,
        test_hermes_home_resolution_is_portable,
        test_roster_is_machine_local,
        test_roster_ignores_empty_or_broken_config,
        test_with_model_is_user_choice,
        test_with_model_bad_input_refuses_clearly,
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
