---
name: client-literature-monitor
version: 0.1.0
author: justin
license: MIT
description: Use when a business client's case files (flagged analytes, topics, keywords) should drive a recurring literature sweep — PubMed per client, new-items-only digests, silent when nothing new. Built for Theorem Metabolic; generalisable to any client with structured case data.
metadata:
  hermes:
    tags: [literature, pubmed, monitoring, client-automation, cron]
    related_skills: [hermes-cron, hermes-agent]
platforms: [macos, windows, linux]
---

# client-literature-monitor — case files drive the literature sweep

Reads each client's structured case data, derives search queries from the items that
actually matter (flagged analytes, open topics), sweeps PubMed, and reports only NEW
items. Empty result = `{"wakeAgent": false}` so the cron job stays silent. State is a
plain JSON seen-set beside the case files.

## When to Use

- A client engagement produces case records with flagged/abnormal markers (Theorem
  Metabolic: hormone panels with out-of-range analytes).
- The client (or you) should know when new published evidence touches their flags.
- Extending an existing client box: point `CLIENTS_ROOT` at that box's case directory.

## Setup on a client box

1. Install the skill: `python3 install.py client-literature-monitor`
2. Copy `scripts/theorem_literature_monitor.py` into `<HERMES_HOME>/scripts/` of the
   client profile (cron `script:` jobs may only reference files under that dir).
3. Edit the constants at the top of the script for the deployment:
   - `CLIENTS_ROOT` — the client case directory on this box
   - `STATE` — where the seen-PMID set lives (beside case data, one per box)
   - `QUERY_HINTS` — per-analyte query fragments (fallback: quoted phrase search)
4. Create the cron job (weekly, agent curates; script pre-check stays silent when
   nothing new):

```bash
hermes cron add "30 7 * * 1" "<curation prompt — see scripts/cron_prompt_template.md>" \
  --name "Literature monitor <client>" \
  --script <profile-relative script filename> \
  --deliver local
```

## Contracts (from CAPA-031's detector rules)

- **Sources are honest:** a network/API failure prints `SOURCES UNKNOWN` — never
  reported as "no new literature".
- **New-only:** every PMID is reported once; the seen-set is the dedupe authority.
- **The script never emails anyone.** The agent turn decides relevance and delivery;
  the script is a read-only collector.
- **Case DBs are opened read-only** (`mode=ro` URI).

## Reference deployment

Theorem Metabolic on mac-mini: cron `66d996ed2a04`, Mondays 07:30, digests to
justin@ascend-ai.co.uk. First sweep found 15 relevant papers for the first client's
flagged analyte; subsequent runs silent until new publications land.
