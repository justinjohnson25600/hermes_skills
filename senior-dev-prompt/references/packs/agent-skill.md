# Pack: agent skill or plugin

For requests to build a skill, agent instructions, a prompt pack or a plugin for an AI agent host.

## Typical gaps
- The exact phrases that should trigger it, and near-misses that must not.
- Which hosts and versions it targets, and which operating systems.
- What it reads and writes (files, paths, state) and where state lives between runs.
- Paid, networked or third-party calls, and who consents to them.
- How success is observed: a baseline scenario without the skill versus with it.
- Distribution: personal only, or published (repository, registry) with an update path.

## NFR candidates
- Trigger description of at most 60 characters, phrased "Use when ...", self-contained before the host's index cut-off.
- Declared platforms are true: no POSIX-only shell where Windows is declared.
- Main instruction file within about 200 lines; detail in references loaded on demand.
- No machine-local paths, usernames, hostnames or private identifiers in published files.
- Deterministic or heavy logic lives in tested scripts, not prose the model re-derives.

## Safeguards
- Paid calls, network calls and installs happen only after explicit consent in the same run.
- Secrets come from environment variables or the host's secret store, never from the skill text.
- Writes are limited to named paths; configuration changes need approval.
- Publishing: sanitisation sweep, licence, version and changelog, and a review gate before release.

## Acceptance-criteria patterns
- Baseline scenario without the skill shows the gap; the same scenario with it shows the fix (two transcripts).
- Trigger check: loads for several real phrasings and stays quiet for named near-misses.
- Frontmatter check: description length, platforms and version agree with the files.
- Script tests pass on every declared operating system.
- A leak sweep over the published files finds no machine paths or private identifiers.

## Common pitfalls
- Writing rules before observing the baseline failure, so nothing proves they are needed.
- A description that is too long, or a trigger buried past the index cut-off.
- Duplicating an existing skill instead of extending it; run the reuse check first.
- Rules phrased only as prohibitions; state the positive target the agent should hit.
- Expecting the current session to see a newly installed skill; skills load at session start.

## Tool search terms
- skill authoring
- prompt engineering
- agent workflow
