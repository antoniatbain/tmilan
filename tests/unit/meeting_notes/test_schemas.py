import pytest
from pydantic import ValidationError

from app.features.meeting_notes.schemas import (
    MeetingSummaryLLMOutput,
    TranscriptIngestRequest,
)
from tests.conftest import CANNED_SUMMARY


def test_llm_output_accepts_canned_payload() -> None:
    output = MeetingSummaryLLMOutput.model_validate(CANNED_SUMMARY)
    assert output.executive_summary == CANNED_SUMMARY["executive_summary"]
    assert len(output.action_items) == 2
    assert output.action_items[1].owner == "unassigned"


def test_llm_output_rejects_missing_owner() -> None:
    bad = {**CANNED_SUMMARY, "action_items": [{"description": "Do a thing", "due_date": None}]}
    with pytest.raises(ValidationError):
        MeetingSummaryLLMOutput.model_validate(bad)


def test_json_schema_shape() -> None:
    schema = MeetingSummaryLLMOutput.model_json_schema()
    assert schema["type"] == "object"
    assert "action_items" in schema["properties"]


def test_ingest_request_rejects_too_short_transcript() -> None:
    with pytest.raises(ValidationError):
        TranscriptIngestRequest(
            client_name="Acme",
            meeting_title="Kickoff",
            transcript_text="too short",
        )


def test_ingest_request_rejects_oversized_transcript() -> None:
    with pytest.raises(ValidationError):
        TranscriptIngestRequest(
            client_name="Acme",
            meeting_title="Kickoff",
            transcript_text="x" * 200_001,
        )


def test_ingest_request_accepts_valid_payload() -> None:
    req = TranscriptIngestRequest(
        client_name="Acme",
        meeting_title="Kickoff",
        transcript_text="x" * 100,
    )
    assert req.client_name == "Acme"
