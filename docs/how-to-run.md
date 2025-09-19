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

```bash
bash tools/run_selector.sh --project-root . --base origin/main --head HEAD --dry-run
```

## Run selector (execute tests)

```bash
bash tools/run_selector.sh --project-root . --base origin/main --head HEAD
```

Environment variables:
- SELECTOR_URL=http://localhost:8000/select-tests
- LLM_MODE=mock|remote
- LLM_API_KEY=... (for remote adapter)
- CONFIDENCE_THRESHOLD=0.6
- EXTRA_GRADLE_ARGS="--info"

Docker usage and CI examples are in README.md and Jenkinsfile.
