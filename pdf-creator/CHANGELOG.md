# Changelog

## 0.1.2
- Windows: find Chrome and Edge where Windows installs them. md_to_pdf.py's _find_chrome() knew only the macOS app paths and PATH names, but Windows puts Chrome and Edge under Program Files (registered in App Paths, not on PATH), so every Windows host stopped at "No PDF backend found" even with pandoc present. Edge ships with Windows and takes the same headless flags. Local change to the vendored script; see UPSTREAM.md.
- The typography lint ran pdfinfo after checking only for pdftotext. Git for Windows ships pdftotext without pdfinfo, so under Hermes' Git Bash the run crashed with FileNotFoundError after the PDF was already written; it now skips the lint unless both tools exist.
- Both changes offered upstream as daymade/claude-code-skills#1158 (issue #1157), same code.

## 0.1.1
- Ship the five themes/*.css from upstream 6b2096236262 (daymade-docs/pdf-creator/themes). 0.1.0 declared only the scripts in skill.json, so no node received a theme and md_to_pdf.py exited with "Theme 'default' not found".
- skill.json records upstream_path and excludes upstream's scripts/tests/ with a reason; check_consistency.py now fails when an upstream file at the pin neither ships nor is excluded.
- Still needs pandoc on the host: md_to_pdf.py converts Markdown with it.

## 0.1.0
- Initial vendored import from daymade/claude-code-skills @ 6b2096236262
