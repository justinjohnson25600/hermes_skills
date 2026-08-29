# Changelog — dev-pair

Semver, newest first. Patch increments (+0.0.1) per published change.

## 1.2.0 — 2026-08-29

New `verify` mode, so a *verification* pass can be routed to a different model —
the same independence argument as code review, applied to finished deliverables.
Minor bump rather than patch: this adds a subcommand and a second output
vocabulary.

- **`devpair verify`** runs the five-pass post-hoc critique of the `verify-results`
  skill (errors, hallucination check, gaps, ranked improvements, verdict) against
  work that already exists. It carries its own role: the deliverable may be a
  report or an analysis, not code, so it must not be told it is reviewing software.
- **Label vocabulary is verify-results', not devpair's** — `[VERIFIED ERROR]`,
  `[UNSUPPORTED CLAIM]`, `[LIKELY ISSUE]`, `[ASSUMPTION]`, `[STYLE/CLARITY]`,
  `[SAFETY/COMPLIANCE]`. Those labels are shared with `quality-guard`, so
  substituting devpair's own `[BLOCKER]` would make the output illegible to it.
- **Gating understands the new vocabulary.** `DO NOT USE` and `REVISE BEFORE USE`
  join the blocking verdicts, and `count_blockers()` now counts `[CRITICAL]` as
  well as `[BLOCKER]` — otherwise a review full of critical findings passed the
  gate.
- **New section: CHECKS THAT WOULD SETTLE THIS.** The reviewer is toolless, so it
  is asked to name the commands and sources that would confirm or refute its own
  findings. This is what makes two-model verification reconcilable: you do not
  arbitrate between opinions, you run the check.
- **Verdict parsing made tolerant** (found by Kimi K3). It required `#` heading
  hashes and end-of-line, so `PASS 5 — VERDICT` without hashes, or an inline
  `VERDICT: APPROVE`, parsed as None. That does not fail safe — unparseable fails
  the gate, so well-formed reviews were being rejected on punctuation. Now accepts
  both, while still rejecting prose that merely mentions the word.
- Tests: 58 → 62 (287 checks). Verified end-to-end against a planted deliverable:
  `devpair verify --gate` returned `DO NOT USE`, exit 2, all five passes plus a
  populated CHECKS section, catching a fabricated statistic and a dosing ambiguity.

## 1.1.9 — 2026-08-29

- Docs/installer follow-up: both READMEs were left at 1.1.8 by the version bump,
  and the install section was POSIX-only despite this being the Windows release
  — it now shows the PowerShell one-liner (verified on a real Windows host) and
  describes the `.cmd` shim and `%LOCALAPPDATA%\hermes` home. Repo now ships
  `skills.json`, so a remote `--list` no longer prints a 404 on a first-time
  install; optional fetches are quiet.

Windows installability. Found while installing onto a Windows host: the skill
installed but was invisible to every Hermes surface, and its own install gate
failed 2 of 243 checks.

- **`platforms:` said `[macos, linux]`.** Hermes filters skills against that
  frontmatter list at seven call sites (`skill_matches_platform`), so on
  Windows the skill installed but never appeared in the available-skills
  list — despite 1.1.7 shipping first-class Windows support (`msvcrt`
  locking, `.cmd` shim, `%LOCALAPPDATA%\hermes` home resolution). Now
  `[macos, linux, windows]`.
- **The unreadable-ledger tests were POSIX-only.** They simulated an
  unreadable ledger with `chmod 0o222`, but on Windows chmod's read-only bit
  blocks writes, never reads — the ledger stayed readable and both checks
  failed (the production refusal itself was never exercised). On Windows the
  test now simulates the same seam production code depends on (`read_text`
  raising `OSError`); POSIX keeps the real chmod. All checks pass on Windows.


## 1.1.8 — 2026-08-29

Second round of the same Luna review. It accepted the 1.1.7 fixes and the
uncapped-permissive asymmetry, then named three things that still stopped the
cap being *reliably* hard. Two were real; the third was a fair challenge to the
test, not the code.

- **Unreadable is not zero.** `_scan_ledger()` turned any read `OSError` into
  `([], 0)`, so a ledger that was appendable but not readable (write-only perms,
  ownership damage) reported zero usage and reopened an already-spent cap.
  Reproduced: cap 1, one run logged, `chmod 222` — the next run was allowed. The
  scanner now returns a third value, `readable`, and distinguishes *no ledger
  yet* (a genuine zero) from *cannot read it* (unknown). Enforcement refuses on
  unknown.
- **A cap that cannot lock is not a hard cap.** Previously an unavailable
  `flock`/`msvcrt` degraded to a stderr warning and carried on, which is exactly
  the "advertised guarantee we cannot keep" this layer exists to avoid. With a
  cap set and no lock available, devpair now refuses; `allow_unlocked_cap: true`
  opts in to an advisory cap deliberately. The refusal names NFS/SMB explicitly,
  since a network filesystem can report a lock while not excluding other hosts —
  the residual failure mode Luna correctly said cannot be detected after the
  fact.
- **The race test proved the wrong thing.** It was thread-only, sharing one
  interpreter. Added a real multi-process test: four separate Python
  interpreters, timed to collide on the same ledger, against `daily_cap: 1` —
  exactly one is allowed and exactly one entry is written.
- Luna's stale-lock concern was investigated and dismissed on its own advice:
  POSIX `flock` releases on descriptor close, including process death, so a
  leftover lock *file* is harmless.
- Tests: 55 → 58 (243 checks).

## 1.1.7 — 2026-08-29

Hardening the 1.1.6 cap after a cross-model review by `openai-codex/gpt-5.6-luna`
found it was advisory in four separate ways. Every finding was reproduced with a
live falsification harness before being fixed, and each now has a regression test.

- **The cap was raceable.** `authorize()` did check-then-append with no lock, so
  two processes both read `used < cap`, both appended, and both called a
  backend. Reproduced: four concurrent runs against `daily_cap: 1` produced four
  `ALLOWED` and four ledger entries. Count and append now happen under one
  exclusive file lock (`flock`, `msvcrt` on Windows); the same repro now yields
  exactly one allowed run and one ledger entry. Where no locking primitive
  exists the cap degrades to advisory **and says so on stderr** rather than
  quietly offering a guarantee it cannot keep.
- **A ledger write failure silently permitted the paid call.** With the ledger
  path unwritable the run proceeded unrecorded, which also made the cap
  permanently uncountable (`runs_today()` stuck at 0). `log_invocation()` now
  reports success, and when a cap or `require_attestation` is in force an
  unrecordable run is refused. With nothing being enforced the ledger stays
  best-effort — an audit trail should never block a review nobody limited.
- **A corrupt line undercounted the quota.** Unreadable lines were skipped
  silently, so a torn write let runs continue past the cap forever. `_scan_ledger()`
  now returns a corruption count, and enforcement refuses on an unprovable
  total: an unprovable limit is not a limit. `devpair audit` stays lenient, so a
  human can still read the surviving history.
- **A torn line ate the next record too** (found while verifying the above, not
  in the review). A crashed writer leaves a line with no trailing newline, and
  the next append concatenated onto it, destroying *both* records. Appends now
  heal the missing newline first, and are `fsync`ed.
- **Valid JSON of the wrong type bricked the whole CLI.** `config.json`
  containing `[]` (or a string, number, or `null`) crashed `_load_cfg()`
  consumers with `AttributeError` — and because `_load_roster()` runs before
  argparse, even `devpair --help` died. Wider than reported: Luna named only
  `daily_cap()`. Non-object configs are now ignored with a clear stderr note.
- Tests: 50 → 55 (228 checks), including a threaded four-way race on the cap.

## 1.1.6 — 2026-08-29

Enforcement. 1.1.5 declared the skill "USER-INVOKED ONLY" and then admitted, in
its own docs, that nothing enforced it — an agent that ignored the paragraph
faced no obstacle. This release replaces most of that admission with mechanism.

- **Invocation ledger.** Every paid run appends to `<hermes-home>/devpair/
  invocations.jsonl` *before* the backend is called: timestamp, mode, reviewer,
  driver, who asked, context size, cwd, pid. Written before rather than after so
  a run that crashes mid-review is still on the record. A corrupt line is
  skipped, never fatal — losing the audit trail must not take the tool down.
- **`devpair audit`** reads it back: `--days N`, `--json`. It explicitly counts
  and flags runs that named nobody as the requester, which is exactly where an
  agent self-initiating would show up. Free to run.
- **`daily_cap` — the part an agent cannot argue with.** A hard ceiling on paid
  runs per day in `config.json`. Past it the process exits without calling any
  backend, regardless of what the caller believes it was authorised to do.
  Measured at 0.08s to refuse, versus a full review's tokens. `0` (default) is
  unlimited; a malformed value falls back to unlimited rather than bricking.
- **`--requested-by WHO`** (env: `DEVPAIR_REQUESTED_BY`) records who asked.
  Optional by default and recorded as `unattributed` when absent;
  `require_attestation: true` makes it mandatory. Documented honestly as an
  attestation a lying caller can forge — a record, not a lock. The cap is the
  lock.
- `--dry-run` stays genuinely free: it is gated before the authorize() call, so
  it never writes a ledger entry or consumes cap. It now also reports cap usage,
  making it a real preflight.
- Docs: SKILL.md and README.md gain an *Accountability* section stating plainly
  which of the three mechanisms an agent can evade and which it cannot. The
  README's "Two ways to use it" is renamed *Using it* — it had grown to four
  subsections; numbering corrected.
- Tests: 44 → 50 (211 checks). The new ones pin that the cap refuses *before*
  `run_reviewer`, that a refused run burns no ledger slot, that `--dry-run`
  spends nothing, and that the test harness redirects the ledger so running the
  suite cannot pollute a real audit trail.

## 1.1.5 — 2026-08-28

Invocation policy and reviewer choice — both driven by how the tool actually
costs money in practice.

- **`--with` and `--reviewer` together now refuse instead of silently picking
  one.** Passing both made `--with` win and discarded `--reviewer` without a
  word, so a user who named two reviewers watched a model they had not chosen
  answer the review. The tool now exits naming both flags. (Found reviewing the
  1.1.5 release itself: the flag-conflict case was exactly the "what the tests
  do not prove" gap called out in that review, and it was real.)

- **The skill is now USER-INVOKED ONLY.** Previous versions instructed agents to
  call devpair "proactively, without being asked", which spends a second model's
  tokens on every non-trivial change — including small ones where the review is
  worth nothing. The skill now states plainly: never self-initiate; if a review
  looks warranted, *offer it in one sentence and stop*. The trigger table that
  read as a standing instruction has been replaced with a mode-selection table
  used only once the user has asked.
- **`--with PROVIDER/MODEL` lets the user name the pair directly.** It does not
  need to be in the roster, and it outranks roster order. Same-family choices
  (a Claude driver reviewed by Claude) warn but proceed — an explicit
  instruction is the user's call, not the tool's. A bare model name resolves its
  provider from the roster when possible, and refuses with the correct form when
  not.
- `followup` is documented as another paid call — offer it, don't fire it
  automatically.
- Cost guidance added: prefer `--files` over a wide `--diff`, and `--dry-run`
  shows the reviewer and context size for free.
- **Documentation pass.** New README section *"Two ways to use it"* covering
  invocation from a Hermes conversation (plain English — there is no slash
  command and no `hermes devpair` subcommand), the manual-only policy, and
  running the CLI yourself; plus *"Selecting the reviewer model"* documenting
  the three precedence levels (`--with` > `--reviewer` > roster `order`) in both
  chat and CLI form. `--driver` is now correctly labelled as an agent's
  responsibility, not something a chat user types.
- Doc consistency fixes found by audit: SKILL.md still advertised 32 tests/125
  checks and told users to hand-edit the `REVIEWERS` dict (superseded by
  `config.json`, which survives upgrades); the README hardcoded
  `~/.hermes/devpair/sessions` despite 1.1.4 making the home portable; the live
  mac-mini SKILL.md was stamped 1.1.5 while still carrying the removed
  "call proactively" text. `.pytest_cache/` added to `.gitignore`.
- **Post-release review by GPT-5.6 Luna (the tool reviewing itself) found three
  more defects, all reproduced before fixing:**
  - `_load_roster()` inferred a family with an `or` chain, but `_family_of()`
    returns the *string* `"unknown"`, which is truthy — so a roster entry like
    `{model: my-fast-coder, provider: anthropic}` with no declared `family`
    stayed `"unknown"` and was offered to a Claude driver as independent. This
    is the same bug class fixed for the driver path in 1.1.3, through a third
    door. Added `_resolve_family(model, provider)`, used by both the roster
    loader and `--with`.
  - `--with` on a target whose model *and* provider are both unrecognised was
    silently presented as independent. It now carries an `unverifiable` flag and
    warns that independence cannot be established, while still proceeding —
    an explicit user instruction is honoured, but never dressed up as a
    guarantee.
  - Docs: a stale check count, an unmatched trailing quote that made the
    `--with` example uncopyable, and a hardcoded `~/.hermes` that contradicted
    1.1.4's portable-home work.
- **`USER-INVOKED ONLY` is now labelled honestly.** Luna's strongest point: it
  is a behavioural instruction, not a technical guarantee — the CLI cannot tell
  a user-approved call from an agent-initiated one. SKILL.md and README now say
  so explicitly and point at the tool-approval layer for a hard gate. Conceded
  rather than papered over.
- **The `unverifiable` fix only covered one of three paths (found by Opus 5 in
  followup).** 1.1.5 flagged an unprovable reviewer on the `--with` path only.
  Automatic selection and `--reviewer` still presented an opaque roster entry as
  independent — and that was the *dangerous* direction, because automatic
  selection is the default and needs no user typo to trigger. An unknown family
  compares as "different" against every driver, so `{model: opaque-model-x,
  provider: mystery-gw}` was silently auto-picked as the proven-independent
  reviewer. Now:
  - `unverifiable` is set on all three selection paths.
  - Proven-independent reviewers sort ahead of unprovable ones, which remain
    available as fallbacks rather than being dropped.
  - `same_family_as_driver` no longer treats `unknown == unknown` as a family
    match, which had misrouted an unknown driver + unknown reviewer into the
    wrong warning.
  - The independence state is printed in the human footer *after* the review
    (where it is actually read) and exposed as `independence` in `--json`, both
    keyed off the reviewer that actually answered — backend fallthrough could
    otherwise report the first choice's independence for a different model.
- Tests: 41 → 44 (175 checks), all passing. The three new tests were confirmed
  to fail against the pre-fix code before the fix was applied.

## 1.1.4 — 2026-08-28

Portability + installer. Until now the tool only ran correctly on the machine
it was written on.

- **State no longer assumes `~/.hermes`.** `_resolve_hermes_home()` checks
  `HERMES_HOME`, then `%LOCALAPPDATA%\hermes` (the real layout on Windows —
  verified on a live box where the home is
  `C:\Users\<user>\AppData\Local\hermes`), then `~/.hermes`, then any dotted
  directory that actually *looks* like a Hermes home. Copying the old build to
  a Windows machine would have written sessions into a directory the agent
  never reads, silently. `config.yaml` is resolved the same way.
- **`--cmd` uses the platform's shell.** `bash -lc` on POSIX, `cmd /c` on
  Windows, which has no bash.
- **The reviewer roster is machine-local.** `config.json` may declare
  `reviewers`, which REPLACES the shipped defaults; families are inferred from
  model or provider when not stated, and malformed entries are dropped rather
  than trusted. A roster copied between machines named providers that did not
  exist locally.
- **Repo-root `install.py` installs any skill** from a `skill.json` manifest:
  detects the Hermes home, installs `SKILL.md`, installs declared code files,
  writes a platform-correct CLI shim (`.cmd` on Windows, interpreter-chain
  bash script on POSIX), generates a starter roster from that machine's own
  configured providers, then runs the skill's test suite as the install gate
  and reports honestly if it fails. `--dry-run` and `--list` supported.
- One-line install (no clone needed):
  `curl -fsSL <raw>/install.py | python3 - dev-pair`
- Tests: 32 → 35 (137 checks), all passing. New: HERMES_HOME resolution,
  machine-local roster, malformed-roster fallback.

## 1.1.3 — 2026-08-28

Security and correctness pass, from an independent cross-model review
(Claude reviewing Kimi's implementation — the tool's own premise applied to
itself). All four findings were reproduced with live tests before fixing.

- **[BLOCKER] Secrets are no longer sent to third-party model APIs.** `gather()`
  previously posted the working tree verbatim: a repo containing an OpenAI key,
  a Postgres URL with a password, and a GitHub token leaked all three into the
  outbound prompt with no warning. Added `redact_secrets()` with 13 credential
  patterns (vendor token shapes, JWTs, private-key blocks, URL passwords,
  secret-looking assignments, auth headers), applied at a single chokepoint on
  `gather()`'s return so no future context source can bypass it. Only the secret
  itself is replaced — key names, URL hosts and header names survive so the
  reviewer can still reason about the code. Obvious placeholders
  (`<your-key-here>`, `changeme`) are deliberately left intact. The user is told
  how many values were redacted.
- **[BLOCKER] The same-family guard now fails CLOSED.** `_family_of()` returned
  `"unknown"` for any model name outside six hardcoded regexes, and `unknown`
  never equals a reviewer's family — so every reviewer was offered as
  "independent". A driver aliased as `my-custom-alias` on `anthropic` was
  offered Claude as an independent reviewer. Now: family is inferred from the
  **provider** when the model name is opaque, and if it is still unidentifiable
  the tool refuses with instructions rather than faking the guarantee.
- **[MAJOR] Untracked files are read, not just named.** `git diff` cannot show
  new files, so a review of new-file-only work saw a filename and nothing else —
  and reported a misleading "no diff found". Untracked files are now included as
  line-numbered code (max 5 files, 8k chars each, 256KB per-file cap, binaries
  and empties skipped), and the false "no diff" note is suppressed when new
  code is present.
- **[MAJOR] A missing `hermes` binary no longer crashes the run.** `run_reviewer`
  caught only `TimeoutExpired`, so `FileNotFoundError` escaped the retry loop and
  killed the process with a traceback. Now a soft failure that falls through to
  the next backend and names the cause.
- `pick_reviewer()` accepts an explicit driver spec (it previously ignored
  `--driver` entirely), and `doctor` gained `--driver` so its same-family column
  reflects the live session rather than the config default.

### Also in 1.1.3 — the deferred feature set

- **`--gate` makes a verdict machine-actionable.** Exits **2** (distinct from 1,
  a backend failure) when the verdict is `DO NOT SHIP` / `NEEDS WORK` / `STOP` /
  `RECONSIDER`, when any `[BLOCKER]` is present even under a good verdict, or
  when the verdict cannot be parsed at all — a gate that can't read the answer
  must not report success. Off by default: devpair stays advisory unless asked.
- **The reviewer's `file:line` claims are now verified.** It reasons from pasted
  text and cannot open files, so every cited anchor is checked against the real
  tree; missing files and past-EOF line numbers are listed under
  `UNVERIFIED CLAIMS` and stored on the session turn. The docs warned about
  hallucinated anchors and then did nothing — now the warning is enforced.
- **`doctor` probes backends in parallel.** Serially this was up to 4 × 300s of
  dead waiting; now one `ThreadPoolExecutor` pass.
- **`--budget N` caps total wall-clock across the whole fallthrough.** Without
  it, three dead candidates at the 420s default meant a 21-minute wait before
  learning nothing worked. Each attempt's timeout is clamped to what remains,
  and the run reports how many backends went untried.
- **Token accounting per turn.** Input/output estimates are shown in the footer
  and stored on the session turn (`tokens_in_est`, `tokens_out_est`) alongside
  the parsed verdict and blocker count — the data needed to tune reviewer order
  for a tool whose every turn is a paid API call.
- **`devpair prune [--days N] [--dry-run]`** for session housekeeping. The
  active session is never deleted regardless of age.
- Tests: 18 → 32 (125 individual checks), all passing. New: secret-leak
  end-to-end, redactor unit cases, fail-closed on unknown family, provider-based
  family inference, `pick_reviewer` driver honouring, untracked-file visibility,
  missing-binary soft failure, verdict parsing/gating, claim verification,
  parallel doctor, wall-clock budget, token estimates, prune semantics.

## 1.1.2 — 2026-08-28

Documentation release.

- Added `README.md`: human-facing documentation covering what the tool is and
  why it exists (cross-model supervision), the architecture, installation and
  configuration, per-mode usage with examples, the output contract, the safety
  model, and a troubleshooting table. SKILL.md remains the agent-facing
  contract; README.md is the operator-facing guide.
- No functional change.

## 1.1.1 — 2026-08-28

Initial public release (first publication to the hermes_skills repo).

- Published copies sanitized for public consumption: provider IDs in the
  shipped `REVIEWERS` roster genericized (edit them to match your own Hermes
  `config.yaml`), machine-specific operational notes removed from SKILL.md,
  wrapper interpreter list made generic.
- No functional change vs 1.1.0.

## 1.1.0 — 2026-08-28

Correctness hardening after self-review of the tool's own guarantees.

- **Driver identity:** added `--driver [PROVIDER/]MODEL` flag and
  `DEVPAIR_DRIVER_MODEL`/`DEVPAIR_DRIVER_PROVIDER` precedence over the
  `config.yaml` default. The same-family guard previously trusted the config
  default, which is wrong in any session running a model override — the tool
  could silently pick the driver's own family as the "independent" reviewer.
- **Wrapper:** the CLI wrapper now smoke-tests an interpreter chain instead of
  hard-depending on a single venv path (a transiently broken venv had killed
  the tool with getpath/init_fs_encoding errors).
- **followup** on a session with no earlier turns now warns on stderr instead
  of silently behaving like a fresh critique.
- **Session saves are atomic** (tmp + os.replace) and a concurrent run now
  merges into the pinned session instead of orphaning a same-timestamp file.
- **`--diff-ref` uses merge-base semantics** (`REF...HEAD`) so branch reviews
  show this branch's changes, not the ref's drift; uncommitted work is
  appended as a separate labelled section.
- **Fixed phantom context command:** the argparse subparser dest (`cmd`)
  collided with the `--cmd/-c` option, so every run without `-c` executed a
  stray `bash -lc pair` and injected its failure into the review prompt.
  Renamed the dest to `subcmd`.
- **doctor** gives slow local reasoning models a 300s probe timeout instead of
  failing a working-but-slow backend at 90s.
- Tests: 12 → 18, all passing (new: driver precedence, same-family guard with
  explicit driver, empty-followup warning, atomic saves, merge-base diff,
  phantom-cmd regression).

## 1.0.0 — 2026-08-26

Initial build.

- Five pairing modes (critique, review, debug, alt, followup) plus log, reset,
  doctor, and --dry-run.
- Reviewer subprocess is read-only by construction (`hermes -z ... -t ""`).
- Same-family reviewer refusal with explicit skip reasons; `--reviewer` as the
  deliberate override; full independent-candidate fallthrough on backend
  failure.
- Session memory (`sessions/*.json`) so followup notices silently dropped
  concerns and concedes when out-argued.
- Forced output shapes per mode; findings ranked BLOCKER/MAJOR/MINOR with
  file:line.
- 12 regression tests covering selection, refusal, side-effects, error
  propagation, and truncation maths.
