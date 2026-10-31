# estate-experiments

Baseline-vs-trial experiment harness with keep/discard receipts. Ships
`experiment_harness.py` (stdlib only) plus the worked reference experiment
(cache the morning check's USB-manifest verify: 5.21s → 0.19s, keep).

## Install

python3 install.py estate-experiments

## Use

An experiment is a directory with `intent.md`, `baseline.sh`, `trial.sh`, `metric.py`.
`python3 scripts/experiment_harness.py run <dir>` writes `receipt.json` with a
`keep`/`discard` verdict. One variable per experiment; nothing auto-applies.

Version 0.1.0 — 2026-10-30: first release, extracted from the hermes-dev ops scripts.
