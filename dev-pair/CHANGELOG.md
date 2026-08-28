# Changelog — dev-pair

Semver, newest first. Patch increments (+0.0.1) per published change.

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
