#!/usr/bin/env bash
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

declare -A TASK_TO_TESTS
total_tests=0

# Parse ARGS_FILE supporting two formats per line:
# 1) "--tests Class.method" (uses default GRADLE_TASK)
# 2) ":module:task --tests Class.method" (explicit task per line)
while IFS= read -r line || [[ -n "$line" ]]; do
  line="$(echo "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  [[ -z "$line" ]] && continue

  # First token determines if it's an explicit task or just --tests
  first_token="${line%% *}"
  if [[ "$first_token" == "--tests" ]]; then
    # Old format: only tests provided; use default GRADLE_TASK
    test_name="${line#--tests }"
    [[ -z "$test_name" || "$test_name" == "--tests" ]] && continue
    task_key="$GRADLE_TASK"
  else
    # New format: <task> --tests <pattern>
    task_key="$first_token"
    if [[ "$line" != *" --tests "* ]]; then
      # Not a tests line; skip
      continue
    fi
    test_name="${line#* --tests }"
    [[ -z "$test_name" ]] && continue
  fi

  current="${TASK_TO_TESTS["$task_key"]-}"
  if [[ -z "$current" ]]; then
    TASK_TO_TESTS["$task_key"]="$test_name"
  else
    TASK_TO_TESTS["$task_key"]+=$'\x1f'"$test_name"
  fi
  total_tests=$((total_tests+1))
done < "$ARGS_FILE"

if [[ "$total_tests" -eq 0 ]]; then
  echo "[selector] No test entries found in $ARGS_FILE."
  if [[ "${FALLBACK_FULL_SUITE:-0}" == "1" ]]; then
    echo "[selector] Fallback enabled -> running full test suite."
    exec "$GRADLE_CMD" "$GRADLE_TASK" ${GRADLE_FLAGS:-}
  else
    echo "[selector] Nothing to do. Exiting 0."
    exit 0
  fi
fi

echo "[selector] Found $total_tests selected test(s) across ${#TASK_TO_TESTS[@]} task group(s)."
echo "[selector] Default Gradle task (for legacy lines): $GRADLE_TASK"
echo "[selector] Chunk size:  $CHUNK_SIZE"

if [[ -f "./gradlew" ]]; then
  chmod +x ./gradlew || true
fi

failures=0

# Iterate over each task group and run tests in chunks
for task in "${!TASK_TO_TESTS[@]}"; do
  IFS=$'\x1f' read -r -a TESTS <<< "${TASK_TO_TESTS[$task]}"
  total="${#TESTS[@]}"
  echo "[selector] Task '$task' has $total test(s)."

  start=0
  chunk_index=1
  while [[ $start -lt $total ]]; do
    end=$(( start + CHUNK_SIZE ))
    [[ $end -gt $total ]] && end=$total
    echo "[selector] Running chunk $chunk_index for task '$task': tests $((start+1))..$end"

    declare -a GRADLE_ARGS
    for (( i=start; i<end; i++ )); do
      GRADLE_ARGS+=( "--tests" "${TESTS[i]}" )
    done

    # Pretty-print command with single quotes (for logs)
    pretty_cmd="$GRADLE_CMD $task"
    for (( i=0; i<${#GRADLE_ARGS[@]}; i+=2 )); do
      pattern="${GRADLE_ARGS[i+1]}"
      pretty_cmd+=" ${GRADLE_ARGS[i]} '${pattern}'"
    done
    [[ -n "${GRADLE_FLAGS:-}" ]] && pretty_cmd+=" ${GRADLE_FLAGS}"
    echo "[selector] > $pretty_cmd"

    # Safe execution (array preserves literals; $ not expanded)
    if ! "$GRADLE_CMD" "$task" "${GRADLE_ARGS[@]}" ${GRADLE_FLAGS:-}; then
      echo "[selector] Chunk $chunk_index failed for task '$task'."
      failures=$((failures+1))
    fi

    start=$end
    chunk_index=$((chunk_index+1))
  done
done

if [[ $failures -gt 0 ]]; then
  echo "[selector] Completed with $failures failing chunk(s)."
  exit 1
fi

echo "[selector] All selected tests passed."