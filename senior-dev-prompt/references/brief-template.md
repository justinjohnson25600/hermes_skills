# Brief template (normative)

Every brief senior-dev-prompt writes follows this contract. `scripts/lint_brief.py` checks the
mechanical parts; a rule change here ships with the matching script and test change.
Placeholders such as `<slug>` below describe what goes there; a brief always carries real values.

## File, title and metadata

- Path: `.hermes/plans/YYYY-MM-DD_HHMMSS-<slug>-brief.md` under the workspace: the session's working
  directory resolved to an absolute path (a code tool's working directory can differ, notably on
  Windows); create the folders when missing. When the working directory is the filesystem root, is
  itself a Hermes home or profile directory, or cannot be written, the workspace is the user's home
  directory; a project folder that merely sits inside a Hermes home stays the workspace. The user
  may name another path.
- First line: `# Brief: <plain title>`.
- Directly under it, one metadata line, keys separated by ` · `:

  `**Metadata:** version: 1 · status: draft · date: 2026-10-12 · tier: T2 · type: new app · route: <the concrete route> · pack: web-app · risk: personal data · self-review: 2 fixed`

| Key | Rule |
|---|---|
| version | Starts at 1; +1 for every amendment, with a change-log line |
| status | draft · blocked (BLOCKING items open) · approved (the user approved it) · running (execution started) · built (definition of done met) |
| date | YYYY-MM-DD of this version |
| tier | T0 to T4 (routing.md) |
| type | new app/tool · new skill or agent instructions · feature in existing code · bugfix · refactor · automation/integration · spike/research · infra/deploy |
| route | The same concrete route as the workflow mandate |
| pack | The domain pack used, or `none` |
| risk | Comma-separated risk flags (safeguards.md), or `none` |
| self-review | Required at T2–T4: `n fixed`, or `skipped (user request)` |
| snapshot | Required when a Co-developer review section exists: the start of dev-pair's `evidence.sha256` for the version the reviewers saw |

A status is history, never consent: reopening a brief revalidates it (SKILL.md, Entry).

## Full schema (T2–T4), in this order

Numbering (`## 1. For you`) is optional; the heading words are not.

1. `## For you` — plain English, no jargon, about 120 words: what the user gets (the representative
   scenario), what they need to provide, how many decisions wait for them, and the rough effort.
2. `## Operating obligations` — for the executing agent only: follow the workflow mandate, show
   evidence before claims, stop at the stop conditions, treat CONFIRMED items as settled. No persona.
3. `## Original request` — the request verbatim as a quote (`> ...`). Secrets become
   `[REDACTED: kind]` and the redaction is disclosed. Interpretations of voice-note or unclear wording
   follow the quote as ASSUMED lines. Only the quoted lines are exempt from the self-check.
4. `## Context` — greenfield (the project folder: named after the slug in the user's projects
   directory when the profile states one, otherwise under the workspace; created at execution with
   version control) or existing (path and what was read). Environment. Profile preferences labelled
   ASSUMED (profile). The reuse check result. Recommended tools, at most 5: name, what it adds,
   source, trust tier, and installed / offered / declined.
5. `## Outcome, users and scenario` — SC-1: one representative input or action and its observable
   result. SC-2: the most consequential failure or empty state. Both map to acceptance criteria.
6. `## Scope and deliverables` — In (the deliverables), Later, Out. Each Out item names the positive
   target that replaces it.
7. `## Requirements and safeguards` — FR-n (functional), NFR-n (binding non-functional only), SG-n
   (safeguards from every risk flag and from the pack). Each needs an acceptance-criteria row.
8. `## Approach and design` — when the design is settled: the chosen approach and one-line reasons
   for the rejected alternatives; components, data flow and interfaces; error handling; testing
   approach. When choices remain open: list exactly those choices; the route then sends only them
   to brainstorming.
9. `## Decision register` — one table, TO CONFIRM and BLOCKING rows first:
   `| Decision | Choice | Status | Why | Override |`.
10. `## Prerequisites you provide` — accounts, API keys, hardware, data, budget, and how secrets are
    supplied: environment variables or the host's secret store, never chat, code or the brief.
11. `## Workflow mandate` — the concrete route (real skill names in order, the real brief and plan
    paths, real phase numbers), the seeding rule, expected artifacts and their paths, where
    co-developer review is offered, the stop point after planning (routing.md), and the first
    execution task after the plan is approved: encode each testable acceptance criterion as a test
    or executable check (failing first where the behaviour is new).
12. `## Acceptance criteria and verification` — `| AC | Covers | Check | Evidence |`. Every FR, NFR,
    SG and SC appears in at least one Covers cell. Check: a command, test or observation that can
    fail. Evidence: what proves it (test output, log, screenshot path).
13. `## Boundaries and stop conditions` — what needs explicit approval (deleting data, spending money,
    publishing, touching credentials, widening scope) and when to stop and ask (a criterion cannot be
    met, a BLOCKING item is reached, a new material fork appears).
14. `## Risks and mitigations`.
15. `## Definition of done` — every row of the acceptance-criteria table passes with its evidence and
    the deliverables are handed over. Refer to the table; do not restate it.
16. `## Co-developer review` — only when reviewers ran (format in codev-review.md). Kept verbatim;
    exempt from the self-check and the word budget.

## Compact schema (T0–T1), in this order

`## For you` (two or three plain lines) · `## Objective and scenario` (the objective, the request as a
quote, SC-1 and SC-2) · `## Scope` (in and out) · `## Decisions` (`| Decision | Choice | Status |`) ·
`## Safeguards` (required whenever a risk flag fired; SG-n each with its check) · `## Route` (concrete)
· `## Acceptance criteria` (the same four-column table) · `## Stop conditions`.

## IDs, labels and amendments

- IDs: FR-n, NFR-n, SG-n, SC-n, AC-n, numbered from 1. Covers cells match IDs exactly (FR-10 does
  not cover FR-1).
- Labels: CONFIRMED (the user said it or inspection proved it) · ASSUMED (an inference, with its
  reason) · TO CONFIRM (a safe default applied that the user should check) · BLOCKING (no safe
  default; the hand-off holds that part).
- Amendments keep identifiers stable: new items take new numbers; removed items stay, marked
  `(withdrawn in vN)`. Bump the version and add a line to a closing `## Change log` section, for
  example `- v2 (2026-10-12): installed writing-plans; route D → A`.

## Word budgets

T0–T1: 350 words. T2: 1,500. T3–T4: 3,000. Not counted: quoted lines, the metadata line and the
Co-developer review section. Over budget: cut repetition, move detail into tables, or re-check the
tier.

## Placeholders

Generated text carries real values, in routes and commands too. Flagged: `TBD`, `TODO`, `FIXME`,
`<token>` (HTML tags, links, e-mail addresses and generics such as `List<T>` are fine), `{token}`
(URL path parameters such as `/tasks/{id}` and `${VAR}` are fine), `[insert ...]`, `[your ...]`.
Quoted user material is exempt.

## Greenfield defaults

Prefer the user's known stack; otherwise a boring, widely supported default with the fewest
dependencies. Every such choice gets a decision-register row with its reason.

## Self-check codes

Run `scripts/lint_brief.py <brief> [--tier T0..T4] [--json]` (exit 0 pass, 1 findings, 2 usage).
Without an interpreter, apply the same rules by hand.

| Code | Meaning | Fix |
|---|---|---|
| NO_METADATA | No `**Metadata:**` line | Add it under the title |
| META_MISSING_KEY | A required key is missing (self-review at T2–T4, snapshot when reviewed) | Add the key |
| BAD_STATUS | Status is not one of the five | Use draft, blocked, approved, running or built |
| BAD_TIER | Tier is not T0–T4 | Re-classify |
| MISSING_SECTION | A required heading is missing (Safeguards whenever a risk flag fired) | Add the section |
| SECTION_ORDER | Sections out of order | Reorder to this template |
| PLACEHOLDER | A placeholder in generated text | Write the real value |
| UNCOVERED_ID | An FR, NFR, SG or SC has no acceptance-criteria row | Add a row, or mark it withdrawn |
| NO_AC_ROWS | No acceptance-criteria table rows | Add the table |
| AC_NO_CHECK | A row has no check | Name a command, test or observation |
| AC_NO_EVIDENCE | A row has no evidence | Name what proves it |
| NO_SAFEGUARD | A risk flag fired but no SG-n exists | Add the safeguards from safeguards.md |
| OVER_BUDGET | Over the tier's word budget | Cut, tabulate, or re-check the tier |
