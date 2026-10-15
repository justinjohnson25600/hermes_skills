---
name: anthropic-skills-index
description: Run 15 open-license Anthropic skills on demand; pointers to the proprietary doc suite.
version: 0.1.0
author: Justin Johnson (justinjohnson25600)
license: Apache-2.0
platforms: [macos, linux, windows]
upstream: anthropics/skills
metadata:
  hermes:
    tags: [vendored-skill, index]
---

# Anthropic Skills — vendored open library + doc-suite pointers

Open-license (Apache-2.0) skills from anthropics/skills live under
`references/library/<name>/SKILL.md` — read one with `read_file` when its task
matches. The proprietary document suite (docx, pdf, pptx, xlsx) is NOT
redistributed: follow `references/library/<name>/README.md` and install from
upstream with npx when needed.

## Included (Apache-2.0, full copies)

- academy-guide
- algorithmic-art
- brand-guidelines
- canvas-design
- claude-api
- discernment-nudge
- doc-coauthoring
- frontend-design
- internal-comms
- mcp-builder
- skill-creator
- slack-gif-creator
- theme-factory
- web-artifacts-builder
- webapp-testing

## Pointers only (© Anthropic, source-available)

- docx
- pdf
- pptx
- xlsx

## Updating

See UPSTREAM.md.
