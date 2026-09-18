from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from claude_agent_sdk import CLINotFoundError

from app.config import Settings
from app.features.meeting_notes.llm.agent import (
    ClaudeStructuredAgent,
    LLMExtractionError,
    LLMTimeoutError,
    LLMUnavailableError,
    MeetingSummaryExtractor,
)
from tests.conftest import CANNED_SUMMARY


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "database_url": "postgresql+asyncpg://x/y",
        "llm_max_attempts": 2,
        "llm_timeout_seconds": 5.0,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


async def _fake_query_yielding(*messages: object):
    for message in messages:
        yield message


class TestClaudeStructuredAgentRun:
    async def test_returns_structured_output_when_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result_message = SimpleNamespace(structured_output=CANNED_SUMMARY, subtype="success")
        monkeypatch.setattr(
            "app.features.meeting_notes.llm.agent.query",
            lambda **_: _fake_query_yielding(result_message),
        )
        agent = ClaudeStructuredAgent(_settings())
        out = await agent.run(system_prompt="sp", user_prompt="up", json_schema={})
        assert out == CANNED_SUMMARY

    async def test_ignores_leading_system_message_before_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression test: a real run starts with a SystemMessage(subtype="init") that
        has no `structured_output` attribute at all but DOES have `subtype` — treating any
        message with a `subtype` as terminal (instead of gating on `structured_output`)
        caused the live smoke test to fail on the very first message."""
        system_message = SimpleNamespace(subtype="init")  # no structured_output attribute
        result_message = SimpleNamespace(structured_output=CANNED_SUMMARY, subtype="success")
        monkeypatch.setattr(
            "app.features.meeting_notes.llm.agent.query",
            lambda **_: _fake_query_yielding(system_message, result_message),
        )
        agent = ClaudeStructuredAgent(_settings())
        out = await agent.run(system_prompt="sp", user_prompt="up", json_schema={})
        assert out == CANNED_SUMMARY

    async def test_raises_extraction_error_on_bad_subtype_with_no_structured_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result_message = SimpleNamespace(
            structured_output=None, subtype="error_max_structured_output_retries"
        )
        monkeypatch.setattr(
            "app.features.meeting_notes.llm.agent.query",
            lambda **_: _fake_query_yielding(result_message),
        )
        agent = ClaudeStructuredAgent(_settings())
        with pytest.raises(LLMExtractionError):
            await agent.run(system_prompt="sp", user_prompt="up", json_schema={})

    async def test_raises_extraction_error_when_stream_ends_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.features.meeting_notes.llm.agent.query",
            lambda **_: _fake_query_yielding(),
        )
        agent = ClaudeStructuredAgent(_settings())
        with pytest.raises(LLMExtractionError):
            await agent.run(system_prompt="sp", user_prompt="up", json_schema={})


class TestMeetingSummaryExtractor:
    async def test_retries_on_timeout_then_raises(self) -> None:
        agent = AsyncMock(spec=ClaudeStructuredAgent)
        agent.run.side_effect = TimeoutError()
        extractor = MeetingSummaryExtractor(agent=agent, settings=_settings(llm_max_attempts=2))
        with pytest.raises(LLMTimeoutError):
            await extractor.extract(
                client_name="Acme",
                meeting_title="Kickoff",
                meeting_date=None,
                transcript_text="x" * 100,
            )
        assert agent.run.call_count == 2

    async def test_does_not_retry_on_validation_error(self) -> None:
        agent = AsyncMock(spec=ClaudeStructuredAgent)
        agent.run.return_value = {"executive_summary": 12345}  # wrong type, missing fields
        extractor = MeetingSummaryExtractor(agent=agent, settings=_settings(llm_max_attempts=3))
        with pytest.raises(LLMExtractionError):
            await extractor.extract(
                client_name="Acme",
                meeting_title="Kickoff",
                meeting_date=None,
                transcript_text="x" * 100,
            )
        assert agent.run.call_count == 1

    async def test_does_not_retry_on_cli_not_found(self) -> None:
        agent = AsyncMock(spec=ClaudeStructuredAgent)
        agent.run.side_effect = CLINotFoundError("no cli")
        extractor = MeetingSummaryExtractor(agent=agent, settings=_settings(llm_max_attempts=3))
        with pytest.raises(LLMUnavailableError):
            await extractor.extract(
                client_name="Acme",
                meeting_title="Kickoff",
                meeting_date=None,
                transcript_text="x" * 100,
            )
        assert agent.run.call_count == 1

    async def test_happy_path_returns_validated_output(self) -> None:
        agent = AsyncMock(spec=ClaudeStructuredAgent)
        agent.run.return_value = CANNED_SUMMARY
        extractor = MeetingSummaryExtractor(agent=agent, settings=_settings())
        out = await extractor.extract(
            client_name="Acme",
            meeting_title="Kickoff",
            meeting_date=None,
            transcript_text="x" * 100,
        )
        assert out.executive_summary == CANNED_SUMMARY["executive_summary"]
