from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db_session
from app.features.meeting_notes.llm.agent import ClaudeStructuredAgent, MeetingSummaryExtractor
from app.features.meeting_notes.schemas import MeetingSummaryResponse, TranscriptIngestRequest
from app.features.meeting_notes.service import MeetingNotesService

router = APIRouter(prefix="/transcripts", tags=["meeting-notes"])


def get_extractor(settings: Settings = Depends(get_settings)) -> MeetingSummaryExtractor:
    agent = ClaudeStructuredAgent(settings)
    return MeetingSummaryExtractor(agent=agent, settings=settings)


@router.post(
    "",
    response_model=MeetingSummaryResponse,
    status_code=201,
    summary="Ingest a call transcript and return a structured summary",
    responses={
        422: {"description": "Invalid request payload"},
        502: {"description": "LLM output failed schema validation"},
        503: {"description": "LLM service unavailable"},
        504: {"description": "LLM call timed out"},
    },
)
async def ingest_transcript(
    payload: TranscriptIngestRequest,
    session: AsyncSession = Depends(get_db_session),
    extractor: MeetingSummaryExtractor = Depends(get_extractor),
) -> MeetingSummaryResponse:
    service = MeetingNotesService(session=session, extractor=extractor)
    return await service.ingest_and_summarise(payload)


@router.get(
    "/{transcript_id}",
    response_model=MeetingSummaryResponse,
    summary="Fetch a previously generated meeting summary by transcript id",
    responses={404: {"description": "No summary found for this transcript id"}},
)
async def get_transcript_summary(
    transcript_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    extractor: MeetingSummaryExtractor = Depends(get_extractor),
) -> MeetingSummaryResponse:
    service = MeetingNotesService(session=session, extractor=extractor)
    result = await service.get_summary(str(transcript_id))
    if result is None:
        raise HTTPException(status_code=404, detail="No summary found for this transcript id")
    return result
