#!/usr/bin/env bash
# Estate skills self-test — run on ANY fleet machine to prove the two skills are
# installed and functional there. Exit 0 = working; anything else = broken.
# Works in both layouts:
#   deployed: <home>/skills/<category>/<skill>/scripts/selftest.sh
#   repo:     <repo>/<skill>/scripts/selftest.sh
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"          # .../<skill>/scripts
skill_dir="$(cd "$here/.." && pwd)"            # .../<skill>

# peer paths for both layouts
if [ -d "$skill_dir/../client-literature-monitor" ]; then        # repo layout
  mon="$skill_dir/../client-literature-monitor/scripts/theorem_literature_monitor.py"
else                                                             # deployed layout
  mon="$skill_dir/../../devops/client-literature-monitor/scripts/theorem_literature_monitor.py"
fi
harness="$here/experiment_harness.py"
tests="$here/test_experiment_harness.py"

fail=0
[ -f "$harness" ] && echo "PASS present: experiment_harness.py" || { echo "FAIL missing: experiment_harness.py"; fail=1; }
[ -f "$mon" ]    && echo "PASS present: theorem_literature_monitor.py" || { echo "FAIL missing: theorem_literature_monitor.py"; fail=1; }

# harness falsifier suite (guard / no-guard / noise verdict logic)
if out="$(python3 "$tests" 2>&1)"; then
  echo "PASS harness falsifier suite: $(echo "$out" | grep -E '^Ran')"
else
  echo "FAIL harness falsifier suite"; echo "$out" | tail -5; fail=1
fi

# harness end-to-end on a synthetic experiment -> keep
tmp="$(mktemp -d)"
mkdir -p "$tmp/exp"
printf '# t\nimprove x\n' > "$tmp/exp/intent.md"
printf '#!/usr/bin/env bash\necho "WORK_DONE n=10"\nsleep 0.30\n' > "$tmp/exp/baseline.sh"
printf '#!/usr/bin/env bash\necho "WORK_DONE n=10"\nsleep 0.05\n' > "$tmp/exp/trial.sh"
printf 'import re\ndef parse(o):\n    return float(re.findall(r"real ([0-9.]+)", o)[-1])\n' > "$tmp/exp/metric.py"
printf '#!/usr/bin/env bash\no="$(cat)"; echo "$o" | grep -q WORK_DONE\n' > "$tmp/exp/guard.sh"
if out2="$(python3 "$harness" run "$tmp/exp" --runs 2 2>&1)" && echo "$out2" | grep -q '"verdict": "keep"'; then
  echo "PASS harness end-to-end: synthetic experiment -> keep"
else
  echo "FAIL harness end-to-end"; echo "$out2" | tail -6; fail=1
fi
rm -rf "$tmp"

# monitor v0.2 interface (two-phase delivery present); no network used
if python3 "$mon" --help 2>&1 | grep -q -- "--confirm-delivered"; then
  echo "PASS monitor v0.2 interface (two-phase delivery present)"
else
  echo "FAIL monitor interface"; fail=1
fi

if [ "$fail" -eq 0 ]; then echo "SELFTEST OK — both skills installed and working on $(hostname -s)"; else echo "SELFTEST FAILED"; fi
exit $fail
