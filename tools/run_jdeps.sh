#!/usr/bin/env bash
set -euo pipefail

LOG_LEVEL=${LOG_LEVEL:-INFO}
_ts() { date +"%Y-%m-%dT%H:%M:%S"; }
_lvl() { echo "$1" | tr '[:lower:]' '[:upper:]'; }
log() { echo "[$(_ts)] [$(_lvl "$1")] $2"; }
info() { log INFO "$1"; }
warn() { log WARN "$1"; }

# run_jdeps.sh
# Usage: run_jdeps.sh <project_root> <output_json>
# Requires classes compiled. It scans build/classes dirs and runs jdeps to emit class dependencies JSON.

ROOT=${1:-.}
OUT=${2:-tools/output/jdeps_graph.json}
mkdir -p "$(dirname "$OUT")"

# Find classpath and classes directories
mapfile -t class_dirs < <(find "$ROOT" -type d \( -path "*/build/classes/java/main" -o -path "*/build/classes/java/test" -o -path "*/out/production/*" \) 2>/dev/null)
log INFO "Found ${#class_dirs[@]} class directories for jdeps scan"

if [[ ${#class_dirs[@]} -eq 0 ]]; then
  echo "{}" > "$OUT"
  log WARN "No class dirs found; output empty jdeps graph to $OUT"
  exit 0
fi

TMP=$(mktemp)
if [[ ! -f "$TMP" ]]; then TMP=$(mktemp -t tmp.XXXXXX); fi

# Run jdeps on each dir and parse output
> "$TMP"
if command -v jdeps >/dev/null 2>&1; then
  for d in "${class_dirs[@]}"; do
    jdeps -verbose:class -cp "$d" "$d" || true
  done | tee "$TMP" >/dev/null
else
  echo "jdeps not found; emitting empty graph" > "$TMP"
  log WARN "jdeps not found; writing empty graph"
fi

# Resolve Python (Windows-friendly)
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
  echo "{}" > "$OUT"
  log WARN "Python not found; wrote empty jdeps graph to $OUT"
  exit 0
fi

if [[ "$PY" == "py -3" ]]; then
  py -3 - "$TMP" "$OUT" << 'PY'
import json, re, sys
jdeps_out, out_path = sys.argv[1], sys.argv[2]

deps = {}
line_re = re.compile(r'\s*([\w.$]+)\s*->\s*([\w.$]+)')
with open(jdeps_out, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        m = line_re.match(line)
        if not m:
            continue
        src, dst = m.group(1), m.group(2)
        if src == dst:
            continue
        deps.setdefault(src, set()).add(dst)

as_json = {k: sorted(v) for k,v in deps.items()}
with open(out_path,'w') as out:
    json.dump(as_json, out, indent=2)
print(f"Wrote {out_path}")
PY
else
  $PY - "$TMP" "$OUT" << 'PY'
import json, re, sys
jdeps_out, out_path = sys.argv[1], sys.argv[2]

deps = {}
line_re = re.compile(r'\s*([\w.$]+)\s*->\s*([\w.$]+)')
with open(jdeps_out, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        m = line_re.match(line)
        if not m:
            continue
        src, dst = m.group(1), m.group(2)
        if src == dst:
            continue
        deps.setdefault(src, set()).add(dst)

as_json = {k: sorted(v) for k,v in deps.items()}
with open(out_path,'w') as out:
    json.dump(as_json, out, indent=2)
print(f"Wrote {out_path}")
PY
fi

exit 0
