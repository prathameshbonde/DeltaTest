#!/usr/bin/env bash
set -euo pipefail

# Logging helpers
LOG_LEVEL=${LOG_LEVEL:-INFO}
_ts() { date +"%Y-%m-%dT%H:%M:%S"; }
_lvl() { echo "$1" | tr '[:lower:]' '[:upper:]'; }
log() { echo "[$(_ts)] [$(_lvl "$1")] $2"; }
info() { log INFO "$1"; }
warn() { log WARN "$1"; }

# run_soot.sh - Build method-level call graph using javap bytecode analysis
# Usage: run_soot.sh <project_root> <output_json>
# 
# This script uses javap to disassemble compiled Java classes and extract
# method invocation patterns. It's a lightweight alternative to full Soot
# analysis that provides sufficient call graph data for test selection.
# 
# Output: JSON array of {caller, callee} method relationships

ROOT=${1:-.}
OUT=${2:-tools/output/call_graph.json}
mkdir -p "$(dirname "$OUT")"

mapfile -t class_files < <(find "$ROOT" -type f \
  \( -path "*/build/classes/java/main/*" \
   -o -path "*/build/classes/java/test/*" \
   -o -path "*/build/classes/kotlin/main/*" \
   -o -path "*/build/classes/kotlin/test/*" \) \
  -name "*.class" 2>/dev/null)
log INFO "Found ${#class_files[@]} class files for javap scan under $ROOT"

if [[ ${#class_files[@]} -eq 0 ]]; then
  log WARN "No .class files found under $ROOT. Did you run Gradle build?"
  echo "[]" > "$OUT"
  log INFO "Wrote empty call graph to $OUT"
  exit 0
fi

TMP=$(mktemp)
if [[ ! -f "$TMP" ]]; then TMP=$(mktemp -t tmp.XXXXXX); fi

# Resolve javap binary (use PATH, then JAVA_HOME)
JAVAP="javap"
if ! command -v "$JAVAP" >/dev/null 2>&1; then
  if [[ -n "${JAVA_HOME:-}" && -x "$JAVA_HOME/bin/javap" ]]; then
    JAVAP="$JAVA_HOME/bin/javap"
  elif [[ -n "${JAVA_HOME:-}" && -x "$JAVA_HOME/bin/javap.exe" ]]; then
    JAVAP="$JAVA_HOME/bin/javap.exe"
  fi
fi

> "$TMP"
if { ! command -v "$JAVAP" >/dev/null 2>&1; } && [[ ! -x "$JAVAP" ]]; then
  echo "javap not found; emitting empty call graph" > "$TMP"
  log WARN "javap not found; writing empty call graph"
else
  for cf in "${class_files[@]}"; do
  # Derive FQCN assuming Gradle class layout (java|kotlin)/(main|test)
  fqcn=$(echo "$cf" | sed -E 's#.*build/classes/(java|kotlin)/(main|test)/##; s#/#.#g; s#\.class$##')
  # Set classpath to the class root (…/build/classes/(java|kotlin)/(main|test))
  class_root=$(echo "$cf" | sed -E 's#(.*build/classes/(java|kotlin)/(main|test))/.*#\1#')
  # Dump bytecode and parse invokes
  "$JAVAP" -classpath "$class_root" -c "$fqcn" 2>/dev/null | awk -v caller_class="$fqcn" '
    BEGIN { cur_method=""; in_code=0 }
    # Capture method headers to know which method body we are in
    /^[ \t]*(public|private|protected|static|final|synchronized|native|abstract)/ && /\(/ && /\);$/ {
      line=$0
      # Extract token immediately before the first '\(' as method name
      if (match(line, /([A-Za-z0-9_$<>]+)\(/, m)) {
        cur_method=m[1]
        if (cur_method=="<init>" || cur_method=="<clinit>") cur_method=""
      }
      next
    }
    # Track entrance into bytecode for the current method
    /^[ \t]*Code:/ { in_code=1; next }
    # Heuristics to leave code section
    (in_code && NF==0) { in_code=0 }
    (in_code && /^[ \t]*}/) { in_code=0 }
    (in_code && /^[ \t]*(public|private|protected|static|final|synchronized|native|abstract)/) { in_code=0 }

    /invoke(static|virtual|interface|special|dynamic)/ {
      # sample: ... invokestatic #2 // Method com/foo/Baz.doIt:()V
      for (i=1;i<=NF;i++) {
        if ($i == "Method" || $i == "InterfaceMethod" || $i == "Dynamic") {
          full=$(i+1)
          gsub("/", ".", full)
          sub(":.*$", "", full)
          # split full (e.g., com.foo.Baz.doIt) into tgt(class) and method (last segment)
          pos=0
          for (j=1; j<=length(full); j++) if (substr(full,j,1)==".") pos=j
          if (pos>0) {
            tgt=substr(full,1,pos-1)
            method=substr(full,pos+1)
          } else {
            next
          }
          gsub("[():;VZBCSIJFD]", "", method)
          if (method != "<init>" && method != "<clinit>") {
            cm = (cur_method=="" ? "?" : cur_method)
            print caller_class"#"cm" -> "tgt"#"method
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
  py -3 tools/python_scripts/process_call_graph.py "$TMP" "$OUT"
else
  $PY tools/python_scripts/process_call_graph.py "$TMP" "$OUT"
fi

exit 0
