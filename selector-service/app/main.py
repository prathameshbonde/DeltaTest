import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from .schemas import SelectRequest, SelectResponse
from .selector import select_tests
from .model_adapter import (
    MockLLM,
    ExternalLLMAdapter,  # backward compatible alias for OpenAI-compatible
    OpenRouterAdapter,
    MistralAdapter,
    CohereAdapter,
    GeminiAdapter,
    AnthropicAdapter,
    AzureOpenAIAdapter,
    OllamaAdapter,
)
from .env_loader import load_dotenv_once

load_dotenv_once()
logging.basicConfig(level=os.environ.get('LOG_LEVEL','INFO'))
logger = logging.getLogger("selector-service")

app = FastAPI(title="Selective Test Selector Service", version="0.1.0")


@app.get("/")
async def root():
    return {"status": "ok", "service": "selector"}


@app.post("/select-tests", response_model=SelectResponse)
async def select_tests_endpoint(req: SelectRequest):
    try:
        mode = os.environ.get('LLM_MODE', 'mock').lower()
        logger.info("/select-tests request: mode=%s, changed=%d, mapping=%d, call_edges=%d, jdeps_nodes=%d, max_tests=%d",
                    mode,
                    len(req.changed_files),
                    len(req.test_mapping),
                    len(req.call_graph),
                    len(req.jdeps_graph),
                    req.settings.max_tests)
        if mode == 'mock':
            # Use our deterministic selector; mock LLM used only as fallback example
            selected, explanations, confidence, metadata = select_tests(
                changed_files=[cf.dict() for cf in req.changed_files],
                call_graph=req.call_graph,
                jdeps_graph=req.jdeps_graph,
                test_mapping=req.test_mapping,
                max_tests=req.settings.max_tests,
            )
        elif mode in ('remote','openai','openai-compatible'):
            adapter = ExternalLLMAdapter()
            logger.debug("adapter: openai-compatible endpoint=%s model=%s", os.environ.get('LLM_ENDPOINT','(default)'), os.environ.get('LLM_MODEL','gpt-4o-mini'))
            selected, explanations, confidence, metadata = adapter.select(req.dict())
        elif mode in ('azure','azure-openai'):
            adapter = AzureOpenAIAdapter()
            logger.debug("adapter: azure-openai resource=%s deployment=%s", os.environ.get('AZURE_OPENAI_ENDPOINT',''), os.environ.get('AZURE_OPENAI_DEPLOYMENT',''))
            selected, explanations, confidence, metadata = adapter.select(req.dict())
        elif mode in ('anthropic','claude'):
            adapter = AnthropicAdapter()
            logger.debug("adapter: anthropic model=%s", os.environ.get('ANTHROPIC_MODEL',''))
            selected, explanations, confidence, metadata = adapter.select(req.dict())
        elif mode in ('gemini','google'):
            adapter = GeminiAdapter()
            logger.debug("adapter: gemini model=%s", os.environ.get('GEMINI_MODEL',''))
            selected, explanations, confidence, metadata = adapter.select(req.dict())
        elif mode in ('cohere',):
            adapter = CohereAdapter()
            logger.debug("adapter: cohere model=%s", os.environ.get('COHERE_MODEL',''))
            selected, explanations, confidence, metadata = adapter.select(req.dict())
        elif mode in ('mistral',):
            adapter = MistralAdapter()
            logger.debug("adapter: mistral endpoint=%s model=%s", os.environ.get('MISTRAL_ENDPOINT',''), os.environ.get('MISTRAL_MODEL',''))
            selected, explanations, confidence, metadata = adapter.select(req.dict())
        elif mode in ('openrouter',):
            adapter = OpenRouterAdapter()
            logger.debug("adapter: openrouter model=%s", os.environ.get('OPENROUTER_MODEL',''))
            selected, explanations, confidence, metadata = adapter.select(req.dict())
        elif mode in ('ollama','local'):
            adapter = OllamaAdapter()
            logger.debug("adapter: ollama host=%s model=%s", os.environ.get('OLLAMA_HOST',''), os.environ.get('OLLAMA_MODEL',''))
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
