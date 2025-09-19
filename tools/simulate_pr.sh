#!/usr/bin/env bash
set -euo pipefail

# Simulate a PR by comparing HEAD~1 to HEAD
BASE=${1:-HEAD~1}
HEAD=${2:-HEAD}
echo "Simulating PR from $BASE to $HEAD"
bash tools/run_selector.sh --project-root . --base "$BASE" --head "$HEAD" --dry-run
