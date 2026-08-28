# hermes_skills

Public skills for [Hermes Agent](https://hermes-agent.nousresearch.com/docs) — the personal AI agent framework by Nous Research.

Each folder is one installable skill: a `SKILL.md` (frontmatter + instructions the agent loads), a `CHANGELOG.md` (semver, newest-first), and any supporting scripts the skill drives.

## Skills

| Skill | Version | What it does |
|---|---|---|
| [dev-pair](dev-pair/) | 1.1.2 | Second-opinion code review / critique from a *different* LLM than the one doing the work — supervisory pair-programming across model families |

## Installing a skill

Copy the skill folder into `~/.hermes/skills/<category>/<skill-name>/` (or your profile's skills directory) and restart Hermes, or reference it from your own skills registry. Skills that drive a CLI (like dev-pair) document their setup in their own SKILL.md.

## Versioning

Skills follow semver from their initial release. This repo increments patch (+0.0.1) per published change; each skill's CHANGELOG.md is the source of truth, newest entry first.

## License

MIT — see [LICENSE](LICENSE).
