# Offline dev-pair assessment

Use source inspection and deterministic fixtures when assessing capabilities.
The user asking for recommendations has not authorised a billed second opinion.
Do not call the real reviewer or `doctor --live` merely to compare features
(static `devpair doctor` makes zero model calls and is fine).

## Isolation

- Resolve the installed launcher, source and tests from this machine; do not
  assume a Unix PATH lookup finds a Windows `.cmd` launcher.
- Put fixture state, temporary files, config and ledgers under the active
  profile's scratch directory. Redirect `HERMES_HOME`, `TMP`, `TEMP`, `TMPDIR`
  and Python's tempfile directory before importing/running fixtures.
- Stub backend execution with a harmless local subprocess or an injected test
  backend. Keep the production source, roster and model configuration untouched.
- Ensure PATH-resolution tests see no `DEVPAIR_HERMES_CMD` override: a global
  offline prefix changes what they are testing. Remove that override only for
  their read-only resolver checks, restoring it before any invocation test.
  (Running `test_devpair.py` directly with a global override fails exactly the
  three resolver checks — a harness artefact, not a defect.)
- Record the suite's final check counts separately from extra fixtures. A green
  suite is not evidence that untested edge cases work. Distinguish a failing test
  harness from a defect in production code.
- Never run a pre-1.2.0 devpair against a real backend unshimmed: it passes
  `-t ""`, which gives the reviewer the full tool set under YOLO approvals.

## What v1.2.0 enforces (and its remaining limits)

- **Config:** strict tri-state for paid paths — a present-but-invalid
  `config.json` refuses paid runs; roster/help readers stay tolerant.
- **Accounting:** every attempt (fallbacks, live doctor probes) is reserved
  before the call; outcome records are not counted as spend; a held ledger lock
  refuses rather than spending unlocked.
- **Gate:** coverage comes from the harness manifest (clipped sections, omitted
  files with reasons, failed `git diff`/`ls-files`, binary untracked files).
  Partial evidence fails the gate unless `--allow-partial`; unknown always fails.
  Limit: a reviewer can still approve a defect it saw and misjudged — the gate
  bounds evidence scope, not reasoning quality.
- **Citations:** checked for packet membership (path suffix, or a location
  reference such as a traceback line in the packet). Limit: line ranges inside a
  diff hunk are not checked.
- **Sessions:** contained names, per-project pointers, per-session locks,
  redaction at load and at rest, quarantine of unparseable files.
  Limit: locks are advisory on network filesystems.
- **Transport/identity:** file transport above the argv limit; receipts from
  `--usage-file` (inline) or Hermes' session store (file). Receipts are Hermes'
  record of the route, not cryptographic proof of the upstream model.
- **Prompts (Council crossover):** framing, stakes, confidence, flip condition
  and falsifier duties; harness gaps shown to the reviewer. No extra calls.

## Benchmark

Comparisons between versions or against the Council belong in the seeded-defect
benchmark (`workspace/devpair-bench`: pre-registered corpus, mechanical scorer,
baseline run through a zero-tool shim), not in ad-hoc impressions. One run per
condition is not a variance estimate.
