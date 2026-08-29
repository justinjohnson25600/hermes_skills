#!/bin/sh
# Install this repo's git hooks. Run once per clone:
#   sh scripts/install-hooks.sh
set -e
root=$(git rev-parse --show-toplevel)
cp "$root/scripts/pre-push" "$root/.git/hooks/pre-push"
chmod +x "$root/.git/hooks/pre-push"
echo "installed pre-push consistency gate -> .git/hooks/pre-push"
echo "check manually with: python3 check_consistency.py"
