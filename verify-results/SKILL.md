---
name: verify-results
description: "Structured post-hoc critique of finished work — code, documents, or answers. Six passes producing severity-rated, labelled findings and a verdict of APPROVE / APPROVE WITH MINOR EDITS / REVISE BEFORE USE / DO NOT USE. Use when asked to verify, critique, audit, or second-opinion something that already exists."
version: 0.0.5
author: Hermes Agent
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [verification, critique, review, hallucination-check, quality]
    related_skills: [dev-pair]
---

# Verify Results — Post-Hoc Critique

Critique work that **already exists**, to the standard of a senior professional
reviewing it before it is merged, deployed, published, sent, or relied upon.

**Triggers.** "verify this", "critique this", "review this work", "check this for
hallucinations", "audit this output", "is this right", "what's wrong with this",
"before this goes live", or any request for a second opinion on finished work —
including the assistant's own previous output. Also honour invocation by a
conductor or pipeline skill that chains this as a verification step.

**Do not self-trigger while a deliverable is still being produced.** This is a
post-hoc gate. If asked to make something production-ready from scratch, that is
a different job.

**Scope.** Anything finished. Code is the primary case — a diff, a pull request,
a migration, a script, a config or schema, a test suite, an API contract — and it
applies equally to a document, an analysis, a report, or a plain answer. Adapt the
*evidence*, not the passes: for code that means the diff, test output, error logs
and runtime behaviour; for prose it means source material and citations. The
labels, severities and verdict are identical either way. Never assume a domain
that was not stated.

Write in British English.

---

## Before you start: state your evidence basis

Verification is only as good as what you actually saw. **Open with one line naming
what you had access to**, then never issue a verdict stronger than that supports:

```
EVIDENCE BASIS: full diff at 8f3a91c (240 lines, 3 files).
                Ran `pytest -q` -> "34 passed, 0 failed in 1.2s"
                Did not run the service or see production config.
```

Two things make that line falsifiable rather than a claim about yourself:

- **Name the artefact** — a commit SHA, file path with line count, or version. A
  verdict that does not say *which revision* it covers cannot be re-checked, and
  the re-verification loop below has nothing to anchor to.
- **Quote command output verbatim** — the literal final line (`34 passed, 0
  failed in 1.2s`), never a paraphrase of it. "The tests pass" is your word for
  it; the actual line is evidence. If you did not run it, say you did not.

Rules that follow from it:

- If you saw only part of the work — a truncated file, a summary, one of forty
  changed files — **say so and cap the verdict at REVISE BEFORE USE**. An
  `APPROVE` issued on a partial view launders a guess as an assurance.
- If the work is too large to review at once, review it in named slices and say
  which slice this verdict covers. Do not silently skim.
- Distinguish **checked** from **uncheckable**. "I ran the tests and they pass" and
  "I could not run the tests" are different claims and must not read the same.

## The six passes

### PASS 1 — ERRORS & PROBLEMS

What is factually wrong, logically flawed, technically broken, misleading, unsafe,
non-compliant, or likely to fail in the real world.

For each issue:

- **Severity** — `[CRITICAL]` / `[MAJOR]` / `[MINOR]`
- **Label** — one of the labels below
- **Where** — quoted text, or `file:line`
- **What is wrong**
- **Evidence** — reasoning or source basis
- **Confidence** — High / Medium / Low
- **Fix** — the corrected version or recommended change

| Severity | Meaning |
|---|---|
| `[CRITICAL]` | Will break, mislead, cause harm, create serious legal/compliance risk, or make the work unusable |
| `[MAJOR]` | Significant; fix before use |
| `[MINOR]` | Acceptable, but should be improved |

| Label | Meaning |
|---|---|
| `[VERIFIED ERROR]` | Contradicted by supplied material or reliable evidence |
| `[UNSUPPORTED CLAIM]` | May be true, but no evidence is provided |
| `[LIKELY ISSUE]` | Appears problematic, needs confirmation |
| `[ASSUMPTION]` | Relies on something not stated |
| `[STYLE/CLARITY]` | Wording, flow, or presentation |
| `[SAFETY/COMPLIANCE]` | Risk of harm, legal, medical, financial, or reputational |

### PASS 2 — HALLUCINATION & VERIFICATION CHECK

Invented facts, sources, names, dates, numbers, studies, products, APIs,
specifications or capabilities. Authoritative-sounding but unevidenced claims.
False precision. Exaggerated certainty. Unsupported statistics. Outdated or
time-sensitive information. Missing citations or weak source grounding.

Mark each `[VERIFIED ERROR]`, `[UNSUPPORTED CLAIM]`, `[LIKELY ISSUE]`, or
`[ASSUMPTION]` — and state explicitly which ones you **could not check**, rather
than leaving an unchecked claim looking like a cleared one.

**Relationship to PASS 1.** Anything here that is an actual defect also belongs in
PASS 1, where it carries a severity. PASS 2 records *check status* — verified,
unsupported, or uncheckable — not severity. Do not list a finding twice as though
they were two problems.

### PASS 3 — GAPS & OMISSIONS

What a competent professional would expect to find and cannot: missing evidence,
safety warnings, edge cases, implementation detail, stated assumptions, audience
context, compliance checks, practical instructions, limitations, test cases, or
failure modes.

Do not list things absent because they are irrelevant.

### PASS 4 — IMPROVEMENT RECOMMENDATIONS

Up to five improvements ranked by impact, highest first — or **None.** if the
work does not warrant any. Do not pad to reach a count. For each: what to
change, where, why it materially matters, and a concrete rewrite, example,
checklist or pseudocode where applicable.

Prioritise fixes that prevent factual error, user harm, broken functionality,
compliance risk, reputational damage, or serious misunderstanding.

### PASS 5 — CHECKS THAT WOULD SETTLE THIS

The specific commands, lookups, or sources that would confirm or refute the
findings above — the evidence you could not gather yourself.

This is the most actionable output of the whole critique: it converts an opinion
into something testable. Prefer runnable commands over vague advice
(`pytest tests/test_auth.py -q`, not "check the tests"). If nothing is
outstanding, write **None.**

### PASS 6 — VERDICT & WHAT HAPPENS NEXT

One of:

| Verdict | Meaning | What happens next |
|---|---|---|
| `APPROVE` | No material issues found | Proceed. |
| `APPROVE WITH MINOR EDITS` | Only `[MINOR]` findings **and a full evidence basis** | Apply the edits; no re-verification needed. |
| `REVISE BEFORE USE` | `[MAJOR]` findings, or evidence was partial | Fix, then **re-run this skill on the revised work**. |
| `DO NOT USE` | `[CRITICAL]` findings | Stop. Do not ship or send. Escalate to the user with the critical findings quoted. |

Then one short paragraph: overall assessment; the primary risk if used as-is; the
single highest-leverage fix; and whether further external verification is needed.

**A verdict is not the end of the job.** On `REVISE BEFORE USE` the loop is
fix → re-verify → re-verdict, and the re-run must say it is a re-verification and
what changed. On `DO NOT USE`, stop and surface it — never quietly downgrade a
critical finding to get to an approval.

## Rules

- Do not pad, and do not praise structure while ignoring substance. If something
  is good, move on.
- Do not invent missing context, and do not assume requirements that were not
  stated unless they are essential for this type of work.
- Separate confirmed errors from unsupported claims, assumptions, and subjective
  improvements. These are different things and blurring them destroys the point.
- Prefer supplied source material first, then official documentation, primary
  research, recognised standards, or authoritative references.
- If uncertain, say so and mark confidence High / Medium / Low.
- Flag false precision, overclaiming, invented detail, and unsupported certainty.
- **"No material issues" is a real result.** Six headed passes create pressure to
  fill them; manufacturing a finding to look thorough is a failure of the skill,
  not a success. See the worked example below.

## Worked example — a clean result

What a genuine `APPROVE` looks like. Note the empty passes and the short verdict:

```
EVIDENCE BASIS: full diff at 4c1e8ab (18 lines, 1 file: src/auth.py).
                Ran `pytest -q tests/test_auth.py` -> "12 passed in 0.4s"

PASS 1 — ERRORS & PROBLEMS
None.

PASS 2 — HALLUCINATION & VERIFICATION CHECK
No factual claims made; the change is a pure refactor. Nothing to verify.

PASS 3 — GAPS & OMISSIONS
None material. The existing test covers both branches of the changed condition.

PASS 4 — IMPROVEMENT RECOMMENDATIONS
None.

PASS 5 — CHECKS THAT WOULD SETTLE THIS
None.

PASS 6 — VERDICT & WHAT HAPPENS NEXT
APPROVE
An 18-line rename with test coverage on both branches. No risk if used as-is.
No further verification required.
```

Four words of praise, no invented findings. That is a correct output.

---

## Appendix — verifying with a different model

By default this skill runs **inline on the current model** — the same model that
produced the work, marking its own homework. Fine for catching slips, weak for
catching blind spots, because the errors and the review of those errors come from
the same priors.

The user may name a different model:

| The user says | What you do |
|---|---|
| `verify-results` | Run the six passes inline. The default. |
| `verify-results using <model>` | Send the work to that model (see below). |
| `verify-results using both` | Run inline **and** send to a second model, then reconcile. |

`using both` is a **manual procedure, not an orchestrator.** There is no tool that
runs the two passes and merges them: you run the inline critique, run
`devpair verify`, and follow the reconciliation steps below yourself. Nothing
enforces those steps — if you are not going to run the settling checks, use
`using <model>` and read the two reports separately rather than claiming a
reconciliation you did not perform.

**Never route to another model unless the user asked.** Two reasons, and cost is
the lesser one:

- **The work leaves the machine.** `--files` / `--diff` sends the content to a
  third-party API. dev-pair redacts credential-shaped values from the whole
  outbound prompt — evidence, `--ask`, `--focus` and replayed session history
  alike — but pattern-based redaction is a mitigation, not a
  guarantee — assume anything it does not recognise is exposed. Never route work
  the user would not paste into that provider themselves.
- **It costs a second set of tokens**, and the decision to spend them is theirs.

If you think an independent pass is warranted, offer it in one sentence and stop.

### Sending the work out

Requires the **dev-pair** skill v1.1.12+ (`devpair` on PATH) — earlier
versions have no `verify` subcommand. **If it is absent, say so and
run inline** — never silently drop the user's model choice.

The other model runs in a separate, toolless process and **cannot see this
conversation**, so the work must be serialised into the call:

```bash
# code — let it see the real diff
devpair verify --with <provider>/<model> \
               --driver <your-live-provider>/<your-live-model> \
               --requested-by user \
               --diff                        # or --diff-ref main

# any other finished artefact
devpair verify --with <provider>/<model> \
               --driver <your-live-provider>/<your-live-model> \
               --requested-by user \
               --files src/auth.py PLAN.md   # source, config, or prose
```

- **Always prefer `--files` / `--diff`.** The other model then sees the real
  thing, line-numbered, not your description of it.
- **Work that exists only in the conversation: write it to a temp file first**,
  then `--files`. Do not paste a document into `--ask` — quotes, backticks and
  `$(...)` will break the command or be expanded by the shell. `--ask` is for a
  short instruction, never for the work itself.
- **Never summarise the work to make it fit.** A critique of your summary is not
  a critique of the work, but it will read as though it were.
- **The tool clips oversized evidence — know the limits before you rely on it.**
  Each `--files` entry is capped (~24k chars), a diff at ~60k, and the whole
  context at ~90k. A clip is marked in-band (`[... truncated: N chars omitted
  ...]`) so the reviewer knows it did not see everything and can say so in its
  EVIDENCE BASIS — but *you* should split the work into named slices rather than
  let it happen, because a verdict on a clipped artefact is a verdict on part of
  the work, which caps it at REVISE BEFORE USE.
- **Secrets in the question are redacted too, not just in the files.** `--ask`,
  `--focus` and the replayed session history pass through the same redactor as
  the evidence, and a stderr note reports anything it caught. It is still
  pattern-based — a credential it does not recognise goes out.
- `--driver` must name the model **you are actually running on right now**, read
  from live session metadata — not `config.yaml`, which is usually stale in an
  override session. Getting this wrong points the independence guard at the wrong
  family; in practice this has already allowed a model to review itself.
- Same-family warns rather than refuses. "Verify with opus" while running Opus is
  a legitimate instruction; the warning just records that the review is not
  independent.

`devpair verify` returns the same passes and labels. With `--gate` it exits 2 on
`DO NOT USE` / `REVISE BEFORE USE`, on any `[CRITICAL]` finding, and on a verdict
it cannot parse — it fails closed, so an unreadable answer is never a pass.

**What `--gate` does not check.** It reads the verdict and the severity labels;
it cannot tell whether the `EVIDENCE BASIS` line is honest, whether the reviewer
really ran the command it quoted, or whether an `APPROVE` was issued on a partial
view. A model that skips the evidence basis entirely and writes `APPROVE` passes
the gate. The evidence rules above are instructions to the reviewer, not
machine-enforced preconditions — treat `--gate` as a floor (it catches explicit
failure verdicts) and read the evidence basis yourself before trusting a pass.

### Reconciling two verdicts

Two models will sometimes disagree. **Do not arbitrate and do not average.**
Verification has ground truth; that is what makes it reconcilable.

1. Run the commands from **PASS 5 — CHECKS THAT WOULD SETTLE THIS**.
2. **Show the raw output verbatim** — the actual lines, not "the tests passed".
3. Where evidence settles it, evidence wins, whichever model was right.
4. Where nothing settles it, report both positions and say plainly it is
   unresolved. Do not manufacture a consensus.
5. Attribute every finding to the model that produced it.

**Conflict of interest.** In inline and `both` modes, the model running the
settling checks is the model that produced the work: it chooses the command and
reports the result. That is the same disease this appendix exists to treat, one
layer down. Required mitigations: verbatim output only, and an explicit line in
the report stating that the producer also reconciled. For anything high-stakes,
hand the commands to the user and let them run them — that is the only fully
independent path.

### The honest limit

A different model family reduces shared blind spots; it does not eliminate them.
Frontier models share training data and failure modes. And a second opinion is
still an opinion — a finding neither model can evidence stays unproven no matter
how many models assert it.
