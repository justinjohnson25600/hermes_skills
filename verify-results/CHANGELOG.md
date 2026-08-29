# Changelog — verify-results

Semver, newest first. Patch increments (+0.0.1) per published change.

## 0.0.2 — 2026-08-29

Reviewed by GPT-5.6 Luna via `devpair review`.

- **`using both` is now labelled a manual procedure, not an orchestrator.** No
  tool runs the two passes and merges them; the reconciliation steps are yours to
  perform and nothing enforces them. Advertising it as a mode without saying so
  invited exactly the failure the section warns about — claiming evidence settled
  a dispute nobody ran.
- **`--gate`'s limits are now stated.** It reads the verdict and severity labels;
  it cannot tell whether the evidence basis is honest or whether an `APPROVE` was
  issued on a partial view. A reviewer that omits the basis entirely still passes.
  Treat it as a floor, not an assurance.
- Minimum dev-pair version pinned (v1.1.12+) — earlier builds have no `verify`
  subcommand, so the appendix would die at argparse.
- **Published** to the public hermes_skills repo with `skill.json` and an entry
  in `skills.json`; it previously existed only under `~/.hermes`, so a fresh
  install could not obtain the skill dev-pair's `verify` mode implements.

## 0.0.1 — 2026-08-29

First versioned release. The skill previously carried no version field at all,
so nothing could be tracked or diffed. Baselined here, with a structural rework
driven by a third-party read of the existing text.

- **Passes first.** `PASS 1` began at line 149 of 218 — 68% of the file was
  routing and meta before an agent reached the actual work. Routing now lives in
  an appendix; PASS 1 starts at 22%.
- **Frontmatter cut from 1,077 to 269 characters.** Skill descriptions are matched
  against user intent; the old one was a wall of triggers, routing phrases and
  prohibitions. Triggers moved into the body.
- **New: evidence-basis gate.** The critique must open by naming what it actually
  saw, and may not issue a verdict stronger than that supports. A partial view
  caps the verdict at `REVISE BEFORE USE` — an `APPROVE` on a truncated diff
  launders a guess as an assurance.
- **New: PASS 5 — CHECKS THAT WOULD SETTLE THIS.** Previously this existed only in
  dev-pair's routed shape, so the inline default — the common case — never
  produced it. It is the most actionable output of the critique: it turns an
  opinion into something testable.
- **New: PASS 6 defines what happens next.** The skill produced a verdict and then
  stopped, which made it a report generator. `REVISE BEFORE USE` now means
  fix → re-verify → re-verdict; `DO NOT USE` means stop and escalate.
- **New: a worked no-findings example.** Six headed passes create pressure to fill
  them. A concrete `APPROVE` with empty passes is what makes "no material issues"
  a usable answer rather than a theoretical one.
- **Checked vs uncheckable are now distinct.** An unverifiable claim and a
  verified-clean claim previously looked identical in the output.
- Dropped the dangling `quality-guard` counterpart (named four times, not
  installed anywhere) and the estate-specific provider IDs in the examples.
- Scope stated explicitly: domain-agnostic, code-first. Adapt the evidence, not
  the passes.

Reviewed before release by GLM-5.3 via `devpair verify` (verdict:
REVISE BEFORE USE). Its findings were checked against the CLI rather than taken
on trust — two were refuted by running its own suggested commands, the rest
applied:

- **Refuted.** It doubted `devpair verify` existed with the documented flags, and
  doubted the gate parsed this skill's verdicts; `devpair verify --help` and the
  source show both are present. It was reasoning from stale session context.
- **Refuted in part.** It warned redaction might not cover the `--files` path; it
  does — `redact_secrets()` sits on the single chokepoint through which all
  gathered context passes.
- **Applied.** The evidence basis is now falsifiable: name the artefact, quote
  command output verbatim. Previously it was self-certified prose.
- **Applied.** A data-egress warning now sits beside the cost gate — routing to
  another model sends the content off the machine, and pattern-based redaction is
  a mitigation, not a guarantee.
- **Applied.** The frontmatter promised three verdicts where the table defines
  four; `APPROVE WITH MINOR EDITS` now also requires a full evidence basis, which
  removes a double-match against `REVISE BEFORE USE`.
- **Applied.** PASS 2's relationship to PASS 1 is defined, so a hallucination is
  not counted as two findings.
