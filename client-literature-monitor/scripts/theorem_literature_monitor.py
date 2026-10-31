#!/usr/bin/env python3
"""Theorem Metabolic literature monitor (mac-mini, hermes-dev profile).

Read-only PubMed sweep for each client's flagged analytes/topics. Derives its queries
from the case DBs (never hand-copied), keeps a seen-PMID state file, and prints a compact
digest of NEW papers only. Empty output = nothing new (cron stays silent). The agent turn
that receives this output decides relevance; this script never emails anyone.

    python3 theorem_literature_monitor.py [--window-days 30] [--all-clients]

State: <clients root>/../theorem-literature-state.json (beside the case files, not in git).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CLIENTS_ROOT = Path.home() / "Documents" / "Theorem Metabolic" / "clients"
STATE = Path.home() / "Documents" / "Theorem Metabolic" / "theorem-literature-state.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UA = {"User-Agent": "theorem-metabolic-literature-monitor/0.1 (justin@theorem.fit)"}

# MeSH-flavoured query fragments per analyte name as they appear in case DBs. Anything
# not mapped here falls back to a plain phrase search.
QUERY_HINTS = {
    "Free Testosterone": '("free testosterone"[Title/Abstract] OR "free androgen"[Title/Abstract]) AND (female*[Title/Abstract] OR women[Title/Abstract])',
    "Testosterone": '"testosterone"[Title/Abstract] AND (female*[Title/Abstract] OR women[Title/Abstract])',
    "Oestradiol": '"estradiol"[Title/Abstract] OR "oestradiol"[Title/Abstract]',
    "Progesterone": '"progesterone"[Title/Abstract]',
    "Prolactin": '"prolactin"[Title/Abstract]',
    "SHBG": '"sex hormone binding globulin"[Title/Abstract] OR SHBG[Title/Abstract]',
    "Sex Hormone Binding Globulin": '"sex hormone binding globulin"[Title/Abstract] OR SHBG[Title/Abstract]',
}
FALLBACK_WINDOW_DAYS = 30


def http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def flagged_topics(db: sqlite3.Connection) -> list[tuple[str, str]]:
    """(analyte name, flag) rows where flag is not 'in-range' — the clinical questions."""
    rows = db.execute("SELECT name, flag FROM analytes WHERE flag IS NOT NULL AND flag != 'in-range'").fetchall()
    return [(str(n), str(f)) for n, f in rows]


def client_dirs() -> list[Path]:
    return sorted(p for p in CLIENTS_ROOT.iterdir() if p.is_dir()) if CLIENTS_ROOT.is_dir() else []


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"seen": {}}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=1))


def search(topic: str, window_days: int) -> list[dict]:
    q = QUERY_HINTS.get(topic, f'"{topic}"[Title/Abstract]')
    term = f"{q} AND ({dt.date.today().year - 1}:{dt.date.today().year}[pdat])"
    params = urllib.parse.urlencode({"db": "pubmed", "term": term, "retmode": "json",
                                     "retmax": 15, "datetype": "pdat", "reldate": window_days})
    try:
        res = http_json(f"{EUTILS}/esearch.fcgi?{params}")["esearchresult"]
    except Exception as exc:  # network faults surface as UNKNOWN, never as "no results"
        return [{"error": f"{type(exc).__name__}: {exc}"}]
    ids = res.get("idlist", [])
    if not ids:
        return []
    params = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
    try:
        docs = http_json(f"{EUTILS}/esummary.fcgi?{params}")["result"]
    except Exception as exc:
        return [{"error": f"{type(exc).__name__}: {exc}"}]
    out = []
    for pid in ids:
        d = docs.get(pid, {})
        if "title" in d:
            out.append({"pmid": pid, "title": re.sub(r"\.$", "", str(d["title"])),
                        "journal": d.get("fulljournalname") or d.get("source", ""),
                        "date": d.get("pubdate", "")})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=FALLBACK_WINDOW_DAYS)
    ap.add_argument("--all-clients", action="store_true",
                    help="report for every client, not only those with flagged analytes")
    args = ap.parse_args()

    state = load_state()
    new_papers: list[str] = []
    errors: list[str] = []
    for cdir in client_dirs():
        dbs = sorted(cdir.glob("*case.sqlite3"))
        if not dbs:
            continue
        try:
            db = sqlite3.connect(f"file:{dbs[0]}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            errors.append(f"{cdir.name}: case DB unreadable: {exc}")
            continue
        topics = flagged_topics(db)
        if not topics and not args.all_clients:
            db.close()
            continue
        client = cdir.name
        seen: set = set(state["seen"].get(client, []))
        for name, flag in topics:
            for paper in search(name, args.window_days):
                if "error" in paper:
                    errors.append(f"{client}/{name}: {paper['error']}")
                    continue
                if paper["pmid"] in seen:
                    continue
                seen.add(paper["pmid"])
                new_papers.append(f"[{client}] {name} ({flag}) — PMID {paper['pmid']}: "
                                  f"{paper['title']} ({paper['journal']}, {paper['date']})")
        state["seen"][client] = sorted(seen)
        db.close()

    save_state(state)
    if errors:
        print("SOURCES UNKNOWN (do not report 'no new literature'):")
        for e in errors:
            print(f"  - {e}")
    for line in new_papers:
        print(line)
    if not new_papers and not errors:
        print('{"wakeAgent": false}')  # scheduler skips the agent turn; nothing new
    return 0


if __name__ == "__main__":
    sys.exit(main())
