# verify-results — check the work before you rely on it

Structured post-hoc critique of finished work: code, documents, or answers. Six
passes produce severity-rated, labelled findings and one of four verdicts —
`APPROVE` / `APPROVE WITH MINOR EDITS` / `REVISE BEFORE USE` / `DO NOT USE`.

## The problem it solves

"Review this" produces a review that *sounds* rigorous and proves nothing. Three
failures happen quietly, every time:

1. **The reviewer does not say what it looked at.** A verdict issued on a
   truncated diff reads exactly like one issued on the whole thing. It launders a
   guess as an assurance, and nobody can tell afterwards which it was.
2. **Confirmed errors get blurred with hunches.** "This is wrong", "this has no
   evidence" and "I would have done it differently" are three different claims.
   Mixed together, none of them is actionable.
3. **It ends in an opinion.** Two reviewers disagree and there is no way to
   settle it, so the louder one wins.

This skill closes each one. It opens with an **evidence basis** naming the
artefact and quoting command output verbatim; it **labels** every finding by
check-status and severity; and it ends with **runnable commands** that would
settle each finding. A disagreement becomes a test, not a debate.

## How it works

You ask for it in plain English. The agent loads the skill and runs six passes
over the work, in order:

| Pass | What it produces |
|---|---|
| **Evidence basis** | One line: what was seen, what was run (quoted verbatim), what could not be checked |
| **1 — Errors & problems** | Each with severity, label, location, evidence, confidence, and a fix |
| **2 — Hallucination check** | Invented facts, sources, APIs, false precision — recorded as *check status*, not severity |
| **3 — Gaps & omissions** | What a competent professional would expect and cannot find |
| **4 — Improvements** | Up to five, ranked by impact — or **None.** |
| **5 — Checks that would settle this** | The specific commands or sources that confirm or refute the findings |
| **6 — Verdict** | One of four, plus the primary risk and the highest-leverage fix |

Severities are `[CRITICAL]` / `[MAJOR]` / `[MINOR]`. Labels are
`[VERIFIED ERROR]`, `[UNSUPPORTED CLAIM]`, `[LIKELY ISSUE]`, `[ASSUMPTION]`,
`[STYLE/CLARITY]`, `[SAFETY/COMPLIANCE]`.

Two rules do most of the work. **A partial view caps the verdict at
`REVISE BEFORE USE`** — you cannot approve what you did not see. And **"no
material issues" is a real result**: six headed passes create pressure to fill
them, and manufacturing a finding to look thorough is a failure of the skill, not
a success.

## Installation

Markdown-only. No code, no dependencies, no configuration.

### Quickest — one line

```bash
curl -fsSL https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/install.py | python3 - verify-results
```

That finds your Hermes home (`$HERMES_HOME`, else `%LOCALAPPDATA%\hermes` on
Windows, else `~/.hermes`) and places `SKILL.md` in the `productivity` category.

### Manual install

```bash
mkdir -p <hermes-home>/skills/productivity/verify-results
cp SKILL.md <hermes-home>/skills/productivity/verify-results/
```

### Prerequisites

None for inline use — any model, any platform.

Routing to a *different* model additionally needs the
[dev-pair](../dev-pair/) skill at **v1.1.12 or later** (earlier versions have no
`verify` subcommand) with `devpair` on PATH. Without it the skill runs inline and
says so, rather than silently ignoring your model choice.

### Verifying the install

```bash
ls <hermes-home>/skills/productivity/verify-results/SKILL.md   # should exist
```

There should be exactly **one** copy. If `SKILL.md` also appears at
`<hermes-home>/verify-results/`, that is a stale artefact from an installer older
than v0.0.4 — delete the stray directory.

## Using it

### 1. From a Hermes conversation — just ask

```
verify this before I commit
audit that output for hallucinations
what's wrong with this migration?
is this right?
check this for hallucinations before it goes to the client
```

The skill triggers on any request for a second opinion on finished work —
including the assistant's own previous output.

### 2. What a clean result looks like

Most reviews are not clean, but this matters more than the noisy case, because a
tool that cannot say "this is fine" will invent problems to stay useful:

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

Four words of praise and no invented findings. That is a correct output.

### 3. What the verdicts commit you to

| Verdict | Means | What happens next |
|---|---|---|
| `APPROVE` | No material issues found | Proceed. |
| `APPROVE WITH MINOR EDITS` | Only `[MINOR]` findings **and** a full evidence basis | Apply the edits; no re-verification. |
| `REVISE BEFORE USE` | `[MAJOR]` findings, **or** the evidence was partial | Fix, then re-run the skill on the revised work. |
| `DO NOT USE` | `[CRITICAL]` findings | Stop. Do not ship or send. The critical findings get quoted to you. |

`REVISE BEFORE USE` is a loop, not a rating: fix → re-verify → re-verdict, and
the re-run must say it is a re-verification and what changed.

### 4. Where it fits

Best used where evidence, not opinion, decides:

- **Pre-merge on a diff.** The strongest case — PASS 5 becomes runnable commands
  rather than advice.
- **Auditing generated output** for hallucinations, where separating a verified
  error from an unsupported claim is the entire job.
- **Client-facing or compliance-sensitive prose** before it is sent — the
  `[SAFETY/COMPLIANCE]` label exists for exactly this.
- **As a CI gate** via `devpair verify --gate` (exit 2 blocks).

Not the tool for: producing work from scratch, or anything still in flight. It is
a post-hoc gate — running it on a half-finished deliverable is a different job.

## Verifying with a different model

By default it runs **inline** — the same model that produced the work, marking
its own homework. That catches slips but is weak on blind spots, because the
errors and the review of them come from the same priors.

With [dev-pair](../dev-pair/) installed you can name another model:

```
verify this using kimi
verify with both
```

`using both` runs inline *and* independently, then reconciles — by running the
PASS 5 checks and letting the evidence decide, not by averaging opinions.

Underneath, that is:

```bash
devpair verify --with <provider>/<model> \
               --driver <your-live-provider>/<your-live-model> \
               --requested-by user \
               --files report.md          # or --diff for code
```

Four things to know before routing anything out:

- **The work leaves your machine.** `--files`/`--diff` posts the content to a
  third-party API. dev-pair redacts credential-shaped values from the whole
  outbound prompt — evidence, your question, and replayed session history — but
  it is pattern-based: anything it does not recognise is sent. Never route work
  you would not paste into that provider yourself.
- **It costs a second set of tokens.** That decision is the user's, so the skill
  never routes unless asked.
- **`using both` is a manual procedure, not an orchestrator.** Nothing runs the
  two passes and merges them for you, and nothing enforces the reconciliation
  steps. If the settling checks are not going to be run, ask for
  `using <model>` and read the two reports separately rather than claiming a
  reconciliation that did not happen.
- **The tool clips oversized evidence** — roughly 24k characters per file, 60k
  for a diff, 90k in total. Clips are marked in-band so the reviewer can see it
  was not shown everything, but split large work into named slices rather than
  let that happen.

### What `--gate` does and does not check

`devpair verify --gate` exits **2** on `DO NOT USE` / `REVISE BEFORE USE`, on any
`[CRITICAL]` finding, on a verdict it cannot parse, and on a review carrying two
*different* verdicts. It fails closed: an answer it cannot read, or cannot pick
between, is never a pass.

What it **cannot** tell is whether the `EVIDENCE BASIS` line is honest, whether
the reviewer really ran the command it quoted, or whether an `APPROVE` was issued
on a partial view. A model that skips the evidence basis entirely and writes
`APPROVE` passes the gate. Treat it as a floor — read the evidence basis yourself
before trusting a pass.

## Troubleshooting

**"It approved something obviously broken."**
Check the `EVIDENCE BASIS` line first. An approval on a partial view is the
skill's known failure mode and the reason that line is mandatory — if it says the
reviewer only saw a summary, the verdict should have been capped at
`REVISE BEFORE USE`. Re-run with the real diff or file attached.

**"It invented findings on work that was fine."**
Padding is an explicit rule violation. Point at the worked example above; "None."
in every pass is a valid output. If it keeps happening, the work being reviewed
may be too vague for the passes to bite on — attach the actual artefact rather
than describing it.

**"I asked for another model and it reviewed inline anyway."**
`devpair` is missing from PATH or is older than v1.1.12. Check with
`devpair verify --help`; if the subcommand is absent, update dev-pair. The skill
is supposed to tell you this rather than silently downgrade — if it did not, that
is a bug worth reporting.

**"The other model's review reads like it saw something else."**
It probably did. The routed reviewer runs toolless in a separate process and
cannot see your conversation, so the work must be serialised into the call with
`--files`/`--diff`. A critique of a *summary* of the work reads exactly like a
critique of the work. Never summarise to make it fit; slice it instead.

**"Two models disagree and I don't know who's right."**
That is what PASS 5 is for. Run the settling checks, show the raw output
verbatim, and let the evidence decide. Where nothing settles it, report both
positions as unresolved rather than manufacturing a consensus.

## The honest limit

A different model family reduces shared blind spots; it does not eliminate them.
Frontier models share training data and failure modes. And a second opinion is
still an opinion — a finding neither model can evidence stays unproven no matter
how many models assert it.

In inline and `both` modes there is also a structural conflict of interest: the
model running the settling checks is the model that produced the work. It chooses
the command and reports the result. The mitigations are verbatim output and an
explicit line saying the producer also reconciled. For anything high-stakes, run
the PASS 5 commands yourself — that is the only fully independent path.

## Version & history

Current: **0.0.5**. See [CHANGELOG.md](CHANGELOG.md) — semver, patch (+0.0.1) per
published change.

## License

MIT.
