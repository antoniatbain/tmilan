from unittest.mock import AsyncMock

from httpx import AsyncClient

from app.features.meeting_notes.llm.agent import (
    MeetingSummaryExtractor,
)
from app.features.meeting_notes.router import get_extractor
from app.main import app
from tests.conftest import CANNED_SUMMARY


def _payload() -> dict:
    return {
        "client_name": "Acme Corp",
        "meeting_title": "Q3 ERP kickoff",
        "transcript_text": "We discussed consolidating three regional ERP systems. " * 3,
    }


async def test_ingest_and_fetch_round_trip(api_client: AsyncClient) -> None:
    resp = await api_client.post("/transcripts", json=_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["executive_summary"] == CANNED_SUMMARY["executive_summary"]
    transcript_id = body["transcript_id"]

    get_resp = await api_client.get(f"/transcripts/{transcript_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["summary_id"] == body["summary_id"]


async def test_invalid_payload_returns_422(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/transcripts",
        json={"client_name": "Acme", "meeting_title": "Kickoff", "transcript_text": "short"},
    )
    assert resp.status_code == 422


async def test_llm_timeout_returns_504(
    api_client: AsyncClient, mock_claude_client: AsyncMock
) -> None:
    from app.config import get_settings

    mock_claude_client.run.side_effect = TimeoutError()
    app.dependency_overrides[get_extractor] = lambda: MeetingSummaryExtractor(
        agent=mock_claude_client, settings=get_settings().model_copy(update={"llm_max_attempts": 1})
    )
    resp = await api_client.post("/transcripts", json=_payload())
    assert resp.status_code == 504


async def test_llm_extraction_error_returns_502(
    api_client: AsyncClient, mock_claude_client: AsyncMock
) -> None:
    mock_claude_client.run.return_value = {"executive_summary": 12345}
    resp = await api_client.post("/transcripts", json=_payload())
    assert resp.status_code == 502


async def test_get_unknown_transcript_returns_404(api_client: AsyncClient) -> None:
    resp = await api_client.get("/transcripts/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_healthz(api_client: AsyncClient) -> None:
    resp = await api_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_openapi_documents_transcripts_route(api_client: AsyncClient) -> None:
    resp = await api_client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/transcripts" in resp.json()["paths"]
