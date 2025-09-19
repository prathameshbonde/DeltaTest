# Tools

- compute_changed_files.sh: Outputs JSON changed files and hunks
- run_jdeps.sh: Emits class-level dependency graph using jdeps
- run_soot.sh: Emits naive call graph using javap bytecode inspection
- map_tests_to_code: Gradle module with TestMapper Java tool to map tests to covered methods
- run_selector.sh: Orchestrator to build payload, call FastAPI, run Gradle tests
