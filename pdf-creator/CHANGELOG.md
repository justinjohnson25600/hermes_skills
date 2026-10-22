# Changelog

## 0.1.1
- Ship the five themes/*.css from upstream 6b2096236262 (daymade-docs/pdf-creator/themes). 0.1.0 declared only the scripts in skill.json, so no node received a theme and md_to_pdf.py exited with "Theme 'default' not found".
- skill.json records upstream_path and excludes upstream's scripts/tests/ with a reason; check_consistency.py now fails when an upstream file at the pin neither ships nor is excluded.
- Still needs pandoc on the host: md_to_pdf.py converts Markdown with it.

## 0.1.0
- Initial vendored import from daymade/claude-code-skills @ 6b2096236262
