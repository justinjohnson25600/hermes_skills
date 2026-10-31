#!/usr/bin/env bash
# Baseline: current estate_morning_check.py wall time (uncached manifest verify).
set -euo pipefail
cd "$(dirname "$0")/../.."
/usr/bin/time -p python3 estate_morning_check.py --date "$(date +%F)" > /dev/null
