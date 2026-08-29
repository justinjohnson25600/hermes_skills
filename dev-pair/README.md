# dev-pair — a second pair of eyes, on a different brain

**dev-pair** is a supervisory code-review tool for [Hermes Agent](https://hermes-agent.nousresearch.com/docs) that reviews your AI agent's work using a **different LLM** than the one doing the work.

## The problem it solves

When an AI agent writes code and then reviews its own code, it approves its own blind spots. The same reasoning that produced the bug produces the review that misses it. Self-review in a single model is close to worthless for exactly the bugs you most need caught.

dev-pair fixes this by construction: the agent doing the work (the **driver**) shells out to a review partner running on a **different model family** (the **reviewer**). A Kimi-driven session gets reviewed by Claude; a Claude-driven session gets reviewed by Kimi or GLM. The reviewer never saw the driver's reasoning, doesn't share its training biases, and is explicitly instructed to be disagreeable when the evidence warrants it.

It is **supervision, not duplication**: the reviewer never writes code, never edits files, and physically cannot — it runs with an empty toolset, so all it can do is read the evidence you hand it and respond.

**It only runs when you ask.** Every review spends a second model's tokens on top of your agent's, so the skill instructs agents never to invoke it on their own initiative — at most they may *offer*. You decide when a second opinion is worth paying for, and with `--with` you decide which model gives it.

## How it works

```
┌──────────────┐   diff / files / plan / error log   ┌──────────────────────┐
│  DRIVER agent│ ───────────────────────────────────▶│  devpair harness      │
│  (e.g. Kimi) │                                     │  (local python3.11)   │
└──────────────┘                                     │                       │
       ▲                                             │  gathers context,     │
       │                                             │  picks a DIFFERENT-   │
       │  structured verdict                         │  family reviewer,     │
       │  (SHIP / BLOCKERs /                        │  builds the prompt    │
       │   questions / alternatives)                 └─────────┬────────────┘
       │                                                       │
       │                                             hermes -z PROMPT -m MODEL
       │                                             --provider P  -t ""   ← no tools
       │                                                       ▼
       │                                             ┌──────────────────────┐
       └─────────────────────────────────────────────│  REVIEWER model       │
                                                     │  (e.g. Claude)        │
                                                     │  read-only by design  │
                                                     └──────────────────────┘
```

Three design decisions do the heavy lifting:

1. **Read-only reviewer.** The reviewer is invoked as `hermes -z "<prompt>" -m <model> --provider <provider> -t ""`. The `-t ""` strips all tools, so the reviewer cannot read your disk, run commands, or edit anything. It only sees the text the harness puts in the prompt.
2. **Same-family refusal.** The tool identifies the driver model, and refuses to pick a reviewer from the same model family — it would rather exit with an error naming why each candidate was skipped than silently let a model grade its own homework. (`--reviewer` exists as a deliberate override with a loud warning.)
3. **Session memory.** Reviews happen in persistent sessions (`<hermes-home>/devpair/sessions/*.json`). When you act on a review and call `followup`, the reviewer sees what it said before — it notices concerns you silently dropped, escalates ones you ignored, and concedes when your reasoning beat its. That's what makes it a *pair* instead of a linter.

## Installation

### Quickest — one line

```bash
curl -fsSL https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/install.py | python3 - dev-pair
```

That detects your Hermes home, installs the skill and its code, writes the
`devpair` CLI, generates a reviewer roster from **your** configured providers,
and runs the 35-test suite as an install gate. Then:

```bash
devpair doctor          # confirm your backends answer
```

> Piping a remote script into an interpreter means trusting the source.
> `install.py` is short and stdlib-only on purpose — read it first if that matters.

### Prerequisites

- [Hermes Agent](https://hermes-agent.nousresearch.com/docs) with `hermes` on PATH
- Python 3.8+ with PyYAML
- git (for the diff-based modes)
- At least **two** configured providers of different model families — one to drive, one to review. With fewer, devpair refuses rather than fake independence.

### Manual install

```bash
mkdir -p <hermes-home>/devpair
cp devpair.py test_devpair.py <hermes-home>/devpair/
# put a `devpair` shim on PATH that runs:  python3 <hermes-home>/devpair/devpair.py "$@"
python3 <hermes-home>/devpair/test_devpair.py    # 211 checks, no network
```

### Configuration

`<hermes-home>/devpair/config.json` — written for you by the installer:

```json
{
  "reviewers": {
    "claude": {"model": "claude-sonnet-4.6", "provider": "anthropic", "family": "claude"},
    "kimi":   {"model": "kimi-k3", "provider": "kimi-coding", "family": "kimi"}
  },
  "order": ["kimi", "claude"]
}
```

`reviewers` **replaces** the built-in roster, so every machine names its own providers — the IDs must match your `config.yaml`. `order` sets preference; reviewers not listed are still used as fallbacks. `family` is inferred from the model or provider when omitted.

**Driver identity** resolves from `--driver` → `DEVPAIR_DRIVER_MODEL`/`DEVPAIR_DRIVER_PROVIDER` → `config.yaml` `model.default`.

### Where state lives

devpair finds your Hermes home in this order: `HERMES_HOME` → `%LOCALAPPDATA%\hermes` (Windows) → `~/.hermes` → any dotted directory that looks like a Hermes home. Sessions live at `<hermes-home>/devpair/sessions/`, and the invocation ledger at `<hermes-home>/devpair/invocations.jsonl`.

## Using it

dev-pair is both a **skill** (your Hermes agent reads it and runs the CLI for
you) and a **plain CLI** (you run it yourself). Same tool, two front doors —
plus the policy and accountability that govern when it is allowed to run.

### 1. From a Hermes conversation — just ask

There is no slash command and no `hermes devpair` subcommand. Skills are
instructions the agent loads, not commands you type. So you speak normally:

```
review that with dev-pair
get a second opinion on this before I commit
dev-pair this bug, I'm stuck
```

The agent works out the mode, fills in the live driver model, and runs the CLI.
You never pass `--driver` yourself — the agent knows which model it is running
on, and that flag exists so it cannot get that wrong.

**Naming the reviewer in chat.** Say which model you want and the agent passes
it through:

```
review that with dev-pair using opus
have kimi look at this
get glm to critique the plan
```

| You say | The agent runs |
|---|---|
| "second opinion on this" | `devpair review --diff --driver <live>` |
| "review with opus" | `devpair review --diff --driver <live> --with anthropic/claude-opus-5` |
| "have kimi review it" | `devpair review --diff --driver <live> --with kimi-coding/kimi-k3` |
| "check this plan first" | `devpair critique --plan ... --driver <live>` |
| "dev-pair this bug" | `devpair debug --error ... --files ... --driver <live>` |
| "tell the pair I fixed 1 and 3" | `devpair followup --ask "..." --driver <live>` |
| "which reviewers work?" | `devpair doctor --driver <live>` |

If you don't name a model, the tool picks the first reviewer that is a
different family from the driver and **tells you which one answered**, so you
can redirect on the next turn.

### 2. Manual invocation only — it never fires by itself

**The agent will not run dev-pair unless you ask.** Every review spends a second
model's tokens on top of the agent's own, so the skill forbids self-initiated
runs: at most the agent may *offer* once ("want me to run this past the dev
pair?") and then wait. Nothing happens until you say yes.

This is deliberate. An always-on reviewer doubles the bill on renames and typo
fixes, and a review nobody asked for is a review nobody reads.

**Caveat, stated plainly:** the instruction is behavioural, but it is not the
only thing standing there. Every paid run is written to an append-only ledger
*before* the call, so `devpair audit` shows you exactly what ran and whether
anyone claimed you asked; and `daily_cap` in `config.json` is a hard refusal —
the process will not call a reviewer past it, whatever an agent believes it was
told. A lying caller can still fill in `--requested-by`, so treat that field as
a record rather than a lock. See [Accountability](#accountability) below.

### 3. Accountability

Three mechanisms back the manual-invocation policy, in descending order of how
much you can trust them:

| Mechanism | What it does | Evadable by an agent? |
|---|---|---|
| `daily_cap` | Hard ceiling on paid runs per day — the process refuses, no backend is called | **No** |
| Invocation ledger | Every paid run appended before the call: when, mode, reviewer, who asked | No (records only) |
| `--requested-by WHO` | Names who asked for this run | Yes — it is an attestation |

```bash
devpair audit              # last 7 days: when, mode, who asked, reviewer, context size
devpair audit --days 1     # just today
devpair audit --json       # machine-readable, includes runs_today and daily_cap
```

`audit` explicitly flags runs that named nobody as the requester — that is where
an agent running the pair unasked would show up. It costs nothing to run.

Set a ceiling in `<hermes-home>/devpair/config.json`:

```json
{ "daily_cap": 10, "require_attestation": true }
```

`daily_cap: 0` (the default) means unlimited. `require_attestation` makes
`--requested-by` mandatory, so a run with no named requester fails instead of
proceeding anonymously. `--dry-run` stays free under both — it never touches the
ledger or the cap, and it now shows how much of your cap is left.

### 4. From your own terminal

```bash
devpair review --diff --with anthropic/claude-opus-5
```

Useful when you are not in a Hermes conversation at all, or in CI with
`--gate`. Here you *should* pass `--driver` if the code was written by a model,
so the same-family guard has something true to work with.

## Selecting the reviewer model

Three levels, most specific first:

| How | Where | Effect |
|---|---|---|
| `--with PROVIDER/MODEL` | CLI, or "use opus" in chat | Uses exactly that model, roster or not. Overrides everything below |
| `--reviewer NAME` | CLI, or "use kimi" in chat | Picks that entry from your roster |
| roster `order` | `config.json` | Default preference when you say nothing |

```bash
devpair review --diff --with anthropic/claude-opus-5   # any reachable model
devpair review --diff --reviewer kimi                  # a roster entry
devpair review --diff                                  # first independent one
```

`--with` accepts any `PROVIDER/MODEL` your Hermes install can reach. If the
model you name shares the driver's family (Claude reviewing Claude) it prints a
warning and **proceeds anyway** — your explicit instruction outranks the guard.
A bare model name resolves its provider from the roster when it can, and tells
you the right form when it cannot.

To change the *default* order instead of naming a model each time, edit
`order` in `<hermes-home>/devpair/config.json`.

## Usage

### The one rule (for agents, not for you)

**Whoever calls the CLI must declare the model doing the work:**

```bash
devpair review --diff --driver kimi-coding/kimi-k3
```

The config-file default is only a guess — if the session is running a model
override, the same-family guard protects the wrong model unless `--driver` is
passed. A Hermes agent knows its own model and the skill requires it to pass
it, so **in chat you never type this**. It matters only when you drive the CLI
by hand.

### The five modes

**`critique`** — before building. Pressure-test the plan while changing it is still cheap:

```bash
devpair critique --plan PLAN.md --driver anthropic/claude-sonnet-4.6
```

**`review`** — after building. The workhorse:

```bash
devpair review --diff --driver kimi-coding/kimi-k3          # uncommitted work
devpair review --diff-ref main --driver kimi-coding/kimi-k3 # branch vs main (merge-base)
devpair review --files src/auth.py --driver kimi-coding/kimi-k3
```

**`debug`** — stuck on a bug for more than two attempts:

```bash
devpair debug --error /tmp/fail.log --files src/router.py --driver kimi-coding/kimi-k3
devpair debug --cmd "pytest -x tests/test_auth.py" --driver kimi-coding/kimi-k3
```

**`alt`** — genuinely torn between two designs:

```bash
devpair alt --ask "cron job or long-running daemon for this watcher?" --driver kimi-coding/kimi-k3
```

**`followup`** — after acting on a review. This is the loop that makes it a pair:

```bash
devpair followup --ask "Fixed 1 and 3 by X. Disagree with 2 because Y." --driver kimi-coding/kimi-k3
```

### What you get back

Every mode forces a structured shape. A `review` looks like:

```
## VERDICT
SHIP AFTER FIXES
The core design is sound but the fallback path has a correctness hole.

## DEFECTS
[BLOCKER] devpair.py:152 — fallback silently picks a same-family reviewer
When every reviewer in `order` is filtered out, line 152 falls back to
order[0] without checking family...

## WHAT THE TESTS DO NOT PROVE
...

## WHAT I'D TEST FIRST
...
```

Verdicts: `SHIP` / `SHIP AFTER FIXES` / `NEEDS WORK` / `DO NOT SHIP` for reviews; `PROCEED` / `PROCEED WITH CHANGES` / `RECONSIDER` / `STOP` for critique/alt/followup. Findings are ranked `[BLOCKER|MAJOR|MINOR]` with `file:line`. "None material" is a valid answer — the reviewer is instructed never to manufacture problems to look useful.

### Utility commands

```bash
devpair doctor    # live-probe every reviewer backend, flag same-family ones
devpair log       # replay what the pair has said this session
devpair reset     # fresh session (do this per feature — stale context pollutes)
```

### Useful flags

| Flag | Effect |
|---|---|
| `--driver PROVIDER/MODEL` | Declare the live session model (see the one rule) |
| `--focus "concurrency"` | Steer attention; critical off-focus findings still reported |
| `--with PROVIDER/MODEL` | Use **this** model as the pair — roster or not. Your explicit choice; same-family warns but proceeds |
| `--reviewer NAME` | Pick a reviewer from your roster |
| `--requested-by WHO` | Record who asked for this run (see Accountability). Env: `DEVPAIR_REQUESTED_BY` |
| `--session NAME` | Named session for parallel workstreams |
| `--timeout N` | Per-backend timeout, default 420s (use 900 for small local models) |
| `--budget N` | Total wall-clock across ALL backends; stops a dead chain burning `timeout × candidates` |
| `--gate` | Exit non-zero on a bad verdict — see below |
| `--json` | Machine-readable output (verdict, blockers, tokens, unverified claims) |
| `--dry-run` | Show who would review and why; no call, no state written |

### Gating (opt-in)

By default devpair is **advisory** — it always exits 0 and lets a human decide.
`--gate` makes the verdict machine-actionable:

```bash
devpair review --diff --driver anthropic/claude-sonnet-4.6 --gate --budget 300
echo $?     # 0 = pass, 2 = gate failed, 1 = no backend answered
```

| Exit | Meaning |
|---|---|
| `0` | Verdict was SHIP / SHIP AFTER FIXES / PROCEED / PROCEED WITH CHANGES, no blockers |
| `1` | No reviewer backend answered (infrastructure failure) |
| `2` | Gate failed: verdict was DO NOT SHIP / NEEDS WORK / STOP / RECONSIDER, **or** a `[BLOCKER]` was found under an otherwise-passing verdict, **or** the verdict could not be parsed |

That last case is deliberate: a gate that cannot read the answer must not report
success. Recommended shape for CI — gate on the mechanical tier (tests, lint,
"the reviewer ran at all"), keep the LLM's judgement advisory until you have
measured its precision on your own codebase.

### Verifying the reviewer's claims

The reviewer cites `file:line` from text it was handed — it cannot open your
files, so those anchors are claims. devpair checks every one against the real
tree and prints anything that doesn't hold up:

```
  UNVERIFIED CLAIMS — the reviewer cited anchors that do not check out:
    · router.py:412 — file has only 380 lines
    · imaginary.py:5 — no such file in this tree
  Treat those findings with extra scepticism.
```

### Housekeeping

```bash
devpair prune --days 30 --dry-run    # see what would go
devpair prune --days 30              # delete sessions older than 30 days
```

The active session is never pruned, regardless of age.

## Safety model

- The **reviewer** is read-only by construction (empty toolset). It cannot touch your machine.
- **Secrets are redacted before they leave your machine.** Everything the harness gathers passes through `redact_secrets()` at a single chokepoint: vendor token shapes (`sk-`, `ghp_`, `AKIA`, `xox`, `AIza`, `ya29`, JWTs), private-key blocks, passwords embedded in URLs, secret-looking `KEY=value` assignments, and bearer tokens in `Authorization` headers are replaced with `[REDACTED:kind]`, and you're told how many were caught. Key *names* and URL hosts survive so the reviewer can still reason about the code. Obvious placeholders (`<your-key-here>`, `changeme`) are left alone.
  This is defence in depth, **not a guarantee** — a novel credential format can still slip through. If you work in a repo full of live secrets, look at what you're sending before you send it.
- **Independence fails closed.** If the driver's model family can't be identified (from the model name, then the provider), the tool refuses rather than offering an unprovable guarantee. Pass `--driver` to resolve it.
- **A reviewer whose independence can't be proven says so.** If neither a reviewer's model name nor its provider maps to a known family, it is labelled `INDEPENDENCE UNVERIFIED` — on automatic selection, `--reviewer`, and `--with` alike — and reviewers that *can* be proven independent are tried first. The unprovable one stays available as a fallback; it simply never claims a guarantee it can't back. Scripts can read this as `independence` (`verified` / `unverified` / `same-family`) in `--json`, and it always describes the model that actually answered, not the first one tried.
- The **harness** gathers context locally, and **`--cmd` runs whatever shell command you give it with your own privileges** — that flag is for you, and it is not sandboxed. Never pass a command you wouldn't run yourself.
- A bad `--diff-ref` is reported as a failure, never disguised as "no diff".
- Session files are written atomically; `--dry-run` and `log` create no state.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `no independent reviewer available` | Every configured reviewer shares the driver's family | Configure a second model family, pass correct `--driver`, or force `--reviewer` accepting the weaker review |
| `cannot identify the driver's model family` | Model name is an alias and the provider is unrecognised | Pass `--driver PROVIDER/MODEL` with the real model; this refusal is deliberate (fail-closed) |
| doctor FAILs on a backend | Auth or provider config | `hermes -z "hi" -m MODEL --provider P -t ""` directly to see the real error |
| Local model times out | Small reasoning models think for ~2 min before answering | `--timeout 900`; doctor already allows 300s for local backends |
| Review reads like generic advice | No evidence was attached | Always pass `--diff`, `--files`, `--plan`, or `--error` |
| `followup` warns about no earlier turns | Wrong session, or `reset` too recently | `devpair log` to find the right session; `--session NAME` to select it |

**Verify its findings before acting.** During this tool's own construction, the reviewer raised a confident BLOCKER that was provably impossible — and conceded immediately when shown the test. It reasons from pasted evidence, not from your runtime. Its `file:line` references are claims, not facts.

## Development

```bash
python3.11 test_devpair.py     # 50 regression tests (211 checks), no network required
```

The suite pins every defect found during the tool's own development: self-review refusal, driver-identity precedence, session side-effects and atomicity, merge-base diff semantics, error propagation, and truncation maths. Run it after any change.

## Version & history

Current: **1.1.6**. See [CHANGELOG.md](CHANGELOG.md) — semver, patch (+0.0.1) per published change.

## License

MIT — see [../LICENSE](../LICENSE).
