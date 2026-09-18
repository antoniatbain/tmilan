from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.features.meeting_notes.llm.agent import (
    ClaudeStructuredAgent,
    LLMTimeoutError,
    MeetingSummaryExtractor,
)
from app.features.meeting_notes.models import MeetingSummary, Transcript
from app.features.meeting_notes.schemas import TranscriptIngestRequest
from app.features.meeting_notes.service import MeetingNotesService
from tests.conftest import CANNED_SUMMARY


def _payload() -> TranscriptIngestRequest:
    return TranscriptIngestRequest(
        client_name="Acme Corp",
        meeting_title="Q3 ERP kickoff",
        transcript_text="We discussed consolidating three regional ERP systems. " * 3,
    )


async def test_happy_path_writes_transcript_and_summary(
    db_session: AsyncSession, mock_claude_client: AsyncMock
) -> None:
    extractor = MeetingSummaryExtractor(agent=mock_claude_client, settings=get_settings())
    service = MeetingNotesService(session=db_session, extractor=extractor)

    response = await service.ingest_and_summarise(_payload())

    assert response.executive_summary == CANNED_SUMMARY["executive_summary"]
    assert len(response.action_items) == 2

    transcripts = (await db_session.execute(select(Transcript))).scalars().all()
    summaries = (await db_session.execute(select(MeetingSummary))).scalars().all()
    assert len(transcripts) == 1
    assert len(summaries) == 1
    assert summaries[0].transcript_id == transcripts[0].id
    assert summaries[0].action_items[1]["owner"] == "unassigned"


async def test_llm_failure_leaves_transcript_without_summary(db_session: AsyncSession) -> None:
    agent = AsyncMock(spec=ClaudeStructuredAgent)
    agent.run.side_effect = TimeoutError()
    extractor = MeetingSummaryExtractor(
        agent=agent, settings=get_settings().model_copy(update={"llm_max_attempts": 1})
    )
    service = MeetingNotesService(session=db_session, extractor=extractor)

    with pytest.raises(LLMTimeoutError):
        await service.ingest_and_summarise(_payload())

    transcripts = (await db_session.execute(select(Transcript))).scalars().all()
    summaries = (await db_session.execute(select(MeetingSummary))).scalars().all()
    assert len(transcripts) == 1
    assert len(summaries) == 0
