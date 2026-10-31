#!/usr/bin/env bash
# Baseline: the pre-cache morning check — cache neutralized so every run does the
# full USB manifest verification. Reconstructed from the live production script
# with the cache hit disabled (v0.2 methodology: same code, one variable changed).
set -euo pipefail
SCRIPTS=~/.hermes/profiles/hermes-dev/scripts
python3 - "$SCRIPTS/estate_morning_check.py" <<'PY'
import sys
from pathlib import Path
src = Path(sys.argv[1]).read_text()
old = 'if cached and cached.get("key") == key and cached.get("verdict") == "ok" and cache_fresh:'
new = 'if False:  # baseline arm: cache disabled, full verify every run'
assert old in src, "cache hunk not found — baseline reconstruction failed"
Path("/tmp/emc_base_copy.py").write_text(src.replace(old, new))
PY
python3 /tmp/emc_base_copy.py --date "$(date +%F)"
