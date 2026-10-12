# Changelog

All notable changes to senior-dev-prompt. Semver; every published change bumps the patch number.

## 0.0.1 — 2026-10-12

First release.

- Turns a rough build request into a senior-developer brief: requirements, risk safeguards,
  acceptance criteria with checks and evidence, a decision register (CONFIRMED / ASSUMED /
  TO CONFIRM / BLOCKING), and a workflow mandate.
- Greenfield by default; reads a project read-only when the request names one, or when it asks to
  fix something and the session is already in a project folder.
- One question round of at most five plain-language questions, each with a "use your
  recommendation" choice; a second round only for a newly found material fork, one bundled
  clarification of a paid reviewer choice, or the user's choice to answer open blockers.
- Routing by tier (T0–T4) and installed tooling: superpowers, GSD (with or without a `.planning/`
  project) or inline phases; every named skill is checked individually and a missing step is
  replaced by its inline equivalent.
- The hand-off prompt names its stop point: routes that write an implementation plan stop and show
  it before implementing, and ordinary wording such as "build it now" does not waive that stop.
  (Measured before release: handed "please start", an agent planned and implemented without
  showing the plan.)
- A feasibility question ("find out whether X is possible before we build") becomes a brief whose
  first phase is a time-boxed spike; the investigation is not run while briefing. (Measured before
  release: without this rule the agent researched and answered the question and wrote no brief.)
- Optional co-developer review through dev-pair: asks how many other model families should review
  the brief; the number is the total of paid calls; one attempt each, separate sessions, receipts
  (`run_id`, route identity, coverage) and triage of every finding. An unanswered reviewer
  clarification leaves that review pending: no guess, no substitute, and the brief is not blocked.
- Domain packs for agent skills and plugins, web apps, scripts and command-line tools, and bots and
  integrations.
- Risk safeguards for user-data mutation, secrets, money, personal data, destructive operations,
  publishing, production systems, and legal or licensing questions.
- Tool suggestions: a read-only search of installed skills, the skills hub and the plugin catalog;
  at most three install offers at hand-off, each inspected and security-scanned by the host before
  install; never forced, never in unattended runs.
- Reopening a saved brief revalidates it before offering anything; an earlier approval is history,
  not consent.
- `scripts/lint_brief.py` (the brief self-check) and `scripts/scout.py` (the tool search), standard
  library only, with `scripts/test_scripts.py` run by the installer after every install.
- Tested on macOS and Windows: scenario runs with and without the skill, and the script suite
  (186 checks) on both. Linux not verified.
