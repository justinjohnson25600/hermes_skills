# quality-guard

A pre-delivery verification gate for AI agents. Turns "check this" into mandatory verification
**actions** — execute the code before presenting it, fetch the docs before citing API behaviour,
search before stating current facts — and makes the result observable through a terse
verification footer.

Because "be accurate" changes nothing: the model already tries to be accurate. What reduces
hallucination is *doing something*, and proving it was done.

## What it does

- **Risk tiers** decide how deep verification goes: internal drafts skip the gate entirely;
  published low-stakes content gets a claims check; relied-upon output (deployed code, client
  documents, clinical/scientific content, instructions others follow) gets the full gate.
- **Claim-type → action mapping**: every claim type has a mandatory action and a tool.
  Code is executed. Documentation is fetched. Current facts are searched. Invented content
  fails the gate.
- **Escalation ladder** when a check fails: verify → qualify (labelled `[ASSUMPTION]`,
  `[UNSUPPORTED CLAIM]`, …) → ask → deliver flagged. A deliverable that fails the gate is
  never labelled production-ready, client-ready or publication-ready.
- **Verification footer** — the observable proof the gate ran:

  ```
  ---
  Verified: code executed, test suite green; mail config fetched via Context7
  Unverified: none
  Assumptions: none
  ```

- **Lane demarcation with verify-results**: this skill runs *before* output exists; verify-results
  is the structured critique *after* output exists. Neither duplicates the other.

Pairs well with [verify-results](../verify-results/) (post-hoc critique) and
[dev-pair](../dev-pair/) (cross-model second opinions).

## Install

```bash
# with the repo as a Hermes tap
hermes skills tap add justinjohnson25600/hermes_skills
hermes skills install justinjohnson25600/hermes_skills/quality-guard

# or single-skill, no tap
hermes skills install https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/quality-guard/SKILL.md
```

`references/verification-actions.md` ships alongside and is loaded on demand — extended
claim-type mapping, mixed-tier documents, partially-runnable code, and conflicting sources.

## Current: **0.1.0**

Initial public release.
