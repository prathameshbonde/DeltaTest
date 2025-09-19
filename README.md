# Selective Test PR Pipeline for Java Gradle Monorepos

This repository provides an end-to-end, runnable example of a selective-test pipeline for large Java Gradle monorepos, powered by a small FastAPI service that can use a mock rule-based LLM or an external LLM provider (adapter placeholder).

Highlights:
- Compute a minimal set of tests to run for a PR based on git diff, class dependencies (jdeps), and a function-level call graph (javap-based fallback), plus a static mapping from tests to code under test.
- Mock LLM selection logic that is deterministic and explainable by default (no internet required).
- CI pipelines for GitHub Actions and Jenkins to run only selected tests and fail if the confidence is below a configurable threshold.
- Example Gradle monorepo with two modules to demonstrate the pipeline.

Quick links:
- docs/how-to-run.md — local and CI run instructions
- docs/design.md — architecture and trade-offs
- docs/api.md — FastAPI endpoint schema

## Quickstart (Local, Mock Mode)

Prerequisites:
- Git Bash or WSL (for the bash scripts) on Windows, or any Linux/macOS shell
- JDK 17+ (provides `jdeps` and `javap`)
- Python 3.10+
- Gradle installed (or use Docker-based commands in docs/how-to-run.md)

1) Start the selector service (mock LLM by default):

```bash
pip install -r selector-service/requirements.txt
# Option A (from repo root):
python -m uvicorn app.main:app --app-dir selector-service --host 0.0.0.0 --port 8000
# Option B (cd into service):
cd selector-service && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2) Build the example monorepo:

```bash
./gradlew build
```

3) Run the selector orchestrator (dry-run prints the Gradle command only):

```bash
bash tools/run_selector.sh --project-root . --base origin/main --head HEAD --dry-run
```

To actually run selected tests, omit `--dry-run`.

Environment variables:
- SELECTOR_URL: FastAPI endpoint (default http://localhost:8000/select-tests)
- LLM_MODE: mock or remote (default mock)
- CONFIDENCE_THRESHOLD: 0.6 by default
- EXTRA_GRADLE_ARGS: appended to Gradle test invocation

## Example CI
- GitHub Actions: `.github/workflows/pr-selective-tests.yml`
- Jenkins: `Jenkinsfile`

## License
MIT — see LICENSE