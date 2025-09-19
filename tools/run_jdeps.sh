#!/usr/bin/env bash
set -euo pipefail

# run_jdeps.sh
# Usage: run_jdeps.sh <project_root> <output_json>
# Requires classes compiled. It scans build/classes dirs and runs jdeps to emit class dependencies JSON.

ROOT=${1:-.}
OUT=${2:-tools/output/jdeps_graph.json}
mkdir -p "$(dirname "$OUT")"

# Find classpath and classes directories
mapfile -t class_dirs < <(find "$ROOT" -type d \( -path "*/build/classes/java/main" -o -path "*/build/classes/java/test" -o -path "*/out/production/*" \) 2>/dev/null)

if [[ ${#class_dirs[@]} -eq 0 ]]; then
  echo "{}" > "$OUT"
  echo "No class dirs found; output empty jdeps graph to $OUT"
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
fi

PY=python3; command -v $PY >/dev/null 2>&1 || PY=python
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

exit 0
