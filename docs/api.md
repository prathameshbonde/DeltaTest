# API

## POST /select-tests

Request: JSON payload built by tools/run_selector.sh

```json
{
  "repo": {
    "name": "example-monorepo",
    "base_commit": "origin/main",
    "head_commit": "HEAD"
  },
  "changed_files": [
    {
      "path": "libs/service-a/src/main/java/com/foo/Bar.java",
      "change_type": "M",
      "hunks": [{"start": 10, "end": 16}],
      "file_name": "Bar.java",
      "lang": "java",
      "fully_qualified_class": "com.foo.Bar",
      "package": "com.foo",
      "class_name": "Bar",
      "touched_methods": [
        {
          "name": "doWork",
          "signature": "public void doWork()",
          "start_line": 11,
          "end_line": 28,
          "fqn": "com.foo.Bar#doWork"
        }
      ]
    }
  ],
  "jdeps_graph": {
    "com.foo.Bar": ["com.foo.Baz"]
  },
  "call_graph": [
    {
      "caller": "com.foo.Bar#doWork",
      "callee": "com.foo.Baz#doIt"
    }
  ],
  "allowed_tests": [
    "com.foo.BarTest#testDoWork",
    "com.foo.BarTest#testDoWorkWithError"
  ],
  "settings": {
    "confidence_threshold": 0.6,
    "max_tests": 500
  }
}
```

Response:
```json
{
  "selected_tests": ["com.foo.BarTest#testDoWork"],
  "explanations": {
    "com.foo.BarTest#testDoWork": "Direct call graph reachability from changed method com.foo.Bar#doWork to this test; changed lines affect method implementation"
  },
  "confidence": 0.87,
  "metadata": {
    "reason_edges": [
      {
        "from": "com.foo.Bar#doWork",
        "to": "com.foo.Baz#doIt"
      }
    ],
    "changed_files": ["libs/service-a/src/main/java/com/foo/Bar.java"]
  }
}
```

## Field Descriptions

### Request Fields
- **repo**: Repository information including name and commit references
- **changed_files**: Array of files modified in the change set, with enriched metadata for Java files
- **jdeps_graph**: Class-level dependency graph where keys are classes and values are arrays of their dependencies
- **call_graph**: Method-level call relationships with caller/callee pairs in format `Class#method`
- **allowed_tests**: Optional list of available tests in the project (auto-discovered if not provided)
- **settings**: Configuration options including confidence threshold and maximum number of tests to select

### ChangedFile Fields
- **path**: Relative path to the changed file
- **change_type**: Git change type (A=Added, M=Modified, D=Deleted)
- **hunks**: Line ranges that were modified
- **file_name**: Base filename (computed from path)
- **lang**: Programming language (e.g., "java")
- **fully_qualified_class**: Full class name including package (for Java files)
- **package**: Package name (for Java files)
- **class_name**: Simple class name (for Java files)
- **touched_methods**: Methods that were modified within the changed line ranges

### Response Fields
- **selected_tests**: Array of test identifiers in format `FullyQualifiedClass#methodName`
- **explanations**: Human-readable explanations for why each test was selected
- **confidence**: Float between 0.0 and 1.0 indicating selection confidence
- **metadata**: Additional data including reason edges and affected files

## Environment Variables

The service behavior can be configured using these environment variables:

- **LLM_MODE**: Selection mode - `mock` (default), `remote`/`openai`/`openai-compatible`, or `gemini`/`google`
- **LLM_API_KEY**: API key for external LLM providers
- **LLM_ENDPOINT**: Custom endpoint for OpenAI-compatible APIs
- **LLM_MODEL**: Model name (e.g., `gpt-4o-mini`, `gemini-1.5-pro`)
- **GEMINI_API_KEY**: Google Gemini-specific API key
- **GEMINI_MODEL**: Google Gemini model name
- **LOG_LEVEL**: Logging level (DEBUG, INFO, WARN, ERROR)
