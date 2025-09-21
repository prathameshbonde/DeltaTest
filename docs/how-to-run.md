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
- **LLM_MODE**: 
  - `mock` (default): deterministic graph-based selection only
  - `hybrid`: combination of deterministic and LLM selection (union of results)
  - `remote`/`openai`/`openai-compatible`: OpenAI-compatible APIs only
  - `gemini`/`google`: Google Gemini APIs only
- **HYBRID_LLM_BACKEND**: For hybrid mode, specifies which LLM to combine with deterministic selection:
  - `mock` (default): uses MockLLM for testing
  - `openai`/`openai-compatible`: uses OpenAI-compatible API
  - `gemini`/`google`: uses Google Gemini API
- **LLM_API_KEY**: API key for external LLM providers
- **LLM_ENDPOINT**: Custom endpoint for OpenAI-compatible APIs
- **LLM_MODEL**: Model name (e.g., gpt-4o-mini)
- **GEMINI_API_KEY**: Google Gemini API key
- **GEMINI_MODEL**: Gemini model name (default: gemini-1.5-pro)
- **CONFIDENCE_THRESHOLD**: 0.6 (default)
- **EXTRA_GRADLE_ARGS**: "--info" or other Gradle options

## Hybrid Mode

The new `hybrid` mode combines the reliability of deterministic graph-based analysis with the contextual understanding of LLM providers. When enabled:

1. **Deterministic Selector**: Analyzes call graphs and dependencies to find tests that transitively call changed methods
2. **LLM Selector**: Uses the configured LLM backend to identify additional tests based on semantic understanding
3. **Union**: Returns the combined set of tests from both approaches, providing better coverage

Example hybrid mode configuration:
```bash
export LLM_MODE=hybrid
export HYBRID_LLM_BACKEND=mock  # or openai, gemini
# If using real LLM backends, also set their respective API keys
export LLM_API_KEY=your_api_key_here
```

The hybrid approach typically provides higher confidence scores when both selectors agree on tests, and comprehensive coverage when they complement each other.

CI examples are in the README.md and Jenkinsfile.
