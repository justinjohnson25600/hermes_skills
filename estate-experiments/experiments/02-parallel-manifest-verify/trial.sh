#!/usr/bin/env bash
# Trial: same manifest, same hashes, N parallel workers — a tiny Python worker per file
# (no nested shell quoting), each printing "<file>: OK" for the guard to count.
set -euo pipefail
cd /Volumes/HermesBK/hermes-dr-backups
LATEST="$(cat LATEST.txt)"
MANIFEST="$LATEST-manifest.sha256"
export MANIFEST
/usr/bin/time -p python3 - <<'PY'
import hashlib
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

lines = [l for l in open(os.environ["MANIFEST"]) if l.strip()]
n = len(lines)
p = min(4, n)

def verify(line: str) -> str:
    want, _, f = line.partition("  ")
    f = f.strip()
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"{f}: OK" if h.hexdigest() == want else f"{f}: FAILED"

with ThreadPoolExecutor(max_workers=p) as ex:
    for r in ex.map(verify, lines):
        print(r)
        if r.endswith("FAILED"):
            raise SystemExit(1)
PY
