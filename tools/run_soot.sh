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
OUT=${2:-"tools/output/call_graph.json"}
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
  "$JAVAP" -classpath "$class_root" -c -private "$fqcn" 2>/dev/null | awk -v caller_class="$fqcn" '
    BEGIN { 
      cur_method=""; 
      in_code=0;
    }
    # Capture method headers to know which method body we are in
    # Enhanced pattern to handle nested test classes and various method signatures
    # Pattern 1: Methods with explicit access modifiers
    /^[ \t]*(public|private|protected|static|final|synchronized|native|abstract).*\(.*\)/ && (/;$/ || /\{$/ || / throws /) {
      line=$0
      # Extract method name - handle various patterns including test methods
      # First try: standard method pattern
      if (match(line, /([A-Za-z0-9_$<>]+)\s*\(/, m)) {
        candidate=m[1]
        # Skip keywords that might be captured
        if (candidate !~ /^(public|private|protected|static|final|synchronized|native|abstract|void|int|long|short|byte|char|float|double|boolean|String|Object|class|interface|enum)$/) {
          cur_method=candidate
          if (cur_method=="<init>" || cur_method=="<clinit>") cur_method=""
        }
      }
      # Second try: for test methods and complex signatures
      if (cur_method == "" && match(line, /\s([a-zA-Z_][a-zA-Z0-9_$]*)\s*\(/, m)) {
        candidate=m[1]
        if (candidate !~ /^(public|private|protected|static|final|synchronized|native|abstract|void|int|long|short|byte|char|float|double|boolean|String|Object|class|interface|enum)$/) {
          cur_method=candidate
        }
      }
      next
    }
    # Pattern 2: Methods without explicit access modifiers (package-private, common in nested test classes)
    /^[ \t]+(void|int|long|short|byte|char|float|double|boolean|String|[A-Z][a-zA-Z0-9_$]*)\s+[a-zA-Z_][a-zA-Z0-9_$]*\s*\(.*\)/ && (/;$/ || /\{$/ || / throws /) {
      line=$0
      # Extract method name for package-private methods
      if (match(line, /^[ \t]+(void|int|long|short|byte|char|float|double|boolean|String|[A-Z][a-zA-Z0-9_$]*)\s+([a-zA-Z_][a-zA-Z0-9_$]*)\s*\(/, m)) {
        cur_method=m[2]
        if (cur_method=="<init>" || cur_method=="<clinit>") cur_method=""
      }
      next
    }
    # Pattern 3: Lambda synthetic methods (e.g., lambda$testMethod$0, lambda$testMethod$1)
    /lambda\$[a-zA-Z_][a-zA-Z0-9_$]*\$[0-9]+/ {
      line=$0
      # Extract the original method name from lambda synthetic method
      if (match(line, /lambda\$([a-zA-Z_][a-zA-Z0-9_$]*)\$[0-9]+/, m)) {
        # Map lambda back to the original test method - use the ORIGINAL method name
        cur_method=m[1]  # Use the original test method name directly
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
          # Clean method name more carefully to preserve test method names
          gsub("[():;VZBCSIJFD\\[\\]]", "", method)
          # Also remove any remaining type descriptors but preserve method names
          gsub(/^L.*\//, "", method)
          
          if (method != "<init>" && method != "<clinit>" && method != "") {
            cm = (cur_method=="" ? "?" : cur_method)
            
            # If this is a lambda method call, attribute it to the original method
            if (match(cm, /^lambda_(.*)$/, lambda_match)) {
              cm = lambda_match[1]  # Use the original method name
            }
            
            # For nested classes, ensure we preserve the full class name with $
            caller_display = caller_class
            target_display = tgt
            print caller_display"#"cm" -> "target_display"#"method
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
  py -3 "tools/python_scripts/process_call_graph.py" "$TMP" "$OUT"
else
  "$PY" "tools/python_scripts/process_call_graph.py" "$TMP" "$OUT"
fi

exit 0
