#!/usr/bin/env bash
# Guard: every manifest entry verified OK in this arm's output — no skipped files.
set -euo pipefail
out="$(cat)"
cd /Volumes/HermesBK/hermes-dr-backups
LATEST="$(cat LATEST.txt)"
expected="$(grep -c . "$LATEST-manifest.sha256")"
oks="$(echo "$out" | grep -c ': OK')"
[ "$oks" -eq "$expected" ]
exit 0
