---
name: dev-pair
description: "Second-opinion critique/review from a different LLM."
version: 1.1.16
author: Justin Johnson
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [code-review, critique, supervision, cross-model, debugging, pairing]
    related_skills: [fail-closed-code-review, requesting-code-review, systematic-debugging, brainstorming]
---

# Dev Pair — The Second Pair of Eyes

## When to Use

**This skill is USER-INVOKED ONLY. Never call `devpair` on your own initiative.**

Every devpair run spends a second model's tokens on top of your own. On small
or routine work that is pure waste, and the decision to spend it belongs to the
user, not to you. Load this skill for the how; wait to be asked for the when.

> **Honest limitation:** the instruction above is behavioural. What backs it is
> in the tool: every paid run is written to an append-only ledger before the
> call (`devpair audit`), and `daily_cap` in `config.json` is a hard refusal the
> process obeys no matter what an agent believes it was told. Attestation
> (`--requested-by`) is a record, not a lock — a lying caller can fill it in.
> The cap is the part that actually bites; the ledger is how you catch the rest.

**Run it only when the user explicitly asks**, in words like:
"get a second opinion", "run it past the dev pair", "devpair this",
"have another model review this", "what does the pair think".

If you believe a review is genuinely warranted — a security boundary, a
concurrency change, a migration, a bug that has survived two fixes — **offer it
in one sentence and stop**: "Want me to run this past the dev pair before we
commit?" Then do nothing until they answer. Do not run it to be thorough, do
not run it because the change feels big, and never run it as a habit.

`devpair` is a supervisory review partner that runs on a **different LLM** than
the agent doing the work. It critiques direction, challenges approach, finds
bugs, and asks the questions that expose gaps.

It does **not** write the implementation and does **not** do the work twice.
It is supervision, not duplication.

## Accountability — the part that is not prose

Three mechanisms, in descending order of how much they can be trusted:

| Mechanism | What it does | Can an agent evade it? |
|---|---|---|
| `daily_cap` in `config.json` | Hard ceiling on paid runs per day; the process refuses | **No** |
| Invocation ledger | Every paid run appended before the call, with who asked | No (but it only records) |
| `--requested-by WHO` | States who asked for this run | Yes — it is an attestation |

Count-and-append happen under one file lock, so concurrent runs cannot both
slip past the same cap. When a cap or `require_attestation` is in force the path
**fails closed**: if the ledger cannot be written, cannot be read, or has
unreadable lines that make today's count unprovable, the run is refused rather
than allowed on an uncountable quota — unknown usage is never treated as zero.
If the filesystem offers no locking at all, a capped run refuses instead of
pretending; `allow_unlocked_cap: true` opts in to an advisory cap. Keep the
ledger on local disk: NFS/SMB can report a lock without excluding other hosts.
With no cap set the ledger is best-effort and never blocks a review.

```bash
devpair audit                 # who ran the pair, when, and who asked
devpair audit --days 1        # just today
devpair audit --json          # machine-readable
```

`devpair audit` flags runs that named nobody as the requester — those are
exactly where an agent self-initiating would show up. Set a ceiling with
`{"daily_cap": 10}` in `<hermes-home>/devpair/config.json`; add
`{"require_attestation": true}` to make `--requested-by` mandatory.

**When you call devpair on the user's behalf, pass `--requested-by user`.** Do
not pass it otherwise — an attestation you filled in yourself is worse than
none, because it launders an unasked-for run as an authorised one.

## Choosing the reviewer — the user decides

If the user names a model, use it. That instruction outranks the roster, the
config order, and the same-family guard:

```bash
devpair review --diff --driver <live-model> --with anthropic/claude-opus-5
```

`--with PROVIDER/MODEL` uses that model whether or not it is in the roster.
Same-family (a Claude driver reviewed by Claude) prints a warning and proceeds —
it is the user's call, not a hard block.

If they name a roster entry instead ("use kimi"), `--reviewer kimi` is the
shorter form. If they express no preference, let the tool pick the first
independent reviewer and **tell them which model answered** so they can redirect.

## Setup

Install with the repo's installer — it finds this machine's Hermes home, writes
the CLI, and generates a reviewer roster from your own configured providers:

```bash
curl -fsSL https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/install.py | python3 - dev-pair
devpair doctor        # confirm the backends answer
```

Manual install: copy `devpair.py` + `test_devpair.py` into
`<hermes-home>/devpair/`, put a shim on PATH that runs it, then declare your
reviewers in `<hermes-home>/devpair/config.json` (see *How It Picks a
Reviewer*). Do NOT edit the `REVIEWERS` dict in the source — config.json
overrides it and survives upgrades.

Requires: Hermes CLI on PATH, Python 3.8+, PyYAML, git (for diff modes).

## What Each Mode Is For

When the user asks for a review, pick the mode that matches what they want:

| They want | Command |
|---|---|
| The approach checked before building | `devpair critique --plan PLAN.md` |
| Written code reviewed | `devpair review --diff` |
| Help with a stuck bug | `devpair debug --error log --files a.py` |
| A choice between two designs | `devpair alt --ask "A or B?"` |
| To answer the pair's last critique | `devpair followup --ask "..."` |
| Finished work verified before it is used | `devpair verify --files report.md` |

Always add `--driver PROVIDER/MODEL` (see The One Rule) and, because the user
asked for this run, `--requested-by user`. If they named a reviewer, add
`--with PROVIDER/MODEL`.

**Cost note:** each run is a second model's full context window. Give it the
narrowest useful evidence — `--files` on the two files that matter beats
`--diff` across forty. `--dry-run` shows who would review and how much context
would be sent, and costs nothing.

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

# user picked the pair themselves:
devpair review   --diff --with anthropic/claude-opus-5

devpair verify   --files report.md   # six-pass post-hoc critique (verify-results)
devpair audit          # who ran the pair, when, and who asked (free)
devpair log            # everything the pair has said this session
devpair reset          # fresh pairing session (new feature = new session)
devpair doctor         # check reviewer backends (probed in parallel)
devpair prune --days 30   # delete old sessions (never the active one)
```

Gating: add `--gate` to exit **2** on DO NOT SHIP / NEEDS WORK / STOP /
RECONSIDER, on any `[BLOCKER]`, on an unparseable verdict, or on two *different*
verdicts in one review (all fail closed — an answer the gate cannot read, or
cannot pick between, is never a pass).
Default is advisory (always exit 0). `--budget N` caps total wall-clock across
all backend attempts. Both are opt-in and safe to add to CI.

Useful flags: `--focus` steers attention, `--with PROVIDER/MODEL` uses any model
the user names (roster or not), `--reviewer <name>` picks a roster entry,
`--driver PROVIDER/MODEL` declares the live session model (see The One Rule),
`--requested-by WHO` records who asked (see Accountability),
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
2. **`followup` is how a review becomes a conversation** — it remembers what it
   said, notices what you silently dropped, and concedes when out-argued. But it
   is another paid call: run it when the user wants the loop closed, or offer it
   ("want me to put these fixes back to the pair?"), not automatically.
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
- verify → `APPROVE` / `APPROVE WITH MINOR EDITS` / `REVISE BEFORE USE` / `DO NOT USE`
  (six passes matching the verify-results skill, opening with an EVIDENCE BASIS line
  that caps the verdict when the reviewer only saw part of the work;
  `[VERIFIED ERROR]`/`[UNSUPPORTED CLAIM]`/`[ASSUMPTION]` labels; PASS 5 is CHECKS
  THAT WOULD SETTLE THIS, naming evidence it could not gather itself)

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

- **Secrets are redacted before send — from the WHOLE prompt.** Gathered
  evidence is scrubbed, and so is the assembled prompt: `--ask`, `--focus` and
  the replayed prior turns all pass through `redact_secrets()` before the call.
  That last one matters most — a reviewer that quoted a credential back at you in
  turn 1 would otherwise re-send it verbatim on every later turn of the session.
  Vendor tokens (`sk-`, `ghp_`, `AKIA`, `xox`, `AIza`, `ya29`), JWTs, private-key
  blocks, URL passwords, secret-looking `KEY=value` assignments and bearer tokens
  in `Authorization` headers become `[REDACTED:kind]`. A stderr note reports the
  count and says whether it came from the evidence or from your question. This is
  defence in depth, not a guarantee — if the repo is full of live credentials,
  check the evidence before sending.
- **Independence fails closed.** If the driver's family can't be identified from
  the model name, it is inferred from the provider; if it still can't, devpair
  REFUSES rather than offering an unprovable guarantee. Pass `--driver` to fix.
- **An unprovable reviewer is labelled, never assumed safe.** If a reviewer's
  family can't be resolved from either its model name or its provider, it is
  marked `INDEPENDENCE UNVERIFIED` on every path — automatic selection,
  `--reviewer`, and `--with` — and proven-independent reviewers are preferred
  ahead of it. It is still usable as a fallback; it just never claims a
  guarantee it cannot support. `--json` reports this as
  `independence: verified | unverified | same-family`.
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

`python3.11 test_devpair.py` (or pytest) — 66 regression tests (344 checks) pinning reviewer
selection, self-review refusal, driver-identity precedence, session
side-effects/atomicity, merge-base diffs, error propagation, truncation
maths, prompt-wide redaction, and the `--gate` exit codes (driven through the
real CLI with a stubbed backend, not asserted against source text). No network
required. Run after any change.

## Files

- `devpair.py` — implementation
- `test_devpair.py` — 66 regression tests (344 checks)
- `devpair` — reference CLI wrapper. The installer generates its own shim
  (`devpair.cmd` on Windows, an interpreter-chain bash script on POSIX), so
  this file is only needed for a manual install.

State at runtime lives under `<hermes-home>/devpair/`: `sessions/*.json` (full
pairing transcripts), `current_session` (pointer), `invocations.jsonl`
(append-only run ledger, read it with `devpair audit`), and optional
`config.json` — `order` to reorder reviewer preference, `reviewers` to declare
your own roster, `daily_cap` for a hard ceiling on paid runs per day, and
`require_attestation` to make `--requested-by` mandatory.
