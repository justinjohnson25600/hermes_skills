# Experiment: parallelize the weekly full manifest verification

## Intent
`check_dr_backup`'s weekly forced full re-verify runs `shasum -a 256 -c` over the USB
backup set — measured 5.36s serial (dominated by waiting on the slow USB volume, not
CPU). The manifest lists independent files; hashing them with N parallel workers should
cut wall time roughly by min(N, files). Metric: wall seconds of the full verify.

## Metric
Wall-clock of the manifest verification (lower = better), measured by the harness.

## Guard
Both arms must produce an OK line for EVERY manifest entry — a verify that skips files
is not a verify. `guard.sh` counts `: OK` lines in the arm output and requires the count
to equal the manifest entry count.

## Risk
Parallel reads on one slow USB spindle can thrash seeks and make it *slower*; that is
exactly what the interleaved/noise-aware verdict will catch (discard, no harm done).
Read-only: no writes to the USB set in either arm.

owner: hermes-dev ops scripts (mac-mini; apply locally, not fleet-managed)
