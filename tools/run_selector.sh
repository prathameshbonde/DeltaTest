#!/usr/bin/env bash
set -euo pipefail

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

export BASE_REF
export HEAD_REF

bash tools/compute_changed_files.sh "$BASE_REF" "$HEAD_REF" tools/output/changed_files.json
bash tools/run_jdeps.sh "$PROJECT_ROOT" tools/output/jdeps_graph.json || true
bash tools/run_soot.sh "$PROJECT_ROOT" tools/output/call_graph.json || true

# Build test mapping using the helper Gradle module (in example-monorepo this is included)
if [ -f "gradlew" ]; then
  ./gradlew :tools:map_tests_to_code:build :tools:map_tests_to_code:mapTestsToCode --no-daemon || true
else
  gradle :tools:map_tests_to_code:build :tools:map_tests_to_code:mapTestsToCode --no-daemon || true
fi

# Assemble input JSON
PY=python3; command -v $PY >/dev/null 2>&1 || PY=python
$PY - << 'PY'
import json, os
out = {
  "repo": {
    "name": os.path.basename(os.getcwd()),
    "base_commit": os.environ.get('BASE_REF','origin/main'),
    "head_commit": os.environ.get('HEAD_REF','HEAD'),
  },
  "changed_files": json.load(open('tools/output/changed_files.json')) if os.path.exists('tools/output/changed_files.json') else [],
  "jdeps_graph": json.load(open('tools/output/jdeps_graph.json')) if os.path.exists('tools/output/jdeps_graph.json') else {},
  "call_graph": json.load(open('tools/output/call_graph.json')) if os.path.exists('tools/output/call_graph.json') else [],
  "test_mapping": json.load(open('tools/output/test_mapping.json')) if os.path.exists('tools/output/test_mapping.json') else [],
  "settings": {
    "confidence_threshold": float(os.environ.get('CONFIDENCE_THRESHOLD','0.6')),
    "max_tests": 500
  }
}
with open('tools/output/input_for_llm.json','w') as f:
  json.dump(out, f, indent=2)
print('Wrote tools/output/input_for_llm.json')
PY

SELECTOR_URL=${SELECTOR_URL:-http://localhost:8000/select-tests}

# Call FastAPI
PY=python3; command -v $PY >/dev/null 2>&1 || PY=python
$PY - "$SELECTOR_URL" << 'PY'
import json, sys, urllib.request
url = sys.argv[1]
req = urllib.request.Request(url, data=open('tools/output/input_for_llm.json','rb').read(), headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))
open('selector_output.json','w').write(json.dumps(data, indent=2))
print('Wrote selector_output.json')
PY

CONF=$($PY -c "import json;print(json.load(open('selector_output.json'))['confidence'])")
THRESH=${CONFIDENCE_THRESHOLD:-0.6}

if python3 - <<PY
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

# Build Gradle --tests arguments
python3 - << 'PY'
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

ARGS=$(cat tools/output/gradle_args.txt || true)
if [[ -z "${ARGS:-}" ]]; then
  echo "No tests selected; exiting successfully."
  exit 0
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "Dry-run: would run gradle test $ARGS ${EXTRA_GRADLE_ARGS:-}"
  exit 0
fi

if [ -f "gradlew" ]; then
  ./gradlew test $ARGS ${EXTRA_GRADLE_ARGS:-} --no-daemon
else
  gradle test $ARGS ${EXTRA_GRADLE_ARGS:-} --no-daemon
fi
