# Tools

- compute_changed_files.sh: Outputs JSON changed files and hunks, plus optional enrichments:
	- file_name, lang
	- For Java files: fully_qualified_class, package, class_name, touched_methods[] with fqn and line spans
- run_jdeps.sh: Emits class-level dependency graph using jdeps
- run_soot.sh: Emits naive call graph using javap bytecode inspection
  
- run_selector.sh: Orchestrator to build payload, call FastAPI, run Gradle tests
