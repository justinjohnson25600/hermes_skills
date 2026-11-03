---
name: quality-guard
version: 1.0.7
platforms: [macos, windows, linux]
description: Use before delivering deployable or relied-upon work.
---

# Quality Guard — Pre-Delivery Verification Gate

## Purpose

This skill exists because "be accurate" changes nothing — the model already tries to be accurate. What reduces hallucination is *doing something*: running the code, fetching the document, invoking the research engine. This skill mandates those actions before a deliverable goes out, and makes the result observable via a short verification footer.

It is a gate, not a checklist. A deliverable that fails the gate is never presented as client-ready, production-ready, or publication-ready.

## When to Use

Use for Tier 3 relied-upon deliverables below, and when Justin asks for the quality guardrail, pre-answer validation, a hallucination check before answering, or production-ready, publication-ready or client-ready work. Keep British English throughout. Routine internal drafts do not trigger this gate; completed-work critiques and domain-owned report gates follow the lane demarcation below.

## Lane demarcation

Two skills share one vocabulary and split the timeline:

- **quality-guard (this skill)** runs *before* output exists — it shapes and verifies the deliverable during production.
- **verify-results** runs *after* output exists — a six-pass structured critique of work already on the table.

If Justin asks for a critique, review, or audit of something already written, hand off to verify-results. If a Theorem report build is in flight, stand down entirely — report-completeness-contract and its sibling gates are the authority there, and double-gating wastes tokens and time.

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
| Code correctness | **Execute it** in the sandbox. Run the linter. Confirm imports resolve and the happy path runs. If it cannot run here (needs Plesk, a live DB, credentials), label it explicitly as untested with the reason. For scripts and CLIs, execute the artefact itself (including `--help` / dry-run paths) — a successful import proves nothing about runtime behaviour. | bash |
| Destructive system action (terminating processes, deleting or renaming live files, bulk changes) | **Dry-run first, then verify the blast radius independently.** Run the tool's classify/dry-run mode, then confirm what it would affect by a second means (e.g. a PID-reuse-guarded ancestry walk), never the tool's own report alone. An "orphan"/"unused" classification must mean the resource has LOST its owner — "unknown to my system" also matches other tenants' LIVE resources on a shared host (measured case: a reaper proposed 12 processes that were the user's open VS Code / Claude Code MCP servers). | bash |
| API / library / framework behaviour | Fetch current documentation before citing signatures, config keys, or behaviour. Never cite from memory for anything versioned. | `web_extract` on the doc URL, or `web_search` to find it first. If a docs MCP (Context7 or similar) is enabled this session, prefer it — but verify it is actually available before relying on it; a mandatory action that names an absent tool silently degrades to citing from memory. |
| Package versions, availability | Check the registry. | npm/PyPI via bash or web |
| Clinical, scientific, physiological claims | Invoke the research engine; use its Research Synopsis. If one already exists in context, cite from it rather than re-searching. | medical-research-engine (Consensus, PubMed) |
| Current facts, prices, laws, product details | Search. If search is unavailable or inconclusive, state the claim as unverified — do not soften it into vague confidence. | web_search |
| User-supplied material | Re-read the actual source before quoting or summarising it. Supplied material outranks every external source. | view / context |
| Statistics, dates, named studies | Verified against a source in this session, or cut, or explicitly flagged. No third option. | as above |

Anything invented to fill a gap — a plausible figure, a remembered API signature, an unfetched citation — fails the gate.

**Bind lint claims to the exact invocation.** Record the executable, working directory and configuration/rule scope. A correctness-only `--isolated --select E9,F` pass is not a full inherited-rule pass. Compare baseline and candidate with the same command before attributing findings, then fix the agreed scope without narrowing load-bearing fail-closed handlers merely to appease a style rule. Prefer specific, justified annotations for intentional safety boundaries over global ignores.

**Bind test claims to exact scope and bytes.** Record the tested revision, commands, excluded maintained files and replaced runtime boundaries. Report primary tests, subtests and skips separately; a regression run excluding pending lifecycle modules is not a whole-suite pass. Quote a runner's final counts and duration from its actual stdout log, not by rounding or reconstructing them from JUnit suite attributes, which measure a different interval and may include subtests. Preserve a passing frozen revision before introducing the next failing contract, and label its result as that baseline rather than current in-flight green. Keep native fixture, shipped-adapter, package and installed-application acceptance as separate verdicts so a component pass cannot silently authorise deployment.

**Execute code hidden behind mocks.** When tests replace subprocess or native-exchange calls, separately execute the exact shipped helper program with only its external boundary intercepted; mocked success does not exercise its escaping, framing, parsing or output. Follow the cross-process helper recipe in `references/verification-actions.md` before relying on that boundary.

**Audit the assertions before trusting green.** Replace tautologies with observable behaviour. When an authorised feature deliberately supersedes a test's method-absence or internal-object-shape expectation, have the controller update that expectation into an equivalent or stronger behavioural safety contract, record the scope change, and rerun it plus the full suite. Preserve permission and no-effect refusals; do not let an implementer silently edit protected tests or exclude the conflict to manufacture green.

## Deployed-code acceptance

1. **For host extensions, verify the real boundary before live activation.** Exercise native callbacks and marshalling in an isolated process, then click the actual host control and inspect the populated UI. Managed calls, parsed Ribbon XML and successful registration are different evidence layers, not substitutes for host acceptance. Use [Desktop integration verification](references/desktop-integration-verification.md) for Office/COM, Word editing and account-authorisation depth.
2. **Test preservation, not merely successful writes.** For shared settings, reproduce two independently loaded snapshots racing with account addition, deletion, credential rotation and token refresh; a decryptable atomic file can still contain a lost update.
3. **Gate the package and the Git index separately.** Publish only an exact allow-listed archive after temporary-archive read-back, and inspect the staged source tree for retained test builds, encrypted stores and credentials. Encryption does not make account data distributable or committable.
4. **Bind release claims to exact bytes.** Freeze the verified artefact, compare the installed and packaged hashes, and keep later test rebuilds from silently replacing the release candidate. For transactional installation, packaging and frozen-build checks, use [Verification actions](references/verification-actions.md).

## Escalation ladder

When a check fails, escalate in this order. Do not skip steps and do not stall on step 3 for minor points.

1. **Verify** — take the action above.
2. **Qualify** — if unverifiable (including when a required tool or connector is unavailable this session), mark it with the shared labels: `[UNSUPPORTED CLAIM]`, `[ASSUMPTION]`, `[LIKELY ISSUE]`, `[SAFETY/COMPLIANCE]` — a deliberate subset of verify-results' full vocabulary; `[VERIFIED ERROR]` and `[STYLE/CLARITY]` rarely apply pre-delivery because such findings are simply fixed.
3. **Ask** — if the unverified claim is load-bearing (the deliverable is wrong or dangerous without it), ask Justin one focused question rather than guessing.
4. **Deliver flagged** — if proceeding anyway, deliver with the limitation stated plainly — and **never label the output production-ready, client-ready, or publication-ready**. That final rule is the actual guardrail; everything above it is process.

**Unattended runs.** Step 3 assumes someone is there to answer. In a cron job, a batch run, or any context with no operator, there is no one to ask — so step 3 does not apply and you go straight to step 4: deliver flagged, with the limitation stated, and never labelled ready. A gate whose only escalation is a question it cannot ask is not a gate.

## Verification footer

**Language check (mandatory, all tiers):** every reply and every client-facing artefact is British English throughout — interim tool commentary included. A model may drift interim narration to another language in long sessions; that drift is a defect: detect it, revert immediately, and continue in English.

Scan client-facing artefacts before delivery — a non-zero count fails the gate. Scan for the **full** drift range, not just Han characters:
`[\u2e80-\u2eff\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\u3100-\u312f\u3130-\u318f\u3400-\u4dbf\u4e00-\u9fff\ua000-\ua4cf\uac00-\ud7af\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef]`

A narrow `[\u4e00-\u9fff]` class covers CJK Unified Ideographs only and misses 9 of 11 realistic drift samples — full-width punctuation, ideographic space, kana, Hangul, Ext-A and compatibility forms all pass clean. Drift usually arrives as punctuation before it arrives as words, so the narrow class misses the earliest signal. Run the shipped checker rather than eyeballing it — it lives beside this skill, so use the absolute path (a bare relative path only resolves when the working directory happens to be the skill folder, which it is not in a cron job):

```
python "%LOCALAPPDATA%\\hermes\\profiles\\<profile>\\skills\\software-development\\quality-guard\\scripts\\quality_gate.py" \
  --response reply.md --artefact report.html --tier 3 --log runs.jsonl
```

Exit code 1 means the gate failed. `--log` appends a JSON-lines run record, so "did the gate run?" has an answer afterwards.

Tier 3 outputs (and Tier 2 with unverified residue) are accompanied by this exact block, kept terse:

```
---
Verified: <actions taken — e.g. "code executed, Pest suite green; Laravel 12 mail config fetched via web_extract">
Unverified: <claims that could not be checked, or "none">
Assumptions: <assumptions relied upon, or "none">
```

**Placement rule:** the footer — and any inline `[UNSUPPORTED CLAIM]`-style labels — belong in the chat response accompanying delivery, or inside internal/technical deliverables. They must **never** appear inside a client-facing artefact (an HTML report, a published page, a document the client reads). The client sees clean work; Justin sees the verification record alongside it.

**Classify checker inputs correctly.** `--artefact` always applies client-facing placement rules, even to Markdown. Check an internal technical hand-off that legitimately contains its verification footer via `--response` in a separate invocation; this checks both the footer and language rather than falsely classifying the hand-off as client-facing. Keep the original failed run in the log; do not delete a required technical footer or weaken the checker merely to obtain green.

**Fill it, or it is not evidence.** The block above is a template. Copying it through with `<actions taken>` still in the slots produces something that looks like proof and contains none. An unfilled placeholder (`<…>`, `TBD`, `TODO`) fails the gate exactly as a missing footer does.

**Keep the exact three labels.** `Verified:` / `Unverified:` / `Assumptions:`, in that order, one per line, unadorned. Variants like `**Verified:**` or `Unresolved:` read the same to a human and are invisible to a checker — and a footer nothing can check is not observable proof. Measured across 17,026 assistant messages in this estate: 180 footer attempts, only 108 in the specified shape. This is where the format fails most often.

The footer is the observable proof the gate ran, and it is what makes this skill testable. Do not narrate the checking process anywhere else in the response — the work stays silent, the footer speaks.

**Apply it to your own work.** This gate is not exempt from itself. Anything produced under it — including changes to this skill, its checker, or its documentation — is a Tier 3 deliverable and carries a footer. A verification skill that never verifies itself is asking for a trust it has not earned.

- **Run the checker on the artefacts you just wrote**, not only the ones you were asked to check. Documentation that describes a rule is the most likely place to break it.
- **Mutate the check before trusting it.** A passing test proves the test ran. Break the thing being checked and confirm the check goes red; if it stays green, the green was worthless.

## Ordering with human-voice-filter

When both run on the same deliverable: quality-guard verifies facts first, human-voice-filter sweeps style second, and the verification footer is appended **after** the voice filter — so the filter cannot soften uncertainty qualifiers, and the quality pass cannot reintroduce banned AI phrasing.

## Reference

For the fuller claim-type → action mapping, including edge cases (mixed-tier documents, code that spans local and Plesk-only behaviour, claims sourced from Justin's own prior reports), read `references/verification-actions.md`.
