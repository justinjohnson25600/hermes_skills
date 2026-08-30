# Changelog — verify-results

Semver, newest first. Patch increments (+0.0.1) per published change.

## 0.0.7 — 2026-08-30

Written after a routed review came back substantially fabricated. The skill had
detailed guidance on *sending* work out and on *reconciling two verdicts*, and
nothing at all on reading the report in between — which is exactly where the
failure landed.

- **New: "Reading the review you get back".** A routed review is untrusted input,
  not an answer. Four cheap triage checks — is there a verdict; what is in the
  `UNVERIFIED CLAIMS` block; does it reference anything outside the packet; does
  its evidence basis match what was sent. A report failing the last three is
  discarded whole, because cherry-picking the plausible findings from a report
  that invented the rest is how a hallucination becomes a commit.

- **PASS 5 now says to RUN the checks, not just name them.** Naming them was
  always half the job; the half that matters is reproducing a finding before
  acting on it. Stated with the asymmetry that justifies the effort: a missed
  defect leaves you where you were, a fabricated one makes you change working
  code to satisfy something that was never true.

- **The honest limit is blunter.** "A second opinion is still an opinion"
  understated it. A routed review can be substantially fabricated and still read
  as competent — correct structure, plausible severities, precise `file:line`
  citations to files the reviewer never saw. Fluency is not evidence.

## 0.0.6 — 2026-08-30

One instruction change, from a GPT-5.6 Luna review of the skill contract.

- **An unavailable reviewer is no longer silently downgraded to inline.** The
  skill said: if `devpair` is absent, say so and run inline. Luna's point stands
  — disclosure makes the substitution non-silent, but it is still a substitution
  the user did not choose, and it swaps an independent review for the same model
  marking its own homework. It now reports that the requested independent review
  cannot be performed and asks, rather than deciding for them.

Also aligned with dev-pair 1.1.20: the routing appendix's `--gate` description
now matches dev-pair's own mode-to-severity table (`verify` blocks on
`[CRITICAL]`, other modes on `[BLOCKER]`).

## 0.0.5 — 2026-08-30

Documentation caught up with what the tool actually does, after a review by
GPT-5.6 Terra flagged a gap between the two.

- **The routing appendix said "never summarise the work to make it fit" without
  mentioning that the tool clips it for you.** Each `--files` entry is capped at
  ~24k chars, a diff at ~60k, the whole context at ~90k. Clips are marked in-band
  so the reviewer knows it saw only part — and can cap its verdict accordingly —
  but a user following the no-summarising rule had no way to know truncation was
  happening at all. The limits and the correct response (split into named slices)
  are now stated next to the rule.

- **The redaction boundary is wider than described.** dev-pair 1.1.15 moved
  redaction from the evidence gatherer to the fully assembled prompt, so `--ask`,
  `--focus` and replayed session history are scrubbed too. The privacy note now
  describes that boundary rather than the narrower one, and still says plainly
  that pattern-based redaction is a mitigation, not a guarantee.

No change to the six passes, the labels, the severities, or the verdicts.

## 0.0.4 — 2026-08-30

Packaging fix found by deploying to the estate.

- `skill.json` listed `SKILL.md` under `files`, which the installer treats as
  *code* to place in the skill's state directory. Every install therefore wrote a
  second copy to `<hermes-home>/verify-results/SKILL.md`, outside `skills/`,
  alongside the correct one — a duplicate the agent could load from the wrong
  path, and a doc that would silently go stale. A markdown-only skill declares no
  `files` at all: the installer places SKILL.md from the category path.

 2026-08-29

README catch-up: 0.0.2 added the honesty caveats to SKILL.md but left the
operator-facing README implying more than the tool delivers.

- README now states that `using both` is a manual procedure with no orchestrator
  and no enforcement, and that `--gate` cannot judge whether an evidence basis is
  honest — a floor, not an assurance.
- Minimum dev-pair version (v1.1.12+) stated in the install section.

 2026-08-29

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

## 0.0.3 — 2026-08-29

README catch-up: 0.0.2 added the honesty caveats to SKILL.md but left the
operator-facing README implying more than the tool delivers.

- README now states that `using both` is a manual procedure with no orchestrator
  and no enforcement, and that `--gate` cannot judge whether an evidence basis is
  honest — a floor, not an assurance.
- Minimum dev-pair version (v1.1.12+) stated in the install section.

 2026-08-29

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
