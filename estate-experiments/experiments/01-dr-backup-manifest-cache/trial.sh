#!/usr/bin/env bash
# Trial: check with the manifest-verification cache, warm cache (the first run writes it).
set -euo pipefail
cd "$(dirname "$0")/../.."
/usr/bin/time -p env EMC_TARGET="$PWD/estate_morning_check_cached.py" python3 experiment_harness_runner.py --date "$(date +%F)" > /dev/null
/usr/bin/time -p env EMC_TARGET="$PWD/estate_morning_check_cached.py" python3 experiment_harness_runner.py --date "$(date +%F)" > /dev/null
