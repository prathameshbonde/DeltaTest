# Design Overview

This project computes a minimal set of tests to run for a PR by combining:
- Changed files and hunks via git diff
- Class-level dependencies via jdeps
- Function-level call graph via a javap-based fallback (Soot can be integrated later)
- Mapping from test methods to code under test via heuristics and bytecode/source scan

It then builds a JSON payload consumed by a FastAPI service that can use either:
- Mock LLM (deterministic rule-based, default)
- External LLM provider (adapter placeholder; requires API key)

The service returns selected tests and explanations with a confidence score; the CI runs only those tests.

## Components

- tools/compute_changed_files.sh: produces changed_files.json
- tools/run_jdeps.sh: produces jdeps_graph.json
- tools/run_soot.sh: produces call_graph.json using javap -c fallback
- tools/map_tests_to_code/: produces test_mapping.json
- tools/run_selector.sh: orchestrates, calls selector-service, runs gradle tests
- selector-service/: FastAPI app with schemas, selector logic, model adapters
- example-monorepo/: A Gradle monorepo with two services and JUnit tests

## Selection Algorithm (Fallback)
1. Parse changed files and line hunks.
2. Use call graph and jdeps to find reachable methods/classes affected.
3. Match test mapping entries whose covered methods/classes intersect the reachable set.
4. Score confidence based on:
   - Graph distance from changed methods to covered methods
   - Number of changed lines (smaller changes -> higher confidence)
   - Mapping density (fraction of covered methods resolved)
5. Explanations summarize the edges and changed files that triggered each test.

## Why javap vs Soot?
Soot is powerful but heavy for a small example. We provide a javap bytecode inspection fallback that identifies method invocation targets, good enough for demos. The interface allows plugging Soot later.

## Security
- The FastAPI server validates inputs using Pydantic and does not execute arbitrary code.
- External LLM calls require explicit environment configuration; none by default.

## Extensibility
- The tools output JSON with stable schemas; teams can swap implementations while preserving interfaces.
- The selector-service can be replaced or extended; contract is defined in docs/api.md.
