---
name: quality-guard
description: "Verify relied-upon work before delivery; record limits."
version: 0.1.1
author: Justin Johnson
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [verification, accuracy, hallucination-prevention, delivery-gate, quality]
    related_skills: [verify-results, dev-pair]
---

# Quality Guard — Pre-Delivery Verification

Require real checks before relied-upon work leaves the agent. The procedure is a safety discipline, not an automatic send blocker or truth detector. The optional helper validates records and bounded execution evidence; it never decides semantic readiness.

## When to Use

- The user asks to apply the quality guardrail, check before answering, or make work client-ready, publication-ready or production-ready.
- Producing deployed code, client documents, instructions others follow, clinical/scientific or compliance-sensitive claims.
- Do not run the full procedure for internal drafts or brainstorming. Use `verify-results` for post-hoc critique of finished work.
- A domain gate replaces only checks whose equivalent coverage is explicit. Retain uncovered factual, delivery and safety checks; avoid duplicating covered work.

## Prerequisites

Use the capabilities actually enabled this session: `terminal`, `read_file`, retrieval/research tools or appropriate equivalents. A named connector is not mandatory. Prefer authoritative documentation for the installed or pinned version; missing access means an explicit limit, never a remembered signature presented as fetched documentation.

The helper needs Python 3.8+ and no packages, credentials, model calls or background services. Resolve a working interpreter for the target system. Execution through `run` is optional and requires an explicitly approved command in the intended sandbox; this skill grants no new permissions.

## Risk tiers

| Tier | Examples | Requirement |
|---|---|---|
| 1 — Internal | exploration, brainstorming, drafts | No mandatory record. Do not imply unperformed verification. |
| 2 — Published, low-stakes | routine marketing or social copy | Check factual claims; remove unsupported claims or make limits explicit. Include a record if uncertainty remains. |
| 3 — Relied upon | deployed code, client work, consequential instructions | Full relevant checks and an operator-facing record. Hold actions with unresolved required checks. |

Apply the strictest tier to the claims it governs, not indiscriminately to every sentence.

## Procedure

1. **Define acceptance.** Name the required checks, final artefacts and relied-upon claims before checking. Distinguish source tests, built/installed bytes, native-host behaviour and live external effects. One layer is not proof of another.
2. **Take real verification actions.** Execute the actual CLI/artefact, its help or dry-run and the applicable tests/linter. For APIs fetch the right version's authoritative docs; for current facts search; for clinical/scientific claims use appropriate primary research. Re-read supplied material for faithful quotations, and independently verify external factual claims: supplied material is not automatically factual truth. Calculate rather than invent figures.
3. **Bound destructive actions independently.** Obtain required permission, preserve a backup and independently check ownership and blast radius. A tool's own dry-run can repeat its own classification error. Unknown ownership is not proof that something is orphaned or safe to remove.
4. **Handle uncertainty safely.** Fix verified errors. For remaining uncertainty use `[UNSUPPORTED CLAIM]`, `[ASSUMPTION]`, `[LIKELY ISSUE]` or `[SAFETY/COMPLIANCE]` with a specific explanation. Ask one focused question when a missing requirement is load-bearing. If nobody is available, **hold unsafe outward delivery or activation**, record the gap and escalate to the operator; do not merely remove a ready label. A genuinely safe limited draft may be delivered with its limits visible. Continue unrelated authorised work and independent monitoring.
5. **Check the final delivered content.** Repair the generating source, rebuild/reassemble and rerun affected checks. A style pass can change facts or qualifications: revalidate those changes before appending the final record. Freeze the checked bytes; compare the installed/package identity where relevant. Test concurrent-data preservation and inspect the package and staged source index separately.
6. **Report observed evidence honestly.** Quote actual tool output, never reconstructed output called verbatim. Record check scope, failures and unavailable paths. Falsify important guards with a known-bad case while a legitimate control stays green. Never label a deliverable ready while a relied-upon requirement is unresolved.

## Verification record and placement

For Tier 3, and Tier 2 with remaining uncertainty, use three terminal, consecutive, unadorned lines in the accompanying operator response (or an appropriate internal technical document):

```text
Verified: actions actually taken and their observed results
Unverified: specific unexecuted paths or none
Assumptions: assumptions relied upon or none
```

Fill every field; placeholders and empty values are not records. Keep shared qualification labels when warranted. The footer is a self-report, **not proof** that checks happened. Refer to actual command results and exact artefacts where available.

Do not put internal records/labels in a client-facing artefact. Substantive limitations the recipient needs must still be visible in suitable language; clean presentation is not concealment. Do not withhold useful progress or blocker information merely because a footer exists.

## Optional helper — bounded mechanical checks

Invoke through `terminal` from this installed skill directory; replace `python` with the working target interpreter:

```text
python scripts/quality_gate.py lint --response response.md --artefact client.html
python scripts/quality_gate.py run --receipt check.json --artefact app.py -- python -m unittest
python scripts/quality_gate.py verify --receipt check.json --artefact app.py
python scripts/test_quality_gate.py
```

- `lint` checks the terminal record and obvious record leakage into explicitly supplied **client** artefacts, not arbitrary readiness prose. Plain text/Markdown responses and text/Markdown/simple HTML artefacts only; UTF-8 and BOM-marked UTF-16, up to 4 MiB per text input. Unsupported formats fail explicitly. No language blacklist. Tier 1/2 may omit the record; the operator still decides whether Tier 2 uncertainty requires one.
- `run` executes only the explicit approved argv after `--`, without a shell or stdin. Completion/accounting is **direct-child-only**, explicitly recorded as `completion_scope: direct_child` and `descendant_completion: not_assessed`. Commands must wait for their own checks before exiting; any surviving descendant, even an ordinary non-detached one, can outlive accounting. It records the direct child's actual exit status, observed output hashes/counts and before/after SHA-256/size manifests for every explicit final artefact. Raw output and argv are not saved. Build first: checks must not rewrite the frozen artefacts. The receipt destination must be new and writable before execution starts.
- `verify` checks all explicitly supplied required receipts against the explicitly supplied current artefacts. It never executes receipt content or follows additional receipt paths. Changed bytes, failed or incomplete checks cannot pass. Receipt provenance is local and forgeable, not authenticated proof.
- Exit **0** means the stated bounded check passed; **1** means findings or a completed failing check; **2** means invalid input, infrastructure failure, timeout/output limit or a required receipt-write failure. JSON is ASCII-safe for Windows pipelines. Every result says `readiness: not_assessed`; **no exit code authorises delivery**.

Read the human [README](README.md), [extended actions](references/verification-actions.md), [helper implementation](scripts/quality_gate.py), [offline tests](scripts/test_quality_gate.py) and [qualification boundaries](VERIFICATION.md). These support files must travel with the skill; a bare SKILL.md is not a complete helper install.

## Pitfalls

- A filled record can be false; a successful format scan does not qualify production behaviour.
- Do not demand every assumption be literally none. Required checks and load-bearing uncertainty govern the readiness decision.
- Text extraction is not browser, Office, PDF or live-service acceptance. Quote examples are not delivery claims.
- Receipts contain local paths and potentially identifying hashes. Keep them private; do not commit them or use this runner for secret-bearing probes. Existing permissions and destructive-action approvals remain binding.
- There is no sandbox, execution attestation, arbitrary-process containment or automatic runtime hook. While the direct child is alive, timeout termination attempts its owned group/tree; once it exits, ordinary as well as detached surviving descendants are outside completion/output accounting. Output limits are monitored, not a hard disk quota. Only regular text/receipt files are accepted, with capped reads; this is not protection against a hostile concurrent filesystem writer.

## Verification

Run the shipped offline suite, compare test names/counts across supported targets and require zero skipped tests. Exercise the actual installed helper, not only imports. Test bad records, legitimate qualifications, failed commands, changed artefacts and broken receipt paths. A mutation must fail its targeted assertion, not merely crash an import. Record procedural scenario outcomes separately; passing helper tests does not establish model compliance or fewer hallucinations.
