#!/usr/bin/env bash
set -euo pipefail

LOG_LEVEL=${LOG_LEVEL:-INFO}
_ts() { date +"%Y-%m-%dT%H:%M:%S"; }
_lvl() { echo "$1" | tr '[:lower:]' '[:upper:]'; }
log() { echo "[$(_ts)] [$(_lvl "$1")] $2"; }
info() { log INFO "$1"; }
warn() { log WARN "$1"; }

# run_soot.sh - lightweight fallback using javap -c to build a naive call graph
# Usage: run_soot.sh <project_root> <output_json>
# Output: JSON array of {caller, callee}

ROOT=${1:-.}
OUT=${2:-tools/output/call_graph.json}
mkdir -p "$(dirname "$OUT")"

mapfile -t class_files < <(find "$ROOT" -type f -path "*/build/classes/java/main/*.class" -o -path "*/build/classes/java/test/*.class" 2>/dev/null)
log INFO "Found ${#class_files[@]} class files for javap scan"

TMP=$(mktemp)
if [[ ! -f "$TMP" ]]; then TMP=$(mktemp -t tmp.XXXXXX); fi

> "$TMP"
if ! command -v javap >/dev/null 2>&1; then
  echo "javap not found; emitting empty call graph" > "$TMP"
  log WARN "javap not found; writing empty call graph"
else
  for cf in "${class_files[@]}"; do
  # Derive FQCN assuming build/classes/java/main root
  fqcn=$(echo "$cf" | sed -E 's#.*build/classes/java/(main|test)/##; s#/#.#g; s#\.class$##')
  # Dump bytecode and parse invokes
  javap -classpath "$(dirname "$cf")" -c "$fqcn" 2>/dev/null | awk -v caller="$fqcn" '
    /invoke(static|virtual|interface|special)/ {
      # example tail: Method com/foo/Baz.doIt:()V
      for (i=1;i<=NF;i++) {
        if ($i ~ /Method/) {
          tgt=$(i+1)
          gsub("/", ".", tgt)
          sub(":.*$", "", tgt)
          method=$(i+2)
          gsub("[():;VZBCSIJFD]", "", method)
          if (method != "<init>") {
            print caller"#? -> "tgt"#"method
          }
          break
        }
      }
    }
  ' || true
  done >> "$TMP"
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
  echo "[]" > "$OUT"
  log WARN "Python not found; wrote empty call graph to $OUT"
  exit 0
fi

if [[ "$PY" == "py -3" ]]; then
  py -3 - "$TMP" "$OUT" << 'PY'
import json, sys
inp, outp = sys.argv[1], sys.argv[2]
edges = []
with open(inp,'r') as f:
    for line in f:
        line = line.strip()
        if not line or '->' not in line:
            continue
        caller, callee = [x.strip() for x in line.split('->',1)]
        # Normalize stray '#?'
        caller = caller.replace('#?', '')
        edges.append({"caller": caller, "callee": callee})
with open(outp,'w') as out:
    json.dump(edges, out, indent=2)
print(f"Wrote {outp}")
PY
else
  $PY - "$TMP" "$OUT" << 'PY'
import json, sys
inp, outp = sys.argv[1], sys.argv[2]
edges = []
with open(inp,'r') as f:
    for line in f:
        line = line.strip()
        if not line or '->' not in line:
            continue
        caller, callee = [x.strip() for x in line.split('->',1)]
        # Normalize stray '#?'
        caller = caller.replace('#?', '')
        edges.append({"caller": caller, "callee": callee})
with open(outp,'w') as out:
    json.dump(edges, out, indent=2)
print(f"Wrote {outp}")
PY
fi

exit 0
