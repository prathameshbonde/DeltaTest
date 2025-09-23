
# DeltaTest — Architecture & Design

## Overview
DeltaTest is a system for selective test execution in CI/CD pipelines. Instead of running all tests on every push or pull request, it identifies which test cases are impacted by recent code changes (via deterministic analysis and LLM-based reasoning), and runs only those. This reduces build time, improves feedback velocity, and lowers resource use.

---

## Components

| Component | Responsibility |
|-----------|-----------------|
| **Run Selector (Shell Scripts)** | Entry point that orchestrates the flow. Invoked in CI/CD (e.g. GitHub Actions) with inputs like project root, base and head commits. Triggers computation of change files, dependency graphs, and selects tests. |
| **Change File Script** | Generates a `git diff` between base and head, extracts which files and methods have changed, and packages this as `change_file.json`. |
| **JDIPS Analysis** | Static (compile-time) class-level dependency graph: which classes import/use which other classes. Useful to understand broad dependencies. |
| **Bytecode Call Graph (“Run Suit”)** | Analyzes compiled classes (production & test) to get method-to-method or class-to-class invocation relationships. Helps in identifying deeply impacted tests. |
| **Selector Service (Python + LLM Adapter)** | Core decision-making service: takes inputs (changed files/methods, dependency graphs, allowed tests) and uses two modes: deterministic traversal + LLM reasoning, then takes a union (with preference/scoring) to decide which tests to run. |
| **Allowed Test List** | A constraint to avoid hallucination: any test the system might suggest must be part of a known set of test classes/methods. |
| **Artifacts & Dashboard** | Outputs like selected test JSON, logs, HTML dashboard (e.g., `index.html`) so users/teams can inspect what tests were chosen, see confidence levels, metadata, etc. |

---

## Data Flow & Workflow

1. **Trigger**  
   - CI/CD pipeline (GitHub Actions) triggers on push / pull request.  
   - Two workflows:  
     - Full build (runs all tests)  
     - Delta test workflow (selective test execution)

2. **Change Detection**  
   - Run `Change File Script` → compute diff between base & head → identify changed files/methods → output as JSON.

3. **Dependency Analysis**  
   - *Class-level* via JDIPS: identify import relationships.  
   - *Bytecode / Method-call graph* via “Run Suit”: which methods in production/test are invoking which other methods (caller-callee relationships).

4. **Test Selection**  
   - **Deterministic mode**: traverse dependency and call graphs starting from changed methods; find all test classes/methods depending on those.  
   - **LLM mode**: given the structured input (changed files/methods, dependency graphs, allowed tests), use a prompt to an LLM to suggest additional relevant tests. Returns selected tests + explanation + confidence + metadata.  

5. **Union & Filtering**  
   - Combine deterministic and LLM selections.  
   - Use “allowed test” filter to ensure tests suggested are valid.  
   - Mark which tests are deterministically selected vs via LLM (for transparency).

6. **Execution**  
   - Generate build commands (e.g. Gradle commands) to run only the selected test cases.  
   - Run them.

7. **Reporting & Artifacts**  
   - Produce JSON of selected tests.  
   - Generate `index.html` dashboard showing which tests ran, reasons, confidence, etc.  
   - Log build time, compare with full build.

---

## Design Decisions & Rationale

- **Hybrid approach (Deterministic + LLM)**:  
  Deterministic ensures correctness and traceability; LLM adds flexibility / covers cases deterministic misses (e.g. non-obvious dependencies). The union ensures safety + improved coverage.

- **Use of static & bytecode analysis**:  
  Static class-level helps quickly eliminate large unrelated parts of the code; bytecode / call graph gives more precise method-level relationships for fine-grained selection.

- **Allowed test list constraint**:  
  Prevents hallucination (LLM suggesting non-existent test methods / names) → ensures safety in production.

- **Artifacts & dashboards**: Transparency and auditability are critical; users need to see why certain tests were selected, especially when some were via LLM.

- **Integration into existing CI/CD**:  
  The system is designed to plug into GitHub Actions (or similar). The shell & Python scripts + orchestration make it portable to many environments.

---

## Non-Functional Considerations

| Aspect | Description |
|--------|-------------|
| **Performance** | The selective approach aims to cut test execution time by ~50% in observed cases, reducing cycle times and resource usage. |
| **Reliability** | Deterministic path provides guaranteed coverage for tests covering changed code; LLM path is supplemental and filtered. |
| **Maintainability** | Modular design: scripts for diff, dependency graphs, service for selection. Easy to extend (e.g. support for other languages, other CI tools). |
| **Scalability** | Works for monorepos with ~600 tests; structure supports more. Batch jobs, artifact storage, etc. |
| **Security** | Depends on ensuring LLM component is safe/trusted; test selection must not drop important tests. Also need to handle secrets / API keys securely. |

---

## Possible Enhancements / Future Work

- Add support for **multi-language repos** (e.g. Python, JS) with corresponding static & bytecode analysis.  
- Improve LLM prompt engineering and possibly chain-of-thought / context retention to reduce irrelevant suggestions.  
- UI improvements for dashboards (visual graphs, filtering).  
- Metrics tracking over many builds: false positives, false negatives (missed tests), LLM confidence calibration.  
- Caching of dependency graphs across builds when there are no major structural changes.  
- Integration with on-prem / secure environment LLM solutions to handle organizations which cannot use public LLM APIs.

---

## Conclusion

DeltaTest presents a robust, hybrid solution for reducing test execution overhead in CI/CD environments, combining static & dynamic analysis with modern AI components while maintaining safety, traceability, and performance. It’s designed for practical integration, visibility, and extensibility.