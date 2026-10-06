# Changelog — llm-council

Semver, newest first. Patch increments (+0.0.1) per published change.

## 1.0.0 — 2026-10-06

First release in hermes_skills. Two parts:

- **SKILL.md** — the LLM Council protocol (independent opinions, anonymised peer
  review, chairman synthesis that preserves dissent), from the `hermes-council`
  plugin, plus a section stating exactly what the installed runtime does and
  does not do, so an agent never claims "fresh independent reviewers" when the
  runtime used self-review.
- **plugin-patch/** — three commits for the `girayk/hermes-council` plugin
  (applies to v1.0.0 `18a6663` and to `8b7d666`), developed test-first and
  reviewed by `zai-indirect/glm-5.3` via dev-pair:
  - default `compact` protocol, no extra calls: members check the premise and end
    with Confidence + Flip condition; reviewers write stake-weighted
    `MATERIAL FLAW:` lines that reach the chairman regardless of ranking; the
    chairman reconciles consensus, dissent, failures, confidence, flip condition
    and a falsifier; per-seat route receipts and a call summary;
  - outbound redaction (Hermes `redact_for_egress`) of every member, reviewer and
    judge message at any nesting depth, and of the chairman guidance;
  - opt-in `protocol: strict`: shuffled labels per deliberation, no member reviews
    its own answer, complete rankings required (one corrective retry, then
    discarded and counted; a failed retry keeps attempt 1's flaws and spend),
    stakes statement required, first-place votes before average rank, and a
    `max_calls` fan-out budget that downgrades visibly to compact;
  - 26 new tests (61 total, all offline); the 35 upstream tests pass unchanged.
