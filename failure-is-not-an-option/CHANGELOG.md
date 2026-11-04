# Changelog

## 0.2.0 — 2026-11-04

- Rewritten to the owner's intent: take the negativity out of models. Assume it can be done, no excuses or premature blockers, change approach until it works, finish everything and prove it.
- Integrity kept as what makes "done" real: never fake results, never bypass security or authority, protect existing work, sessions and secrets.
- Replaces the 0.1.0 draft's long procedural boundary text (about 1,470 words → about 550).
- Independent review (GLM-5.3, sandboxed, three rounds): round 1 changes required (no self-certified exhaustion; a dead end is a finding, never an exit; mandate limit vs "out of scope" excuse), round 2 approve with two minor notes (applied: evidence-triggered dead end; an unanswered question stays in alerts), round 3 approve on the exact released text. Open minor note: "retrying the alert" could name its antecedent more explicitly.
- Tests on the released text: `test_failure_principle.py` 8/8 and `test_install.py` 13/13 on macOS, Windows (3.11) and Linux (WSL, 3.12).

## 0.1.0 — unreleased candidate

- Draft the task-persistence, evidence, authorised-help, side-effect reconciliation and scoped-stop guidance.
- State explicitly that guidance does not implement durable approvals, recovery, notification or managed continuation.
- Candidate only: independent exact-content review, behavioural and platform verification, owner-specific onboarding and release gates remain outstanding. The installer does not run these repository-level tests automatically.
