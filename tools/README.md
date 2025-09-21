# Tools

This directory contains the orchestration scripts that build the inputs for the selector service:

- **compute_changed_files.sh**: Outputs JSON changed files and hunks, plus optional enrichments:
	- file_name, lang
	- For Java files: fully_qualified_class, package, class_name, touched_methods[] with fqn and line spans
- **run_jdeps.sh**: Emits class-level dependency graph using jdeps
- **run_soot.sh**: Emits method-level call graph using javap bytecode inspection fallback
- **run_selector.sh**: Main orchestrator that builds payload, calls FastAPI service, and runs Gradle tests

## Prerequisites

- JDK 17+ (provides `jdeps` and `javap` tools)
- Python 3.10+ (for payload assembly and JSON processing)
- Git Bash or WSL on Windows (for shell script execution)
- Target Gradle project must be built at least once (for bytecode analysis)

## Usage

The main entry point is `run_selector.sh`:

```bash
# Dry run (shows what would be executed)
bash tools/run_selector.sh --project-root /path/to/gradle/project --dry-run

# Execute selected tests
bash tools/run_selector.sh --project-root /path/to/gradle/project --base origin/main --head HEAD
```

## Output

All tools write their outputs to `tools/output/`:
- `changed_files.json`: Git diff analysis with Java metadata
- `jdeps_graph.json`: Class dependency relationships
- `call_graph.json`: Method call relationships
- `gradle_args.txt`: Generated test execution arguments
- `selector_output.json`: Complete service response
