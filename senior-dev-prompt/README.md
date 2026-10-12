# senior-dev-prompt

Turn a rough build idea ("make me an app that reminds my clients about their workouts") into the
brief a senior developer would write before anyone touches code: requirements, safeguards,
acceptance criteria you can check, the decisions only you can make, and a workflow sized to the job.
Optionally, other AI model families review the brief before it is handed off.

It is for people who describe what they want rather than how to build it. The brief is what a
coding agent then executes; where the route includes an implementation plan, the agent stops and
shows you the plan before building.

## What it does, and what it never does

- **Asks only what changes the build:** one round of at most five plain-language questions, each
  with "Not sure — use your recommendation" (a second round only for a newly found material fork,
  one bundled clarification of a paid reviewer choice, or your choice to answer open blockers).
  Safe defaults are labelled so you can change them;
  a decision with no safe default stays open as a blocker.
- **Writes the brief and nothing else in your project:** one file under `.hermes/plans/` in your
  workspace (review evidence, if any, goes to a temporary folder). No code, no configuration
  changes and no installs while briefing; a paid review happens only if you ask for one.
- **Stays on the machine you are talking to:** it reads only this machine and never connects to
  another one while briefing. If your request names a machine or place by nickname ("the server",
  "the office box"), it asks which one you mean; work on another machine becomes the plan's first
  task.
- **Brings specialist checklists** for four kinds of build (agent skills and plugins, web apps,
  scripts and command-line tools, bots and integrations), so the brief covers what a requester rarely
  mentions: dry-runs and undo for scripts, rate limits and kill switches for bots, accessibility and
  backups for web apps.
- **Turns every risk into a safeguard with a check:** touching your files, secrets, money, personal
  data, production systems, publishing, and legal or licensing questions.
- **Routes the work** to the workflow skills you have installed (superpowers or GSD), sized to the
  job, and substitutes an inline step for anything missing.
- **Checks itself** with a script before handing over: every requirement and scenario mapped to an
  acceptance criterion with a stated check and evidence, no placeholders left in commands, within
  its word budget. (This checks the brief, not the software built from it.)
- **Optional co-developer review:** it asks how many other model families should review the brief.
  Each review is one paid model call, made only with your answer.
- **Suggests tools:** it searches installed skills, the skills hub and the plugin catalog, and at
  hand-off offers up to three installs. Nothing is installed unless you pick it, after the host's
  inspection and security scan.

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/install.py | python3 - senior-dev-prompt
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/install.py | python - senior-dev-prompt
```

Manual: copy this folder into your Hermes skills directory as
`skills/software-development/senior-dev-prompt/`. The installer runs the skill's own tests after
installing (`scripts/test_scripts.py`) and reports `verify passed.`. Start a new session afterwards:
skills load at session start.

## Prerequisites

None are required. Each optional piece improves the result, and the skill says what it substituted
when one is missing:

| Optional | What it adds | Without it |
|---|---|---|
| superpowers skills (writing-plans, test-driven-development, and so on) | The workflow the brief routes to | The brief names inline steps: plan, test first, verify |
| GSD skills | Phase-tracked projects for larger work | Same inline steps, plus a phase list |
| dev-pair (this repository) | Co-developer review by other model families | The count question is skipped and the brief says why |
| Python 3.8+ (Hermes' own interpreter is enough) | The self-check and the tool search scripts | The agent applies the same rules by hand |

## Usage

Ask in plain words:

```
you:   turn this into a proper brief: a script that renames my photos by the date they were taken
agent: (asks up to five questions, for example: which folder; what to do with photos that have no date;
        "How many co-developers should review this brief?")
agent: Brief saved: .hermes/plans/2026-10-12_101500-photo-renamer-brief.md
       For you: a script that previews every rename first, never overwrites, and can undo a run...
       Run now / Save only / Edit first / Install these to improve the result?
```

"Run now" starts the routed workflow. Where the route writes an implementation plan, the agent stops
after writing it and shows you the plan before building anything: approving the brief approves the
design, not a plan you have not seen.

### Reopening a brief

"Reopen my photo renamer brief" (or `/senior-dev-prompt reopen photo renamer`). The skill finds the
brief, re-checks it against what is installed now, and offers the same choices. An earlier approval
is history, not consent: anything that costs money or installs software asks again.

## Co-developers: cost and privacy

The question is: "How many co-developers should review this brief? Each is a different AI model
family. Only the brief is sent to that model's provider (not your files or memory), and each review is
one extra paid model call." Answer with a number (`2`), model names (`2: model-a, model-b`), or `0`.
The number you give is the total number of paid calls. Reviews run through dev-pair, so its ledger,
daily cap and secret redaction apply, and each result carries a `run_id` you can check with
`devpair audit`. No answer means no review.

## Tool suggestions

During briefing the skill searches (read-only) for skills and plugins that would improve the result.
The brief lists up to five with their source and trust tier; the hand-off offers at most three, with
missing workflow skills first. For each one you pick, it runs `hermes skills inspect` (or
`hermes plugins show`), then installs through the host's security scan. A blocked or incomplete scan
is reported and skipped, never forced. Plugins are labelled as code that may install Python packages
and needs a restart. Nothing is offered or installed in unattended runs. Say "no tool suggestions" to
turn the search off.

## Domain packs

`references/packs/` holds one checklist per kind of build, each under six headings: typical gaps,
NFR candidates, safeguards, acceptance-criteria patterns, common pitfalls, tool search terms. To add
one, copy an existing pack, keep the six headings and at most 60 lines, list two to five search terms,
and run the tests.

## The scripts by hand

```bash
python3 scripts/lint_brief.py .hermes/plans/2026-10-12_101500-photo-renamer-brief.md   # exit 0 pass, 1 findings, 2 usage
python3 scripts/scout.py --pack script-cli --want writing-plans --max 5                   # read-only; never installs
python3 scripts/test_scripts.py                                                           # 7 regression tests (186 checks)
```

On Windows use `py` or Hermes' own interpreter. `--json` gives machine-readable output.

## Troubleshooting

- **The skill does not trigger:** start a new session after installing; ask "turn this into a proper
  brief".
- **"Co-developer review unavailable":** dev-pair is not installed, or every configured reviewer is
  in the same model family as the model you are using. `devpair doctor` shows the roster.
- **Tool search is slow:** a hub search can take up to about 20 seconds. The scout runs at most
  three searches at a time and fetches the plugin catalog once, so a full search usually takes under
  a minute; a search that times out is reported as one ERROR line and the rest still report.
- **The self-check fails on a brief you edited:** run `lint_brief.py` on it; each finding names the
  fix (the codes are explained in `references/brief-template.md`).
- **Where is my brief?** In `.hermes/plans/` inside the folder the session started in. A session
  started at the top of the disk or in Hermes' own folder saves under your home folder instead. The
  hand-off always shows the full path.
- **It asked which machine I meant:** your request named a machine or place by nickname, and the
  agent's memory could point at more than one. Answer once; left unanswered, the brief targets the
  machine you are talking to (unless what it can read there shows you meant another) and marks that
  TO CONFIRM.

## Honest limits

- The brief is only as good as the answers: defaults are labelled, but they are still guesses.
- Tool ranking is by keyword fit, trust tier and install counts; the agent judges real fit.
- Reviews by other models catch different mistakes, not all mistakes.
- Built and tested on Hermes; other agent hosts are not supported yet.
- Tested on macOS and Windows. Linux, and delivery on messaging platforms (the brief attached as a
  document), have not been tested yet.

## Version

0.0.2 — see [CHANGELOG.md](CHANGELOG.md). Semver; +0.0.1 per published change.
