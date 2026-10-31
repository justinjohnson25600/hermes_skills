# client-literature-monitor

PubMed sweep driven by client case files' flagged markers. New-items-only digests,
honest-unknown source handling, silent (`{"wakeAgent": false}`) when nothing new.
Built for Theorem Metabolic; `CLIENTS_ROOT` points it at any client's case directory.

## Install

python3 install.py client-literature-monitor

## Setup per client box

1. Copy `scripts/theorem_literature_monitor.py` into the client profile's
   `<HERMES_HOME>/scripts/` (cron script jobs resolve there only).
2. Set `CLIENTS_ROOT`, `STATE`, `QUERY_HINTS` at the top of the script.
3. Create the weekly cron job with the prompt from
   `scripts/cron_prompt_template.md`, `--script <filename>`, `--deliver local`.

Version 0.2.0 — 2026-10-30: first release, extracted from the Theorem Metabolic
deployment on mac-mini (cron 66d996ed2a04).
