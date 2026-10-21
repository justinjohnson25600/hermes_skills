---
name: quality-guard
description: "Pre-delivery verification gate. Converts 'check this' into mandatory verification ACTIONS — execute code before presenting it, fetch docs before citing API behaviour, search before stating current facts. ALWAYS trigger when the user says 'apply the quality guardrail', 'run the pre-answer validation', 'check this before answering', 'use the hallucination guardrail', 'make this production-ready', 'publication-ready', or 'client-ready', or when producing any Tier 3 deliverable: code for deployment, client-facing documents, published clinical/scientific content, instructions others will follow, or compliance-sensitive marketing claims (routine marketing copy is Tier 2). Do NOT trigger for internal drafts, brainstorms, or exploratory chat. Do NOT trigger where another domain gate owns quality (e.g. a domain-specific report-completeness contract) or for post-hoc critique of finished work (verify-results)."
version: 0.1.0
author: Justin Johnson
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [verification, accuracy, hallucination-prevention, delivery-gate, quality]
    related_skills: [verify-results, dev-pair]
---

# Quality Guard — Pre-Delivery Verification Gate

## Purpose

This skill exists because "be accurate" changes nothing — the model already tries to be accurate. What reduces hallucination is *doing something*: running the code, fetching the document, searching for the fact. This skill mandates those actions before a deliverable goes out, and makes the result observable via a short verification footer.

It is a gate, not a checklist. A deliverable that fails the gate is never presented as client-ready, production-ready, or publication-ready.

## Lane demarcation

Two skills share one vocabulary and split the timeline:

- **quality-guard (this skill)** runs *before* output exists — it shapes and verifies the deliverable during production.
- **verify-results** runs *after* output exists — a structured critique of work already on the table.

If the user asks for a critique, review, or audit of something already written, hand off to verify-results. If a domain-specific quality gate is in flight (e.g. a report-completeness contract for a specific workflow), stand down entirely — that gate is the authority there, and double-gating wastes tokens and time.

## Risk tiers

Verification depth scales with what the output touches. Decide the tier first; it determines everything downstream.

| Tier | Examples | Obligation |
|------|----------|------------|
| **1 — Internal** | drafts, brainstorms, exploration, "what do you think about…" | Skill does not run. No footer. |
| **2 — Published, low-stakes** | social captions, blog posts, routine marketing copy, image prompts | Claims check only: every factual claim verified or removed. Footer optional, include if anything was left unverified. Compliance-sensitive claims within Tier 2 content escalate to Tier 3 per the mixed-tier rule (see reference). |
| **3 — Relied upon** | deployed code, client documents, clinical/scientific content, instructions others will follow, compliance-sensitive claims | Full verification actions mandatory. Footer mandatory. Gate applies. |

## Verification actions

The core of the skill. For each claim type in the deliverable, take the action — do not substitute a mental check for a real one.

| Claim type | Mandatory action | Tool |
|------------|-----------------|------|
| Code correctness | **Execute it** in the sandbox. Run the linter. Confirm imports resolve and the happy path runs. If it cannot run here (needs a live database, credentials, a browser), label it explicitly as untested with the reason. | terminal |
| API / library / framework behaviour | Fetch current documentation before citing signatures, config keys, or behaviour. Never cite from memory for anything versioned. | Context7, web_fetch |
| Package versions, availability | Check the registry. | npm/PyPI via terminal or web |
| Clinical, scientific, physiological claims | Invoke a research workflow or fetch primary sources; cite the source of every figure. | web_search, web_fetch |
| Current facts, prices, laws, product details | Search. If search is unavailable or inconclusive, state the claim as unverified — do not soften it into vague confidence. | web_search |
| User-supplied material | Re-read the actual source before quoting or summarising it. Supplied material outranks every external source. | read_file / context |
| Statistics, dates, named studies | Verified against a source in this session, or cut, or explicitly flagged. No third option. | as above |

Anything invented to fill a gap — a plausible figure, a remembered API signature, an unfetched citation — fails the gate.

## Escalation ladder

When a check fails, escalate in this order. Do not skip steps and do not stall on step 3 for minor points.

1. **Verify** — take the action above.
2. **Qualify** — if unverifiable (including when a required tool or connector is unavailable this session), mark it with the shared labels: `[UNSUPPORTED CLAIM]`, `[ASSUMPTION]`, `[LIKELY ISSUE]`, `[SAFETY/COMPLIANCE]` — a deliberate subset of verify-results' full vocabulary; `[VERIFIED ERROR]` and `[STYLE/CLARITY]` rarely apply pre-delivery because such findings are simply fixed.
3. **Ask** — if the unverified claim is load-bearing (the deliverable is wrong or dangerous without it), ask the user one focused question rather than guessing.
4. **Deliver flagged** — if proceeding anyway, deliver with the limitation stated plainly — and **never label the output production-ready, client-ready, or publication-ready**. That final rule is the actual guardrail; everything above it is process.

## Verification footer

Tier 3 outputs (and Tier 2 with unverified residue) are accompanied by this exact block, kept terse:

```
---
Verified: <actions taken — e.g. "code executed, test suite green; Laravel 12 mail config fetched via Context7">
Unverified: <claims that could not be checked, or "none">
Assumptions: <assumptions relied upon, or "none">
```

**Placement rule:** the footer — and any inline `[UNSUPPORTED CLAIM]`-style labels — belong in the chat response accompanying delivery, or inside internal/technical deliverables. They must **never** appear inside a client-facing artefact (an HTML report, a published page, a document the client reads). The client sees clean work; the user sees the verification record alongside it.

The footer is the observable proof the gate ran, and it is what makes this skill testable. Do not narrate the checking process anywhere else in the response — the work stays silent, the footer speaks.

## Ordering with a style pass

When a style/voice filter runs on the same deliverable: quality-guard verifies facts first, the style pass sweeps second, and the verification footer is appended **after** the style pass — so the filter cannot soften uncertainty qualifiers, and the quality pass cannot reintroduce banned phrasing.

## Reference

For the fuller claim-type → action mapping, including edge cases (mixed-tier documents, code that spans sandbox and live-only behaviour, claims sourced from the user's own prior work), read `references/verification-actions.md`.
