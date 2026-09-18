from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TranscriptIngestRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=200)
    meeting_title: str = Field(min_length=1, max_length=300)
    meeting_date: date | None = None
    transcript_text: str = Field(min_length=50, max_length=200_000)


class ActionItem(BaseModel):
    description: str
    owner: str
    due_date: str | None = None


class MeetingSummaryLLMOutput(BaseModel):
    """The contract handed to the LLM as a JSON schema and validated on the way back.

    ``due_date`` on ActionItem is deliberately free text (not a date type): forcing
    the model to produce ISO dates from a transcript that says "next Friday" is the
    most likely cause of a structured-output retry failure. Extra keys from the model
    are ignored rather than rejected, so a stray field doesn't fail the whole call.
    """

    executive_summary: str
    key_decisions: list[str]
    action_items: list[ActionItem]
    risks: list[str]


class MeetingSummaryResponse(BaseModel):
    transcript_id: UUID
    summary_id: UUID
    client_name: str
    meeting_title: str
    meeting_date: date | None
    created_at: datetime
    llm_model: str
    executive_summary: str
    key_decisions: list[str]
    action_items: list[ActionItem]
    risks: list[str]
