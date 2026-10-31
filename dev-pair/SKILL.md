---
name: dev-pair
description: "Second-opinion critique/review from a different LLM."
version: 1.2.9
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
| `daily_cap` in `config.json` | Hard ceiling on paid ATTEMPTS per day (every fallback and every live doctor probe counts) | Not through concurrent calls; a present-but-invalid config REFUSES paid runs |
| Invocation ledger | Every paid attempt reserved before the call (who asked, which reviewer), plus an outcome record after it | No (but it only records) |
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

The enforcement config is read strictly for paid paths: absent = no limits,
valid = enforced, and **anything else (unparseable JSON, a non-object, a cap
that is not a non-negative integer, a non-boolean `require_attestation`)
refuses every paid run** — it is never read as "unlimited". `--dry-run` and
`devpair audit` say `CONFIG INVALID` when that is the case. A ledger lock held
by another run for more than 30 s refuses the attempt rather than spending
outside the cap.

```bash
devpair audit                 # who ran the pair, when, and who asked
devpair audit --days 1        # just today
devpair audit --json          # machine-readable
```

`devpair audit` flags runs that named nobody as the requester — those are
exactly where an agent self-initiating would show up. Set a ceiling with
`{"daily_cap": 10}` in `<hermes-home>/devpair/config.json`; add
`{"require_attestation": true}` to make `--requested-by` mandatory.

To find the calls one task made, match by `run_id`. Every result carries it (in
`--json`, the human footer, and the `FAILED` line when no backend answered), and
each ledger attempt records it with the session name, joined to its outcome in
`devpair audit --json` (its `runs` list). Never reason from global daily counts.
On dev-pair 1.2.2 and older the ledger had no session name and `--json` had no
`run_id`; there, filter by working directory, reviewer and time window, and run
each batch from its own directory when attribution matters.

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

### More than one reviewer (a panel)

If the user asks for several reviewers, each one is a separate paid run, and two
defaults quietly break their independence:

- **Name each reviewer** (`--with` or `--reviewer`). Auto-pick always takes the
  first independent entry in the roster, so unnamed runs all reach the same model.
- **Give each reviewer its own `--session NAME`.** The implicit session belongs
  to the project, and later runs in it are sent the earlier turns, so the second
  reviewer would read the first one's critique and anchor on it. Separate
  sessions also keep each thread open for its own `followup`.

Send every reviewer the same revision of the artefact. Then triage every finding
from all of them (accepted, partly accepted, or rejected with the reason) into a
single revision. Where reviewers contradict each other, make the call yourself
and show the user both positions and your resolution. Never average them or drop
the minority view. Report one row per reviewer: verdict, finding counts by
severity, the model the route receipt says answered, coverage, and the evidence
`sha256` (which revision it saw). Attribute each adopted change to its source
(which reviewer, or you), and say where you departed from a reviewer's proposal
and why.

Running the panel:

- **Launch reviewers in parallel**, one background process each with its own
  `--session` and its own `--json` output file. The ledger and cap are locked,
  so concurrent runs are safe; running them one after another only doubles the
  wait.
- **Write your own findings list before opening any review.** Reading theirs
  first anchors you; comparing afterwards shows what only you caught and what
  you missed.
- **A second round on a revised artefact is a `followup` on each reviewer's own
  session** (paid again, so only when the user asks), with the new revision
  attached as evidence. Each reviewer re-checks its own earlier findings against
  the revision while staying blind to the others; ask it to lead with any
  earlier finding the revision integrated wrongly or incompletely.
- **After triage, probe every claim the artefact makes about real tools**: read
  the source, run `--help` or a dry run, inspect the actual data. Reviewers only
  read the text, so an artefact that misdescribes a tool passes all of them.
- **Anything you add after the last review is unreviewed.** Mark it so in the
  artefact and in your report, and put it before the panel at the next gate
  rather than presenting it as endorsed.

### Sequential co-development chains (cumulative contributors)

When the user names several models to contribute to one document in order — each
reads the draft plus the earlier contributors' raw reviews — run one paid
`critique` per contributor, strictly in sequence (each depends on the previous
output, so the parallel panel rules above do not apply), each in its own
`--session`:

- **Contributor N's evidence is the current draft plus the prior reviewers' raw
  responses.** Pass each earlier response as its own `--files` entry (watch the
  per-file cap; confirm `coverage: complete`) and let the contributor read them
  unfiltered — never substitute your triage summary for the raw reviews.
- **Preserve each contributor's exact input snapshot** (the draft as that
  contributor saw it) and its `--json` receipt next to the final artefact. The
  chain's provenance is only auditable if every packet survives.
- **`--gate` exit 2 is triage input in a chain, not a failed review.** A
  PROCEED WITH CHANGES verdict still fails the gate when the findings include a
  `[BLOCKER]`; in a chain that blocker is the next revision's input. Aggregate
  and report from route receipts (verdict, findings, reported model, coverage),
  not from gate exit codes.
- **Edits made after the last contributor are unreviewed.** Say so in the
  artefact's status line and in the report; presenting the chain as endorsing
  final bytes is a false provenance claim. A convergence round (all
  contributors re-review the final text) is a new set of paid calls — propose
  it, never auto-run it.
- **Carry the owner's non-negotiable wording verbatim through every revision.**
  When the user fixes a phrase as standing policy, keep it byte-identical; do
  not paraphrase the load-bearing line into a weaker variant and do not adopt a
  reviewer's softer rewrite — a hedged headline gives a lazy executor exactly
  the early exit the line exists to close.

### Named fallback ladders and the closeout state

When the user sets a ladder ("after N disagreements with X, try Y, then decide
yourself"), the spend is bounded only if you bound it in writing:

- **Count the ladder BEFORE the first paid call.** Record which rounds are
  already consumed, including rounds that predate the instruction (by run id),
  and what one "try" means: distinct original review scopes are distinct FIRST
  rounds, not retries of one repair. Spend against the written budget, never a
  fresh mental count.
- **Resolve a named fallback model to an exact provider/model before launching
  it.** A spoken name is not a route; if no configured provider/model matches
  exactly, report and ask. Never launch a lookalike.
- **Reviewer exhaustion waives nothing.** After the last allowed round YOU
  adjudicate every outstanding claim against the source and real outputs:
  reviewer agreement is not a vote that skips tests or gates, a verified serious
  defect is still fixed, and absent runtime evidence is never reported as done.
- **Persist the closeout state to a machine-readable file** whenever the loop
  can outlive the context window: the user's authority verbatim, scope limits,
  per-reviewer budgets consumed and remaining, exact model resolutions, and the
  final-ruling rule. The next window reads the file instead of re-deriving the
  budget, and cannot overspend by forgetting rounds it never saw.

## Setup

Install with the repo's installer — it finds this machine's Hermes home, writes
the CLI, and generates a reviewer roster from your own configured providers:

```bash
curl -fsSL https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/install.py | python3 - dev-pair
devpair doctor        # static check: zero model calls, free
devpair doctor --live --requested-by user   # PAID: one reserved, capped probe per backend
```

Manual install: copy `devpair.py` + `test_devpair.py` into
`<hermes-home>/devpair/`, put a shim on PATH that runs it, then declare your
reviewers in `<hermes-home>/devpair/config.json` (see *How It Picks a
Reviewer*). Do NOT edit the `REVIEWERS` dict in the source — config.json
overrides it and survives upgrades.

Requires: Hermes CLI on PATH, Python 3.8+, PyYAML, git (for diff modes).

### Calling it from an agent terminal

Bare `devpair` may not resolve there: the session PATH is assembled by the host
and need not carry `<hermes-home>/bin`, and git-bash on Windows mangles PATH, so
`devpair: command not found` does not mean it is missing. Call the installed
shim by its full native path, `<hermes-home>/bin/devpair` (`devpair.cmd` on
Windows; forward slashes under git-bash). The shim pins the interpreter and the
CLI location, so the full path is also the deterministic form for scripts and
background runs. Run static `devpair doctor` first: it validates config and
roster with zero model calls and prints the driver/reviewer table you are about
to spend against.

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

Before a named-model gated run, `--dry-run` with the exact intended `--driver`,
`--with`, `--requested-by`, evidence and `--gate` options. Inspect the selected
reviewer, evidence coverage, included files and packet size, then make the paid
call separately. Do not chain the dry run and the paid call in one shell
command: reading the dry run is the decision. A clean dry run is routing and
coverage evidence, not a verdict.

**`debug` emits analysis, not an approval verdict**, so `debug --gate` fails
closed and is the wrong gate for a debugging session. An advisory debug result
can carry `verdict: null` and a computed `gate_failed`. Judge whether the
analysis completed from its response, route receipt and coverage; do not spend
another paid call just to manufacture a verdict, and present it as diagnostic
advice, not approval of later changes.

### Reviewing a workflow, not just code

When the ask is "review all your work / the whole procedure", pass every script
in the pipeline with `--files` and put the architecture in `--ask`: what each
script does, how they chain, what runs on a schedule, and the operational
constraints (weak hardware, unattended runs). Add `--focus` naming the risk
classes: access control, data loss, silent failure. A cross-model review at this
level catches process defects no single-file review can see: identity resolved
process-wide in a multi-user server, a rebuild that deletes the good index
before the new one is validated, a queue that retries poison rows forever. In
`--json` output the verdict is `verdict`, blocker count `blockers`, evidence
`coverage`, and the full review text `response`. Verify each blocker against the
code before implementing, then run the test suite, because fixes for one finding
can regress another.

## Commands

**The examples below are abbreviated syntax** — they show each mode's own flags.
Every real paid call must also carry `--driver PROVIDER/MODEL` and, when the user
asked for it, `--requested-by user` (see The One Rule and Accountability). Only
the first example is written out in full:

```bash
devpair critique --plan PLAN.md --ask "worth building this way?" \
                 --driver <live-provider>/<live-model> --requested-by user

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
devpair doctor         # static: config, roster, CLI — zero model calls
devpair doctor --live --requested-by user   # PAID: probes each backend (reserved + capped)
devpair prune --days 30   # delete old sessions + stale sidecars (never an active one)
devpair prune --redact    # one-time: rewrite stored sessions through the redactor
```

Gating: add `--gate` to exit **2** on a failing verdict, on a highest-severity
finding, on an unparseable verdict, or on two *different* verdicts in one review
(all fail closed — an answer the gate cannot read, or cannot pick between, is
never a pass). The vocabulary differs by mode and the gate accepts **both**:

| Mode | Failing verdicts | Blocking severity |
|---|---|---|
| `critique` / `alt` / `followup` | RECONSIDER, STOP | `[BLOCKER]` |
| `review` | DO NOT SHIP, NEEDS WORK | `[BLOCKER]` |
| `verify` | DO NOT USE, REVISE BEFORE USE | `[CRITICAL]` |
| `debug` | *(emits no verdict)* | `[BLOCKER]` |

All six modes are covered. **`debug` has no verdict line at all**, so
`debug --gate` always fails closed — that is the unparseable-verdict rule, not a
bug, but it makes `--gate` the wrong tool for a debugging session.

`verify` mirrors verify-results and emits `[CRITICAL]` where every other mode
emits `[BLOCKER]`; the gate counts either, so a verify report full of
`[CRITICAL]` findings cannot pass under an `APPROVE`.
**The gate is coverage-aware.** Every run builds a harness-side evidence
manifest: what was sent, which sections were truncated, which requested files or
untracked files were left out (and why), failed `git diff` calls, and a sha256 of
the packet. An approval on PARTIAL evidence fails the gate (exit 2) — the
reviewer saying "I saw everything" cannot override the manifest. Pass
`--allow-partial` to accept it deliberately; the result is then labelled PARTIAL
on stderr and in `--json` (`coverage: partial`). Without `--gate` a partial
packet stays advisory but is still announced on stderr (`EVIDENCE PARTIAL`, even
with `--json`). Unknown coverage always fails.
`--strict-citations` additionally fails the gate when the reviewer cites a
`file:line` that does not exist or was not in the evidence it was sent (default:
advisory). The reviewer is also TOLD the harness-reported gaps in its prompt.

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

When you edit the roster in `config.json`: back the file up first; declare
`family` on any entry whose model and provider names do not reveal it (a
DeepSeek model, a custom endpoint), or it is labelled INDEPENDENCE UNVERIFIED
on every path; then confirm with `devpair doctor` (static) and a `--dry-run`
that names the driver, which prints the reviewer that would answer and the
fallback order. Entries missing from `order` still serve as fallbacks.

## The Rules That Make It Work

1. **Give it real evidence.** `--diff`/`--files` beats describing the code. The
   harness gathers context itself and launches the reviewer with an explicit
   ZERO-tool toolset (`-t context_engine`, override `reviewer_toolset`) plus
   `--ignore-rules`, so it is read-only by construction and never receives your
   SOUL/memory/AGENTS.md. (Versions ≤1.1.22 passed `-t ""`, which Hermes reads as
   "use the config toolsets" — the reviewer had terminal/write tools under YOLO.
   An unknown toolset name is refused by Hermes, never widened.)
2. **`followup` is how a review becomes a conversation** — it remembers what it
   said, notices what you silently dropped, and concedes when out-argued. But it
   is another paid call: run it when the user wants the loop closed, or offer it
   ("want me to put these fixes back to the pair?"), not automatically. If a
   requested `--gate` fails, stop before the gated phase and report the actual
   exit, verdict and findings. Do not continue because the prose sounds
   favourable, and do not issue `followup` or another paid critique on your own:
   wait for the user's decision before spending again.
3. **Disagreeing is legitimate.** Push back with reasoning. A pair you always
   obey is just a slow linter. But answer every point — it will notice silence.
4. **Report its verdict to the user honestly**, including when it says STOP or
   DO NOT SHIP. Never quietly bury a critique you disagree with — surface it
   with your counter-argument and let the user decide.
5. **`devpair reset` per feature.** Session memory is the point, but stale
   context from unrelated work pollutes the review.

## Converging a multi-round review (followup loops)

A reviewer that returns STOP after each fix is usually probing successive shapes
of one defect class. Close the loop with evidence, not argument:

1. **Encode every flip condition as a test before replying.** Build the
   reviewer's exact counterexample (its "what would change my mind" sentence),
   drive it through EVERY caller that shares the logic, and pair it with the
   control it named (the genuinely valid case must still pass). Send the
   followup with only the round's diff plus the new tests as `--files`, and
   write the ask as one line per prior finding saying exactly how it was
   applied. The reviewer then answers RESOLVED / NOT RESOLVED per item against
   the diff instead of re-reviewing from scratch.
2. **After two rounds on the same class, change the design, not the next
   shape.** Patching one phrasing per round invites the next phrasing. Switch to
   a fail-closed check independent of the logic being attacked (for example a
   residual scan over whatever the matcher did NOT consume). A detector that
   reuses the expander's grammar inherits its blind spots.
3. **Declare the guarantee's scope in the followup ask.** State what the
   safeguard promises and what is out of scope, so the reviewer judges a bounded
   claim and can return PROCEED instead of hunting an unbounded one.
4. **Avoid arbitrary thresholds in a fix.** A length floor or size cutoff added
   to close one finding is the boundary the next round attacks; derive the
   condition from the structure (the source's own separators, its own names).
5. **Measure false positives after every tightening.** Run the check over the
   real corpus it guards, compare finding counts before and after, and read
   every new hit in context; fix alias or coverage gaps rather than loosening the
   rule.
6. **Keep one implementation.** When a gate and a lint share logic, make one
   import the other's function and assert it in a test; parity that rests on two
   copies plus a corpus will rightly be rejected.

Before/after evidence and the finding classes worth pre-empting locally are in
`references/field-notes.md`.

## Verdicts

- critique/alt/followup → `PROCEED` / `PROCEED WITH CHANGES` / `RECONSIDER` / `STOP`
- review → `SHIP` / `SHIP AFTER FIXES` / `NEEDS WORK` / `DO NOT SHIP`
- verify → `APPROVE` / `APPROVE WITH MINOR EDITS` / `REVISE BEFORE USE` / `DO NOT USE`
  (six passes matching the verify-results skill, opening with an EVIDENCE BASIS line
  that caps the verdict when the reviewer only saw part of the work;
  `[VERIFIED ERROR]`/`[UNSUPPORTED CLAIM]`/`[ASSUMPTION]` labels; PASS 5 is CHECKS
  THAT WOULD SETTLE THIS, naming evidence it could not gather itself)

Findings are ranked `[BLOCKER|MAJOR|MINOR]` with `file:line`; every BLOCKER or
MAJOR must name the decision it changes. "None material" is a valid answer — the
pair is instructed not to manufacture problems to look useful. Every non-verify
review ends with `## CONFIDENCE` and `## WHAT WOULD CHANGE MY MIND` (one flip
condition and one falsifier); the reviewer treats your question as a hypothesis
and challenges a wrong premise first. These are prompt-level Council crossovers
— no extra calls.

- **`review --gate` passes `SHIP AFTER FIXES` with exit 0.** Only `NEEDS WORK` /
  `DO NOT SHIP` (or a `[BLOCKER]`) fail it. If the caller needs an unconditional
  approval, read `verdict` from `--json` and treat anything but `SHIP` as a hold;
  exit status alone has been mistaken for approval.
- **One verdict value per review.** If your `--ask` requests extra verdict
  sections, a `VERDICT: PROCEED` line beneath a `## REMAINING VERDICT` heading is
  not parsed and the gate fails closed ("no parseable VERDICT line"). A heading
  followed by the bare token, or a single inline `VERDICT: TOKEN`, parses.
  Preserve a raw null result; do not relabel it green or buy an unchanged rerun
  for punctuation.

## Pitfalls

- **Read the route receipt, not the banner.** Every attempt records requested vs REPORTED provider/model: inline prompts from Hermes' `--usage-file`, large (file-transport) prompts from Hermes' own session store (`state.db`, read-only) by the returned session id. `identity` is `reported-match`, `reported-mismatch` (also shouted on stderr, even with `--json`) or `unknown` — never assumed. A match is what Hermes reported, not cryptographic proof of the upstream model. Do not present a mismatched or unknown route as the requested model's endorsement; if a strict requested-provider probe fails authentication, report the blocker rather than substituting another model silently. In `--json`, find the receipt by content (the object carrying `identity` and `reported_model`): `review` and `followup` results nest it differently, so a missing top-level `receipt` key does not mean the route went unverified. A `PROBE_OK` or a banner never proves the route: Hermes can fall back to another model and still answer (see `references/field-notes.md` for isolated probes).
- **A profile in `DEVPAIR_HERMES_CMD` can hide the route receipt.** With `-p <profile>` only in the command prefix, the session lands in that profile's store while devpair reads the default home's, so the receipt says `identity: unknown`. Also set `HERMES_PROFILE=<profile>` for the devpair call.
- **User-requested reasoning effort is per invocation.** Confirm the installed Hermes CLI and target adapter support the requested level, then append e.g. `--reasoning max` to the native Hermes command prefix in `DEVPAIR_HERMES_CMD`; retain `--driver`, `--with` and `--requested-by user` on devpair. Do not change persistent model/config defaults for a review. `--timeout`/`--budget` limit wall-clock, not reasoning effort; elapsed time or token totals do not prove a named model ran at max.
- **Large prompts travel by file, not argv.** Past ~30k chars on Windows (CreateProcess caps a command line at 32,767) the prompt goes through a private temp file to `hermes chat -Q --query-file --format stream-json`; `DEVPAIR_PROMPT_TRANSPORT=inline|file|auto` overrides. A forced-inline oversize prompt is reported as "too large", never as "CLI not found". If a reviewer's answer arrives but the call never returns (observed under a profile with host-isolated plugins and MCP servers), set `DEVPAIR_PROMPT_TRANSPORT=file` and repeat the dry run: the `--query-file` path exits cleanly there.
- **A review that finishes but prints nothing (Windows).** A virtualenv's `Scripts\hermes.exe` listed on PATH before `<hermes-home>\bin\hermes.exe` can complete the turn (usage file written, reply saved in `state.db`) yet relay nothing to stdout. Since 1.2.6 devpair uses the installer's CLI in place of a `Scripts` launcher or a failed PATH lookup, recovers a completed silent turn read-only from the session store (receipt `recovered_from: session-store`, plus a warning), and `devpair doctor` flags a launcher override. Test a candidate command with `<cmd> -z "Reply OK"`: it must print OK. Empty stdout is a failure whatever the exit code.
- **Provider rate-limiting masquerades as a timeout.** An upstream HTTP 429 exhausts the CLI's 3 retries slowly and presents as "reviewer timed out after Ns". Probe cheaply (`hermes -z "Reply PROBE_OK" -m <model> --provider <p> -t context_engine --ignore-rules` — never `-t ""`, which loads every tool); if the probe fails fast with a usage limit, wait for the reset time named in the failure text and probe again. Spend the paid review only once a probe answers: a review sent into a live limit still burns a capped attempt plus minutes of timeout. A timeout kills the whole reviewer process tree. A first attempt that burns its whole timeout with no output, on a complete packet with a probe that answers, is a wedged generation: rerun the identical packet once; two full-timeout stalls in a row mean the task is too big, so split it.
- **Under an MSYS/git-bash terminal `shutil.which('hermes')` fails for the child python** (POSIX-mangled PATH) — every review dies as "CLI not found" while `devpair doctor` (direct API probes) stays green. Since 1.2.6 a failed lookup falls back to `<hermes-home>\bin\hermes.exe` when it exists; otherwise set `DEVPAIR_HERMES_CMD` to the NATIVE absolute path of hermes.exe; bash-exported env can also vanish through extra spawn layers, so the durable fix is a self-setting shim (`if not defined DEVPAIR_HERMES_CMD set "DEVPAIR_HERMES_CMD=%~dp0hermes.exe"` in devpair.cmd).
- **Reviewing with no evidence** produces generic advice. Attach the diff or files.
- **Same-family review** — heed the warning, pass `--reviewer` or fix `--driver`.
- **Evidence is size-capped per section, so check sizes before a paid run.** Diffs truncate at ~60k chars (the manifest records it and `--gate` will refuse an approval on it). Review them in slices: `--diff-ref` takes no pathspec, so slice by committing per-area changes or by cloning the repo and restoring one file onto the base commit. A `--plan` is capped at 30,000 chars and each `--files` entry at 24,000 including the line numbers devpair adds (90,000 in total). Overflow is cut from the MIDDLE and the run carries on: the packet gets a truncation marker, the reviewer is told what is missing, `--json` reports `coverage: partial` with `coverage_gaps`, and stderr says `EVIDENCE PARTIAL`. Nothing fails without `--gate`, so a caller that ignores both gets a review of a document with a hole in it. For a long plan or brief, split it at section boundaries into consecutive parts of at most ~18k chars, pass them all with `--files`, and make `--plan` a one-line pointer ("one document in N consecutive files; read them in order"). Confirm with `--dry-run` (free) that every part goes in full, then check that `coverage` is `complete` in the result. Large packets are slow too: ~55k chars took 4–6 minutes per frontier reviewer, close to the 420 s default, so pass `--timeout 900` (near the 90k cap, `--timeout 1800`). Budgeting arithmetic and splitting several coupled documents: `references/field-notes.md`.
- **Evidence kept outside the working tree draws false citation flags.** The `UNVERIFIED CLAIMS` check resolves cited paths against the current tree, so a file that WAS sent from elsewhere (a scratch folder, a staging copy) can be reported as missing. Re-check the cited lines in the file actually sent before discarding a review on that flag, and keep the flag rather than editing the receipt. Run from the tree that holds the evidence to avoid it.
- **Redaction can rewrite ordinary code.** Assigned-secret redaction also replaces lines such as `run(secret=secret)` and `token = (deadline, proc)`, so the reviewer can report a defect that is not in your source. Watch the redaction count and anchor findings against the real file (details in `references/field-notes.md`).
- **A fixed count of authorised calls does not authorise the loop.** "Authorise both calls" covers the two named runs; sending your fixes back for re-verification is a NEW paid call and needs its own ask. If an extra call slips out, disclose it in the same report (session, run id, token estimate) and put retrospective approval on the user's decision list; never fold it silently into "verification".
- **A short verdict-less reply is a failed attempt**, not a review (a model expecting tools often answers "I'll check X first…"); devpair falls through to the next backend. Long verdict-less reviews are kept and fail the gate closed.
- **Treating it as an oracle.** It has no access to your terminal, tests, or
  runtime — it reasons from what you pasted. Verify its claims before acting on
  them, especially file:line references. A packet of planning documents alone
  (no source) forces it to reconstruct code from memory: it cites `file:line` it
  never saw. The harness flags those as unverified, and each still needs checking
  against the real file before acting (they may well be right).
- **First call after idle** can take 60-90s. That is the model thinking, not a hang.
- **Small local reasoning models are slow reviewers.** A 9B-class local model
  emits a long reasoning trace before content — even a trivial probe takes
  ~2 minutes, and a real review with a large diff can exceed the 420s default.
  When falling back to local, pass `--timeout 900`.
- **`hermes -z` needs a non-interactive env**; the wrapper handles this, and
  scrubs operator-session env (`HERMES_YOLO_MODE`, resume/session/model
  overrides) from the reviewer's environment.
- **`devpair doctor` is free; `doctor --live` is not** — each live probe is a
  reserved, capped, ledgered paid attempt. Use static doctor first.
- **Verify its findings before acting.** In the session that built this tool the
  pair raised a confident BLOCKER that was simply wrong (an IndexError that was
  impossible because of a falsy-default idiom). It conceded immediately when
  shown the test. Run the check, then act.
- **Watch for regressions from its own suggestions.** One of its good ideas was
  implemented in a way that reintroduced a side-effect it had itself flagged a
  turn earlier. Run the test suite after taking its advice.
- **More field notes** (route probes, credential pools, packet budgeting, hashing,
  Windows recovery, multi-round evidence): `references/field-notes.md`.

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
- **Redaction does not know what is PROPRIETARY.** `redact_secrets()` catches
  credential-shaped values only; licensed source, client material or a reference
  corpus you must not transmit crosses untouched. If such material is in or
  beside the evidence, build a normalised corpus of its lines and make your
  packet step REFUSE to send when any outgoing line (evidence, digest, even the
  `--plan`/`--ask` text) matches one after whitespace normalisation, testing only
  lines long enough that a match means copying. Re-run the check on every
  rebuild, not once.
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
- **Output survives a legacy console.** stdout/stderr are reconfigured to UTF-8
  at startup with `errors="replace"`. Without it a Windows console's cp1252
  default raised `UnicodeEncodeError` on the banner *after* the reviewer had
  answered and the ledger entry was written — the paid review was lost to a
  traceback.
- **The backend command is resolved, not assumed.** `hermes` is looked up through
  `PATHEXT` on Windows, so a `.cmd`/`.bat` shim works and not only a `.exe`. If
  Hermes lives somewhere PATH cannot reach, or behind a wrapper, set
  `DEVPAIR_HERMES_CMD` to a command prefix; the reviewer arguments are appended
  to it.

  **How the value is parsed.** devpair splits it into arguments itself, not via a
  shell — no globbing, no `$VAR` expansion, no pipes. Two rules:

  - **Quote the individual path, never the whole value.** Quoting everything
    (`"python3 /opt/cli.py"`) yields a single argument with a space in its name,
    which cannot launch.
  - **Backslashes survive**, so a Windows path needs no doubling.

  ```bash
  # POSIX — no spaces in any path
  export DEVPAIR_HERMES_CMD='/usr/bin/python3 /opt/hermes/cli.py'
  # a path that contains a space: quote THAT path only
  export DEVPAIR_HERMES_CMD='"/opt/my tools/hermes" --profile default'
  ```
  ```
  rem Windows — the same value form works unchanged
  set DEVPAIR_HERMES_CMD="C:\Program Files\Hermes\hermes.exe" --profile default
  ```

- **The pair's `file:line` claims are checked against the PACKET**, in both
  the `file:438` and prose `file line 438` styles: a cited file that was not in
  the evidence sent is flagged (path-suffix match, or the file appearing in the
  packet as a location such as a traceback `File ".../x.py", line 42`), as are
  missing files and past-EOF lines. Line ranges inside a diff are not checked,
  so an empty problem list still does not prove the claimed defect is real.
- **Sessions are per project, contained and redacted at rest.** The implicit
  session belongs to the current git top-level (or cwd); another project never
  silently continues or replays it (an explicit `--session` that belongs to a
  different project prints a warning). Session names are validated (no paths,
  `..`, Windows device names). Concurrent runs append under a per-session lock;
  if a lock is held past its 30 s deadline the paid turn is saved to a
  `<session>.turn-*.json` sidecar instead of being written unlocked. Unparseable
  session files are quarantined (redacted), never silently overwritten. Every
  stored turn — old ones included — is redacted when loaded.
- **Each turn reports token estimates** and stores the parsed verdict, blocker
  count and any unverified claims on the session, so `--json` gives a caller
  everything it needs without re-parsing prose.

## Offline Capability Assessment

When comparing or proposing enhancements, inspect the installed implementation
and exercise local fixtures without paid reviewer calls. Read
`references/offline-assessment.md` for safe isolation, configuration/gate limits,
evidence provenance and concurrent-session caveats. These are current operating
limitations, not implemented fixes; re-check source after an upgrade.

## Tests

`python test_devpair.py` (or pytest) — regression suite (see Files for the
current count) pinning reviewer selection, self-review refusal, driver-identity
precedence, zero-tool launch and file transport, route receipts, process-tree
timeouts, tri-state enforcement and per-attempt reservations, static/live
doctor, session containment/per-project pointers/locking/redaction at rest,
evidence manifests and the coverage-aware `--gate` (driven through the real CLI
with a stubbed backend). No network required. Run after any change; set
`DEVPAIR_HERMES_CMD` to a stub so nothing can reach a real backend.

## Files

- `devpair.py` — implementation
- `test_devpair.py` — 110 regression tests (605 checks)
- `references/field-notes.md` — field-tested notes behind the Pitfalls
- `references/offline-assessment.md` — inspecting the install without paid calls
- `devpair` — reference CLI wrapper. The installer generates its own shim
  (`devpair.cmd` on Windows, an interpreter-chain bash script on POSIX), so
  this file is only needed for a manual install.

State at runtime lives under `<hermes-home>/devpair/` (or wherever
`DEVPAIR_HOME` points — use that for isolated test runs; a `HERMES_HOME` naming a
missing directory is skipped with a stderr warning, never silently): `sessions/*.json` (full
pairing transcripts, redacted, owner-only where supported), `current_session`
(per-project pointer map; a legacy single-name pointer is still honoured for its
own project), `invocations.jsonl` (append-only ledger: `attempt` reservations —
with the session name and run id — and `outcome` records; read it with
`devpair audit`), and optional `config.json` —
`order` to reorder reviewer preference, `reviewers` to declare your own roster,
`daily_cap` for a hard ceiling on paid attempts per day, `require_attestation`
to make `--requested-by` mandatory, `reviewer_toolset` (default
`context_engine`) and `prompt_transport` (`auto`/`inline`/`file`).

**Upgrading from ≤1.1.22:** old sessions load unchanged (and are redacted on
load); run `devpair prune --redact` once to rewrite them on disk. Old ledger
lines without `kind` still count as paid runs. Old `independence: verified`
labels in saved sessions describe family separation only — they were never route
receipts.
