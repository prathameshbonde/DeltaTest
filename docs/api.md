# API

## POST /select-tests

Request: JSON payload built by tools/run_selector.sh

```
{
  "repo": {"name":"example-monorepo","base_commit":"origin/main","head_commit":"HEAD"},
  "changed_files": [
    {
      "path":"libs/service-a/src/main/java/com/foo/Bar.java",
      "change_type":"M",
      "hunks":[{"start":10,"end":16}],
      "file_name":"Bar.java",
      "lang":"java",
      "fully_qualified_class":"com.foo.Bar",
      "touched_methods":[{"fqn":"com.foo.Bar#doWork","start_line":11,"end_line":28}]
    }
  ],
  "jdeps_graph": {"com.foo.Bar":["com.foo.Baz"]},
  "call_graph": [
    {"caller":"com.foo.Bar#doWork","callee":"com.foo.Baz#doIt"}
  ],
  "settings": {"confidence_threshold":0.6,"max_tests":500}
}
```

Response:
```
{
  "selected_tests": ["com.foo.BarTest#testDoWork"],
  "explanations": {
    "com.foo.BarTest#testDoWork": "Direct call graph reachability from changed method com.foo.Bar#doWork to this test; changed lines affect method implementation"
  },
  "confidence": 0.87,
  "metadata": {
    "reason_edges": [{"from":"com.foo.Bar#doWork","to":"com.foo.Baz#doIt"}],
    "changed_files": ["libs/service-a/src/main/java/com/foo/Bar.java"]
  }
}
```
