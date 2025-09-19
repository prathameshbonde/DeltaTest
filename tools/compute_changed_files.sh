#!/usr/bin/env bash
set -euo pipefail

LOG_LEVEL=${LOG_LEVEL:-INFO}
_ts() { date +"%Y-%m-%dT%H:%M:%S"; }
_lvl() { echo "$1" | tr '[:lower:]' '[:upper:]'; }
log() { echo "[$(_ts)] [$(_lvl "$1")] $2"; }
info() { log INFO "$2"; }
warn() { log WARN "$2"; }

# compute_changed_files.sh
# Usage: compute_changed_files.sh <base> <head> <output_json>
# Outputs JSON with changed files and hunks.

BASE_REF=${1:-origin/main}
HEAD_REF=${2:-HEAD}
OUT=${3:-tools/output/changed_files.json}

# Resolve Python executable
# Resolve Python executable (Windows-friendly)
PY=""
if [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/Scripts/python.exe" ]]; then
    PY="$VIRTUAL_ENV/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
elif command -v py >/dev/null 2>&1; then
    PY="py -3"
else
    echo "Python interpreter not found. Please install Python 3 or activate your venv." >&2
    mkdir -p "$(dirname "$OUT")"
    echo "[]" > "$OUT"
    exit 0
fi

mkdir -p "$(dirname "$OUT")"

# If not a git repo, or no commits yet, write empty changes and exit cleanly
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    log WARN "Not a git repository; producing empty change set."
    echo "[]" > "$OUT"
    exit 0
fi

# Normalize HEAD ref
if ! git rev-parse "$HEAD_REF" >/dev/null 2>&1; then
        if git rev-parse HEAD >/dev/null 2>&1; then
            log WARN "Head ref $HEAD_REF not found; using HEAD."
        HEAD_REF="HEAD"
    else
            log WARN "No commits yet; producing empty change set."
        echo "[]" > "$OUT"
        exit 0
    fi
fi

# Ensure we have a valid base; if missing, use the empty tree so first-commit diffs work
if ! git rev-parse "$BASE_REF" >/dev/null 2>&1; then
    EMPTY_TREE=$(git hash-object -t tree /dev/null 2>/dev/null || echo 4b825dc642cb6eb9a060e54bf8d69288fbee4904)
        log WARN "Base ref $BASE_REF not found; falling back to empty tree."
    BASE_REF="$EMPTY_TREE"
fi

# Export the (potentially adjusted) refs for the Python snippet below
export BASE_REF
export HEAD_REF

# Collect changed files and hunks using git diff --unified=0
TMP=$(mktemp)
# Windows Git Bash mktemp compatibility
if [[ ! -f "$TMP" ]]; then TMP=$(mktemp -t tmp.XXXXXX); fi

log INFO "Computing git diff between $BASE_REF and $HEAD_REF"
git diff --no-color -U0 "$BASE_REF" "$HEAD_REF" > "$TMP" || true

# Run embedded Python, supporting both "python" and "py -3"
if [[ "$PY" == "py -3" ]]; then
  py -3 - "$TMP" "$OUT" << 'PY'
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
    parts = line.split(maxsplit=1)
    if len(parts) == 2:
        typ, path = parts
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
else
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
    parts = line.split(maxsplit=1)
    if len(parts) == 2:
        typ, path = parts
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
fi

exit 0
