#!/usr/bin/env bash
set -euo pipefail

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

PROJECT_ROOT="."
BASE_REF="origin/main"
HEAD_REF="HEAD"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root) PROJECT_ROOT=$2; shift 2;;
    --base) BASE_REF=$2; shift 2;;
    --head) HEAD_REF=$2; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    *) echo "Unknown arg $1"; exit 2;;
  esac
done

mkdir -p tools/output
info "Starting selector orchestration (project_root=$PROJECT_ROOT base=$BASE_REF head=$HEAD_REF dry_run=$DRY_RUN)"

export BASE_REF
export HEAD_REF
export PROJECT_ROOT

info "Computing changed files"
bash tools/compute_changed_files.sh "$BASE_REF" "$HEAD_REF" tools/output/changed_files.json "$PROJECT_ROOT"
info "Building jdeps graph (best-effort)"
bash tools/run_jdeps.sh "$PROJECT_ROOT" tools/output/jdeps_graph.json || true
info "Building call graph (best-effort)"
bash tools/run_soot.sh "$PROJECT_ROOT" tools/output/call_graph.json || true

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
  echo "Python interpreter not found. Skipping service call and test arg generation; dry-run may still print planned args if available." >&2
  PY=""
fi

# Assemble input JSON
debug "Assembling input_for_llm.json"
if [[ -n "$PY" && "$PY" != "py -3" ]]; then
  $PY - << 'PY'
import json, os, re
from pathlib import Path

def build_allowed_tests(root: str):
  tests = []
  root_path = Path(root or '.')
  for p in root_path.rglob('src/test/java/**/*.java'):
    try:
      text = p.read_text(encoding='utf-8', errors='ignore')
    except Exception:
      continue
    pkg = None
    m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', text, re.MULTILINE)
    if m:
      pkg = m.group(1)
    lines = text.splitlines()
    brace = 0
    pending_class = None
    class_stack = []
    class_brace_levels = []
    pending_test_annot = False
    # Patterns
    class_re = re.compile(r'^\s*(?:@[\w.$]+(?:\([^)]*\))?\s*)*(?:public|protected|private)?\s*(?:static\s+)?class\s+([A-Za-z_][\w$]*)\b')
    method_header = re.compile(r'^\s*(?:@[\w.$]+(?:\([^)]*\))?\s*)*(?:public|protected|private)?\s*(?:static\s+)?[\w\[\].<>]+\s+([A-Za-z_][\w$]*)\s*\([^)]*\)')
    for line in lines:
      # track annotations
      if '@Test' in line or '@org.junit.Test' in line or '@ParameterizedTest' in line or '@RepeatedTest' in line:
        pending_test_annot = True
      cm = class_re.match(line)
      if cm:
        pending_class = cm.group(1)
        # class body may open on same line
        if '{' in line:
          brace += line.count('{') - line.count('}')
          class_stack.append(pending_class)
          class_brace_levels.append(brace)
          pending_class = None
          continue
      # method detection
      mm = method_header.match(line)
      if mm and class_stack:
        name = mm.group(1)
        is_junit4 = name.startswith('test')
        if pending_test_annot or is_junit4:
          cls = '$'.join(class_stack)
          fqc = (pkg + '.' if pkg else '') + cls
          tests.append(f"{fqc}#{name}")
        pending_test_annot = False
      # brace tracking and class pushes/pops
      if pending_class and '{' in line:
        # handled above, but keep for robustness
        pass
      if '{' in line or '}' in line:
        opens = line.count('{')
        closes = line.count('}')
        # If we saw a class header earlier and encounter first '{', push class
        if pending_class and opens > 0:
          brace += opens
          class_stack.append(pending_class)
          class_brace_levels.append(brace)
          pending_class = None
          # consume remaining braces for this line
          if closes:
            brace -= closes
        else:
          brace += opens
          brace -= closes
        # Pop classes whose scope ended
        while class_brace_levels and brace < class_brace_levels[-1]:
          class_brace_levels.pop()
          class_stack.pop()
    # end for lines
  return sorted(set(tests))

allowed = build_allowed_tests(os.environ.get('PROJECT_ROOT') or '.')
out = {
  "repo": {
    "name": os.path.basename(os.getcwd()),
    "base_commit": os.environ.get('BASE_REF','origin/main'),
    "head_commit": os.environ.get('HEAD_REF','HEAD'),
  },
  "changed_files": json.load(open('tools/output/changed_files.json')) if os.path.exists('tools/output/changed_files.json') else [],
  "jdeps_graph": json.load(open('tools/output/jdeps_graph.json')) if os.path.exists('tools/output/jdeps_graph.json') else {},
  "call_graph": json.load(open('tools/output/call_graph.json')) if os.path.exists('tools/output/call_graph.json') else [],
  "allowed_tests": allowed,
  "settings": {
    "confidence_threshold": float(os.environ.get('CONFIDENCE_THRESHOLD','0.6')),
    "max_tests": 500
  }
}
with open('tools/output/input_for_llm.json','w') as f:
  json.dump(out, f, indent=2)
print('Wrote tools/output/input_for_llm.json')
PY
elif [[ "$PY" == "py -3" ]]; then
  py -3 - << 'PY'
import json, os, re
from pathlib import Path

def build_allowed_tests(root: str):
  tests = []
  root_path = Path(root or '.')
  for p in root_path.rglob('src/test/java/**/*.java'):
    try:
      text = p.read_text(encoding='utf-8', errors='ignore')
    except Exception:
      continue
    pkg = None
    m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', text, re.MULTILINE)
    if m:
      pkg = m.group(1)
    lines = text.splitlines()
    brace = 0
    pending_class = None
    class_stack = []
    class_brace_levels = []
    pending_test_annot = False
    class_re = re.compile(r'^\s*(?:@[\w.$]+(?:\([^)]*\))?\s*)*(?:public|protected|private)?\s*(?:static\s+)?class\s+([A-Za-z_][\w$]*)\b')
    method_header = re.compile(r'^\s*(?:@[\w.$]+(?:\([^)]*\))?\s*)*(?:public|protected|private)?\s*(?:static\s+)?[\w\[\].<>]+\s+([A-Za-z_][\w$]*)\s*\([^)]*\)')
    for line in lines:
      if '@Test' in line or '@org.junit.Test' in line or '@ParameterizedTest' in line or '@RepeatedTest' in line:
        pending_test_annot = True
      cm = class_re.match(line)
      if cm:
        pending_class = cm.group(1)
        if '{' in line:
          brace += line.count('{') - line.count('}')
          class_stack.append(pending_class)
          class_brace_levels.append(brace)
          pending_class = None
          continue
      mm = method_header.match(line)
      if mm and class_stack:
        name = mm.group(1)
        is_junit4 = name.startswith('test')
        if pending_test_annot or is_junit4:
          cls = '$'.join(class_stack)
          fqc = (pkg + '.' if pkg else '') + cls
          tests.append(f"{fqc}#{name}")
        pending_test_annot = False
      if pending_class and '{' in line:
        pass
      if '{' in line or '}' in line:
        opens = line.count('{')
        closes = line.count('}')
        if pending_class and opens > 0:
          brace += opens
          class_stack.append(pending_class)
          class_brace_levels.append(brace)
          pending_class = None
          if closes:
            brace -= closes
        else:
          brace += opens
          brace -= closes
        while class_brace_levels and brace < class_brace_levels[-1]:
          class_brace_levels.pop()
          class_stack.pop()
  return sorted(set(tests))

allowed = build_allowed_tests(os.environ.get('PROJECT_ROOT') or '.')
out = {
  "repo": {
    "name": os.path.basename(os.getcwd()),
    "base_commit": os.environ.get('BASE_REF','origin/main'),
    "head_commit": os.environ.get('HEAD_REF','HEAD'),
  },
  "changed_files": json.load(open('tools/output/changed_files.json')) if os.path.exists('tools/output/changed_files.json') else [],
  "jdeps_graph": json.load(open('tools/output/jdeps_graph.json')) if os.path.exists('tools/output/jdeps_graph.json') else {},
  "call_graph": json.load(open('tools/output/call_graph.json')) if os.path.exists('tools/output/call_graph.json') else [],
  "allowed_tests": allowed,
  "settings": {
    "confidence_threshold": float(os.environ.get('CONFIDENCE_THRESHOLD','0.6')),
    "max_tests": 500
  }
}
with open('tools/output/input_for_llm.json','w') as f:
  json.dump(out, f, indent=2)
print('Wrote tools/output/input_for_llm.json')
PY
else
  echo "Skipping input assembly due to missing Python."
fi

SELECTOR_URL=${SELECTOR_URL:-http://localhost:8000/select-tests}
info "Calling selector service: $SELECTOR_URL"

# Call FastAPI
if [[ -n "$PY" && "$PY" != "py -3" ]]; then
  $PY - "$SELECTOR_URL" << 'PY'
import json, sys, urllib.request
url = sys.argv[1]
try:
    req = urllib.request.Request(url, data=open('tools/output/input_for_llm.json','rb').read(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    open('selector_output.json','w').write(json.dumps(data, indent=2))
    print('Wrote selector_output.json')
except Exception as e:
    # Fallback to empty selection
    fallback = {"selected_tests": [], "confidence": 0.0, "reason": f"service_error:{e.__class__.__name__}"}
    open('selector_output.json','w').write(json.dumps(fallback, indent=2))
    print('Selector service unavailable; wrote empty selection to selector_output.json', file=sys.stderr)
PY
elif [[ "$PY" == "py -3" ]]; then
  py -3 - "$SELECTOR_URL" << 'PY'
import json, sys, urllib.request
url = sys.argv[1]
try:
    req = urllib.request.Request(url, data=open('tools/output/input_for_llm.json','rb').read(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    open('selector_output.json','w').write(json.dumps(data, indent=2))
    print('Wrote selector_output.json')
except Exception as e:
    fallback = {"selected_tests": [], "confidence": 0.0, "reason": f"service_error:{e.__class__.__name__}"}
    open('selector_output.json','w').write(json.dumps(fallback, indent=2))
    print('Selector service unavailable; wrote empty selection to selector_output.json', file=sys.stderr)
PY
else
  warn "Skipping selector service call due to missing Python; no tests will be selected."
  echo '{"selected_tests":[],"confidence":0.0,"reason":"python-missing"}' > selector_output.json
fi

if [[ -n "$PY" && "$PY" != "py -3" ]]; then
  # Enforce allowed_tests filter to prevent hallucinated selections
  $PY - << 'PY'
import json
inp = json.load(open('tools/output/input_for_llm.json'))
allowed = set(inp.get('allowed_tests') or [])
sel = json.load(open('selector_output.json'))
selected = [t for t in sel.get('selected_tests', []) if (not allowed) or (t in allowed)]
ex = {k:v for k,v in (sel.get('explanations') or {}).items() if k in selected}
sel['selected_tests'] = selected
sel['explanations'] = ex
open('selector_output.json','w').write(json.dumps(sel, indent=2))
print('Filtered selector_output.json against allowed_tests')
PY
elif [[ "$PY" == "py -3" ]]; then
  py -3 - << 'PY'
import json
inp = json.load(open('tools/output/input_for_llm.json'))
allowed = set(inp.get('allowed_tests') or [])
sel = json.load(open('selector_output.json'))
selected = [t for t in sel.get('selected_tests', []) if (not allowed) or (t in allowed)]
ex = {k:v for k,v in (sel.get('explanations') or {}).items() if k in selected}
sel['selected_tests'] = selected
sel['explanations'] = ex
open('selector_output.json','w').write(json.dumps(sel, indent=2))
print('Filtered selector_output.json against allowed_tests')
PY
fi
 
if [[ -n "$PY" && "$PY" != "py -3" ]]; then
  CONF=$($PY -c "import json;print(json.load(open('selector_output.json'))['confidence'])")
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
  if $PY - <<PY
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

# Build Gradle --tests arguments
debug "Building Gradle test args from selector output"
if [[ -n "$PY" && "$PY" != "py -3" ]]; then
  $PY - << 'PY'
import json, os
sel = json.load(open('selector_output.json'))
selected = sel.get('selected_tests', [])
args = []
for t in selected:
    cls, meth = t.split('#',1)
    args.append(f"--tests {cls}.{meth}")
open('tools/output/gradle_args.txt','w').write(' '.join(args))
print('Wrote tools/output/gradle_args.txt')
PY
elif [[ "$PY" == "py -3" ]]; then
  py -3 - << 'PY'
import json, os
sel = json.load(open('selector_output.json'))
selected = sel.get('selected_tests', [])
args = []
for t in selected:
    cls, meth = t.split('#',1)
    args.append(f"--tests {cls}.{meth}")
open('tools/output/gradle_args.txt','w').write(' '.join(args))
print('Wrote tools/output/gradle_args.txt')
PY
else
  echo "" > tools/output/gradle_args.txt
fi

ARGS=$(cat tools/output/gradle_args.txt || true)
if [[ -z "${ARGS:-}" ]]; then
  info "No tests selected; exiting successfully."
  exit 0
fi

if [[ $DRY_RUN -eq 1 ]]; then
  info "Dry-run: would run gradle test $ARGS ${EXTRA_GRADLE_ARGS:-}"
  exit 0
fi

if [ -f "gradlew" ]; then
  info "Running Gradle tests via ./gradlew"
  ./gradlew test $ARGS ${EXTRA_GRADLE_ARGS:-} --no-daemon
elif [ -f "gradlew.bat" ]; then
  info "Running Gradle tests via gradlew.bat"
  ./gradlew.bat test $ARGS ${EXTRA_GRADLE_ARGS:-} --no-daemon
else
  info "Running Gradle tests via system Gradle"
  gradle test $ARGS ${EXTRA_GRADLE_ARGS:-} --no-daemon
fi
