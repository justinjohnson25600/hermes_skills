# Upstream: anthropics/skills

- Source: https://github.com/anthropics/skills
- Imported: 2026-10-15 (main)
- License: mixed — skills under references/library/ are Apache-2.0 (each carries
  its own LICENSE.txt); the document suite (docx, pdf, pptx, xlsx) is
  © Anthropic, PBC, not redistributed — pointers only.

## Updating

1. Fetch upstream, note the commit SHA.
2. Refresh references/library/<open skill> dirs; leave proprietary pointers as-is.
3. Bump version +0.0.1; CHANGELOG entry; `python3 check_consistency.py`; deploy.
