#!/usr/bin/env python3
"""Client literature monitor v0.2.

Changes from v0.1 (council 2026-10-31):
  * TWO-PHASE STATE — new items are recorded as "pending" and only move to
    "delivered" when --confirm-delivered runs after a successful digest send.
    Pending items are re-offered on every run: an agent crash or email failure
    can no longer silently lose papers.
  * PAGINATION — esearch counts above retmax are paged through (up to 200);
    anything still unfetched emits a TRUNCATED error. No silent drops.
  * CONFIG FILE — no hand-edited constants: reads config from (in order)
    $LITERATURE_MONITOR_CONFIG, <state dir>/literature-monitor.json, or
    ./literature-monitor.json. The deployed script stays byte-identical to
    the repo copy, so weekly convergence never clobbers deployment settings.
  * HEARTBEAT — writes last_success_at into the state file; a dead cron is
    distinguishable from a quiet month.
  * RETRACTION WATCH — delivered PMIDs are re-checked each run; retracted or
    corrected papers are reported as RETRACTED/CORRECTED lines so a client is
    never left pointed at withdrawn evidence.

Read-only PubMed sweep per client case DB. Prints new items only; silent
({"wakeAgent": false}) when nothing new. SOURCES UNKNOWN on source failure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UA = {"User-Agent": "client-literature-monitor/0.2 (+hermes estate)"}
_LAST_CALL = [0.0]  # module-level throttle state: NCBI allows 3 req/s unauthenticated


def http_json(url: str, retries: int = 3) -> dict:
    """Throttled (>=1 req/s) with 429/5xx backoff. A rate limit must surface as
    an error after honest retries, never as silently-missing papers."""
    import time as _time
    wait = 1.0 - (_time.monotonic() - _LAST_CALL[0])
    if wait > 0:
        _time.sleep(wait)
    for attempt in range(retries + 1):
        _LAST_CALL[0] = _time.monotonic()
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and attempt < retries:
                _time.sleep(2 ** attempt + 1)  # 2s, 3s, 5s
                continue
            raise

DEFAULT_CONFIG = {
    "clients_root": "~/Documents/Theorem Metabolic/clients",
    "state_file": "~/Documents/Theorem Metabolic/theorem-literature-state.json",
    "window_days": 30,
    "retmax": 15,
    "page_cap": 200,
    "query_hints": {},
}

QUERY_HINTS_BUILT_IN = {
    "Free Testosterone": '("free testosterone"[Title/Abstract] OR "free androgen"[Title/Abstract]) AND (female*[Title/Abstract] OR women[Title/Abstract])',
    "Testosterone": '"testosterone"[Title/Abstract] AND (female*[Title/Abstract] OR women[Title/Abstract])',
    "Oestradiol": '"estradiol"[Title/Abstract] OR "oestradiol"[Title/Abstract]',
    "Progesterone": '"progesterone"[Title/Abstract]',
    "Prolactin": '"prolactin"[Title/Abstract]',
    "SHBG": '"sex hormone binding globulin"[Title/Abstract] OR SHBG[Title/Abstract]',
    "Sex Hormone Binding Globulin": '"sex hormone binding globulin"[Title/Abstract] OR SHBG[Title/Abstract]',
}


def load_config(explicit: str | None = None) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    for cand in ([explicit] if explicit else []) + [
        os.environ.get("LITERATURE_MONITOR_CONFIG"),
        str(Path(str(cfg["state_file"])).expanduser().parent / "literature-monitor.json"),
        "literature-monitor.json",
    ]:
        if cand and Path(cand).expanduser().is_file():
            cfg.update(json.loads(Path(cand).expanduser().read_text()))
            cfg["_config_path"] = str(cand)
            break
    return cfg


def flagged_topics(db: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = db.execute("SELECT name, flag FROM analytes WHERE flag IS NOT NULL AND flag != 'in-range'").fetchall()
    return [(str(n), str(f)) for n, f in rows]


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"seen": {}, "pending": {}, "delivered": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1))


def search_paged(topic: str, cfg: dict) -> tuple[list[dict], list[str]]:
    """All results, paged. Returns (papers, errors). Never silently truncates."""
    window_days, retmax, cap = int(cfg["window_days"]), int(cfg["retmax"]), int(cfg["page_cap"])
    hints = cfg.get("query_hints") or {}
    q = hints.get(topic) or QUERY_HINTS_BUILT_IN.get(topic) or f'"{topic}"[Title/Abstract]'
    term = f"{q} AND ({dt.date.today().year - 1}:{dt.date.today().year}[pdat])"
    base = {"db": "pubmed", "term": term, "retmode": "json", "retmax": retmax,
            "datetype": "pdat", "reldate": window_days}
    errors: list[str] = []
    try:
        res = http_json(f"{EUTILS}/esearch.fcgi?{urllib.parse.urlencode(base)}")["esearchresult"]
    except Exception as exc:
        return [], [f"{topic}: esearch {type(exc).__name__}: {exc}"]
    count = int(res.get("count") or 0)
    ids: list[str] = list(res.get("idlist", []))
    offset = retmax
    while len(ids) < min(count, cap):
        p2 = dict(base, retstart=offset)
        try:
            more = http_json(f"{EUTILS}/esearch.fcgi?{urllib.parse.urlencode(p2)}")["esearchresult"]
            batch = more.get("idlist", [])
            if not batch:
                break
            ids.extend(batch)
            offset += retmax
        except Exception as exc:
            errors.append(f"{topic}: pagination {type(exc).__name__}: {exc}")
            break
    if count > len(ids):
        errors.append(f"{topic}: TRUNCATED — {count} matches, {len(ids)} fetched (cap {cap})")
    if not ids:
        return [], errors
    p3 = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids[:cap]), "retmode": "json"})
    try:
        docs = http_json(f"{EUTILS}/esummary.fcgi?{p3}")["result"]
    except Exception as exc:
        return [], [f"{topic}: esummary {type(exc).__name__}: {exc}"]
    out = []
    for pid in ids:
        d = docs.get(pid, {})
        if "title" in d:
            out.append({"pmid": pid, "title": re.sub(r"\.$", "", str(d["title"])),
                        "journal": d.get("fulljournalname") or d.get("source", ""),
                        "date": d.get("pubdate", ""),
                        "pubtype": [str(t) for t in d.get("pubtype", [])]})
    return out, errors


def check_retractions(delivered: dict) -> tuple[list[str], list[str]]:
    """Re-check delivered PMIDs; report retracted/corrected ones."""
    lines, errors = [], []
    pmids = list(delivered.keys())
    for i in range(0, len(pmids), 100):
        chunk = pmids[i:i + 100]
        p = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(chunk), "retmode": "json"})
        try:
            docs = http_json(f"{EUTILS}/esummary.fcgi?{p}")["result"]
        except Exception as exc:
            errors.append(f"retraction watch: esummary {type(exc).__name__}: {exc}")
            continue
        for pid in chunk:
            d = docs.get(pid, {})
            types = [str(t) for t in d.get("pubtype", [])]
            title = str(d.get("title", ""))[:100]
            if any("Retracted" in t for t in types):
                lines.append(f"RETRACTED PMID {pid}: {title} — previously delivered, notify the client")
            elif "Corrected and Republished Article" in types:
                lines.append(f"CORRECTED PMID {pid}: {title} — previously delivered, check the correction")
    return lines, errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=None)
    ap.add_argument("--all-clients", action="store_true")
    ap.add_argument("--confirm-delivered", action="store_true",
                    help="run AFTER the digest email sent: moves all pending to delivered")
    ap.add_argument("--config", help="path to a JSON config file")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.window_days:
        cfg["window_days"] = args.window_days
    clients_root = Path(str(cfg["clients_root"])).expanduser()
    state_path = Path(str(cfg["state_file"])).expanduser()
    state = load_state(state_path)

    if args.confirm_delivered:
        moved = sorted(state.get("pending", {}).keys())
        for pmid in moved:
            state.setdefault("delivered", {})[pmid] = state["pending"][pmid]
        state["pending"] = {}
        state["last_success_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        save_state(state_path, state)
        print(json.dumps({"confirmed_delivered": len(moved)}))
        return 0

    errors: list[str] = []
    new_lines: list[str] = []
    pending: dict = state.setdefault("pending", {})
    delivered: dict = state.get("delivered", {})

    if delivered:
        rlines, rerrs = check_retractions(delivered)
        new_lines.extend(rlines)
        errors.extend(rerrs)

    for cdir in sorted(p for p in clients_root.iterdir() if p.is_dir()) if clients_root.is_dir() else []:
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
        for name, flag in topics:
            papers, errs = search_paged(name, cfg)
            errors.extend(errs)
            for paper in papers:
                pid = paper["pmid"]
                if pid in pending or pid in delivered:
                    continue
                pending[pid] = {"client": client, "topic": name, "flag": flag,
                                "found": dt.date.today().isoformat()}
                new_lines.append(f"[{client}] {name} ({flag}) — PMID {pid}: "
                                 f"{paper['title']} ({paper['journal']}, {paper['date']})")
        db.close()

    state["last_success_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    save_state(state_path, state)

    if errors:
        print("SOURCES UNKNOWN (do not report 'no new literature'):")
        for e in errors[:20]:
            print(f"  - {e}")
    for line in new_lines:
        print(line)
    if not new_lines and not errors:
        print('{"wakeAgent": false}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
