import json, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.selector import select_tests  # type: ignore


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
    assert any(e[0] == "com.foo.Bar#doWork" for e in [(x['from'], x['to']) for x in metadata['reason_edges']]) or metadata['reason_edges'] == []

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
        
        "settings": {"confidence_threshold": 0.6, "max_tests": 100}
    }
    r = client.post('/select-tests', json=payload)
    assert r.status_code == 200
    data = r.json()
    assert 'selected_tests' in data and isinstance(data['selected_tests'], list)
