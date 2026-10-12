# Pack: script or command-line tool

For requests to build a script, command-line tool or file-processing utility.

## Typical gaps
- Exact inputs (folders, file types, flags) and outputs (changed files, reports).
- What happens on name collisions, missing metadata and partial failures.
- Which operating systems, and how it is started (terminal, double-click, schedule).
- Whether a run can be undone.
- Packaging: a single file, an installable package or an executable.

## NFR candidates
- Preview first: dry-run by default, or a `--dry-run` flag that changes nothing.
- Idempotent: a second run changes nothing more.
- Exit codes 0 success, 1 partial failure, 2 usage error, plus a one-line summary.
- Cross-platform paths, non-ASCII file names and long Windows paths handled.
- Standard library only unless a dependency earns its place.

## Safeguards
- Preview before any change; changes limited to the folder the user named.
- Never overwrite: add a suffix or skip, and report it.
- An undo log (old name, new name) written before changes, and an undo command that replays it.
- Destructive operations copy first or keep a backup.

## Acceptance-criteria patterns
- Fixture folder: dry-run lists the changes and leaves checksums unchanged.
- Apply, then undo: names and contents match the originals (checksums).
- Collision fixture: both files survive.
- Odd inputs (no metadata, non-ASCII name, read-only file) are reported, not fatal.
- Runs on each declared operating system (test matrix or transcripts).

## Common pitfalls
- Using file modification time when the user meant capture or creation time.
- Time stamps without a time zone.
- Recursing into folders the user did not name.
- Stopping at the first bad file instead of reporting and continuing.

## Tool search terms
- python cli
- file automation
- shell scripting
