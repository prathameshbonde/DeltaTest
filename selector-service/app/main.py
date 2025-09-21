"""
FastAPI service for selective test selection in Java Gradle monorepos.

This service analyzes changed files, dependency graphs, and call graphs to determine
which tests should be run for a given PR or code change. It supports multiple selection
modes including deterministic graph-based analysis, LLM-powered selection, and a hybrid
approach that combines both for optimal coverage and reliability.

Supported modes:
- mock: Deterministic graph-based selection only
- hybrid: Combination of deterministic and LLM selection (union of results)  
- openai/remote: OpenAI-compatible LLM APIs only
- gemini/google: Google Gemini APIs only
"""
import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from .schemas import SelectRequest, SelectResponse
from .selector import select_tests, select_tests_hybrid
from .model_adapter import (
    ExternalLLMAdapter,
    GeminiAdapter
)
from .env_loader import load_dotenv_once

load_dotenv_once()
logging.basicConfig(level=os.environ.get('LOG_LEVEL','INFO'))
logger = logging.getLogger("selector-service")

app = FastAPI(title="Selective Test Selector Service", version="0.1.0")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "selector"}


@app.post("/select-tests", response_model=SelectResponse)
async def select_tests_endpoint(req: SelectRequest):
    """
    Main endpoint for test selection.
    
    Analyzes changed files, dependency graphs, and call graphs to determine
    which tests should be executed. Supports multiple LLM modes including:
    - mock: deterministic graph-based selection only
    - hybrid: combination of deterministic and LLM selection (union)
    - OpenAI-compatible APIs, and Google Gemini for LLM-only selection
    
    Args:
        req: SelectRequest containing changed files, graphs, and settings
        
    Returns:
        SelectResponse with selected tests, explanations, and confidence score
        
    Raises:
        HTTPException: For unsupported LLM modes or processing errors
    """
    try:
        mode = os.environ.get('LLM_MODE', 'mock').lower()
        logger.info("/select-tests request: mode=%s, changed=%d, call_edges=%d, jdeps_nodes=%d, max_tests=%d",
                    mode,
                    len(req.changed_files),
                    len(req.call_graph),
                    len(req.jdeps_graph),
                    req.settings.max_tests)
        if mode == 'mock':
            # Use our deterministic selector; mock LLM provides empty selection by design
            selected, explanations, confidence, metadata = select_tests(
                changed_files=[cf.dict() for cf in req.changed_files],
                call_graph=req.call_graph,
                jdeps_graph=req.jdeps_graph,
                allowed_tests=req.allowed_tests,
                max_tests=req.settings.max_tests,
            )
        elif mode == 'hybrid':
            # Use hybrid approach: deterministic + configured LLM adapter
            # Check for LLM configuration and use appropriate adapter
            llm_backend = os.environ.get('HYBRID_LLM_BACKEND', 'mock').lower()
            
            if llm_backend == 'mock':
                from .model_adapter import MockLLM
                llm_adapter = MockLLM()
            elif llm_backend in ('openai', 'openai-compatible'):
                llm_adapter = ExternalLLMAdapter()
            elif llm_backend in ('gemini', 'google'):
                llm_adapter = GeminiAdapter()
            else:
                logger.warning("Unknown HYBRID_LLM_BACKEND '%s', falling back to mock", llm_backend)
                from .model_adapter import MockLLM
                llm_adapter = MockLLM()
            
            logger.debug("hybrid mode: using %s LLM backend", llm_backend)
            selected, explanations, confidence, metadata = select_tests_hybrid(
                changed_files=[cf.dict() for cf in req.changed_files],
                call_graph=req.call_graph,
                jdeps_graph=req.jdeps_graph,
                allowed_tests=req.allowed_tests,
                max_tests=req.settings.max_tests,
                llm_adapter=llm_adapter,
            )
        elif mode in ('remote','openai','openai-compatible'):
            # Use OpenAI-compatible API adapter
            adapter = ExternalLLMAdapter()
            logger.debug("adapter: openai-compatible endpoint=%s model=%s", os.environ.get('LLM_ENDPOINT','(default)'), os.environ.get('LLM_MODEL','gpt-4o-mini'))
            selected, explanations, confidence, metadata = adapter.select(req.dict())
        elif mode in ('gemini','google'):
            # Use Google Gemini API adapter
            adapter = GeminiAdapter()
            logger.debug("adapter: gemini model=%s", os.environ.get('GEMINI_MODEL',''))
            selected, explanations, confidence, metadata = adapter.select(req.dict())
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported LLM_MODE {mode}")

        logger.info("/select-tests response: selected=%d, confidence=%.2f", len(selected), confidence)
        if logger.isEnabledFor(logging.DEBUG):
            sample = selected[:10]
            logger.debug("selected sample: %s", sample)
        return SelectResponse(
            selected_tests=selected,
            explanations=explanations,
            confidence=confidence,
            metadata=metadata,
        )
    except Exception as e:
        logger.exception("Selection failed")
        raise HTTPException(status_code=500, detail=str(e))


def _run_dev():
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=False)


if __name__ == "__main__":
    _run_dev()
