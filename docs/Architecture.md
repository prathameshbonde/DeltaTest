# 🏗️ DeltaTest - Solution Architecture

DeltaTest accelerates CI/CD pipelines by running **only the tests impacted by code changes**, using a hybrid of **deterministic dependency analysis** and **LLM reasoning**.

---

## 📐 Architecture Diagram

```mermaid
[CI/CD Pipeline (GitHub Actions)]
                |
         [Run Selector (Shell)]
         /       |         \
  [Change]   [JDIPS]    [Bytecode]
  (git diff) (class-graph) (method graph)
        \       |        /
         \      |       /
     [Selector Service (Python + LLM)]
        /                      \
[Deterministic Traversal]   [LLM Reasoning]
         \                     /
          \                   /
           [Union + Filter (allowed_tests)]
                  |
        [Selective Test Execution (Gradle)]
                  |
         [Artifacts & Dashboard (JSON, HTML)]