#!/usr/bin/env python3
"""Cron ops ledger — passive record of what the scheduler actually ran.

Source of truth: each profile's cron/executions.db (table `executions`:
job_id, status, started_at, finished_at, error). Read from a SNAPSHOT copy so the
live store is never opened by this tool (no lock contention with the ticker).

    python3 cron_ops_ledger.py [profile_home ...] [--days 14]

Per job: runs, median duration, failures, last status. Ranked slowest-and-most-
frequent first — the candidate list for experiments ("where is time spent?").
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sqlite3
import statistics
import tempfile
from pathlib import Path

OK_STATES = {"ok", "success", "completed", "done"}


def read_executions(home: Path, days: int) -> list[dict]:
    src = home / "cron" / "executions.db"
    if not src.is_file():
        return []
    tmp = Path(tempfile.mkdtemp(prefix="cronledger_")) / "snap.db"
    try:
        shutil.copy2(src, tmp)  # snapshot: never open the live store
        con = sqlite3.connect(str(tmp))
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
        cur = con.execute(
            "SELECT job_id, status, started_at, finished_at FROM executions "
            "WHERE started_at >= ? ORDER BY started_at", (cutoff,))
        out = []
        for job_id, status, started, finished in cur.fetchall():
            dur = None
            try:
                a = dt.datetime.fromisoformat(str(started).replace("Z", "+00:00"))
                b = dt.datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
                dur = (b - a).total_seconds()
            except (TypeError, ValueError):
                pass
            out.append({"job_id": job_id, "status": status, "started_at": started, "duration_s": dur})
        con.close()
        return out
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("homes", nargs="*", default=[str(Path.home() / ".hermes" / "profiles" / "hermes-dev")])
    ap.add_argument("--days", type=int, default=14)
    a = ap.parse_args()
    for h in a.homes:
        home = Path(h).expanduser()
        rows = read_executions(home, a.days)
        print(f"== {home.name}: {len(rows)} runs in last {a.days}d")
        if not rows:
            continue
        by_job: dict[str, list[dict]] = {}
        for r in rows:
            by_job.setdefault(str(r["job_id"]), []).append(r)
        def med(rs):
            d = [r["duration_s"] for r in rs if r["duration_s"] is not None]
            return statistics.median(d) if d else 0.0
        for job, rs in sorted(by_job.items(), key=lambda kv: -med(kv[1]) * len(kv[1])):
            fails = sum(1 for r in rs if str(r["status"]).lower() not in OK_STATES)
            print(f"  {job[:14]:<14} n={len(rs):<3} median={med(rs):8.1f}s "
                  f"fails={fails:<3} last={rs[-1]['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
