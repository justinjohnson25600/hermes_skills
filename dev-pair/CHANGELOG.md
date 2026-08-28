# Changelog — dev-pair

Semver, newest first. Patch increments (+0.0.1) per published change.

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
