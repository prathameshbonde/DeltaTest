# Copilot Instructions for DeltaTest (Selective Tests for Java Gradle Monorepos)

## Big picture
- Goal: Given a PR/diff, compute a minimal-but-sufficient set of JUnit tests to run for a large Gradle monorepo.
- Flow: tools/*.sh build inputs → selector-service (FastAPI) scores/returns tests → Gradle runs only those tests.
- Inputs produced under `tools/output/`:
  - `changed_files.json` from `tools/compute_changed_files.sh` (git diff + line hunks)
  - `jdeps_graph.json` from `tools/run_jdeps.sh` (class-level deps via jdeps)
  - `call_graph.json` from `tools/run_soot.sh` (javap-based fallback call graph)
- Service: `selector-service/app` provides `POST /select-tests` and returns `{ selected_tests[], explanations{}, confidence, metadata }`.

## Key directories
- `selector-service/app/` — FastAPI (`main.py`), schemas (`schemas.py`), selector core (`selector.py`), LLM adapters (`model_adapter.py`).
- `tools/` — Orchestrator `run_selector.sh` and data builders; writes artifacts to `tools/output/` and `selector_output.json`.
- Root Gradle: `build.gradle`, `settings.gradle` (includes composite build of `Java MonoRepo/`).
- Docs: `docs/design.md`, `docs/how-to-run.md`, `docs/api.md`.
- Example monorepo: `Java MonoRepo/` (Spring Boot services). It has its own `.github/copilot-instructions.md` focused on README maintenance for that subproject.

## Contracts & conventions
- API request/response: see `docs/api.md` and Pydantic models in `selector-service/app/schemas.py`.
- Test id format is `FullyQualifiedClass#method` (e.g., `com.foo.BarTest#testDoWork`). Gradle args are built as `--tests Class.method` by `tools/run_selector.sh`.
- File-to-class heuristic in `selector.py` assumes `/src/**/java/.../Class.java → pkg.Class` when computing reachability.
- Confidence threshold: `CONFIDENCE_THRESHOLD` (default 0.6). Orchestrator fails the build if confidence < threshold (skipped in `--dry-run`).
- Outputs: `selector_output.json` (service response), `tools/output/gradle_args.txt` (assembled `--tests` flags).

## Developer workflows (Windows notes included)
- Start service (mock mode by default): see `docs/how-to-run.md`. Typical:
  - Install deps: `pip install -r selector-service/requirements.txt`
  - Run: `python -m uvicorn app.main:app --app-dir selector-service --host 0.0.0.0 --port 8000`
- Build monorepo: `./gradlew.bat build` (or `./gradlew build` on Bash). JUnit Platform is configured in root `build.gradle`.
- Run selector orchestrator (requires Git Bash or WSL for bash scripts):
  - Dry run: `bash tools/run_selector.sh --project-root . --dry-run`
  - Execute:   `bash tools/run_selector.sh --project-root .`
  - Scripts auto-detect Python (`python3|python|py -3`) and handle first-commit diffs and non-git dirs gracefully.
- CI: Jenkins pipeline `Jenkinsfile` installs Python deps, starts the service, builds with Gradle, then runs `tools/run_selector.sh`.

## Integration points
- LLM modes via `LLM_MODE`: `mock` (default), `remote|openai|openai-compatible`, `azure|azure-openai`, `anthropic|claude`, `gemini|google`, `cohere`.
  - See `selector-service/app/model_adapter.py` for env vars per provider (e.g., `LLM_API_KEY`, `LLM_ENDPOINT`, `AZURE_OPENAI_*`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `COHERE_API_KEY`).
  - Adapters expect strict JSON responses; parsing fallbacks attempt to extract a JSON object from text if needed.
- Selector core (`selector.py`) combines `changed_files`, `jdeps_graph`, and `call_graph` to build reachability. In mock mode it may return an empty selection; Gradle step is skipped when no tests are selected.
- To extend selection logic: start in `selector.py` (heuristics) or add a provider in `model_adapter.py`. Keep `selected_tests` format and confidence semantics stable.

## Gotchas & tips
- Ensure the FastAPI service is running before `tools/run_selector.sh`; otherwise confidence defaults low and the threshold step can fail the build.
- `run_jdeps.sh` and `run_soot.sh` need compiled classes; run `gradle/gradlew build` before invoking them directly.
- On Windows, prefer Git Bash for the `tools/*.sh` scripts; PowerShell is fine for Gradle and Python processes.
- Composite build: `settings.gradle` includes `Java MonoRepo/`; building the root project also builds the example services.
- For changes inside `Java MonoRepo/`, follow its own `.github/copilot-instructions.md` for README updates; test selection still flows through this repo’s tools and service.

## Pointers to examples
- Service endpoint handler: `selector-service/app/main.py` → `@app.post("/select-tests")`.
- Test arg assembly: `tools/run_selector.sh` writes `tools/output/gradle_args.txt` from `selector_output.json`.
- Data schemas: `selector-service/app/schemas.py` and examples in `docs/api.md`.
