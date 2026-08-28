---
name: dev-pair
description: "Second-opinion critique/review from a different LLM."
version: 1.1.3
author: Justin Johnson
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [code-review, critique, supervision, cross-model, debugging, pairing]
    related_skills: [fail-closed-code-review, requesting-code-review, systematic-debugging, brainstorming]
---

# Dev Pair — The Second Pair of Eyes

## When to Use

Load this skill whenever you are about to build, review, debug, or choose
between designs for anything non-trivial — and call `devpair` in **proactively**,
without being asked. See the table below for the exact trigger moments.

`devpair` is a supervisory review partner that runs on a **different LLM** than the
agent doing the work. It critiques direction, challenges approach, finds bugs, and
asks the questions that expose gaps.

It does **not** write the implementation and does **not** do the work twice.
It is supervision, not duplication.

## Setup

1. Copy `devpair.py` somewhere stable (e.g. `~/.hermes/devpair/devpair.py`).
2. Install the `devpair` wrapper script onto your PATH (e.g. `~/.local/bin/`)
   and `chmod +x` it. Edit the interpreter candidate list at the top if your
   python3.11 lives elsewhere.
3. Edit the `REVIEWERS` dict near the top of `devpair.py` to match the provider
   IDs and models in your own Hermes `config.yaml`. Each reviewer must be
   reachable via `hermes -z "..." -m MODEL --provider PROVIDER -t ""`.
4. Run `devpair doctor` to verify your backends answer.

Requires: Hermes Agent CLI on PATH, python3.11+, PyYAML, git (for diff modes).

## When to Call It In

Call the pair in **proactively** — do not wait to be asked. The whole value is
catching things *before* effort is sunk in.

| Moment | Command |
|---|---|
| Chosen an approach, before building | `devpair critique --plan PLAN.md` |
| Non-trivial code written | `devpair review --diff` |
| Stuck on a bug >2 attempts | `devpair debug --error log --files a.py` |
| Two designs, unsure which | `devpair alt --ask "A or B?"` |
| Answering the pair's critique | `devpair followup --ask "..."` |

Specifically, always call it for: security/auth boundaries, concurrency, data
migrations, anything touching credentials or money, a design that will be hard to
reverse, and any bug that survived two fix attempts.

**Skip it** for: typos, formatting, renames, one-line obvious fixes, and work the
user explicitly wants done fast without review.

## Commands

```bash
devpair critique --plan PLAN.md --ask "worth building this way?"
devpair review   --diff                      # uncommitted + untracked
devpair review   --diff-ref main --focus "error paths, cleanup"
devpair review   --files src/auth.py src/session.py
devpair debug    --error /tmp/fail.log --files src/router.py
devpair debug    --cmd "pytest -x tests/test_auth.py"   # runs it, includes output
devpair alt      --ask "cron job or long-running daemon?"
devpair followup --ask "Fixed 1 and 3. Disagree with 2 because ..."

devpair log            # everything the pair has said this session
devpair reset          # fresh pairing session (new feature = new session)
devpair doctor         # check reviewer backends (probed in parallel)
devpair prune --days 30   # delete old sessions (never the active one)
```

Gating: add `--gate` to exit **2** on DO NOT SHIP / NEEDS WORK / STOP /
RECONSIDER, on any `[BLOCKER]`, or on an unparseable verdict (fails closed).
Default is advisory (always exit 0). `--budget N` caps total wall-clock across
all backend attempts. Both are opt-in and safe to add to CI.

Useful flags: `--focus` steers attention, `--reviewer <name>` forces a backend,
`--driver PROVIDER/MODEL` declares the live session model (see The One Rule),
`--json` for machine-readable output, `--session NAME` for parallel work,
`--timeout N` (default 420s), `--dry-run` shows who would review and why without
calling anyone or touching session state. `--diff-ref REF` diffs merge-base
style (`REF...HEAD` — your branch's changes, not the ref's) and appends any
uncommitted work as a separate section.

## The One Rule You Must Not Skip

**Always pass the LIVE session model as `--driver PROVIDER/MODEL`** on every
`devpair` call. The tool's core guarantee — the reviewer is a different model
family than the one doing the work — is keyed off the driver identity, and its
default source (`config.yaml` `model.default`) is only a guess. If the session
is running on an override (one model while the config default is another),
the guard will happily pick the driver's own family as "independent". You know
what model YOU are; the config file doesn't. Env vars `DEVPAIR_DRIVER_MODEL` /
`DEVPAIR_DRIVER_PROVIDER` work too.

## How It Picks a Reviewer

Reads the driver model (from `--driver`, then `DEVPAIR_DRIVER_*`, then
`config.yaml`), then picks the first reviewer from the configured order that
is a **different model family**, then every other independent reviewer as
retry candidates. If every candidate is same-family it REFUSES with the skip
reasons — it never silently self-reviews (`--reviewer` is the deliberate
override). Backend failure falls through the full independent list.

The shipped roster is an example: a Kimi model, a Claude model, a GLM model,
and a small local Qwen via LM Studio (works offline). Yours should name
whatever providers your Hermes install has.

## The Rules That Make It Work

1. **Give it real evidence.** `--diff`/`--files` beats describing the code. The
   harness gathers context itself and passes it with `-t ""` (no tools), so the
   reviewer is read-only by construction — it physically cannot edit your code.
2. **Always `followup` after acting on a review.** This is what makes it a pair
   rather than a one-shot linter. It remembers what it said, notices what you
   silently dropped, and concedes when you out-argue it.
3. **Disagreeing is legitimate.** Push back with reasoning. A pair you always
   obey is just a slow linter. But answer every point — it will notice silence.
4. **Report its verdict to the user honestly**, including when it says STOP or
   DO NOT SHIP. Never quietly bury a critique you disagree with — surface it
   with your counter-argument and let the user decide.
5. **`devpair reset` per feature.** Session memory is the point, but stale
   context from unrelated work pollutes the review.

## Verdicts

- critique/alt/followup → `PROCEED` / `PROCEED WITH CHANGES` / `RECONSIDER` / `STOP`
- review → `SHIP` / `SHIP AFTER FIXES` / `NEEDS WORK` / `DO NOT SHIP`

Findings are ranked `[BLOCKER|MAJOR|MINOR]` with `file:line`. "None material" is
a valid answer — the pair is instructed not to manufacture problems to look useful.

## Pitfalls

- **Reviewing with no evidence** produces generic advice. Attach the diff or files.
- **Same-family review** — heed the warning, pass `--reviewer` or fix `--driver`.
- **Huge diffs** get truncated at ~60k chars. Review in slices with `--files`.
- **Treating it as an oracle.** It has no access to your terminal, tests, or
  runtime — it reasons from what you pasted. Verify its claims before acting on
  them, especially file:line references.
- **First call after idle** can take 60-90s. That is the model thinking, not a hang.
- **Small local reasoning models are slow reviewers.** A 9B-class local model
  emits a long reasoning trace before content — even a trivial probe takes
  ~2 minutes, and a real review with a large diff can exceed the 420s default.
  When falling back to local, pass `--timeout 900`.
- **`hermes -z` needs a non-interactive env**; the wrapper handles this. Don't
  invoke the reviewer through `hermes chat`.
- **Run `devpair doctor` before relying on a backend** — provider auth rots
  silently, and doctor is the cheap way to find out.
- **Verify its findings before acting.** In the session that built this tool the
  pair raised a confident BLOCKER that was simply wrong (an IndexError that was
  impossible because of a falsy-default idiom). It conceded immediately when
  shown the test. Run the check, then act.
- **Watch for regressions from its own suggestions.** One of its good ideas was
  implemented in a way that reintroduced a side-effect it had itself flagged a
  turn earlier. Run the test suite after taking its advice.

## Safety Behaviours You Should Know

- **Secrets are redacted before send.** Everything gathered passes through
  `redact_secrets()` at one chokepoint: vendor tokens (`sk-`, `ghp_`, `AKIA`,
  `xox`, `AIza`, `ya29`), JWTs, private-key blocks, URL passwords, secret-looking
  `KEY=value` assignments and `Authorization:` headers become `[REDACTED:kind]`.
  A stderr note reports the count. This is defence in depth, not a guarantee —
  if the repo is full of live credentials, check the evidence before sending.
- **Independence fails closed.** If the driver's family can't be identified from
  the model name, it is inferred from the provider; if it still can't, devpair
  REFUSES rather than offering an unprovable guarantee. Pass `--driver` to fix.
- **New/untracked files are included as code**, not just listed — `git diff`
  can't show them, so new-file-only work would otherwise be reviewed blind
  (max 5 files, 8k chars each; binaries skipped).
- **A missing `hermes` binary is a soft failure** — it falls through to the next
  backend instead of crashing.

- **The pair's `file:line` claims are auto-verified.** Anchors that name a
  missing file or a line past EOF are listed under `UNVERIFIED CLAIMS` — treat
  those findings with extra scepticism; the rest checked out against the tree.
- **Each turn reports token estimates** and stores the parsed verdict, blocker
  count and any unverified claims on the session, so `--json` gives a caller
  everything it needs without re-parsing prose.

## Tests

`python3.11 test_devpair.py` (or pytest) — 32 regression tests (125 checks) pinning reviewer
selection, self-review refusal, driver-identity precedence, session
side-effects/atomicity, merge-base diffs, error propagation, and truncation
maths. No network required. Run after any change.

## Files

- `devpair.py` — implementation
- `test_devpair.py` — 18 regression tests
- `devpair` — CLI wrapper (smoke-tests an interpreter chain so a broken venv
  doesn't kill the tool; edit candidates for your machine)

State at runtime lives under `~/.hermes/devpair/`: `sessions/*.json` (full
pairing transcripts), `current_session` (pointer), and optional `config.json`
(`{"order": ["claude","kimi","local"]}`) to reorder reviewer preference.
