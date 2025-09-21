#!/usr/bin/env bash
set -euo pipefail

# Orchestrator script for selective test execution pipeline
# This script coordinates change detection, dependency analysis, and test selection
# by calling the appropriate tools and the selector service.

# Logging helpers
LOG_LEVEL=${LOG_LEVEL:-INFO}
_ts() { date +"%Y-%m-%dT%H:%M:%S"; }
_lvl() { echo "$1" | tr '[:lower:]' '[:upper:]'; }
log() { echo "[$(_ts)] [$(_lvl "$1")] $2"; }
debug() { [[ "$LOG_LEVEL" == "DEBUG" ]] && log DEBUG "$1" || true; }
info() { log INFO "$1"; }
warn() { log WARN "$1"; }
error() { log ERROR "$1"; }

# run_selector.sh - Orchestrate change detection, graph building, LLM selection, and gradle test run
# Usage: run_selector.sh --project-root <dir> --base <base> --head <head> [--dry-run]
#
# This script:
# 1. Detects changed files using git diff
# 2. Builds class dependency graph using jdeps
# 3. Builds method call graph using javap
# 4. Assembles JSON payload and calls selector service
# 5. Runs selected tests with Gradle

PROJECT_ROOT="."
BASE_REF="origin/main"
HEAD_REF="HEAD"
DRY_RUN=0

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root) PROJECT_ROOT=$2; shift 2;;
    --base) BASE_REF=$2; shift 2;;
    --head) HEAD_REF=$2; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    *) echo "Unknown arg $1"; exit 2;;
  esac
done

mkdir -p "tools/output"
info "Starting selector orchestration (project_root=$PROJECT_ROOT base=$BASE_REF head=$HEAD_REF dry_run=$DRY_RUN)"

# Export variables for child scripts
export BASE_REF
export HEAD_REF
export PROJECT_ROOT

# Step 1: Analyze changed files and extract Java metadata
info "Computing changed files"
bash "tools/compute_changed_files.sh" "$BASE_REF" "$HEAD_REF" "tools/output/changed_files.json" "$PROJECT_ROOT"

# Step 2: Build class-level dependency graph (best-effort, may fail if no compiled classes)
info "Building jdeps graph (best-effort)"
bash "tools/run_jdeps.sh" "$PROJECT_ROOT" "tools/output/jdeps_graph.json" || true

# Step 3: Build method-level call graph (best-effort, may fail if no compiled classes)
info "Building call graph (best-effort)"
bash "tools/run_soot.sh" "$PROJECT_ROOT" "tools/output/call_graph.json" || true

# Resolve Python executable (Windows-friendly)
# Try common Python installation patterns
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
  echo "Python interpreter not found. Skipping service call and test arg generation; dry-run may still print planned args if available." >&2
  PY=""
fi

# Assemble input JSON
debug "Assembling input_for_llm.json"
if [[ -n "$PY" && "$PY" != "py -3" ]]; then
  "$PY" "tools/python_scripts/build_input.py"
elif [[ "$PY" == "py -3" ]]; then
  py -3 "tools/python_scripts/build_input.py"
else
  echo "Skipping input assembly due to missing Python."
fi

SELECTOR_URL=${SELECTOR_URL:-http://localhost:8000/select-tests}
info "Calling selector service: $SELECTOR_URL"

# Call FastAPI
if [[ -n "$PY" && "$PY" != "py -3" ]]; then
  "$PY" "tools/python_scripts/call_service.py" "$SELECTOR_URL"
elif [[ "$PY" == "py -3" ]]; then
  py -3 "tools/python_scripts/call_service.py" "$SELECTOR_URL"
else
  warn "Skipping selector service call due to missing Python; no tests will be selected."
  echo '{"selected_tests":[],"confidence":0.0,"reason":"python-missing"}' > selector_output.json
fi

if [[ -n "$PY" && "$PY" != "py -3" ]]; then
  # Enforce allowed_tests filter to prevent hallucinated selections
  "$PY" "tools/python_scripts/filter_results.py"
elif [[ "$PY" == "py -3" ]]; then
  py -3 "tools/python_scripts/filter_results.py"
fi
 
if [[ -n "$PY" && "$PY" != "py -3" ]]; then
  CONF=$("$PY" -c "import json;print(json.load(open('selector_output.json'))['confidence'])")
elif [[ "$PY" == "py -3" ]]; then
  CONF=$(py -3 -c "import json;print(json.load(open('selector_output.json'))['confidence'])")
else
  CONF=0.0
fi
THRESH=${CONFIDENCE_THRESHOLD:-0.6}
debug "Confidence from selector=$CONF threshold=$THRESH"

if [[ $DRY_RUN -eq 1 ]]; then
  info "Dry-run: skipping confidence threshold check."
elif [[ -n "$PY" && "$PY" != "py -3" ]]; then
  if "$PY" - <<PY
c=$CONF
th=$THRESH
import sys
sys.exit(0 if float(c) >= float(th) else 1)
PY
  then
  info "Confidence $CONF >= threshold $THRESH"
  else
  warn "Confidence $CONF < threshold $THRESH"
    exit 1
  fi
elif [[ "$PY" == "py -3" ]]; then
  if py -3 - <<PY
c=$CONF
th=$THRESH
import sys
sys.exit(0 if float(c) >= float(th) else 1)
PY
  then
    echo "Confidence $CONF >= threshold $THRESH"
  else
    echo "Confidence $CONF < threshold $THRESH"
    exit 1
  fi
else
  echo "Confidence $CONF < threshold $THRESH"
  exit 1
fi

# Build Gradle task-qualified --tests arguments
debug "Building Gradle test args from selector output (module-qualified)"
if [[ -n "$PY" && "$PY" != "py -3" ]]; then
  "$PY" "tools/python_scripts/build_gradle_args.py"
elif [[ "$PY" == "py -3" ]]; then
  py -3 "tools/python_scripts/build_gradle_args.py"
else
  echo "" > "tools/output/gradle_args.txt"
fi

ARGS=$(cat "tools/output/gradle_args.txt" || true)
if [[ -z "${ARGS:-}" ]]; then
  info "No tests selected; exiting successfully."
  exit 0
fi

if [[ $DRY_RUN -eq 1 ]]; then
  info "Dry-run: would run gradle test $ARGS ${EXTRA_GRADLE_ARGS:-}"
  exit 0
fi

