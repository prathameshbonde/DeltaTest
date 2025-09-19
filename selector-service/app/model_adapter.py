import os
from typing import Dict, Any, List, Tuple


class MockLLM:
    def __init__(self):
        pass

    def select(self, payload: Dict[str, Any]) -> Tuple[List[str], Dict[str, str], float, Dict[str, Any]]:
        # Delegate to deterministic heuristics would happen in selector.py; here we just pass-through by contract
        # For the mock, just select tests where any 'covers' exists when there are changes
        tests = []
        explanations = {}
        tm = payload.get('test_mapping', [])
        changed = payload.get('changed_files', [])
        if not changed:
            return [], {}, 0.5, {'reason': 'no changes'}
        for e in tm:
            if e.get('covers'):
                tests.append(e['test'])
                explanations[e['test']] = 'Mock selection: has covers and repo changed.'
        conf = 0.7 if tests else 0.4
        return tests[: payload.get('settings', {}).get('max_tests', 500)], explanations, conf, {'mode': 'mock'}


class ExternalLLMAdapter:
    def __init__(self, endpoint: str = None, api_key_env: str = 'LLM_API_KEY'):
        self.endpoint = endpoint or os.environ.get('LLM_ENDPOINT', '')
        self.api_key = os.environ.get(api_key_env, '')

    def select(self, payload: Dict[str, Any]):
        # Placeholder: demonstrate shape; do not actually call external network
        if not self.api_key or not self.endpoint:
            raise RuntimeError('ExternalLLMAdapter not configured: set LLM_ENDPOINT and LLM_API_KEY')
        # In a real implementation, you'd use requests to POST payload and parse response
        # Here we simulate a no-op selection with low confidence
        return [], {}, 0.3, {'mode': 'external', 'note': 'placeholder'}
