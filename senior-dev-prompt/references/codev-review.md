# Co-developer review (normative)

Co-developers are other AI model families that review the brief through dev-pair before hand-off.
Each review is one paid model call, made only with the user's explicit choice in this run (H5).

## 1. Availability (free)

- dev-pair is available when `devpair` runs, `devpair doctor` (static, never `--live`) succeeds,
  and the driver's family is known (the live model and provider this session runs on).
- Eligible reviewers: roster entries and user-named models whose family differs from the driver's,
  one per family, roster order, named models first. **K** = the number of distinct eligible families.
- Without dev-pair, skip the question and write in the brief: "Co-developer review unavailable:
  dev-pair is not installed", with the install pointer from its README.
- With dev-pair but K = 0, skip the question and write why (for example: every configured reviewer
  shares the driver's family). An unknown driver family also means K = 0 for this run.

## 2. The question

Asked in the intake form when one happens anyway, otherwise once in the hand-off form. Exact text:

> How many co-developers should review this brief? Each is a different AI model family. Only the
> brief is sent to that model's provider (not your files or memory), and each review is one extra
> paid model call. (0–K)

Choices: the recommendation first (1 for T2+, 0 for T0–T1), "0 — no review", and up to two other
values. Free text accepts a number, model names, or both. A count already stated in the request is
the answer.

## 3. Reading the answer — all before any paid call

Normalise first: digits and number words become a count; names alone are a choice whose count is the
number of names. **N is always the total number of paid calls.**

| Answer | Result |
|---|---|
| `0`, none, no, blank, timeout | No review |
| `N` | N reviewers from roster order, one per eligible family |
| `N: m1, m2` | Named models first, remaining slots from roster order |
| `m1, m2` | N = the number of names |
| N smaller than the number of names | One clarification |
| N larger than K | Cap the independent slots at K (a confirmed driver-family reviewer is extra to K, not capped); name the families that were available. If the cap would drop a reviewer the user named, one clarification |
| A bare name not in the roster | Resolve through the host's provider and model config; still unresolved: one clarification asking for PROVIDER/MODEL |
| Two names in one family | One clarification: which one (one reviewer per family) |
| A name in the driver's family | Warn that it is not independent; use it only on explicit confirmation. It then takes one of the N paid slots and never counts toward K |
| Anything unparseable | 0; the hand-off says the answer could not be read and reviewers can still be requested |

Bundle every clarification for a paid choice into one message. An unanswered clarification means no
review for that slot: no guess and no substitute. It is a pending review choice, not a BLOCKING
decision (no paid call is the safe default), and the hand-off names it. Before launching, show one
line with the final reviewers and the total: "Reviewers: model-a (family a), model-b (family b) — 2
paid calls."

## 4. Coverage check (free)

Run each command with `--dry-run` first and read its `evidence` line. When it reports `partial`, split
the brief into parts of about 18,000 characters in a temporary folder outside the project, pass them
with `--files`, and keep `--plan` a one-line pointer. A review of partial evidence is labelled PARTIAL.

## 5. Run

One attempt per reviewer, concurrently when background processes are available, each in its own
session so reviewers stay blind to each other:

```
devpair critique --plan "Development brief: <title>" --files <brief path> --ask "<fixed question>" --driver <live provider/model> --with <reviewer provider/model> --requested-by user --session <slug>-cd-<family> --json
```

Only the brief file is sent (H6). Use the real values for every slot.

## 6. Fixed review question (exact)

> Act as a senior engineer reviewing a development brief that another agent will execute. Will
> executing it produce the right thing, built the right way, provably? Check for missing or wrong
> requirements, acceptance criteria that cannot be verified, workflow routing wrong for the size or
> risk, risky defaults, missing safeguards, scope creep, and anything a non-expert requester would
> regret. Rank findings BLOCKER / MAJOR / MINOR; for each, name the decision it changes and the exact
> edit you propose.

## 7. Receipts

From each call's JSON: `verdict`, `run_id` (dev-pair 1.2.3+), `session`, `route.identity`,
`coverage`, `evidence.sha256`, `unverified_claims`, `response`. A review is **verified** only when
`route.identity` is `reported-match` and `coverage` is `complete`; otherwise label it UNVERIFIED
ROUTE or PARTIAL. The snapshot is the start of `evidence.sha256`.

## 8. Triage every finding

ACCEPT / PARTIAL / REJECT, each with a reason. Verify factual claims before accepting. A finding
that cites a section or line the brief does not contain is REJECTED unless its substance is
verified independently; `unverified_claims` is an input. A disagreement between reviewers that is the
user's call becomes a TO CONFIRM row. STOP and RECONSIDER verdicts are reported verbatim and pause
execution for the user.

## 9. Revise and record

Apply accepted changes, bump the version, revalidate (Step 7b), then append the section:

```
## 16. Co-developer review
Reviewers: <provider/model> (family), ... — one paid call each, separate sessions. Snapshot reviewed: <sha256 start> (version <n>).
Run report: consented N · attempted n · completed n · verified n (run IDs ...).
Verdicts as written: ...
| # | Finding | Reviewer | Decision | Reason |
Changes made: ...
```

and set `snapshot:` in the metadata line. Earlier reviews stay attached to the snapshot they saw.

## 10. Failures

Cap refusal, authentication error, HTTP 429, timeout, verdict-less reply: report each per reviewer
with its cause and continue with the rest. Run a replacement model only when the user names one.
Never present a failed review as completed (NFR-5).

## 11. Follow-up

When an accepted BLOCKER changed the brief materially, offer one `devpair followup` round in one
sentence; run it only on yes.

## 12. Run report

Build the report from each call's own JSON and exit status — consented / attempted / completed /
verified — citing each `run_id` so the user can cross-check with `devpair audit`. Do not read the
ledger and never use global daily counts.
