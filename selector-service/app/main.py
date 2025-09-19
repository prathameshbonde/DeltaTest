import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from .schemas import SelectRequest, SelectResponse
from .selector import select_tests
from .model_adapter import MockLLM, ExternalLLMAdapter

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
        if mode == 'mock':
            # Use our deterministic selector; mock LLM used only as fallback example
            selected, explanations, confidence, metadata = select_tests(
                changed_files=[cf.dict() for cf in req.changed_files],
                call_graph=req.call_graph,
                jdeps_graph=req.jdeps_graph,
                test_mapping=req.test_mapping,
                max_tests=req.settings.max_tests,
            )
        elif mode == 'remote':
            adapter = ExternalLLMAdapter()
            selected, explanations, confidence, metadata = adapter.select(req.dict())
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported LLM_MODE {mode}")

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
