# Verification actions — extended mapping and edge cases

Read this when the SKILL.md table doesn't cleanly cover the situation.

## Mixed-tier documents

A document can contain tiers side by side — e.g. a blog post (Tier 2) embedding a dosage claim (Tier 3). The strictest tier present governs the claims it applies to, not the whole document: verify the dosage via medical-research-engine; the surrounding prose only needs the Tier 2 claims check. The footer covers the whole deliverable.

## Code that cannot fully run in the sandbox

Common in Justin's stack: Laravel code needing his Plesk-hosted DBs, mail through his SMTP config, Alpine.js behaviour needing a browser.

- Run everything that *can* run: syntax (`php -l`), static analysis, unit-testable logic extracted and executed, `composer.json`/`package.json` dependency sanity.
- For the remainder, state precisely what was and wasn't executed in the footer: "syntax-checked and logic unit-tested locally; SMTP path untested — requires live Plesk mail config."
- Never present partial checks as end-to-end verification. Name the executed layer and the remaining gate separately; Justin may deploy what the response appears to approve.

## Cross-process helper programs

Use this recipe when a tested controller launches embedded source or a helper script:

1. Load the exact shipped helper bytes or source constant, not a rewritten test equivalent. Restore temporary changes to argv, stdout, import paths and module bindings after the test.
2. Intercept only the native exchange or other external effect. Capture the request and return explicitly labelled unit-test input; do not mock the whole subprocess and then claim the helper ran.
3. Execute the helper with representative positional data and capture its actual stdout. For a newline-framed JSON protocol, check both the request bytes and the output terminator; an extra source-string escaping layer can turn a newline into two literal characters.

```python
import json

assert request.endswith(bytes([10]))
assert not request.endswith(bytes([92, 110]))
payload, end = json.JSONDecoder().raw_decode(stdout)
assert stdout[end:] == chr(10)
```

4. Add malformed/refused replies and precision-boundary inputs. Exercise the helper's own identity comparison rather than assuming it shares the controller's implementation; duplicated code can introduce a wider tolerance.
5. Mutate framing or identity evidence and confirm the test rejects it. A source-text search for an API name, or an assertion containing an unconditional true branch, proves no behaviour.
6. Run the actual adapter in an authorised disposable native fixture. Keep this verdict separate from the intercepted-helper test; the latter establishes executable protocol behaviour, not real peer control or successful recovery.

## Shared settings and token persistence

1. Load two independent snapshots, change the newer snapshot, then attempt a save through the older one; assert preservation of additions, deletions, selections and rotated credentials, not just successful decryption.
2. Protect the complete read–modify–write transaction with a lock or revision compare-and-swap; a lock around individual Load and Save calls does not prevent a stale snapshot overwriting current data.
3. Persist asynchronous refresh results by merging token fields into the latest unchanged account identity/configuration and unchanged token baseline; never save an entire stale review-window settings object after a request finishes.
4. Advance the caller's revision only when its configuration snapshot remains current; adopting a newer revision without adopting its configuration defeats stale-write protection.

## Installation and publication failure paths

1. Snapshot the dedicated registration and verify its disabled state **before** changing its target; an enabled previous registration can otherwise load an unverified replacement after an intermediate failure.
2. Verify the isolated loader/ABI gate before enabling, and inject failures after each registration stage. Restore prior values on failure, read them back, and keep startup disabled until a known-good activation is verified.
3. Create registry keys only when absent; recreating a PowerShell registry key with `New-Item -Force` can erase previously written values. For native `RegistryKey.SetValue` rollback, open an explicitly writable key and dispose it; a provider `Get-Item` handle is not evidence of write access.
4. Stage an exact file allow-list in a fresh directory, create an archive at a unique temporary name on the destination volume, read back exact membership and reject missing, duplicate or unlisted entries, then publish atomically. Remove failed temporary archives/stages without deleting a prior valid publication.
5. Exercise dirty-stage markers, actual corrupted archives and a locked publication destination; assert both rejection and absence of a newly published bad archive. Check archive payload hashes against the live-tested binaries.
6. Inspect the Git index independently with `git diff --cached --name-only -z` and `git diff --cached --check`; positive-list packaging does not stop a broad `git add` from staging retained test data. Add ignore-rule regressions for retained build directories and encrypted stores, including a negative assertion that intended source assets remain trackable.

## Frozen binaries and rebuilding verification

1. Record the tested release hashes and relevant source/build inputs before deployment; a non-deterministic compiler can produce different bytes from unchanged source.
2. Keep verification outputs separate from the frozen candidate where the build supports it. When an existing verification command overwrites the candidate, snapshot its bytes and inputs first, run the checks, prove the inputs stayed unchanged, restore the frozen bytes, then hash-verify equality with the installation and archive.
3. Refuse restoration of an earlier binary after relevant source/build inputs change; rebuild and verify a new candidate instead. Report source-level test results separately from exact installed-binary acceptance.

## Stack-specific verification shortcuts

- **Laravel / Filament / Pest / Tailwind / Alpine.js** — versions move quickly; use an enabled documentation MCP when available, otherwise retrieve current official docs with `web_extract`. Confirm the returned content actually contains the contract being cited; a page title or navigation-only extraction is not API evidence. Never use memory alone for config keys, method signatures or breaking changes.
- **Plesk behaviour** — documentation is thin and version-dependent. If a claim rests on Plesk-specific behaviour that can't be verified, flag it and recommend an empirical test on the server rather than asserting.
- **PostgreSQL vs MySQL differences** — Figurs is PostgreSQL by deliberate choice. Verify dialect-specific SQL against the right engine; don't assume MySQL semantics carry over.

## Claims sourced from Justin's own prior work

A figure from an earlier Theorem report, a config from a past conversation, a decision recorded in memory: these count as user-supplied material (top of the evidence order) **only if actually re-read in this session**. A remembered version of Justin's own data is still a memory, and memories drift. If it can't be retrieved, mark it `[ASSUMPTION]`.

## When search results conflict

Two sources disagreeing is information, not noise. Prefer primary over secondary, newer over older for anything versioned, and say the disagreement exists rather than silently picking a side. A one-line "sources conflict on X; going with Y because Z" in the deliverable outranks fake certainty.

## What does NOT need verification

Don't burn tool calls on: stable fundamentals (how HTTP works, SQL join semantics), arithmetic the sandbox can confirm in one line, matters of judgement or style, or claims Justin supplied this session and that were read directly. Over-verification is its own failure mode — it adds latency and noise without adding truth.
