import os
import json
import re
import logging
from typing import Dict, Any, List, Tuple, Optional

import requests


logger = logging.getLogger("selector.adapters")


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
        result = tests[: payload.get('settings', {}).get('max_tests', 500)]
        logger.debug("MockLLM.select: changed=%d mapping=%d -> selected=%d conf=%.2f", len(changed), len(tm), len(result), conf)
        return result, explanations, conf, {'mode': 'mock'}


class ExternalLLMAdapter:
    """
    External LLM adapter that calls an OpenAI-compatible Chat Completions API.

    Expected environment variables:
    - LLM_ENDPOINT: Base URL to the chat completions endpoint (default: OpenAI https://api.openai.com/v1/chat/completions)
    - LLM_API_KEY: API key for Authorization: Bearer <key>
    - LLM_MODEL: Model name (e.g., gpt-4o-mini, gpt-4o, gpt-4.1-mini, etc.). Default: gpt-4o-mini
    - LLM_TEMPERATURE: Sampling temperature (default 0.2)
    - LLM_MAX_TOKENS: Max tokens for response (default 800)
    """

    def __init__(self, endpoint: Optional[str] = None, api_key_env: str = 'LLM_API_KEY'):
        default_endpoint = 'https://api.openai.com/v1/chat/completions'
        self.endpoint = (endpoint or os.environ.get('LLM_ENDPOINT') or default_endpoint).strip()
        self.api_key = os.environ.get(api_key_env, '').strip()
        self.model = os.environ.get('LLM_MODEL', 'gpt-4o-mini').strip()
        self.temperature = float(os.environ.get('LLM_TEMPERATURE', '0.2'))
        self.max_tokens = int(os.environ.get('LLM_MAX_TOKENS', '800'))

    def select(self, payload: Dict[str, Any]):
        if not self.api_key:
            raise RuntimeError('ExternalLLMAdapter not configured: LLM_API_KEY is missing')
        if not self.endpoint:
            raise RuntimeError('ExternalLLMAdapter not configured: LLM_ENDPOINT is missing')

        sys_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(payload)

        body = {
            'model': self.model,
            'messages': [
                { 'role': 'system', 'content': sys_prompt },
                { 'role': 'user', 'content': user_prompt },
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            # If the endpoint supports it, this will force a JSON response
            # OpenAI: {"type":"json_object"}
            'response_format': { 'type': 'json_object' }
        }

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

        logger.debug("ExternalLLMAdapter.call: endpoint=%s model=%s", self.endpoint, self.model)
        try:
            resp = requests.post(self.endpoint, headers=headers, json=body, timeout=60)
        except requests.RequestException as e:
            # Network error: return safe fallback
            logger.warning("ExternalLLMAdapter network error: %s", e.__class__.__name__)
            return [], {}, 0.3, { 'mode': 'external', 'error': f'network:{e.__class__.__name__}' }

        if resp.status_code >= 400:
            logger.warning("ExternalLLMAdapter HTTP error: %s", resp.status_code)
            return [], {}, 0.3, { 'mode': 'external', 'error': f'http:{resp.status_code}', 'body': self._safe_text(resp)[:300] }

        content = self._extract_content(resp.json())
        parsed = self._parse_json(content)
        if not parsed:
            # Try to salvage any JSON object substring
            parsed = self._parse_json(self._extract_first_json_block(content))

        if not parsed:
            logger.warning("ExternalLLMAdapter parse failed; content(head)=%.100s", content)
            return [], {}, 0.3, { 'mode': 'external', 'error': 'parse-failed', 'raw': content[:500] }

        selected = parsed.get('selected_tests') or []
        explanations = parsed.get('explanations') or {}
        confidence = parsed.get('confidence') or 0.5
        metadata = parsed.get('metadata') or {}
        metadata.update({'mode': 'external', 'provider': 'openai-compatible'})
        logger.info("ExternalLLMAdapter: selected=%d conf=%.2f", len(selected), float(confidence))
        return selected, explanations, float(confidence), metadata

    # ----- prompt builders -----
    def _build_system_prompt(self) -> str:
        return (
            "You are an expert build/CI assistant that selects the minimal yet sufficient set of JUnit tests "
            "to run for a given code change in a large Java Gradle monorepo. "
            "Use only the provided structured inputs (changed files with hunks, test-to-code mapping, dependency graphs). "
            "Favor precision and recall trade-offs that keep runtime low while maintaining correctness. "
            "Always respond with a strict JSON object matching this schema: "
            "{\n  \"selected_tests\": string[],\n  \"explanations\": { [test: string]: string },\n  \"confidence\": number,\n  \"metadata\": object\n}. "
            "selected_tests must contain fully qualified test method names in the form Class#method (no spaces). "
            "confidence is a float in [0,1]. Explanations should be short, evidence-based, and reference inputs."
        )

    def _build_user_prompt(self, payload: Dict[str, Any]) -> str:
        repo = payload.get('repo', {})
        name = repo.get('name', 'repo')
        base = repo.get('base_commit', '')
        head = repo.get('head_commit', '')
        settings = payload.get('settings', {})
        max_tests = settings.get('max_tests', 500)

        # Summaries with caps to keep prompt small
        changed = payload.get('changed_files', [])
        jdeps = payload.get('jdeps_graph', {})
        call_graph = payload.get('call_graph', [])
        test_map = payload.get('test_mapping', [])

        def summarize_changed(max_items=100) -> str:
            parts = []
            for i, cf in enumerate(changed[:max_items]):
                hunks = cf.get('hunks', [])
                parts.append(f"- {cf.get('path','?')} ({cf.get('change_type','M')}), hunks={[(h.get('start'), h.get('end')) for h in hunks][:5]}")
            more = max(0, len(changed) - max_items)
            if more:
                parts.append(f"... and {more} more files")
            return "\n".join(parts) if parts else "(none)"

        def summarize_test_map(max_items=200) -> str:
            parts = []
            for e in test_map[:max_items]:
                t = e.get('test','?')
                covers = e.get('covers', [])[:5]
                parts.append(f"- {t} -> covers: {covers}")
            more = max(0, len(test_map) - max_items)
            if more:
                parts.append(f"... and {more} more tests")
            return "\n".join(parts) if parts else "(none)"

        def summarize_graphs(max_edges=200) -> str:
            # jdeps: count only
            jdeps_nodes = len(jdeps)
            # call graph: sample
            sample_edges = []
            for e in call_graph[:max_edges]:
                caller = e.get('caller','?')
                callee = e.get('callee','?')
                sample_edges.append(f"- {caller} -> {callee}")
            more = max(0, len(call_graph) - max_edges)
            s = [f"jdeps nodes: {jdeps_nodes}"]
            if sample_edges:
                s.append("call graph sample:\n" + "\n".join(sample_edges[:50]))
            if more:
                s.append(f"... and {more} more call edges")
            return "\n".join(s)

        instructions = (
            "Task: From the inputs, choose up to {max_tests} JUnit tests that most likely cover or are impacted by the changes. "
            "Use test_mapping to link tests to classes/methods. Use jdeps/call graph for transitive impact. "
            "Prefer fewer tests when confidence is high; include more when changes are wide or uncertain. "
            "If there is no signal, return an empty list with a lower confidence and explain why."
        ).format(max_tests=max_tests)

        return (
            f"Repository: {name}\n"
            f"Base: {base}\nHead: {head}\n\n"
            f"Changed files:\n{summarize_changed()}\n\n"
            f"Test mapping (sample):\n{summarize_test_map()}\n\n"
            f"Graphs summary:\n{summarize_graphs()}\n\n"
            f"{instructions}\n\n"
            "Return strictly JSON with keys: selected_tests, explanations, confidence, metadata."
        )

    # ----- response helpers -----
    def _extract_content(self, data: Dict[str, Any]) -> str:
        try:
            return data['choices'][0]['message']['content']
        except Exception:
            return json.dumps(data)

    def _safe_text(self, resp: requests.Response) -> str:
        try:
            return resp.text
        except Exception:
            return ''

    def _parse_json(self, text: Optional[str]) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        text = text.strip()
        # Try direct JSON parse
        try:
            return json.loads(text)
        except Exception:
            pass
        # Try code block fenced JSON
        m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        return None

    def _extract_first_json_block(self, text: str) -> str:
        # Fallback: find the outermost {...}
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]
        return ''


class AzureOpenAIAdapter(ExternalLLMAdapter):
    def __init__(self):
        # Azure settings
        self.resource = os.environ.get('AZURE_OPENAI_ENDPOINT', '').rstrip('/')  # e.g., https://myres.openai.azure.com
        self.deployment = os.environ.get('AZURE_OPENAI_DEPLOYMENT', '')
        self.api_version = os.environ.get('AZURE_OPENAI_API_VERSION', '2024-02-15-preview')
        self.api_key = os.environ.get('AZURE_OPENAI_API_KEY', '')
        self.model = self.deployment or os.environ.get('LLM_MODEL', 'gpt-4o-mini')
        self.temperature = float(os.environ.get('LLM_TEMPERATURE', '0.2'))
        self.max_tokens = int(os.environ.get('LLM_MAX_TOKENS', '800'))

    def select(self, payload: Dict[str, Any]):
        if not self.resource or not self.deployment or not self.api_key:
            raise RuntimeError('AzureOpenAIAdapter not configured: set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_KEY')
        sys_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(payload)
        url = f"{self.resource}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"
        body = {
            'messages': [
                {'role':'system','content':sys_prompt},
                {'role':'user','content':user_prompt},
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'response_format': {'type':'json_object'}
        }
        headers = {
            'api-key': self.api_key,
            'Content-Type': 'application/json',
        }
        logger.debug("AzureOpenAIAdapter.call: resource=%s deployment=%s", self.resource, self.deployment)
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=60)
        except requests.RequestException as e:
            logger.warning("AzureOpenAI network error: %s", e.__class__.__name__)
            return [], {}, 0.3, {'mode':'external','provider':'azure-openai','error':f'network:{e.__class__.__name__}'}
        if resp.status_code >= 400:
            logger.warning("AzureOpenAI HTTP error: %d", resp.status_code)
            return [], {}, 0.3, {'mode':'external','provider':'azure-openai','error':f'http:{resp.status_code}','body':self._safe_text(resp)[:300]}
        content = self._extract_content(resp.json())
        parsed = self._parse_json(content) or self._parse_json(self._extract_first_json_block(content))
        if not parsed:
            logger.warning("AzureOpenAI parse failed")
            return [], {}, 0.3, {'mode':'external','provider':'azure-openai','error':'parse-failed','raw':content[:500]}
        selected = parsed.get('selected_tests',[])
        conf = float(parsed.get('confidence',0.5))
        logger.info("AzureOpenAI: selected=%d conf=%.2f", len(selected), conf)
        return selected, parsed.get('explanations',{}), conf, {**parsed.get('metadata',{}), 'mode':'external','provider':'azure-openai'}


class AnthropicAdapter(ExternalLLMAdapter):
    def __init__(self):
        self.api_key = os.environ.get('ANTHROPIC_API_KEY','')
        self.model = os.environ.get('ANTHROPIC_MODEL','claude-3-5-sonnet-20240620')
        self.temperature = float(os.environ.get('LLM_TEMPERATURE','0.2'))
        self.max_tokens = int(os.environ.get('LLM_MAX_TOKENS','800'))

    def select(self, payload: Dict[str, Any]):
        if not self.api_key:
            raise RuntimeError('AnthropicAdapter not configured: set ANTHROPIC_API_KEY')
        sys_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(payload)
        url = 'https://api.anthropic.com/v1/messages'
        headers = {
            'x-api-key': self.api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        }
        body = {
            'model': self.model,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'system': sys_prompt,
            'messages': [ {'role':'user','content':user_prompt} ]
        }
        logger.debug("AnthropicAdapter.call: model=%s", self.model)
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=60)
        except requests.RequestException as e:
            logger.warning("Anthropic network error: %s", e.__class__.__name__)
            return [], {}, 0.3, {'mode':'external','provider':'anthropic','error':f'network:{e.__class__.__name__}'}
        if resp.status_code >= 400:
            logger.warning("Anthropic HTTP error: %d", resp.status_code)
            return [], {}, 0.3, {'mode':'external','provider':'anthropic','error':f'http:{resp.status_code}','body':self._safe_text(resp)[:300]}
        data = resp.json()
        try:
            # Newer API returns list of content blocks
            if isinstance(data.get('content'), list):
                content = ''.join(part.get('text','') for part in data['content'])
            else:
                content = json.dumps(data)
        except Exception:
            content = json.dumps(data)
        parsed = self._parse_json(content) or self._parse_json(self._extract_first_json_block(content))
        if not parsed:
            logger.warning("Anthropic parse failed")
            return [], {}, 0.3, {'mode':'external','provider':'anthropic','error':'parse-failed','raw':content[:500]}
        selected = parsed.get('selected_tests',[])
        conf = float(parsed.get('confidence',0.5))
        logger.info("Anthropic: selected=%d conf=%.2f", len(selected), conf)
        return selected, parsed.get('explanations',{}), conf, {**parsed.get('metadata',{}), 'mode':'external','provider':'anthropic'}


class GeminiAdapter(ExternalLLMAdapter):
    def __init__(self):
        self.api_key = os.environ.get('GEMINI_API_KEY','')
        self.model = os.environ.get('GEMINI_MODEL','gemini-1.5-pro')
        self.temperature = float(os.environ.get('LLM_TEMPERATURE','0.2'))
        self.max_tokens = int(os.environ.get('LLM_MAX_TOKENS','800'))

    def select(self, payload: Dict[str, Any]):
        if not self.api_key:
            raise RuntimeError('GeminiAdapter not configured: set GEMINI_API_KEY')
        sys_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(payload)
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}'
        body = {
            'systemInstruction': { 'role':'system', 'parts': [{'text': sys_prompt}] },
            'contents': [ { 'role':'user', 'parts': [ {'text': user_prompt} ] } ],
            'generationConfig': {
                'temperature': self.temperature,
                'maxOutputTokens': self.max_tokens
            }
        }
        logger.debug("GeminiAdapter.call: model=%s", self.model)
        try:
            resp = requests.post(url, json=body, timeout=60)
        except requests.RequestException as e:
            logger.warning("Gemini network error: %s", e.__class__.__name__)
            return [], {}, 0.3, {'mode':'external','provider':'gemini','error':f'network:{e.__class__.__name__}'}
        if resp.status_code >= 400:
            logger.warning("Gemini HTTP error: %d", resp.status_code)
            return [], {}, 0.3, {'mode':'external','provider':'gemini','error':f'http:{resp.status_code}','body':self._safe_text(resp)[:300]}
        data = resp.json()
        try:
            content = data['candidates'][0]['content']['parts'][0]['text']
        except Exception:
            content = json.dumps(data)
        parsed = self._parse_json(content) or self._parse_json(self._extract_first_json_block(content))
        if not parsed:
            logger.warning("Gemini parse failed")
            return [], {}, 0.3, {'mode':'external','provider':'gemini','error':'parse-failed','raw':content[:500]}
        selected = parsed.get('selected_tests',[])
        conf = float(parsed.get('confidence',0.5))
        logger.info("Gemini: selected=%d conf=%.2f", len(selected), conf)
        return selected, parsed.get('explanations',{}), conf, {**parsed.get('metadata',{}), 'mode':'external','provider':'gemini'}


class CohereAdapter(ExternalLLMAdapter):
    def __init__(self):
        self.api_key = os.environ.get('COHERE_API_KEY','')
        self.model = os.environ.get('COHERE_MODEL','command-r-plus')
        self.temperature = float(os.environ.get('LLM_TEMPERATURE','0.2'))
        self.max_tokens = int(os.environ.get('LLM_MAX_TOKENS','800'))

    def select(self, payload: Dict[str, Any]):
        if not self.api_key:
            raise RuntimeError('CohereAdapter not configured: set COHERE_API_KEY')
        sys_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(payload)
        url = 'https://api.cohere.com/v1/chat'
        headers = { 'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json' }
        body = {
            'model': self.model,
            'message': user_prompt,
            'preamble': sys_prompt,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens
        }
        logger.debug("CohereAdapter.call: model=%s", self.model)
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=60)
        except requests.RequestException as e:
            logger.warning("Cohere network error: %s", e.__class__.__name__)
            return [], {}, 0.3, {'mode':'external','provider':'cohere','error':f'network:{e.__class__.__name__}'}
        if resp.status_code >= 400:
            logger.warning("Cohere HTTP error: %d", resp.status_code)
            return [], {}, 0.3, {'mode':'external','provider':'cohere','error':f'http:{resp.status_code}','body':self._safe_text(resp)[:300]}
        data = resp.json()
        content = data.get('text') or json.dumps(data)
        parsed = self._parse_json(content) or self._parse_json(self._extract_first_json_block(content))
        if not parsed:
            logger.warning("Cohere parse failed")
            return [], {}, 0.3, {'mode':'external','provider':'cohere','error':'parse-failed','raw':content[:500]}
        selected = parsed.get('selected_tests',[])
        conf = float(parsed.get('confidence',0.5))
        logger.info("Cohere: selected=%d conf=%.2f", len(selected), conf)
        return selected, parsed.get('explanations',{}), conf, {**parsed.get('metadata',{}), 'mode':'external','provider':'cohere'}


class MistralAdapter(ExternalLLMAdapter):
    def __init__(self):
        self.endpoint = os.environ.get('MISTRAL_ENDPOINT','https://api.mistral.ai/v1/chat/completions')
        self.api_key = os.environ.get('MISTRAL_API_KEY','')
        self.model = os.environ.get('MISTRAL_MODEL','mistral-large-latest')
        self.temperature = float(os.environ.get('LLM_TEMPERATURE','0.2'))
        self.max_tokens = int(os.environ.get('LLM_MAX_TOKENS','800'))

    def select(self, payload: Dict[str, Any]):
        if not self.api_key:
            raise RuntimeError('MistralAdapter not configured: set MISTRAL_API_KEY')
        sys_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(payload)
        headers = { 'Authorization': f'Bearer {self.api_key}', 'Content-Type':'application/json' }
        body = {
            'model': self.model,
            'messages': [ {'role':'system','content':sys_prompt}, {'role':'user','content':user_prompt} ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'response_format': {'type':'json_object'}
        }
        logger.debug("MistralAdapter.call: endpoint=%s model=%s", self.endpoint, self.model)
        try:
            resp = requests.post(self.endpoint, headers=headers, json=body, timeout=60)
        except requests.RequestException as e:
            logger.warning("Mistral network error: %s", e.__class__.__name__)
            return [], {}, 0.3, {'mode':'external','provider':'mistral','error':f'network:{e.__class__.__name__}'}
        if resp.status_code >= 400:
            logger.warning("Mistral HTTP error: %d", resp.status_code)
            return [], {}, 0.3, {'mode':'external','provider':'mistral','error':f'http:{resp.status_code}','body':self._safe_text(resp)[:300]}
        content = self._extract_content(resp.json())
        parsed = self._parse_json(content) or self._parse_json(self._extract_first_json_block(content))
        if not parsed:
            logger.warning("Mistral parse failed")
            return [], {}, 0.3, {'mode':'external','provider':'mistral','error':'parse-failed','raw':content[:500]}
        selected = parsed.get('selected_tests',[])
        conf = float(parsed.get('confidence',0.5))
        logger.info("Mistral: selected=%d conf=%.2f", len(selected), conf)
        return selected, parsed.get('explanations',{}), conf, {**parsed.get('metadata',{}), 'mode':'external','provider':'mistral'}


class OpenRouterAdapter(ExternalLLMAdapter):
    def __init__(self):
        self.endpoint = os.environ.get('OPENROUTER_ENDPOINT','https://openrouter.ai/api/v1/chat/completions')
        self.api_key = os.environ.get('OPENROUTER_API_KEY','')
        self.model = os.environ.get('OPENROUTER_MODEL','openrouter/auto')
        self.temperature = float(os.environ.get('LLM_TEMPERATURE','0.2'))
        self.max_tokens = int(os.environ.get('LLM_MAX_TOKENS','800'))

    def select(self, payload: Dict[str, Any]):
        if not self.api_key:
            raise RuntimeError('OpenRouterAdapter not configured: set OPENROUTER_API_KEY')
        sys_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(payload)
        headers = { 'Authorization': f'Bearer {self.api_key}', 'Content-Type':'application/json' }
        body = {
            'model': self.model,
            'messages': [ {'role':'system','content':sys_prompt}, {'role':'user','content':user_prompt} ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'response_format': {'type':'json_object'}
        }
        logger.debug("OpenRouterAdapter.call: endpoint=%s model=%s", self.endpoint, self.model)
        try:
            resp = requests.post(self.endpoint, headers=headers, json=body, timeout=60)
        except requests.RequestException as e:
            logger.warning("OpenRouter network error: %s", e.__class__.__name__)
            return [], {}, 0.3, {'mode':'external','provider':'openrouter','error':f'network:{e.__class__.__name__}'}
        if resp.status_code >= 400:
            logger.warning("OpenRouter HTTP error: %d", resp.status_code)
            return [], {}, 0.3, {'mode':'external','provider':'openrouter','error':f'http:{resp.status_code}','body':self._safe_text(resp)[:300]}
        content = self._extract_content(resp.json())
        parsed = self._parse_json(content) or self._parse_json(self._extract_first_json_block(content))
        if not parsed:
            logger.warning("OpenRouter parse failed")
            return [], {}, 0.3, {'mode':'external','provider':'openrouter','error':'parse-failed','raw':content[:500]}
        selected = parsed.get('selected_tests',[])
        conf = float(parsed.get('confidence',0.5))
        logger.info("OpenRouter: selected=%d conf=%.2f", len(selected), conf)
        return selected, parsed.get('explanations',{}), conf, {**parsed.get('metadata',{}), 'mode':'external','provider':'openrouter'}


class OllamaAdapter(ExternalLLMAdapter):
    def __init__(self):
        self.host = os.environ.get('OLLAMA_HOST','http://localhost:11434')
        self.model = os.environ.get('OLLAMA_MODEL','llama3.1')
        self.temperature = float(os.environ.get('LLM_TEMPERATURE','0.2'))
        self.max_tokens = int(os.environ.get('LLM_MAX_TOKENS','800'))

    def select(self, payload: Dict[str, Any]):
        sys_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(payload)
        url = f"{self.host.rstrip('/')}/api/chat"
        body = {
            'model': self.model,
            'messages': [
                {'role':'system','content':sys_prompt},
                {'role':'user','content':user_prompt}
            ],
            'stream': False,
            'format': 'json'
        }
        logger.debug("OllamaAdapter.call: host=%s model=%s", self.host, self.model)
        try:
            resp = requests.post(url, json=body, timeout=60)
        except requests.RequestException as e:
            logger.warning("Ollama network error: %s", e.__class__.__name__)
            return [], {}, 0.3, {'mode':'external','provider':'ollama','error':f'network:{e.__class__.__name__}'}
        if resp.status_code >= 400:
            logger.warning("Ollama HTTP error: %d", resp.status_code)
            return [], {}, 0.3, {'mode':'external','provider':'ollama','error':f'http:{resp.status_code}','body':self._safe_text(resp)[:300]}
        data = resp.json()
        try:
            content = data.get('message', {}).get('content') or json.dumps(data)
        except Exception:
            content = json.dumps(data)
        parsed = self._parse_json(content) or self._parse_json(self._extract_first_json_block(content))
        if not parsed:
            logger.warning("Ollama parse failed")
            return [], {}, 0.3, {'mode':'external','provider':'ollama','error':'parse-failed','raw':content[:500]}
        selected = parsed.get('selected_tests',[])
        conf = float(parsed.get('confidence',0.5))
        logger.info("Ollama: selected=%d conf=%.2f", len(selected), conf)
        return selected, parsed.get('explanations',{}), conf, {**parsed.get('metadata',{}), 'mode':'external','provider':'ollama'}
