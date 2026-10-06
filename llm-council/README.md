# llm-council — multi-model deliberation that keeps the dissent

Four advisor seats answer a hard question independently, review each other
anonymously, and a chairman synthesises — preserving disagreement instead of
averaging it away. This folder ships the **protocol** (`SKILL.md`) and **patches
for the runtime** that implements it, the `girayk/hermes-council` plugin.

## Install the skill

```bash
curl -fsSL https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/install.py | python3 - llm-council
```

This installs `SKILL.md` (and this README and the patches beside it) under
`<hermes-home>/skills/autonomous-ai-agents/llm-council/`. On its own the skill
tells an agent how to run a council with subagents. If the plugin is installed
too, its bundled copy appears as `hermes-council:llm-council` — same protocol;
this copy adds the runtime-honesty section.

## Upgrading the hermes-council plugin

The plugin is third-party and carries no licence file, so its code is **not**
redistributed here — only our changes, as `git format-patch` output:

   - `0001-devpair-convergence-phases-5-6-premise-confidence-fl.patch`
   - `0002-docs-compact-vs-strict-protocol-table-exact-call-cou.patch`
   - `0003-council-review-fixes-GLM-5.3-failed-corrective-retry.patch`

```bash
hermes plugins install girayk/hermes-council            # if not installed yet
cd <hermes-home>/plugins/hermes-council                 # (per profile: profiles/<p>/plugins/…)
git am <hermes-home>/skills/autonomous-ai-agents/llm-council/plugin-patch/*.patch
HERMES_AGENT_SRC=<hermes-agent> pytest tests -q          # expect 61 passed
hermes plugins validate .
```

Verified to apply on upstream `18a6663` (v1.0.0) and `8b7d666`. A later
`hermes plugins update` may conflict with the patched files — re-apply after
updating, or keep the plugin pinned.

### What the patches change

| | compact (default) | strict (`protocol: strict`) |
|---|---|---|
| Labels | seat order → Response A, B, C… | shuffled per deliberation |
| Who reviews | every member, own answer included | never its own answer (or the judge) |
| Ranking parse | lenient | complete permutation, one corrective retry, then discarded + counted |
| Stakes | `MATERIAL FLAW:` lines requested | a flaw line or "No material flaws found." required |
| Aggregation | average rank | first-place votes, then average rank |
| Calls | up to `2N+1` | up to `3N+1`; `max_calls` downgrades visibly to compact |

Both protocols: members state Confidence and a Flip condition; material flaws are
kept in the chairman guidance whatever the ranking; every outbound member,
reviewer and judge message (and the guidance) passes through Hermes' fail-closed
egress scrub; members and reviewers never get tools — only the chairman acts.

Strict is **self-excluded peer review, not fresh reviewers**: the reviewers are
still the Stage-1 seats. When you need truly fresh reviewers, follow `SKILL.md`
with subagents.

## Status

Strict mode has not been benchmarked against compact; it stays opt-in. Seat
models are yours to configure (`hermes council configure`); none are set by
these patches.

## Credits

Protocol and runtime: [girayk/hermes-council](https://github.com/girayk/hermes-council),
after [karpathy/llm-council](https://github.com/karpathy/llm-council).

Current: **1.0.0**. See [CHANGELOG.md](CHANGELOG.md).
