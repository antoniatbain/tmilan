from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.features.meeting_notes.llm.agent import (
    LLMExtractionError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.features.meeting_notes.router import router as meeting_notes_router

app = FastAPI(title="ConsultNotes API", version="0.1.0")
app.include_router(meeting_notes_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(LLMTimeoutError)
async def llm_timeout_handler(request: Request, exc: LLMTimeoutError) -> JSONResponse:
    return JSONResponse(status_code=504, content={"detail": str(exc)})


@app.exception_handler(LLMUnavailableError)
async def llm_unavailable_handler(request: Request, exc: LLMUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(LLMExtractionError)
async def llm_extraction_handler(request: Request, exc: LLMExtractionError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})
