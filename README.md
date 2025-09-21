# Selective Test PR Pipeline for Java Gradle Monorepos

This repository provides an end-to-end framework for implementing selective test execution in large Java Gradle monorepos, powered by a FastAPI service that supports multiple LLM providers or deterministic mock logic.

Highlights:
- Compute a minimal set of tests to run for a PR based on git diff, class dependencies (jdeps), and a function-level call graph (javap-based fallback).
- Mock LLM selection logic that is deterministic and explainable by default (no internet required).
- Support for external LLM providers including OpenAI-compatible APIs and Google Gemini.
- CI pipelines for GitHub Actions and Jenkins to run only selected tests and fail if the confidence is below a configurable threshold.
- Comprehensive tooling for change detection, dependency analysis, and test selection orchestration.

Quick links:
- docs/how-to-run.md — local and CI run instructions
- docs/design.md — architecture and trade-offs
- docs/api.md — FastAPI endpoint schema

## Quickstart (Local, Mock Mode)

Prerequisites:
- Git Bash or WSL (for the bash scripts) on Windows, or any Linux/macOS shell
- JDK 17+ (provides `jdeps` and `javap`)
- Python 3.10+

1) Start the selector service (mock LLM by default):

```bash
pip install -r selector-service/requirements.txt
# Option A (from repo root):
python -m uvicorn app.main:app --app-dir selector-service --host 0.0.0.0 --port 8000
# Option B (cd into service):
cd selector-service && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2) Prepare your Java Gradle project (ensure it has been built at least once):

```bash
# In your target Gradle project directory
./gradlew build
```

3) Run the selector orchestrator (dry-run prints the Gradle command only):

```bash
bash tools/run_selector.sh --project-root /path/to/your/gradle/project --base origin/main --head HEAD --dry-run
```

To actually run selected tests, omit `--dry-run`.

Environment variables:
- SELECTOR_URL: FastAPI endpoint (default http://localhost:8000/select-tests)
- LLM_MODE: mock, remote/openai/openai-compatible, or gemini/google (default mock)
- CONFIDENCE_THRESHOLD: 0.6 by default
- EXTRA_GRADLE_ARGS: appended to Gradle test invocation

**LLM Provider Configuration:**
- For OpenAI-compatible APIs: Set `LLM_API_KEY` and optionally `LLM_ENDPOINT`, `LLM_MODEL`
- For Google Gemini: Set `GEMINI_API_KEY` and optionally `GEMINI_MODEL`

## Example CI
- GitHub Actions: `.github/workflows/pr-selective-tests.yml` (if available)
- Jenkins: `Jenkinsfile`

## License
MIT — see LICENSE