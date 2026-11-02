#!/usr/bin/env bash
# Baseline: the current serial full verification (what production does weekly).
set -euo pipefail
cd /Volumes/HermesBK/hermes-dr-backups
LATEST="$(cat LATEST.txt)"
/usr/bin/time -p shasum -a 256 -c "$LATEST-manifest.sha256" 2>/dev/null
