# hermes_skills

Public skills for [Hermes Agent](https://hermes-agent.nousresearch.com/docs) — the personal AI agent framework by Nous Research.

Each folder is one installable skill: a `SKILL.md` (frontmatter + instructions the agent loads), a `CHANGELOG.md` (semver, newest-first), and any supporting scripts the skill drives.

## Skills

| Skill | Version | What it does |
|---|---|---|
| [dev-pair](dev-pair/) | 1.1.14 | Second-opinion code review / critique from a *different* LLM than the one doing the work — supervisory pair-programming across model families. **User-invoked only** (ledger + daily cap enforce it); you choose the reviewing model |

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
| [verify-results](verify-results/) | 0.0.4 | Structured post-hoc critique of finished work — six passes producing labelled findings and an APPROVE / REVISE / DO NOT USE verdict. Runs inline, or routes to a different model via dev-pair |

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
