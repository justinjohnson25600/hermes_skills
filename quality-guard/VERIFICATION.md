# Quality-guard 0.1.1 — qualification scope

This records candidate qualification, not publication, automatic runtime enforcement or a production-readiness certificate.

## Executed checks

- Offline shipped suite: **54 passed, 0 failed, zero skipped tests** on macOS Python **3.9.6** and **3.11.15**, and native Windows Python **3.12.12**. Test-name sets match across the isolated Mac/Windows installs.
- The repository installer installed the complete manifest into isolated homes and ran `verify_skill`. After correcting a Windows-only fixture cleanup race, **five consecutive native Windows installer runs passed 54/54**. No real profile was upgraded by these canaries.
- Source files staged to the two platforms were byte-identical. The existing repository installer converts LF to CRLF on Windows; installed raw hashes were retained separately, and decoded text content matches. Receipts bind actual final installed artefact bytes, not a substitute source hash.
- Native Hermes catalog discovery, skill loading and linked-file loading were exercised in isolated homes on macOS and Windows. New-authoring frontmatter validation passed; the indexed description remains short and meaningful.
- The native community security scan allowed the candidate (`safe`); informational findings include the explicit subprocess runner and synthetic test fixtures. This is not a claim that pattern scanning establishes correctness.
- **Eleven guard mutations** each turned one previously passing targeted test red on its own assertion. They cover blank records, legitimate qualifications, client placement, command failure, stale bytes, receipt overwrite, timeout, deep-JSON error handling, regular-file input, capped reads and explicit completion scope. Import failures were not counted.

## Independent-review corrections

An independent review found three gaps despite the original 49-test suite passing:

1. Excessively nested receipt JSON escaped structured error handling. It now returns an input error rather than an uncaught recursion traceback.
2. FIFO text/receipt inputs could hang; metadata size alone did not bound reads. Non-regular inputs are now refused, opened-file type is rechecked, and the actual read is capped. A common guard test runs on both platforms; POSIX additionally exercises actual FIFOs.
3. Ordinary grandchildren could outlive their parent and escape later output accounting. The contract is now explicitly **direct-child-only**, in both documentation and required receipt fields. This does not add process-tree containment: commands must wait for all checks they spawn, and asynchronous work requires separate verification.

Five simulated procedural scenarios covered unattended destructive-safety failure, an authorised limited SMTP draft, a dosage changed by a style pass, version-matched documentation through an alternate tool, and a format-only gate plus recipient caveats. These were instruction-application simulations, not real deliveries or evidence of improved model compliance.

## What these checks do not establish

- No Linux runtime or Python 3.8 runtime execution was performed. Python 3.8 syntax compatibility was checked, not substituted for a minimum-runtime test.
- A successful record scan, forged/local receipt, unit suite, catalog load or security scan does not establish factual truth, production readiness or adequacy of the operator's required-check list.
- No hostile concurrent filesystem containment, arbitrary-process sandboxing, descendant completion guarantee, live third-party integration or automatic send blocker is provided.
- Publication, Hub fetched-version readback and rollout are separate release steps. A qualified local candidate is not proof that those steps happened.
