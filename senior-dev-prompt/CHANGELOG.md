# Changelog

All notable changes to senior-dev-prompt. Semver; every published change bumps the patch number.

## 0.0.6
- H2: a clarify form that times out or is cancelled, then answered by the user's next
  message, counts as answered; proceed on it and never re-ask.
- Pitfall: when over the word budget, cut a few large phrases in one editing pass;
  deleting blank lines saves nothing and gluing lines together breaks section structure.
- Landed from the live authoring copy, where it had been honed but never published.

## 0.0.5
- skill.json now declares scripts/review_gate.py and scripts/test_review_gate.py —
  0.0.4 shipped the 191-check test_scripts.py without the files it exercises, so
  every Windows verify failed with FileNotFoundError (install.py ships declared
  files only). Manifest-complete is part of the release, not an afterthought.

## 0.0.4
- Landed from the live authoring copy (was never committed): H5 consent wording reworked -
  naming a reviewer authorizes its initial call; explicit "iterate until agreement" also
  authorizes necessary follow-ups and only named fallbacks; verify reported routes separately
  from model-family attribution; reference to references/codev-review.md
- 0.0.3's intro wording tightened; machine-question target stays TO CONFIRM until the user picks

## 0.0.3 — 2026-10-12

- A machine or place named by nickname ("the X box") gets the first question, in fixed words:
  "Which machine do you mean by 'the X box'?", with this machine and each machine the agent's
  memory names as choices. Until the user picks, the target stays TO CONFIRM, even when memory and
  the nickname agree.
- Measured on this release's exact text, with the field request and a memory note naming another
  machine (four runs): all four asked that question first, with this machine among the choices;
  none connected anywhere; none of the three briefs written marked the machine CONFIRMED. One run
  stopped after printing its questions, because the request asked "what do you need to ask?". Two
  earlier wordings fell short. Without fixed words, one run of three asked only how much it could
  read on the remembered machine. With fixed words but without "even when they agree", one brief
  of four marked the remembered machine CONFIRMED, citing "your words + profile memory".
- Correction to the 0.0.2 entry, whose measurement note said every 0.0.2 run asked which machine
  was meant. Four of five did. The five runs used three successive drafts of 0.0.2 (one ran the
  published text), and both 0.0.1 runs had also asked first where the skill should run, so asking
  was not new in 0.0.2. The measured difference was the CONFIRMED label: one brief of two on 0.0.1,
  none of five on the 0.0.2 drafts. The note had been scored by matching patterns in the questions
  instead of reading them.
- A few sentences shortened to stay inside the skill's 12,000-character limit.

## 0.0.2 — 2026-10-12

Fixes from the first field use, on a home network where several machines run Hermes.

- Reads stay on the machine the session runs on: the skill never connects to another machine while
  briefing. (Seen in the field: asked about "the X box", an agent matched the nickname to a
  different machine named in its memory, inspected that machine over SSH before asking anything,
  and wrote its first brief against the wrong machine.)
- A machine or place named by nickname ("the server", "the X box") is asked about in the question
  round. Unconfirmed, the target is this machine unless reading it shows otherwise; either way it
  stays TO CONFIRM (memory alone never makes it CONFIRMED), and any work on another machine becomes
  the plan's first task. The brief's Context names the target machine.
- A question round the user missed can be asked again, unchanged, when they ask for it (the
  one-round rule did not allow that before); an unanswered round still uses the labelled defaults.
- Word budgets: draft to about 90% of the budget; when a cut is needed, make a few large edits,
  starting with sections that repeat a table. (Seen in the field: one-word trims used up the
  session's tool-call limit before the brief passed its self-check.)
- Numbers in a brief carry their source: measured (with the artefact) or projected (with the
  basis); a projection stays ASSUMED until it is measured.
- Two pitfalls that repeated the procedure were removed and one was shortened, to stay inside the
  skill's 12,000-character limit.
- Measured before release, with the field request and a memory note naming another machine: no run
  on either version connected anywhere in this setup (the field connection did not reproduce), but
  on 0.0.1 one brief of two labelled the machine from memory CONFIRMED; on 0.0.2 none of five did,
  and every run asked which machine it was. A plain build request with no answers still produced a
  brief that passes the self-check. When the request itself asks "what do you need to ask?", some
  runs answer with the questions and stop instead of writing a brief on defaults.
  (Corrected in 0.0.3: four of the five asked which machine was meant, not every run, and the five
  runs used three successive drafts of this release.)

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
