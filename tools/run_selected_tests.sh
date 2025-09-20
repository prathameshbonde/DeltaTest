#!/usr/bin/env bash
#
# Run selectively chosen JUnit tests from tools/output/gradle_args.txt.
# Intended for GitHub Actions (Linux) but works locally (Git Bash/WSL).
#
# Usage:
#   .github/scripts/run_selected_tests.sh [args_file] [gradle_task]
# Env:
#   GRADLE_CMD (default: ./gradlew)
#   CHUNK_SIZE (default: 150)  # number of tests per Gradle invocation
#   FALLBACK_FULL_SUITE=1 to run full test suite if no selected tests
#   GRADLE_FLAGS extra flags (e.g. "--no-daemon --build-cache")
set -euo pipefail

ARGS_FILE="${1:-tools/output/gradle_args.txt}"
GRADLE_TASK="${2:-test}"
GRADLE_CMD="${GRADLE_CMD:-./gradlew}"
CHUNK_SIZE="${CHUNK_SIZE:-150}"

if [[ ! -f "$ARGS_FILE" ]]; then
  echo "[selector] Args file not found: $ARGS_FILE"
  if [[ "${FALLBACK_FULL_SUITE:-0}" == "1" ]]; then
    echo "[selector] Fallback enabled -> running full test suite."
    exec "$GRADLE_CMD" "$GRADLE_TASK" ${GRADLE_FLAGS:-}
  else
    echo "[selector] No tests to run. Exiting 0."
    exit 0
  fi
fi

# Collect tests
declare -a TESTS
while IFS= read -r line || [[ -n "$line" ]]; do
  line="$(echo "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"  # trim
  [[ -z "$line" ]] && continue
  # Accept either "--tests com.Foo#bar" or raw "--tests ..." tokens
  if [[ "$line" == --tests* ]]; then
    # If the line already starts with --tests, split into flag + value
    test_name="${line#--tests }"
    [[ -z "$test_name" || "$test_name" == "--tests" ]] && continue
    TESTS+=("$test_name")
  fi
done < "$ARGS_FILE"

if [[ "${#TESTS[@]}" -eq 0 ]]; then
  echo "[selector] No test entries found in $ARGS_FILE."
  if [[ "${FALLBACK_FULL_SUITE:-0}" == "1" ]]; then
    echo "[selector] Fallback enabled -> running full test suite."
    exec "$GRADLE_CMD" "$GRADLE_TASK" ${GRADLE_FLAGS:-}
  else
    echo "[selector] Nothing to do. Exiting 0."
    exit 0
  fi
fi

echo "[selector] Found ${#TESTS[@]} selected tests."
echo "[selector] Gradle task: $GRADLE_TASK"
echo "[selector] Chunk size:  $CHUNK_SIZE"

# Ensure wrapper is executable (useful in fresh checkouts)
if [[ -f "./gradlew" ]]; then
  chmod +x ./gradlew || true
fi

# Run in chunks to avoid extremely long command lines
total="${#TESTS[@]}"
start=0
chunk_index=1
failures=0

while [[ $start -lt $total ]]; do
  end=$(( start + CHUNK_SIZE ))
  [[ $end -gt $total ]] && end=$total
  echo "[selector] Running chunk $chunk_index: tests $((start+1))..$end"

  # Build args: --tests pattern per test
  declare -a GRADLE_ARGS
  for (( i=start; i<end; i++ )); do
    # Quote patterns exactly; Gradle interprets '.' and '*' as patterns normally
    GRADLE_ARGS+=( "--tests" '${TESTS[i]}' )
  done

  # Execute
  if ! "$GRADLE_CMD" $GRADLE_TASK "${GRADLE_ARGS[@]}" ${GRADLE_FLAGS:-}; then
    echo "[selector] Chunk $chunk_index failed."
    failures=$((failures+1))
  fi
  start=$end
  chunk_index=$((chunk_index+1))
done

if [[ $failures -gt 0 ]]; then
  echo "[selector] Completed with $failures failing chunk(s)."
  exit 1
fi

echo "[selector] All selected tests passed."