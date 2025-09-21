"""
Model adapters for external LLM providers and mock selection logic.

This module provides adapters for different LLM providers including OpenAI-compatible APIs,
Google Gemini, and a mock adapter for testing. Each adapter implements the same interface
to provide test selection, explanations, and confidence scoring.
"""
import os
import json
import re
import logging
from typing import Dict, Any, List, Tuple, Optional

import requests


logger = logging.getLogger("selector.adapters")


class MockLLM:
    """
    Mock LLM adapter for testing and deterministic behavior.
    
    This adapter provides a simple implementation that returns empty selections
    with low confidence, suitable for testing the pipeline without external dependencies.
    """
    def __init__(self):
        pass

    def select(self, payload: Dict[str, Any]) -> Tuple[List[str], Dict[str, str], float, Dict[str, Any]]:
        """
        Mock selection that returns empty results.
        
        Args:
            payload: Request payload (unused in mock mode)
            
        Returns:
            Tuple of (empty_tests, empty_explanations, low_confidence, metadata)
        """
        # Deterministic fallback lives in selector.py. The mock adapter doesn't invent tests without mapping.
        changed = payload.get('changed_files', [])
        if not changed:
            return [], {}, 0.5, {'reason': 'no changes', 'mode': 'mock'}
        logger.debug("MockLLM.select: changed=%d -> selected=%d conf=%.2f", len(changed), 0, 0.4)
        return [], {}, 0.4, {'mode': 'mock'}


class ExternalLLMAdapter:
    """
    External LLM adapter that calls an OpenAI-compatible Chat Completions API.

    This adapter supports any service that implements the OpenAI chat completions API,
    including OpenAI itself, Azure OpenAI, and various open-source LLM serving platforms.

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
            "Use only the provided structured inputs (changed files with hunks and dependency graphs). "
            "You will be given both a brief summary and the FULL JSON for changed_files, jdeps_graph, and call_graph. "
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

        # Summaries with caps to keep prompt readable; full JSON is attached below
        changed = payload.get('changed_files', [])
        jdeps = payload.get('jdeps_graph', {})
        call_graph = payload.get('call_graph', [])
        allowed_tests = payload.get('allowed_tests', [])

        def summarize_changed(max_items=100) -> str:
            parts = []
            for i, cf in enumerate(changed[:max_items]):
                hunks = cf.get('hunks', [])
                tm = cf.get('touched_methods') or []
                tm_s = ", ".join((m.get('fqn') or m.get('name') or '?') + (f"[{m.get('start_line')}-{m.get('end_line')}]" if m.get('start_line') and m.get('end_line') else '') for m in tm[:5])
                java_ctx = ''
                if cf.get('lang') == 'java':
                    java_ctx = f" class={cf.get('fully_qualified_class') or cf.get('class_name')}"
                    if tm_s:
                        java_ctx += f" touched=[{tm_s}]"
                parts.append(f"- {cf.get('path','?')} ({cf.get('change_type','M')}){java_ctx}, hunks={[(h.get('start'), h.get('end')) for h in hunks][:5]}")
            more = max(0, len(changed) - max_items)
            if more:
                parts.append(f"... and {more} more files")
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
            "Use jdeps/call graph for transitive impact. "
            "Prefer fewer tests when confidence is high; include more when changes are wide or uncertain. "
            "If there is no signal, return an empty list with a lower confidence and explain why."
        ).format(max_tests=max_tests)

        # Attach full inputs as compact JSON for the model to consume
        full_inputs = {
            'changed_files': changed,
            'jdeps_graph': jdeps,
            'call_graph': call_graph,
            'allowed_tests': allowed_tests,
        }
        full_inputs_json = json.dumps(full_inputs, ensure_ascii=False, separators=(",", ":"))

        return (
            f"Repository: {name}\n"
            f"Base: {base}\nHead: {head}\n\n"
            f"Changed files (summary):\n{summarize_changed()}\n\n"
            f"Graphs (summary):\n{summarize_graphs()}\n\n"
            f"{instructions}\n\n"
            "Full inputs (JSON) — changed_files, jdeps_graph, call_graph:\n"
            "```json\n" + full_inputs_json + "\n```\n\n"
            "Additionally, you will be provided an allowed_tests array in the payload. You must ONLY return tests from allowed_tests. Do not invent or hallucinate tests; if unsure, return an empty list with a clear explanation."
            " Return strictly JSON with keys: selected_tests, explanations, confidence, metadata."
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
