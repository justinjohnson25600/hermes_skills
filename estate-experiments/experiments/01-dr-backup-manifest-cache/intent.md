# Experiment: cache the DR-backup manifest verification

## Intent
`check_dr_backup` is 94% of the morning check's wall time (5.07s of 5.36s measured
2026-10-30, cProfile: the `shasum -c` over the USB manifest). The manifest set only
changes once per day (04:00 backup), but the check re-hashes ~465 MB every run and on
every agent-driven re-run. Cache the verification keyed by (manifest sha256, LATEST.txt)
and skip re-hashing when both are unchanged since the last PASS — same freshness contract
(the cache key IS the content being verified), one hash of a 4 KB manifest per run instead
of the whole archive set.

## Metric
Wall-clock seconds of `estate_morning_check.py --date <today>` (full script, JSON overall
line ignored; lower is better). Arms measured back-to-back on the same morning inputs.

## Risk
A stale cache could mask a corrupted archive that changes on disk without the manifest
changing. Mitigated: the cache key is the manifest's own content hash — if any archive
byte changes, the manifest no longer matches reality only if the USB set was rewritten
with the same manifest, which the daily backup never does (each set is timestamped).
Cache lives beside the watcher state (Application Support), not on the USB drive.

owner: hermes-dev ops scripts (mac-mini; apply locally, not fleet-managed)

## Guard (v0.2)
Each arm must still run the full morning check and emit its JSON verdict block
(`ESTATE MORNING CHECK` header + a dr_backup result). A faster arm that skipped
the checks fails the guard and is discarded.
