# quality-guard

Verification discipline before relied-upon output, with a small optional evidence helper. Current: **0.1.1**.

It requires actual checks, explicit uncertainty and safe holds—not a self-written declaration that something is ready. A verification footer is a record, **not proof** of execution. The Python helper validates a finite structural/evidence contract; it is not a truth detector, sandbox or automatic send blocker.

## What changed

- Safe unattended handling: hold unsafe outward actions when a required check is unavailable; escalate while unrelated authorised work continues.
- Execute the actual delivered CLI/artefact; independently check destructive-action ownership and blast radius.
- Recheck final bytes and facts after assembly/style edits; distinguish source, installed, host and live integration evidence.
- Use available tools and authoritative docs for the pinned version; supplied material is not automatically external factual truth.
- Delegate only covered checks to a domain gate. Preserve generic concurrency, package/index and exact-byte acceptance lessons without private integration policy.
- Add `lint`, explicit check execution/receipt recording, receipt verification and an offline regression suite. No mandatory language policy or fleet-parity helper.

## Installation

Use Hermes' scanned community Hub install:

```text
hermes skills install skills-sh/justinjohnson25600/hermes_skills/quality-guard
```

Or add the public repository as a tap and install its source-qualified skill, or use its installer:

```text
hermes skills tap add justinjohnson25600/hermes_skills
hermes skills install justinjohnson25600/hermes_skills/quality-guard
python install.py quality-guard
```

The repo installer's `verify_skill` runs the shipped tests. The Hub/direct-source installation must include `references/verification-actions.md`, `scripts/quality_gate.py` and `scripts/test_quality_gate.py`; confirm their presence and run the suite after installing. The repository also carries this README, release history and manifest. A direct SKILL.md URL is supported only when its explicitly referenced helper files are fetched and scanned; do not hand-copy one file and claim a working helper.

No pip dependencies, API keys, extra model calls, services or global hooks. Python **3.8+**; choose a working interpreter (`python3` or a full path if `python` is absent/a store alias). In an agent session, execute the commands using `terminal`. Paths below are relative to the installed skill directory; input paths are your real delivery/check files, not these documentation examples.

The repository installer writes native text newlines (LF on POSIX, CRLF on Windows). Retain raw hashes and explicitly account for that conversion when comparing source with the installed helper; other content differences are not acceptable. Fingerprint the **actual installed final artefacts** for execution receipts, never substitute source hashes for them.

## Use the skill

Ask: “apply the quality guardrail to this”. Internal drafts do not require the full procedure; published low-stakes work needs a claims check; relied-upon work needs relevant verification and a record.

A real operator-facing record has meaningful values:

```text
Verified: local unit suite executed; installed CLI help exercised
Unverified: SMTP delivery requires the production account
Assumptions: test fixtures represent the supported input schema
```

This is a **limited result**, not an assertion that the SMTP integration is ready. Keep internal records out of a client-facing document while preserving any caveat the recipient needs.

## Helper commands

### 1. Validate a record and client placement

```text
python scripts/quality_gate.py lint --response response.md --artefact client.html
```

The final three lines must be consecutive, unadorned `Verified:`, `Unverified:`, `Assumptions:` fields with non-empty values. Known placeholders and bare qualification labels fail; a specific `[UNSUPPORTED CLAIM] SMTP path` is allowed. Fenced examples do not substitute for a record. `--tier 1` or `--tier 2` permits no record; decide separately whether Tier 2 uncertainty requires one. `--artefact` means a **client-facing** file, not an internal technical document intentionally containing its record.

Responses: `.txt`, `.md`, `.markdown`. Client artefacts additionally support `.html`/`.htm` through simple HTML text extraction. UTF-8 (optional BOM) and BOM-marked UTF-16 are supported; each text/receipt input is a **regular file** limited to **4 MiB**, with the read itself capped. Other formats, FIFOs/devices, malformed encodings and excessive JSON nesting fail explicitly. Export a PDF/Office document to inspect text, then separately verify its real rendering/native behaviour. No language restrictions; no heuristic production-ready detection.

### 2. Execute an explicitly approved check and record evidence

Build first and freeze the checked artefacts. Obtain normal permission for the command and use its intended sandbox. This runner does not make destructive or untrusted code safe.

```text
python scripts/quality_gate.py run --receipt check.json --artefact app.py -- python -m unittest
```

This runs the explicit argument vector, without a shell or interactive stdin. A new receipt records a run ID, the **direct child's** completion/return code, command/observed-output SHA-256 hashes and output byte counts, and before/after file hashes/sizes. It does **not** store raw argv or stdout/stderr. Existing receipt files are never overwritten, and invalid input/destination is refused before execution.

Default direct-child timeout: **60 seconds** (`--timeout`). Default combined output threshold: **1 MiB** (`--max-output-bytes`); monitoring can overshoot between polls and is not a disk quota. Temporary output handles are closed after accounting. Windows children use no console window; while the direct child remains alive, termination attempts only its owned tree/group.

**Direct-child-only contract:** receipts/results say `completion_scope: direct_child` and `descendant_completion: not_assessed`. Any descendant surviving its parent—ordinary or detached—can keep running/writing after the helper finalises its snapshot; later output/work is outside these limits and hashes. A zero direct-child exit is not process-tree completion. Use commands that wait for every check they spawn, and independently verify asynchronous work. This is not a sandbox or hostile-filesystem/process containment system. Use only approved bounded checks, never secret-bearing probes.

### 3. Check receipts against final files

```text
python scripts/quality_gate.py verify --receipt check.json --artefact app.py
```

Repeat `--receipt` for each required check and `--artefact` for each final file. Each receipt must cover the same explicit artefact set. Only those approved paths are read; commands and additional paths in a receipt are never followed. A failed/incomplete check, net changes during checking, or later file changes cannot pass.

**Boundary:** receipts are ordinary local JSON and can be forged or edited. Hashes bind snapshots, not the appropriateness of a test, uninterrupted file stability, authorisation, arbitrary factual truth or live-system readiness. The required-check list is supplied by the operator; omitted requirements are not discovered automatically. Preserve actual tool output elsewhere when needed, and verify its provenance before citing it.

## Results and exit codes

All normal command results are ASCII-safe JSON with `schema_version`, `tool_version`, `scope`, `status`, `findings`, `error` and **`readiness: not_assessed`**. Parser usage errors use argparse's normal stderr and exit 2.

| Exit | Meaning |
|---|---|
| 0 | The specific structural/evidence check passed; **not permission to deliver** |
| 1 | Policy/record findings, stale evidence, changed checked bytes, or a completed non-zero check |
| 2 | Invalid/unsupported/unreadable input, execution/receipt I/O failure, timeout or output limit |

A qualifying footer can therefore pass `lint` while a production check remains unavailable. The procedural policy must still hold that unsafe outward action. Do not collapse these independent decisions into one green label.

## Tests and acceptance

```text
python scripts/test_quality_gate.py
```

The suite uses local scratch fixtures and harmless Python child commands, no network/model calls. It covers records, legitimate labels, placement, Unicode pipelines, receipts, failures, timeout/output limits and stale/unapproved paths. Compare the complete test-name set and count across target platforms; zero failures with skipped tests is not full qualification. See the [qualification record and limits](VERIFICATION.md), [CHANGELOG.md](CHANGELOG.md) and [extended verification actions](references/verification-actions.md) for workflow acceptance.

## Troubleshooting

- **Record finding:** use the terminal three-line form with real details, not quoted examples, bold labels or placeholders.
- **Exit 2:** inspect `error` and inputs; do not relabel a broken check as a policy rejection.
- **Existing/unwritable receipt:** preserve it, choose a new private writable destination, then retry only if the command remains approved.
- **Stale artefact:** fix the generating source, rebuild, rerun relevant checks against final bytes and create new receipts.
- **Missing helper/reference:** reinstall the complete scanned package; verify actual files and run the installed suite.
- **Unverified load-bearing path:** hold unsafe delivery/activation and escalate. Do not “fix” the result by replacing the uncertainty with `none`.

Receipts include local paths and identifying hashes: keep them private, outside commits and public release archives. Honed local skill copies, opted-out profiles and domain-specific adapters need explicit preservation/merge decisions, never blind replacement.
