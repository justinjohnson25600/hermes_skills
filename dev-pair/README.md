# dev-pair — a second pair of eyes, on a different brain

**dev-pair** is a supervisory code-review tool for [Hermes Agent](https://hermes-agent.nousresearch.com/docs) that reviews your AI agent's work using a **different LLM** than the one doing the work.

## The problem it solves

When an AI agent writes code and then reviews its own code, it approves its own blind spots. The same reasoning that produced the bug produces the review that misses it. Self-review in a single model is close to worthless for exactly the bugs you most need caught.

dev-pair fixes this by construction: the agent doing the work (the **driver**) shells out to a review partner running on a **different model family** (the **reviewer**). A Kimi-driven session gets reviewed by Claude; a Claude-driven session gets reviewed by Kimi or GLM. The reviewer never saw the driver's reasoning, doesn't share its training biases, and is explicitly instructed to be disagreeable when the evidence warrants it.

It is **supervision, not duplication**: the reviewer never writes code, never edits files, and physically cannot — it runs with an empty toolset, so all it can do is read the evidence you hand it and respond.

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
3. **Session memory.** Reviews happen in persistent sessions (`~/.hermes/devpair/sessions/*.json`). When you act on a review and call `followup`, the reviewer sees what it said before — it notices concerns you silently dropped, escalates ones you ignored, and concedes when your reasoning beat its. That's what makes it a *pair* instead of a linter.

## Installation

### Prerequisites

- [Hermes Agent](https://hermes-agent.nousresearch.com/docs) installed, with its `hermes` CLI on your PATH
- python3.11+ with PyYAML
- git (for the diff-based modes)
- At least **two** configured model providers of different families (e.g. an Anthropic key and a Kimi key) — one to drive, one to review

### Steps

```bash
# 1. Install the tool
mkdir -p ~/.hermes/devpair
cp devpair.py ~/.hermes/devpair/

# 2. Install the wrapper onto your PATH
cp devpair ~/.local/bin/devpair
chmod +x ~/.local/bin/devpair

# 3. Point the wrapper at your install (if you used a different path)
#    export DEVPAIR_PY=/path/to/devpair.py   — or edit the variable at the top

# 4. Edit the REVIEWERS dict near the top of devpair.py to match the
#    provider IDs and model names in YOUR ~/.hermes/config.yaml

# 5. Verify every backend answers
devpair doctor
```

The wrapper smoke-tests a chain of python interpreters (`import encodings` must succeed) so a half-broken venv can't kill the tool with cryptic getpath errors.

Optional: install the skill folder itself (`SKILL.md`) into `~/.hermes/skills/software-development/dev-pair/` so your Hermes agent loads it automatically and knows when/how to call the tool proactively.

### Configuration

- **`~/.hermes/devpair/config.json`** (optional): `{"order": ["claude", "kimi", "local"]}` reorders reviewer preference. Reviewers not listed are still used as fallback candidates.
- **Driver identity** is resolved from `--driver` flag → `DEVPAIR_DRIVER_MODEL`/`DEVPAIR_DRIVER_PROVIDER` env vars → `config.yaml` `model.default`, in that order.

## Usage

### The one rule

**Always tell it what model is actually doing the work:**

```bash
devpair review --diff --driver kimi-coding/kimi-k3
```

The config-file default is a guess; if your session runs a different model than the config default, the same-family guard will protect the wrong model unless you pass `--driver`. Any Hermes agent calling this tool knows its own model and must pass it.

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
| `--reviewer NAME` | Force a specific reviewer (deliberate same-family override, warned) |
| `--session NAME` | Named session for parallel workstreams |
| `--timeout N` | Per-backend timeout, default 420s (use 900 for small local models) |
| `--json` | Machine-readable output |
| `--dry-run` | Show who would review and why; no call, no state written |

## Safety model

- The **reviewer** is read-only by construction (empty toolset). It cannot touch your machine.
- The **harness** gathers context locally, and **`--cmd` runs whatever shell command you give it with your own privileges** — that flag is for you, and it is not sandboxed. Never pass a command you wouldn't run yourself.
- A bad `--diff-ref` is reported as a failure, never disguised as "no diff".
- Session files are written atomically; `--dry-run` and `log` create no state.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `no independent reviewer available` | Every configured reviewer shares the driver's family | Configure a second model family, pass correct `--driver`, or force `--reviewer` accepting the weaker review |
| doctor FAILs on a backend | Auth or provider config | `hermes -z "hi" -m MODEL --provider P -t ""` directly to see the real error |
| Local model times out | Small reasoning models think for ~2 min before answering | `--timeout 900`; doctor already allows 300s for local backends |
| Review reads like generic advice | No evidence was attached | Always pass `--diff`, `--files`, `--plan`, or `--error` |
| `followup` warns about no earlier turns | Wrong session, or `reset` too recently | `devpair log` to find the right session; `--session NAME` to select it |

**Verify its findings before acting.** During this tool's own construction, the reviewer raised a confident BLOCKER that was provably impossible — and conceded immediately when shown the test. It reasons from pasted evidence, not from your runtime. Its `file:line` references are claims, not facts.

## Development

```bash
python3.11 test_devpair.py     # 18 regression tests, no network required
```

The suite pins every defect found during the tool's own development: self-review refusal, driver-identity precedence, session side-effects and atomicity, merge-base diff semantics, error propagation, and truncation maths. Run it after any change.

## Version & history

Current: **1.1.2**. See [CHANGELOG.md](CHANGELOG.md) — semver, patch (+0.0.1) per published change.

## License

MIT — see [../LICENSE](../LICENSE).
