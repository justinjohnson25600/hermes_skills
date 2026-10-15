---
name: cybersecurity-skills-index
description: On-demand lookup over 818 security procedure skills; one prompt row.
version: 0.1.0
author: Justin Johnson (justinjohnson25600)
license: Apache-2.0
platforms: [macos, linux, windows]
upstream: mukul975/Anthropic-Cybersecurity-Skills
upstream_pin: see UPSTREAM.md
metadata:
  hermes:
    tags: [vendored-skill, security, index]
---

# Cybersecurity Skills Index (818 upstream skills)

The upstream library ships 818 separate SKILL.md files. Installing them all as
individual Hermes skills would add ~65KB of skill index to EVERY system prompt on
EVERY API call. This skill ships them instead as a lookup LIBRARY under
`references/library/` and turns the skill itself into a router:

1. Read `references/index.json` (name, one-line description, domain per skill).
2. Pick the 1-3 SKILL.md files that match the task; read them with `read_file`
   from this skill's own `references/library/<name>/SKILL.md`.
3. Follow the chosen upstream skill's procedure. Supporting files live beside it.

Do NOT load more than 3 skills at once; they are procedures, not context.

## Domains covered

cybersecurity (818) … (full counts in references/index.json)

## Finding skills

- By task: grep descriptions in references/index.json via `search_files`.
- By MITRE technique: `references/mappings/mitre-attack/`.
- By NIST CSF / OWASP: `references/mappings/nist-csf/`, `references/mappings/owasp/`.

## Prerequisites

Upstream skills reference standard security tooling (nmap, ldap3, impacket,
yara, volatility3, …). Most are NOT installed by this skill; check before use.

## Scope & authorization

These are DEFENSIVE/offensive-security PROCEDURES for authorized engagements,
CTF, and lab work. Confirm the engagement is authorized before executing any
offensive procedure. No tooling is bundled; nothing executes automatically.

## Updating the library

See UPSTREAM.md — refresh references/library + index.json together.
