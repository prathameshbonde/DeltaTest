#!/usr/bin/env bash
set -euo pipefail

# run_soot.sh - lightweight fallback using javap -c to build a naive call graph
# Usage: run_soot.sh <project_root> <output_json>
# Output: JSON array of {caller, callee}

ROOT=${1:-.}
OUT=${2:-tools/output/call_graph.json}
mkdir -p "$(dirname "$OUT")"

mapfile -t class_files < <(find "$ROOT" -type f -path "*/build/classes/java/main/*.class" -o -path "*/build/classes/java/test/*.class" 2>/dev/null)

TMP=$(mktemp)
if [[ ! -f "$TMP" ]]; then TMP=$(mktemp -t tmp.XXXXXX); fi

> "$TMP"
if ! command -v javap >/dev/null 2>&1; then
  echo "javap not found; emitting empty call graph" > "$TMP"
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

PY=python3; command -v $PY >/dev/null 2>&1 || PY=python
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

exit 0
