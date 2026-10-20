# dev-pair field notes

Lessons from running dev-pair across many machines, kept out of SKILL.md so the
main file stays short. Each note was hit in real use. Re-check version-specific
details after an upgrade: a later release may fix what a note works around.

## Routes, probes and receipts

- **Hermes can fall back to another model and still return text.** A rejected
  model name (HTTP 400) or another provider error can trigger the configured
  fallback, and the run still answers. A `PROBE_OK` therefore proves nothing
  about the route, and the stream-json `init` event only echoes the model you
  asked for. After a direct `hermes chat` run, check the profile's
  `logs/agent.log` for the session: require an API call naming the requested
  model and provider and no `Fallback activated` line. Version labels in model
  names are not always API names; confirm the exact name the provider accepts.
- **Probe a route in isolation before trusting it.** Check that `auth.json`
  holds a credential for the provider (key presence only, never print values),
  then probe with no fallback chain:
  `hermes chat --query-file Q --oneshot --provider P --model M --toolsets context_engine --ignore-user-config --ignore-rules --max-turns 1`.
  It fails fast on a dead route (and writes no session row, so do not look for
  one), or call the provider's endpoint directly and read the response's own
  `model` field. Never report a reviewer as reachable from a non-isolated probe.
- **An exhausted credential pool looks like a silent hang.** A direct call can
  print nothing until the timeout while `hermes auth status <provider>` still
  says logged in. Look in the profile's `logs/agent.log` for
  `credential pool: no available entries`. A profile session's inherited
  `HERMES_HOME` can pin the exhausted pool: running the nested call from the
  root home (`HERMES_HOME=` cleared, no `--profile`) answered in seconds where a
  fresh login inside the profile did not. Probe that way before blaming usage
  limits, and never substitute another model.
- **Large-reasoning cloud reviewers can exceed 900 s on a ~40k-char packet.**
  Probe first: an instant answer means slowness, not an outage. Retry once with
  a longer `--timeout`/`--budget` and a word limit in `--ask`.
- **Custom OpenAI-compatible providers may report provider `custom`.** The
  receipt then shows ROUTE MISMATCH on the provider label while the model name
  matches. Record it as such; do not hide it or call it a match.
- **The reviewer CLI can fall back even when devpair has one named backend.**
  Inspect the effective cloud and local fallback chain before a bounded
  named-model run. To forbid fallback for one run, a task-local launcher can
  validate the explicit provider/model, `context_engine` and `--ignore-rules`,
  then supply an empty `hermes_cli.fallback_config.get_fallback_chain` before
  the CLI imports. Verify the installed call sites first, never edit shared
  source, config or credentials, prove offline that a configured fallback is
  rejected, and still read the route receipt afterwards. On launcher-managed
  installs, get the real interpreter command from the native launcher's
  `--print-runtime-command`; a guessed venv or bare system Python can lack
  Hermes' dependencies.
- **Take duration and token counts from the receipt, not the human footer.**
  A far smaller input token count than the packet size means the reviewer's
  own context was compacted (see *Effective context window* below).
- **A profile in `DEVPAIR_HERMES_CMD` can hide the route receipt.** With
  `-p <profile>` only in the command prefix, a file-transport run's session lands
  in that profile's `state.db` while devpair reads the default home's, so the
  receipt says `identity: unknown`. Also set `HERMES_PROFILE=<profile>` for the
  devpair call (devpair then reads `profiles/<profile>/state.db`), or read that
  store read-only for the run's time window (`sessions.model`,
  `billing_provider`, no `role='tool'` messages) and cite the session id.

## Evidence packets

- **Budget the packet arithmetically, not by eye.** Caps are per section: a
  `--plan` 30,000 chars (raw), each `--files` entry 24,000 including the
  line-number prefix devpair adds (`{i:>5}| `, 7 chars per line plus the
  newline, so a 3,000-line file overflows long before 24,000 raw chars), and
  90,000 in total including headers and joins. Replicate the prefix in a
  script, add ~1k for headers, target 87,000 or less, and confirm with
  `--dry-run` (free), which prints the exact context figure.
- **Several coupled documents over the total cap: split by coupling.**
  Documents a reviewer must cross-check belong in one packet. Carry each
  document IN FULL in exactly one packet and give every packet a verbatim
  digest of the others (frontmatter and objective, quoted, not summarised) so
  the interfaces between them stay checkable. If a packet still overflows,
  shrink a digest, never a full document. Check that `coverage` is `complete`
  for every packet before the first paid call. Near the 90k cap pass
  `--timeout 1800`.
- **A complete packet is not dependency-complete source.** A complete diff can
  omit the unchanged lock construction, worker shutdown, defaults and caller
  contracts the reviewer needs. Include that closure and real test output, or
  the reviewer may rightly cap its verdict on missing context while inventing
  plausible defects in code it never saw. Prove or refute each such finding
  against the source instead of buying an unchanged rerun.
- **Redaction can rewrite ordinary code (dev-pair 1.2.x).** Assigned-secret
  redaction also replaces non-credential lines such as `secret=lambda key: None,`,
  `run(secret=secret)` and `token = (time.monotonic() + timeout, proc)`, so the
  reviewer sees broken code and can report a defect that does not exist. Watch
  the redaction count devpair prints, and if code like this is in scope, anchor
  every finding against the real source. A task-local adapter may mask only
  individually verified, exact non-credential expressions around the unchanged
  redactor; prove it still redacts synthetic credentials and arbitrary
  non-whitelisted assignments.
- **Your own scrubbing can rewrite evidence too.** If you scrub names or paths
  from a packet by substring replacement, a short term that also occurs inside
  code identifiers rewrites the code itself; one such scrub produced a confident
  phantom BLOCKER and cost a paid round. Before launch, grep the built packet for
  sentinel strings known to be in the source (option values, keywords). On a
  collision, fix the scrub, rebuild and re-check.
- **A packet builder that pins evidence from git objects cannot carry
  untracked files.** Sourcing files via `git show <sha>:<path>` fails on
  anything not committed (exit 128, nothing sent). Commit what you want
  reviewed first, or route drafts through the builder's scratch-file input.
- **Keep archived diff packets byte-exact without weakening whitespace
  checks.** Space-only diff context lines trip `git diff --check` when archived
  as text files. Put byte-exact packet parts in a ZIP, verify each hash after
  reading the ZIP back, and record the archive's SHA-256. Never strip hashed
  content or disable a repository's whitespace gate to archive evidence.
- **A source-hash mismatch may be line endings, not tampering.** A builder
  that pins git blobs hashes LF bytes; a verifier reading a Windows workspace
  under autocrlf hashes CRLF. Hash both forms (convert the sealed bytes LF to
  CRLF explicitly and re-hash) before treating a difference as a changed
  candidate, and record both hashes.
- **Start a packet-reading interpreter in UTF-8 mode on Windows**
  (`python -X utf8`). Setting `PYTHONUTF8` inside an already-running process is
  too late for `Path.read_text()`, and matching file hashes alone do not detect
  decoding corruption in the text you built from them.
- **Effective context window.** For a near-cap one-shot run, the model
  catalog's context length is advisory: the profile's `model.context_length`
  and the provider entry's `context_length` override it. With `compression`
  enabled, an oversized packet can be summarised inside the reviewer's own
  context, invisible to devpair's manifest, so coverage reads complete while the
  reviewer critiques a digest. Read the chain with a key-allowlisted config read
  (never print auth blocks). After the run, compare the receipt's input tokens
  with the packet size.

## Windows

- **Require output, even in machine mode.** Some launchers complete a turn and
  relay nothing by design, so a silent exit 0 is ambiguous. A candidate command
  must print `OK` for `<cmd> -z "Reply OK"`, and a stream-json probe must print
  JSON events; empty stdout is a failure whatever the exit code.
- **Recovering a lost review by hand.** Since 1.2.6 devpair recovers a completed
  silent turn itself. For an older run, the session store still holds the reply:
  read it read-only by session id (never resume or write through the store).
  Some stripped Windows venvs lack the sqlite3 DLL, so probe `import sqlite3`
  and switch interpreter rather than debugging the import. Trust a recovery only
  against an independently obtained copy; a single read proves only that the
  store holds text.

## Multi-round reviews and spend

- **Show before/after evidence, not counts.** Reproduce every counterexample
  before fixing it, and prove the "before" from an isolated checkout of the
  reviewed commit (a separate worktree with the new tests copied in) so the run
  cannot see the fixes. Separate regression guards (tests that already passed)
  from defect tests (red before, green after), and capture raw artifacts
  (verbatim stderr lines, query results) rather than describing them. A packet
  that only says "N red, M green" invites another paid round to re-check it.
- **Pre-empt the recurring finding classes before a paid round.** A
  `$`-anchored `re.match` still accepts a trailing newline (use `fullmatch` for
  grammar tokens). Sanitising a warning's message leaves
  `warnings.formatwarning` prefixing the source path, so a privacy test must read
  the subprocess's full stderr. Second-resolution timestamps tie when two events
  share a second, so order on numeric epochs and make the test prove the tie. An
  hour of local red tests is cheaper than a follow-up paid round.
- **A rerun after a wedged attempt.** A first attempt that burns its whole
  timeout with zero output, on a packet the manifest proves complete and with a
  probe that answers, is a wedged generation: keep its files under a failed name
  and rerun the identical packet once. Two consecutive full-timeout stalls mean
  the task is too big; split it into smaller reviews.
- **Match late notices to their run before acting on them.** A background
  process's exit notice can arrive long after the run was handled, and a replayed
  tool result can describe an earlier packet. Compare its run id and the packet
  hash with the archived review before treating it as a new failure or a new
  answer.
