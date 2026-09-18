from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.meeting_notes.llm.agent import MeetingSummaryExtractor
from app.features.meeting_notes.models import MeetingSummary, Transcript
from app.features.meeting_notes.schemas import MeetingSummaryResponse, TranscriptIngestRequest


class MeetingNotesService:
    """Orchestrates the ingest → LLM extraction → persist pipeline.

    Deliberately two transactions, not one spanning the LLM call: holding a DB
    transaction open across a ~2-minute LLM call would pin a pool connection and an
    idle-in-transaction snapshot per request. The trade-off is that an LLM failure
    leaves a `transcripts` row with no summary — an honest partial state (the
    transcript *was* received), not silently discarded. Re-summarisation of an
    existing transcript is out of scope for this walking skeleton.
    """

    def __init__(self, session: AsyncSession, extractor: MeetingSummaryExtractor) -> None:
        self._session = session
        self._extractor = extractor

    async def ingest_and_summarise(
        self, payload: TranscriptIngestRequest
    ) -> MeetingSummaryResponse:
        transcript = Transcript(
            client_name=payload.client_name,
            meeting_title=payload.meeting_title,
            meeting_date=payload.meeting_date,
            transcript_text=payload.transcript_text,
        )
        async with self._session.begin():
            self._session.add(transcript)
            await self._session.flush()

        llm_output = await self._extractor.extract(
            client_name=payload.client_name,
            meeting_title=payload.meeting_title,
            meeting_date=payload.meeting_date,
            transcript_text=payload.transcript_text,
        )

        summary = MeetingSummary(
            transcript_id=transcript.id,
            executive_summary=llm_output.executive_summary,
            key_decisions=llm_output.key_decisions,
            action_items=[item.model_dump() for item in llm_output.action_items],
            risks=llm_output.risks,
            llm_model=self._extractor.settings.llm_model,
        )
        async with self._session.begin():
            self._session.add(summary)
            await self._session.flush()

        return MeetingSummaryResponse(
            transcript_id=transcript.id,
            summary_id=summary.id,
            client_name=transcript.client_name,
            meeting_title=transcript.meeting_title,
            meeting_date=transcript.meeting_date,
            created_at=summary.created_at,
            llm_model=summary.llm_model,
            executive_summary=llm_output.executive_summary,
            key_decisions=llm_output.key_decisions,
            action_items=llm_output.action_items,
            risks=llm_output.risks,
        )

    async def get_summary(self, transcript_id: str) -> MeetingSummaryResponse | None:
        stmt = (
            select(Transcript, MeetingSummary)
            .join(MeetingSummary, MeetingSummary.transcript_id == Transcript.id)
            .where(Transcript.id == transcript_id)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        transcript, summary = row
        return MeetingSummaryResponse(
            transcript_id=transcript.id,
            summary_id=summary.id,
            client_name=transcript.client_name,
            meeting_title=transcript.meeting_title,
            meeting_date=transcript.meeting_date,
            created_at=summary.created_at,
            llm_model=summary.llm_model,
            executive_summary=summary.executive_summary,
            key_decisions=summary.key_decisions,
            action_items=summary.action_items,
            risks=summary.risks,
        )
