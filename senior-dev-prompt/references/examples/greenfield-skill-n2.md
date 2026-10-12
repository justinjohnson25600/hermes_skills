# Brief: Release-notes drafting skill

**Metadata:** version: 2 · status: approved · date: 2026-10-12 · tier: T2 · type: new skill or agent instructions · route: writing-plans → writing-skills (baseline scenario first) → requesting-code-review → verification-before-completion · pack: agent-skill · risk: public publishing · self-review: 2 fixed · snapshot: 9c41d07e

## 1. For you
You get a skill that turns the commits since your last tag into draft release notes grouped as Added, Fixed and Changed (SC-1). When nothing changed since the last tag it says so instead of inventing notes (SC-2). You provide a git repository with at least one tag. Two decisions wait for you, both with a safe default already applied (the TO CONFIRM rows in section 9). Effort: one session.

## 2. Operating obligations
Follow the workflow mandate in section 11 in order. Treat CONFIRMED items as settled. Show evidence before claiming any step is done. Stop at the conditions in section 13.

## 3. Original request
> build me a skill that writes release notes from my git history so I can publish it for others

ASSUMED: "publish it for others" means a public skills repository.

## 4. Context
Greenfield: a new folder `release-notes-skill` under the workspace, created at execution with version control initialised. Environment: an agent host with a skills directory and a code tool that runs Python. Reuse check: no installed skill drafts release notes; a hub search found two community skills that format changelogs but do not read git history (decision register, row 2). Recommended tools: `writing-skills` (installed; test-driven skill authoring) and `requesting-code-review` (installed).

## 5. Outcome, users and scenario
Users: the requester, and anyone who installs the published skill.
- SC-1: in a repository tagged v1.2.0 with five commits since, such as "fix: crash on empty input" and "feat: export to CSV", asking for release notes yields a Markdown section with Added, Fixed and Changed entries and the commit range.
- SC-2: with no commits since the last tag, the skill replies "No changes since v1.2.0" and writes nothing.

## 6. Scope and deliverables
In: SKILL.md, a standard-library helper script that collects and groups commits, its tests, README and CHANGELOG. Later: posting the notes to a release page. Out: editing git history; instead, read-only git commands.

## 7. Requirements and safeguards
- FR-1: collect the commits between the last tag and HEAD.
- FR-2: group them by conventional-commit prefix; unprefixed commits go under Changed.
- FR-3: show the draft in the conversation; write a file only when asked.
- NFR-1: works on macOS, Linux and Windows, with a description of at most 60 characters.
- NFR-2: the helper script uses the standard library only.
- SG-1: read-only git access; no commits, tags or pushes.
- SG-2: before publishing, a sanitisation sweep finds no personal paths, names or tokens in the published files.

## 8. Approach and design
A short SKILL.md tells the agent to run `scripts/collect.py`, which finds the last tag with `git describe --tags --abbrev=0`, lists the commit subjects since that tag with `git log`, groups them by prefix and prints Markdown. Rejected: a plugin (code that needs a restart for a read-only job) and asking a hosted model to group commits (cost and non-determinism). Errors: no tags, so explain and offer the full history; not a git repository, so say so. Testing: fixture repositories built in temporary folders.

## 9. Decision register
| Decision | Choice | Status | Why | Override |
|---|---|---|---|---|
| Quote commit messages verbatim | Yes, first line only | TO CONFIRM | Most readable; may expose internal wording | Say "paraphrase" |
| Build or reuse | Build | TO CONFIRM | Two hub skills format changelogs but cannot read git history | Name one to extend |
| Grouping rule | Conventional-commit prefixes | ASSUMED | Widely used; unprefixed commits go under Changed | Name another scheme |
| Licence | MIT | ASSUMED | Common for public skills | Name another |

## 10. Prerequisites you provide
A git repository with at least one tag. No accounts or secrets are needed.

## 11. Workflow mandate
Route (column A, skill-authoring override): writing-plans → writing-skills (baseline scenario first) → requesting-code-review → verification-before-completion. Write the plan to `.hermes/plans/2026-10-12_101500-release-notes-skill-plan.md`, then stop and show it before implementing; approving this brief approves the design, not the plan. After the plan is approved, the first task encodes AC-1 to AC-6 as tests or executable checks. CONFIRMED items are settled; raise a new question only for a material fork found with evidence. Offer co-developer review of the plan in one sentence.

## 12. Acceptance criteria and verification
| AC | Covers | Check | Evidence |
|---|---|---|---|
| AC-1 | FR-1, FR-2, SC-1 | Fixture repository with five commits since v1.2.0 gives grouped notes with the right counts | Test output |
| AC-2 | SC-2, FR-3 | Fixture with no new commits gives "No changes since v1.2.0" and writes no file | Test output |
| AC-3 | NFR-1 | Frontmatter check plus the script tests on all three operating systems | CI log |
| AC-4 | NFR-2 | Import scan finds only standard-library modules | Test output |
| AC-5 | SG-1 | The tests' git command log contains only describe and log | Test output |
| AC-6 | SG-2 | Sanitisation sweep over the published files returns no matches | Sweep output |

## 13. Boundaries and stop conditions
Ask before publishing, creating a repository or tagging a release. Stop and ask when an acceptance criterion cannot be met, a TO CONFIRM row turns out to matter, or a new material fork appears.

## 14. Risks and mitigations
Commit messages may leak internal details: decision row 1, plus a preview before publishing. Unusual tag names: fall back to the full history and say so.

## 15. Definition of done
Every row in section 12 passes with its evidence, the plan's tasks are complete, and the published folder passes the sanitisation sweep.

## 16. Co-developer review
Reviewers: provider-one/model-alpha (family alpha) and provider-two/model-beta (family beta), one paid call each, separate sessions. Snapshot reviewed: 9c41d07e (version 1).
Run report: consented 2 · attempted 2 · completed 2 · verified 2 (run IDs 20261012-101200-1111-2222 and 20261012-101200-3333-4444).
Verdicts as written: alpha "PROCEED WITH CHANGES"; beta "PROCEED".

| # | Finding | Reviewer | Decision | Reason |
|---|---|---|---|---|
| R1 | An empty range must not produce invented notes | alpha | ACCEPT | Became SC-2 and AC-2 |
| R2 | Add a plugin that posts to the release page | beta | REJECT | Out of scope for version 1; listed under Later |

## Change log
- v2 (2026-10-12): co-developer finding R1 accepted, R2 rejected; revalidated.
