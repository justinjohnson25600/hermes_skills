# Changelog

## 0.3.2 - 2026-11-05
- fix: the install verifier's end-to-end probe judged a 0.25s wall-clock gap over 2 runs; on Windows, Git-for-Windows bash start-up jitter exceeded it (jj-amd: spread 0.296s > margin 0.242s), so a correct install failed as "within noise". The probe now scores arms deterministically (SCORE 10 vs SCORE 1): it still proves arms run under bash, the guard, metric parsing and the verdict, with no timing dependence.

## 0.3.1 - 2026-11-02
- fix: harness ran arms with a bare `bash`; on Windows that is System32\bash.exe (WSL launcher), so every arm exited 127 and experiments were mislabelled `discard`. `bash_exe()` now resolves Git-for-Windows bash on win32 and raises a clear error when none is installed.
- verify_install.py reuses `bash_exe()`; prints a named NOTE (not a pass-through) where no Git bash exists; ASCII-only output.

## 0.3.0 — 2026-11-02
- cron_ops_ledger.py: passive per-job run ledger from executions.db (snapshot read, never the live store).
- selftest.sh: per-machine proof both skills are installed and working (deployed and repo layouts).
- Experiment 02 (parallel manifest verify): 8.16s -> 1.18s median, guard-checked, keep; applied.

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
