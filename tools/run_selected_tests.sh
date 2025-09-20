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

declare -a TESTS
while IFS= read -r line || [[ -n "$line" ]]; do
  line="$(echo "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  [[ -z "$line" ]] && continue
  if [[ "$line" == --tests* ]]; then
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

if [[ -f "./gradlew" ]]; then
  chmod +x ./gradlew || true
fi

total="${#TESTS[@]}"
start=0
chunk_index=1
failures=0

while [[ $start -lt $total ]]; do
  end=$(( start + CHUNK_SIZE ))
  [[ $end -gt $total ]] && end=$total
  echo "[selector] Running chunk $chunk_index: tests $((start+1))..$end"

  declare -a GRADLE_ARGS
  for (( i=start; i<end; i++ )); do
    GRADLE_ARGS+=( "--tests" "${TESTS[i]}" )
  done

  # Pretty-print command with single quotes (for logs)
  pretty_cmd="$GRADLE_CMD $GRADLE_TASK"
  for (( i=0; i<${#GRADLE_ARGS[@]}; i+=2 )); do
    # GRADLE_ARGS[i] is --tests; GRADLE_ARGS[i+1] is the pattern
    pattern="${GRADLE_ARGS[i+1]}"
    pretty_cmd+=" ${GRADLE_ARGS[i]} '${pattern}'"
  done
  [[ -n "${GRADLE_FLAGS:-}" ]] && pretty_cmd+=" ${GRADLE_FLAGS}"
  echo "[selector] > $pretty_cmd"

  # Safe execution (array preserves literals; $ not expanded)
  if ! "$GRADLE_CMD" "$GRADLE_TASK" "${GRADLE_ARGS[@]}" ${GRADLE_FLAGS:-}; then
    echo "[selector] Chunk $chunk_index failed."
    failures=$((failures+1))
  fi

  # If you truly need to force single quotes to reach Gradle (normally unnecessary),
  # uncomment below (less safe due to eval):
  # eval "$pretty_cmd"

  start=$end
  chunk_index=$((chunk_index+1))
done

if [[ $failures -gt 0 ]]; then
  echo "[selector] Completed with $failures failing chunk(s)."
  exit 1
fi

echo "[selector] All selected tests passed."