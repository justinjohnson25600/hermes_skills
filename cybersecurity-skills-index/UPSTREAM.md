# Upstream: mukul975/Anthropic-Cybersecurity-Skills

- Source: https://github.com/mukul975/Anthropic-Cybersecurity-Skills
- Imported upstream commit `54a798831d2266a3ca61ce68a7acb80b81160d57` (index 1.1.0)
- License: Apache-2.0 (LICENSE file carried at skill root)
- Contents: references/library/ = upstream skills/ verbatim; references/index.json =
  upstream index.json; references/mappings/ = upstream MITRE/NIST/OWASP mappings.

## Updating

1. Clone upstream, note the new commit SHA and regenerate/compare references/index.json.
2. Replace references/library/ and references/mappings/ wholesale.
3. Bump version +0.0.1 here; add a CHANGELOG entry noting the new upstream commit.
4. `python3 check_consistency.py`, then deploy.
