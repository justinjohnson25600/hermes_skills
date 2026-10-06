---
name: llm-council
description: Use when the user asks for a council, second opinions, a debate, or multi-perspective deliberation on a question — or when a decision is high-stakes, contested, or ambiguous enough that a single answer risks being confidently wrong or sycophantic. Triggers include "/council", "council", "get multiple opinions", "stress-test this idea", "am I right about", "devil's advocate", "should I".
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [council, deliberation, multi-model, review, anti-sycophancy]
    related_skills: [dev-pair, verify-results]
---

# LLM Council

## Overview

Convene a council of independent AI advisors to deliberate on a question, then synthesize a final answer that preserves disagreement instead of smoothing it over. The council is built to disagree with the user when warranted.

**Core principle: independence before interaction.** Council members must form positions in isolation, review each other blind, and dissent must survive into the final answer.

(Sources and design rationale: see the repository README.)

## This protocol vs the installed `council` runtime

This page is the protocol an agent runs itself with subagents. The plugin's
runtime (the `council` provider / `council_deliberate` tool / `/council`) is an
approximation, and you must not claim more than it does:

- **compact** (default): members review ALL anonymised answers **including their
  own**; labels follow seat order; rankings parse leniently; aggregation is by
  average rank. This is cheaper but is NOT "fresh independent reviewers".
- **strict** (`protocol: strict`, opt-in): labels shuffled per deliberation, no
  member reviews its own answer, complete rankings required (one corrective
  retry, then discarded and counted), stakes statement required, first-place
  votes before average rank. Reviewers are still Stage-1 seats, not fresh
  subagents — say "self-excluded peer review", not "fresh reviewers".
- Both: members state Confidence + Flip condition; `MATERIAL FLAW:` lines are kept
  in the chairman guidance regardless of ranking; outbound text is redacted;
  members/reviewers have no tools; only the chairman acts.

When the user needs the full protocol below (fresh reviewers, the user's own
position entered anonymously), run it yourself with subagents rather than
claiming the runtime did.

## When NOT to Use

- Simple factual lookups or mechanical tasks — a council adds cost, not accuracy.
- When the user asked a quick question and did not opt into deliberation — offer the council, don't force it.

## The Protocol

Run all three stages. Do not skip Stage 2 even if Stage 1 answers look similar — surface-level agreement often hides different reasoning.

### Stage 0 — Frame the question

Restate the user's question neutrally before dispatching. Strip any framing that presupposes the answer the user wants (e.g., "don't you think X is better?" becomes "compare X and Y"). If the user's framing contains a flawed premise, the council must be asked about the premise too, not fed it as fact.

Two rules govern what survives reframing:

- **Strip evaluative framing** — the user's stated preference, validation-seeking phrasing, leading adjectives.
- **Keep decision-relevant facts as neutral facts** — constraints, prior commitments, sunk costs ("the decision has already been announced to the team" stays in, stated flatly, because it changes the practical analysis).

If the user stated their own preferred answer, set it aside for Stage 2 (see below) — it does not get a Stage 1 seat.

### Stage 1 — Independent opinions (parallel)

Dispatch **4 council members** (default; user may set 3–6) as parallel subagents in a single message. Each member gets the same neutral question but a distinct lens:

| Seat | Lens |
|------|------|
| First-Principles Analyst | Reason from fundamentals; ignore convention and popularity |
| Skeptic | Assume the obvious answer is wrong; hunt for failure modes, hidden costs, base rates |
| Pragmatist | What actually works in practice — constraints, effort, reversibility, second-order effects |
| Researcher | Ground claims in verifiable evidence; use web search/code inspection where available |

**Absent-party rule:** if the question involves someone who isn't in the room — a coworker, cofounder, customer, reviewer, team — reassign the Pragmatist seat to **Absent-Party Advocate**: construct that party's strongest, most sympathetic case and state what a fair resolution looks like from their side. This targets the headline harm documented in Cheng et al. (2025) — reduced willingness to repair relationships — and benchmarked as the single largest quality gain.

Each member's prompt MUST include these standing orders:

```
You are one member of an advisory council. Other members are answering
independently; you cannot see their answers.
- Commit to a clear position. "It depends" without a decision rule is a
  non-answer.
- Do not flatter or validate the asker. If the question's premise is
  flawed, say so first.
- State your confidence (low/medium/high) and the top 1-2 things that
  would change your mind.
- If the question involves an action the user took or plans, end with
  one line: "ENDORSE: yes/partial/no" — whether you endorse it as right.
- Return raw analysis, not a message to the user.
```

Members are blind to each other and to which seat produced which review later.

### Stage 2 — Anonymized peer review (parallel)

Prepare the review packet:

1. **Shuffle** the Stage 1 responses and label them Response A, B, C, D.
2. **Sanitize** each response: delete self-identifying lines ("as a skeptic…", "reasoning from first principles…") and any persona references. Reviewers must judge arguments, not seats.
3. **If the user stated a preferred answer**, add it as one more anonymized response (paraphrased in the same neutral register) — it gets ranked and critiqued like the rest. Do not mark it as the user's.

Dispatch **one reviewer per council seat** (default 4, matching council size), in parallel. Reviewers are fresh subagents, never the original members. **Each reviewer receives the full packet of all responses** and must:

1. Rank all responses from strongest to weakest on accuracy, insight, and completeness.
2. Apply **stake-weighted criticism** to every response, including the one ranked first: identify flaws that would change a decision if real, and for each flaw **name the decision that would change**. If a response has no such flaw, write exactly "no material flaws found" — fabricated nitpicks are worse than admitting no flaws, because boilerplate criticism launders sycophancy ("I received criticism, therefore this is balanced").
3. List every claim the responses disagree on, explicitly.
4. Note where a response's stated confidence is out of line with its evidence.

Praise without critique is forbidden. A review that skips the stake-weighted rule (flaws with no named decision, or neither flaws nor the explicit "no material flaws found" line) gets re-run once with the rule made emphatic; if it fails again, discard it and note the discard in the tally.

### Stage 3 — Chairman synthesis

You (the main agent) are the chairman. Aggregate the rankings first: order responses by **count of first-place votes; break ties by average rank**. If you disagree with the resulting order, say so in the tally and explain why — never silently substitute your own ranking. After the tally is fixed, you may de-anonymize: attribute positions by seat name (e.g., "the Skeptic dissented"), which is more useful to the reader than letters.

Produce the final deliverable with exactly these parts, in order:

1. **Verdict** — the council's answer in 2–4 sentences, leading with the conclusion, including an overall confidence level derived from members' stated confidence and reviewer agreement.
2. **Vote tally + endorsement split** — how reviewers ranked the responses (e.g., "Response C ranked first by 3 of 4 reviewers"). If the user's own position was reviewed (Stage 2, step 3), report where it ranked. If members gave ENDORSE lines, report the split ("N of M councilors endorsed your action") followed by: "Note: language models endorse users' actions ~50% more often than humans do — treat even this council's output as biased toward you."
3. **The other side** *(only when an absent party exists)* — that party's strongest case, **quoting the Absent-Party Advocate directly**, not summarizing.
4. **Consensus** — points every member independently converged on. When the question involves a relationship or another party, this must include concrete, sequenced next actions (what to say, in what order) — principles alone benchmarked worse than a plain assistant here.
5. **Dissent** — disagreements, stated in the dissenter's strongest form. If a minority position exists, present it as a live alternative, not a footnote. Never write "the council broadly agrees" when it didn't.
6. **What would change the verdict** — the 2–4 strongest flip conditions from members' "what would change my mind" statements; drop duplicates and trivia.
7. **The one observation that would prove this verdict wrong** — a single concrete, checkable falsifier (e.g., "find a written record of X; if it exists, the verdict flips"). One sharp falsifier beats a generic verification checklist nobody runs.

## Anti-Sycophancy Rules (all stages, including the chairman)

These counter the failure modes documented in Cheng et al. (2025):

| Sycophantic reflex | Council rule |
|---|---|
| Open with agreement/validation ("Great question!", "You're right that…") | Open with the position itself |
| Endorse the user's stated plan because they stated it | The user's preference gets no Stage 1 seat; it enters Stage 2 anonymized and gets critiqued like any other response |
| Smooth disagreement into a mushy middle | Preserve dissent verbatim in Stage 3, part 4 |
| Foster dependence ("ask me anytime!") | End with a single concrete falsifier the user can check without the AI (Stage 3, part 7) |
| Erase the absent party from a conflict | The Absent-Party Advocate seat argues their strongest case, quoted verbatim (Stage 3, part 3) |
| Present the AI as objective | Disclose the endorsement split and the ~50% LLM over-endorsement base rate (Stage 3, part 2) |
| Soften bad news about the user's idea | If the council's verdict is "no", the Verdict says "no" in the first sentence |

## Execution Notes

- Stage 1 and Stage 2 dispatches each go in a single message so subagents run concurrently.
- If the runtime supports model selection, diversify models across seats (e.g., mix model tiers) — model diversity approximates Karpathy's multi-provider council. If not, persona diversity alone still works.
- Keep member responses out of the user-facing output; the final deliverable is only the Stage 3 synthesis (offer the full transcript on request). Brief progress lines while stages run ("dispatching 4 council members…") are fine.
- Council size: 3 minimum (below that, "peer review" is a dialogue, not a council). Above 6, review cost grows quadratically for little gain.

## Common Mistakes

- **Leaking identities into Stage 2** — reviewers who know the Skeptic wrote Response B review the persona, not the argument.
- **Reusing Stage 1 members as their own reviewers** — self-review re-introduces commitment bias; use fresh subagents.
- **Chairman overriding the tally silently** — if you disagree with the reviewers' ranking, say so and why; don't quietly substitute your own verdict.
- **Passing the user's loaded framing straight to members** — Stage 0 exists because a council fed a leading question returns a confident echo.
