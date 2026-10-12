# Routing (normative)

How the brief's workflow mandate is chosen. Every skill a route names is verified installed, one by
one (H4); a missing step uses its inline equivalent. Placeholders here (`<brief path>`) describe what
goes in; a brief always carries the real value.

## Tier signals

- **T0 trivial:** one obvious, reversible change, under about 15 minutes.
- **T1 small:** one component; the behaviour is already clear.
- **T2 medium:** one feature, skill or tool; one session; several files.
- **T3 large:** several components or phases; several sessions; persistent state.
- **T4 epic:** several independent subsystems.

## Pick the column, in order

1. The user's stated framework, if it is installed (if not, say so and continue).
2. A GSD project (`.planning/` exists) and GSD installed: column C.
3. Superpowers and GSD both installed: column A for T0–T2, column B for T3–T4.
4. Only one installed: its column.
5. Neither: column D.

`.planning/` without GSD installed: its documents are context only; pick by rules 3–5.

## Matrix

| Tier | A — superpowers | B — GSD, no `.planning/` | C — GSD project | D — neither |
|---|---|---|---|---|
| T0 | Do it, then verification-before-completion | gsd-fast | gsd-fast | Inline: do, then verify with evidence |
| T1 | test-driven-development → verification-before-completion | Inline: test-first, then verify (mention gsd-new-project if the user wants tracking) | gsd-quick | Inline: test-first, then verify |
| T2 | Settled design: writing-plans → using-git-worktrees (existing repo only) → subagent-driven-development or executing-plans → requesting-code-review → verification-before-completion → finishing-a-development-branch. Open design choices: brainstorming seeded with the brief and limited to those choices, then the same chain | Greenfield: gsd-new-project (interactive, brief as context) → gsd-plan-phase 1 --prd `<brief path>` → gsd-execute-phase 1 → gsd-verify-work 1. Existing repo: inline full phases (mention gsd-onboard) | gsd-phase (add) → gsd-plan-phase `<new phase number>` --prd `<brief path>` → gsd-execute-phase → gsd-verify-work (gsd-quick --full when it fits one plan) | Inline full phases: clarify → design → plan → test-first build → review → verify → ship |
| T3 | Decompose into sub-projects; the full T2 chain for the first; the rest as a roadmap | Greenfield: gsd-new-project → per phase: gsd-plan-phase → gsd-execute-phase → gsd-verify-work → gsd-ship. Existing repo: gsd-onboard first | gsd-new-milestone → per phase as in B | Inline phases plus a phase list |
| T4 | Decompose; brief the first sub-project at its own tier; roadmap for the rest | As T3, one milestone per subsystem | gsd-new-milestone per subsystem | Roadmap only |

**Concrete values.** Write every route with real values: the actual brief path, plan path and phase
number. The self-check flags placeholders in routes.

**GSD greenfield** starts with interactive `gsd-new-project`; `--auto` implies GSD's auto-approval
mode and is used only when the user opts in.

## Type overrides (resolved through the same column)

| Type | A | B and D | C |
|---|---|---|---|
| Bugfix | systematic-debugging, regression test via test-driven-development | Inline: reproduce → isolate → hypothesise → fix with a regression test → verify | gsd-debug |
| Spike | A time-boxed spike section in the brief | B: gsd-spike; D: a time-boxed spike section | gsd-spike |
| Skill or agent instructions | T2+: writing-plans → writing-skills (baseline scenario first) → requesting-code-review → verification-before-completion; T0–T1: writing-skills | Inline: baseline scenario → write → re-test → refine | The same, tracked as a phase |

## Partial installation

Check every skill of the chosen chain on its own. Replace a missing one with its inline equivalent,
keep the approval and verification gates, and say in the brief and at hand-off what was substituted.
Nothing is installed while briefing; missing skills are offered at hand-off (H11).

| Missing skill | Inline equivalent |
|---|---|
| brainstorming | Present the design section and get the user's approval |
| writing-plans | A written plan of small tasks with files and checks (the bundled `plan` skill when present) |
| test-driven-development | Write the failing test or check first, then the code |
| subagent-driven-development / executing-plans | Execute the plan's tasks in order, running each task's check |
| requesting-code-review | Review the diff against the acceptance criteria; offer co-developers in one sentence |
| verification-before-completion | Run every acceptance-criteria check and show the evidence before claiming done |
| using-git-worktrees / finishing-a-development-branch | Work on a branch; at the end summarise and ask: merge, open a pull request, or keep |
| A GSD command | The column D phase covering the same step |

## Seeding rule

Downstream workflows treat CONFIRMED items as settled and do not re-ask them; they may raise a new
question only for a material fork they find with evidence. When brainstorming runs, it still presents
its design and gets approval (the brief shortens that step, never skips it). GSD keeps its approval
gates unless the user opted into `--auto`. Measured before release: brainstorming, given an approved
brief with a settled design, asked nothing again and moved straight to writing-plans.

## The hand-off prompt names its stop point

Measured before release: handed "I have approved the brief, please start", the agent planned *and
implemented* without showing the plan. Approving a brief approves the design, not an unseen plan. So
every "Run now" prompt says where to stop:

- **Routes that write an implementation plan** (column A at T2+, the GSD plan step in B and C,
  column D's plan phase): "Use the approved brief at `<brief path>` as the design; CONFIRMED items are
  settled. Load `<first skill>`, write the implementation plan to `<plan path>`, then stop and show me
  the plan before implementing anything."
- **Open design choices** (column A, T2): "Load brainstorming with the brief at `<brief path>`. Ask
  only about the open choices in section 8; everything CONFIRMED is settled. After I approve the
  design, write the plan, then stop and show it before implementing."
- **GSD routes:** run the commands in order and keep GSD's own approval gates; after the plan step,
  stop before the execute step.
- **T0–T1 and roadmap-only routes:** no plan stop; do the work and verify with evidence.
- **Waiving the plan stop:** only when the user explicitly asks to skip reviewing the plan and
  confirms it; the prompt then says "write the plan, then execute it" and the brief's change log
  records the waiver. Ordinary wording such as "build it now" or "go" is not a waiver: Run now keeps
  the stop.

The workflow mandate (brief section 11) repeats the same stop point.

## Combined choices at hand-off

When the user picks several things at once, run them in this order: edits → installs → reroute and
version bump → revalidate → co-developer reviews → revise and revalidate → run. Execution starts only
after the reroute and the reviews are complete.
