#!/usr/bin/env bash
set -euo pipefail

# compute_changed_files.sh
# Usage: compute_changed_files.sh <base> <head> <output_json>
# Outputs JSON with changed files and hunks.

BASE_REF=${1:-origin/main}
HEAD_REF=${2:-HEAD}
OUT=${3:-tools/output/changed_files.json}

# Resolve Python executable
PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
    PY=python
fi

mkdir -p "$(dirname "$OUT")"

# Ensure we have the commits locally
if ! git rev-parse "$BASE_REF" >/dev/null 2>&1; then
    echo "Base ref $BASE_REF not found; falling back to HEAD~1" >&2
    BASE_REF="HEAD~1"
fi

# Collect changed files and hunks using git diff --unified=0
TMP=$(mktemp)
# Windows Git Bash mktemp compatibility
if [[ ! -f "$TMP" ]]; then TMP=$(mktemp -t tmp.XXXXXX); fi

git diff --no-color -U0 "$BASE_REF" "$HEAD_REF" > "$TMP" || true

$PY - "$TMP" "$OUT" << 'PY'
import json, re, sys, os

diff_path, out_path = sys.argv[1], sys.argv[2]
changed = []
current = None
hunk_re = re.compile(r'^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@')
file_re = re.compile(r'^\+\+\+ b\/(.*)$')
change_type_map = {}

# Use name-status for change type
import subprocess
base = os.environ.get("BASE_REF","origin/main")
head = os.environ.get("HEAD_REF","HEAD")
try:
    ns = subprocess.check_output(["git","diff","--name-status",base, head], text=True)
except Exception:
    ns = ""
for line in ns.strip().splitlines():
    if not line.strip():
        continue
    typ, path = line.split(maxsplit=1)
    change_type_map[path.strip()] = typ

with open(diff_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if line.startswith('+++ b/'):
            path = file_re.match(line).group(1)
            current = {"path": path, "change_type": change_type_map.get(path, "M"), "hunks": []}
            changed.append(current)
        elif line.startswith('@@') and current is not None:
            m = hunk_re.match(line)
            if m:
                start = int(m.group('new_start'))
                count = int(m.group('new_count') or '1')
                current["hunks"].append({"start": start, "end": start + max(count-1,0)})

with open(out_path,'w',encoding='utf-8') as out:
    json.dump(changed, out, indent=2)
print(f"Wrote {out_path}")
PY

exit 0
