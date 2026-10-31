#!/usr/bin/env bash
# Guard for the reference experiment (v0.2): an arm "did the work" iff the
# morning check actually ran its checks and produced its JSON verdict block —
# not merely exited 0 quickly. Reads the arm's full output on stdin.
set -euo pipefail
out="$(cat)"
echo "$out" | grep -q "ESTATE MORNING CHECK"
echo "$out" | grep -q '"check": "dr_backup"'
n="$(echo "$out" | grep -o '"verdict"' | wc -l | tr -d ' ')"
[ "$n" -ge 5 ]
exit 0
