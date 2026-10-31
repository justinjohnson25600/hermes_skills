#!/usr/bin/env bash
# Trial: the production check as-is (manifest-verification cache active, weekly
# forced full re-verify). One variable differs from baseline: the cache.
set -euo pipefail
python3 ~/.hermes/profiles/hermes-dev/scripts/estate_morning_check.py --date "$(date +%F)"
