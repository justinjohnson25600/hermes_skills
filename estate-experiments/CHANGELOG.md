# Changelog

## 0.2.0 — 2026-10-31
- Guard-checked verdicts: keep requires guard.sh proving the arm did the work; no guard = unproven.
- Interleaved multi-run arms (default 3): median vs spread; verdicts inside noise refused.
- Per-run JSONL ledger + `ledger` rollup command (passive baselines).
- Receipts name the target owner; falsifier suite scripts/test_experiment_harness.py
  (red on v0.1: a work-skipping trial with a better metric got keep).

## 0.1.0 — 2026-10-30
- First release: `experiment_harness.py` (run/show, keep/discard verdicts, receipts),
  runner shim, and the reference experiment `01-dr-backup-manifest-cache`
  (baseline 5.21s → trial 0.19s, verdict keep, applied to the estate morning check).
