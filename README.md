# hermes_skills

Public skills for [Hermes Agent](https://hermes-agent.nousresearch.com/docs) — the personal AI agent framework by Nous Research.

Each folder is one installable skill: a `SKILL.md` (frontmatter + instructions the agent loads), a `CHANGELOG.md` (semver, newest-first), and any supporting scripts the skill drives.

## Skills

| Skill | Version | What it does |
|---|---|---|
| [dev-pair](dev-pair/) | 1.1.20 | Second-opinion code review / critique from a *different* LLM than the one doing the work — supervisory pair-programming across model families. **User-invoked only** (ledger + daily cap enforce it); you choose the reviewing model |
| [verify-results](verify-results/) | 0.0.7 | Structured post-hoc critique of finished work — six passes producing labelled findings and an APPROVE / REVISE / DO NOT USE verdict. Runs inline, or routes to a different model via dev-pair |

## Contributing / releasing

Every published version string, test-count claim, and `platforms:` list has to
agree with the code. That is checked mechanically, not by memory:

```bash
sh scripts/install-hooks.sh          # once per clone — installs a pre-push gate
python3 check_consistency.py         # check
python3 check_consistency.py --fix   # repair the mechanical drift
```

The gate blocks a push when a README lags a version bump, when a doc claims a
test count the suite does not report, when `platforms:` omits a platform the
code actually supports, when `skills.json` is stale, or when the copy installed
under your Hermes home has drifted from the repo. It also refuses to let you
reason about the remote from a stale ref — it fetches first.

## Delivering to a fleet

`agents.json` lists the Hermes agents that receive skills; `deploy.py` installs to
every enabled one in parallel.

```bash
python3 deploy.py --list                    # who receives, and what is blocking the rest
python3 deploy.py dev-pair verify-results   # deliver named skills
python3 deploy.py --all                     # everything in skills.json
python3 deploy.py dev-pair --dry-run        # show the plan, change nothing
```

Adding a machine is a **data edit** — append an entry to `agents.json`, no code
change:

```json
{ "name": "box", "host": "user@100.x.y.z", "platform": "windows",
  "hermes_home": "%LOCALAPPDATA%\\hermes", "enabled": true, "role": "worker" }
```

Set `enabled: false` with a `blocked_reason` for a machine that is known but not
yet reachable; `--list` prints the reason so it stays visible instead of being
quietly forgotten. Two boxes sit in that state today — `jj-hp-prodesk` and
`jack-laptop` — both waiting on the mac's public key being authorised.

### Before you publish a code change: run it on another platform

Three releases in a row shipped a test that passed on macOS and failed on every
Windows agent. `deploy.py`'s check-count guard caught each one *after* the push.
Staging to one non-origin box first turns that into a pre-publish check:

```bash
# copy the working tree to an agent and run its suite there, before committing
python3 contribute.py --scan            # confirm you know what differs first
ssh <agent> "python %LOCALAPPDATA%\\hermes\\devpair\\test_devpair.py"
```

A **lower check count** on the remote is the signal, not the "0 failed" line —
it means assertions are being skipped, and a skipped assertion is silent. Three
real bugs hid behind that: a stub written in the locale encoding, an env-var
parsed with the wrong shlex mode, and a console encoding that killed the process
*after* the paid API call had been made.

### Editing a skill on another machine

Deploys are one-way: `deploy.py` overwrites each agent's copy, so an edit made on
a worker is destroyed by the next delivery. `contribute.py` is the way back.

```bash
python3 contribute.py --scan                     # what differs, on every agent
python3 contribute.py --from hermes-windows      # show that box's changes
python3 contribute.py --from hermes-windows --apply   # write them into the repo
```

`--apply` stages the files and stops — it never commits, never pushes, and never
bumps a version. You review the diff, bump the version, run the tests, then
commit and `deploy.py` it back out.

`agents.json` carries an `authoring` flag. Only the origin box has it set, and
`--scan` warns when an install-only agent has local edits that a deploy is about
to overwrite. **The Windows agents deliberately hold no git credentials** —
wincredman is broken there and non-interactive HTTPS has no tty to read a
username from, so pulling over the existing SSH channel beats giving five
machines push rights to a public repo.

Four behaviours worth knowing, each of which exists because of a real failure:

- **It waits for the CDN.** `raw.githubusercontent.com` serves a cached copy for
  minutes after a push, so a deploy that races it installs the *previous*
  release. `deploy.py` polls until the CDN serves the version this repo has.
- **Payloads go via a temp file.** Long inline `python -c` commands are truncated
  by `cmd.exe`; the payload is base64'd to `%TEMP%` and executed there.
- **It removes stale copies.** Per-profile skill directories
  (`<home>/profiles/*/skills/`) accumulate their own outdated copies of a skill,
  and an agent may load one of those instead of the canonical one.
- **It compares check counts, not just pass/fail.** An agent reporting fewer
  checks than its peers is *skipping* them — a green "0 failed" hides it. A lower
  count is reported as a failure, because that is exactly how a drift guard was
  found to be inert on every Windows install.

## Installing a skill

**One line, no clone:**

```bash
curl -fsSL https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/install.py | python3 - dev-pair
```

Or from a clone:

```bash
python3 install.py --list              # what's available
python3 install.py dev-pair --dry-run  # show every action, change nothing
python3 install.py dev-pair            # install
```

The installer finds this machine's Hermes home (`HERMES_HOME`,
`%LOCALAPPDATA%\hermes`, `~/.hermes`, or a dotted dir that looks like one),
installs `SKILL.md` into the right category, and — for skills that ship code —
installs the code, writes a platform-correct CLI shim, seeds any config from
this machine's own providers, and runs the skill's test suite as an install
gate. Re-running upgrades in place.

> Piping a remote script into an interpreter means trusting the source.
> `install.py` is short and stdlib-only on purpose — read it first if that matters.

**Manual install** works too: copy the skill folder into
`<hermes-home>/skills/<category>/<skill-name>/`.

### Skill anatomy

| File | Required | Purpose |
|---|---|---|
| `SKILL.md` | yes | The skill itself — what the agent loads |
| `CHANGELOG.md` | yes | Semver history, newest first |
| `README.md` | for non-trivial skills | Human-facing docs |
| `skill.json` | only if the skill ships code | Install manifest: files, entrypoint, CLI name, verify command |

Markdown-only skills need no `skill.json` — the installer just places
`SKILL.md` and stops.

## Versioning

Skills follow semver from their initial release. This repo increments patch (+0.0.1) per published change; each skill's CHANGELOG.md is the source of truth, newest entry first.

## License

MIT — see [LICENSE](LICENSE).
