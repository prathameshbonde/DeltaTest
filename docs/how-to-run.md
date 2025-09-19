# How to Run

Prereqs: JDK 17+, Python 3.10+, Gradle, and bash (Git Bash on Windows works).

## Start the service (mock mode)

```bash
pip install -r selector-service/requirements.txt
# Option A (from repo root):
python -m uvicorn app.main:app --app-dir selector-service --host 0.0.0.0 --port 8000
# Option B (cd into service):
cd selector-service && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Build example monorepo

```bash
./gradlew build
```

## Run selector (dry-run)

Recommended simple dry-run (auto-detects base/head):

```bash
bash tools/run_selector.sh --project-root . --dry-run
```

Notes:
- If `origin/main` is missing, the scripts fall back to the empty tree so first-commit diffs work.
- On Windows, if `python` isn't on PATH, either activate your virtualenv (so `python.exe` is available) or install Python 3; the scripts also try `py -3`.

## Run selector (execute tests)

```bash
bash tools/run_selector.sh --project-root .
```

Environment variables:
- SELECTOR_URL=http://localhost:8000/select-tests
- LLM_MODE=mock|remote
- LLM_API_KEY=... (for remote adapter)
- CONFIDENCE_THRESHOLD=0.6
- EXTRA_GRADLE_ARGS="--info"

Docker usage and CI examples are in README.md and Jenkinsfile.
