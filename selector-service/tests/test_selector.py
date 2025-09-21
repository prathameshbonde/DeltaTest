import json, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.selector import select_tests, CallGraph, extract_touched_methods, find_affected_tests  # type: ignore


def test_call_graph_creation():
    """Test CallGraph class functionality."""
    call_graph_edges = [
        {"caller": "com.foo.TestClass#testMethod", "callee": "com.foo.Service#method1"},
        {"caller": "com.foo.Service#method1", "callee": "com.foo.Utils#helper"},
        {"caller": "com.foo.AnotherTest#testStuff", "callee": "com.foo.Service#method2"},
    ]
    
    graph = CallGraph(call_graph_edges)
    
    # Test forward relationships
    assert "com.foo.Service#method1" in graph.get_callees("com.foo.TestClass#testMethod")
    assert "com.foo.Utils#helper" in graph.get_callees("com.foo.Service#method1")
    
    # Test reverse relationships
    assert "com.foo.TestClass#testMethod" in graph.get_callers("com.foo.Service#method1")
    assert "com.foo.Service#method1" in graph.get_callers("com.foo.Utils#helper")
    
    # Test test method identification
    assert graph.is_test_method("com.foo.TestClass#testMethod") == True
    assert graph.is_test_method("com.foo.AnotherTest#testStuff") == True
    assert graph.is_test_method("com.foo.Service#method1") == False


def test_extract_touched_methods():
    """Test extraction of touched methods from changed files."""
    changed_files = [
        {
            "path": "src/main/java/com/foo/Service.java",
            "lang": "java",
            "fully_qualified_class": "com.foo.Service",
            "class_name": "Service",
            "touched_methods": [
                {"fqn": "com.foo.Service#method1"},
                {"fqn": "com.foo.Service#method2"}
            ]
        }
    ]
    
    touched = extract_touched_methods(changed_files)
    assert "com.foo.Service#method1" in touched
    assert "com.foo.Service#method2" in touched
    assert "com.foo.Service#<init>" in touched  # Constructor should be added
    assert "com.foo.Service#Service" in touched  # Class name constructor


def test_find_affected_tests():
    """Test finding affected tests through call graph traversal."""
    changed_files = [
        {
            "path": "src/main/java/com/foo/Service.java",
            "lang": "java", 
            "fully_qualified_class": "com.foo.Service",
            "class_name": "Service",
            "touched_methods": [{"fqn": "com.foo.Service#processData"}]
        }
    ]
    
    call_graph = [
        {"caller": "com.foo.ServiceTest#testProcessData", "callee": "com.foo.Service#processData"},
        {"caller": "com.foo.IntegrationTest#testWorkflow", "callee": "com.foo.Service#processData"},
        {"caller": "com.foo.Service#processData", "callee": "com.foo.Utils#helper"},
        {"caller": "com.foo.OtherTest#testUnrelated", "callee": "com.foo.Other#method"},
    ]
    
    affected_tests, metadata = find_affected_tests(changed_files, call_graph, {})
    
    # Should find the two tests that call the changed method
    assert "com.foo.ServiceTest#testProcessData" in affected_tests
    assert "com.foo.IntegrationTest#testWorkflow" in affected_tests
    assert "com.foo.OtherTest#testUnrelated" not in affected_tests
    
    assert metadata['touched_methods_count'] > 0
    assert metadata['test_methods_count'] == 2


def test_select_tests_with_graph_logic():
    """Test the main select_tests function with graph-based logic."""
    changed_files = [
        {
            "path": "src/main/java/com/foo/Service.java",
            "lang": "java",
            "fully_qualified_class": "com.foo.Service", 
            "class_name": "Service",
            "hunks": [{"start": 10, "end": 15}],
            "touched_methods": [{"fqn": "com.foo.Service#processData"}]
        }
    ]
    
    call_graph = [
        {"caller": "com.foo.ServiceTest#testProcessData", "callee": "com.foo.Service#processData"},
        {"caller": "com.foo.IntegrationTest#testWorkflow", "callee": "com.foo.Service#processData"},
    ]
    
    allowed_tests = [
        "com.foo.ServiceTest#testProcessData",
        "com.foo.IntegrationTest#testWorkflow",
        "com.foo.UnrelatedTest#testSomething"
    ]
    
    selected, explanations, confidence, metadata = select_tests(
        changed_files, call_graph, {}, allowed_tests, max_tests=10
    )
    
    # Should select the two tests that call the changed method
    assert len(selected) == 2
    assert "com.foo.ServiceTest#testProcessData" in selected
    assert "com.foo.IntegrationTest#testWorkflow" in selected
    assert "com.foo.UnrelatedTest#testSomething" not in selected
    
    # Should have explanations for selected tests
    assert len(explanations) == 2
    
    # Confidence should be reasonable since we found direct connections
    assert confidence >= 0.5
    
    # Metadata should include graph analysis details
    assert metadata['selection_method'] == 'graph_based_traversal'
    assert metadata['graph_analysis']['test_methods_count'] == 2


def test_select_via_call_graph():
    changed_files = [
        {"path": "libs/service-a/src/main/java/com/foo/Bar.java", "change_type": "M", "hunks": [{"start": 10, "end": 12}]}
    ]
    jdeps = {"com.foo.Bar": ["com.foo.Baz"]}
    call_graph = [
        {"caller": "com.foo.Bar#doWork", "callee": "com.foo.Baz#doIt"}
    ]
    selected, explanations, confidence, metadata = select_tests(
        changed_files, call_graph, jdeps, max_tests=10
    )

    assert isinstance(selected, list)
    assert confidence >= 0.0


def test_fastapi_endpoint():
    from fastapi.testclient import TestClient
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from app.main import app
    client = TestClient(app)
    payload = {
        "repo": {"name": "example", "base_commit": "origin/main", "head_commit": "HEAD"},
        "changed_files": [
            {"path": "libs/service-a/src/main/java/com/foo/Bar.java", "change_type": "M", "hunks": [{"start": 1, "end": 1}]}
        ],
        "jdeps_graph": {"com.foo.Bar": ["com.foo.Baz"]},
        "call_graph": [{"caller": "com.foo.Bar#doWork", "callee": "com.foo.Baz#doIt"}],
        "allowed_tests": ["com.foo.BarTest#testDoWork"],
        "settings": {"confidence_threshold": 0.6, "max_tests": 100}
    }
    r = client.post('/select-tests', json=payload)
    assert r.status_code == 200
    data = r.json()
    assert 'selected_tests' in data and isinstance(data['selected_tests'], list)
