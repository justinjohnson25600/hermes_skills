# Upstream: daymade/claude-code-skills

- Source: https://github.com/daymade/claude-code-skills
- Pinned commit: `6b2096236262bc5b43ba5c0b9ec25084addef0fd`
- License: MIT

## Updating

1. Fetch upstream and check out the new commit.
2. Replace SKILL.md (and support files) with the upstream copies, then re-apply every entry
   under "Local changes" below that upstream does not yet carry.
3. Bump `version` +0.0.1 in skill.json and SKILL.md; add a CHANGELOG entry.
4. Run `python3 check_consistency.py`, then deploy (`fleet pdf-creator`).

## Local changes

Both entries below are offered upstream as daymade/claude-code-skills#1158 (issue #1157), with
the same code: `_find_chrome()` plus its new helper `_windows_browser_candidates()`, and the lint
guard. Once a re-vendored upstream carries that PR, drop these entries instead of re-applying them.

- `scripts/md_to_pdf.py` `_find_chrome()` / `_windows_browser_candidates()`: also looks for
  Chrome and Edge in Windows' install locations (Program Files, Program Files (x86), per-user
  LocalAppData) and `msedge` on PATH. Upstream at the pin, and at its main as of 2026-10-22,
  knows only the macOS app paths and PATH names, so on Windows it finds no PDF backend (0.1.2).
- `scripts/md_to_pdf.py` `_lint_pdf_typography()`: skips unless both `pdftotext` and
  `pdfinfo` exist. Upstream checks only `pdftotext`, then runs `pdfinfo` (0.1.2).
