# Upstream: daymade/claude-code-skills

- Source: https://github.com/daymade/claude-code-skills
- Pinned commit: `6b2096236262bc5b43ba5c0b9ec25084addef0fd`
- License: MIT

## Updating

1. Fetch upstream and check out the new commit.
2. Replace SKILL.md (and support files) with the upstream copies.
3. Bump `version` +0.0.1 in skill.json and SKILL.md; add a CHANGELOG entry.
4. Run `python3 check_consistency.py`, then deploy (`fleet pdf-creator`).
