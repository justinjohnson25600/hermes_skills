# Changelog

## 0.2.0 — 2026-10-31
- Two-phase state: new items pending -> delivered only after --confirm-delivered
  (agent runs it post-email). Crashes can no longer lose papers; pending re-offers.
- Pagination past retmax (cap 200) with TRUNCATED error; no silent drops.
- Throttled E-utilities client (1 req/s) with 429/5xx backoff — retry honestly,
  never silently drop.
- JSON config file (env LITERATURE_MONITOR_CONFIG / beside state / cwd) replaces
  hand-edited constants; deployed script stays repo-identical.
- last_success_at heartbeat in state; dead cron distinguishable from quiet.
- Retraction/correction watch over delivered PMIDs.

## 0.1.0 — 2026-10-30
- First release: `theorem_literature_monitor.py` (PubMed E-utilities, case-DB-derived
  queries, seen-PMID dedupe, SOURCES UNKNOWN honesty, wakeAgent-false silence),
  cron prompt template. Reference deployment: Theorem Metabolic, mac-mini,
  cron 66d996ed2a04 (Mondays 07:30).
