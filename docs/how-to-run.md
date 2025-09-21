# How to Run

Prerequisites: JDK 17+, Python 3.10+, and bash (Git Bash on Windows works).

## Start the service (mock mode)

```bash
pip install -r selector-service/requirements.txt
# Option A (from repo root):
python -m uvicorn app.main:app --app-dir selector-service --host 0.0.0.0 --port 8000
# Option B (cd into service):
cd selector-service && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Prepare your target Gradle project

The tools work with any Gradle project that has been built at least once:

```bash
# In your target project directory
./gradlew build
```

Note: The tools require compiled classes for dependency analysis via jdeps and call graph extraction.

## Run selector (dry-run)

Recommended simple dry-run (auto-detects base/head):

```bash
bash tools/run_selector.sh --project-root /path/to/your/gradle/project --dry-run
```

Explicit commit references:

```bash
bash tools/run_selector.sh --project-root /path/to/your/gradle/project --base origin/main --head HEAD --dry-run
```

Notes:
- If `origin/main` is missing, the scripts fall back to the empty tree so first-commit diffs work.
- On Windows, if `python` isn't on PATH, either activate your virtualenv (so `python.exe` is available) or install Python 3; the scripts also try `py -3`.

## Run selector (execute tests)

```bash
bash tools/run_selector.sh --project-root /path/to/your/gradle/project
```

Environment variables:
- **SELECTOR_URL**: http://localhost:8000/select-tests (default)
- **LLM_MODE**: mock (default), remote/openai/openai-compatible, or gemini/google
- **LLM_API_KEY**: API key for external LLM providers
- **LLM_ENDPOINT**: Custom endpoint for OpenAI-compatible APIs
- **LLM_MODEL**: Model name (e.g., gpt-4o-mini)
- **GEMINI_API_KEY**: Google Gemini API key
- **GEMINI_MODEL**: Gemini model name (default: gemini-1.5-pro)
- **CONFIDENCE_THRESHOLD**: 0.6 (default)
- **EXTRA_GRADLE_ARGS**: "--info" or other Gradle options

CI examples are in the README.md and Jenkinsfile.
