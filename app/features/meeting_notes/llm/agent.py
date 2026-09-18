import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from datetime import date
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    CLIConnectionError,
    CLINotFoundError,
    ProcessError,
    query,
)
from pydantic import ValidationError

from app.config import Settings
from app.features.meeting_notes.llm.prompts import SYSTEM_PROMPT, build_extraction_prompt
from app.features.meeting_notes.schemas import MeetingSummaryLLMOutput

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base class for all LLM-call failures raised by this module."""


class LLMTimeoutError(LLMError):
    """The call did not complete within the configured timeout. Retryable."""


class LLMUnavailableError(LLMError):
    """The Claude Agent SDK/CLI could not be reached or crashed. Not retryable."""


class LLMExtractionError(LLMError):
    """The model did not return output matching the required schema. Not retryable."""


class ClaudeStructuredAgent:
    """Thin transport over the Claude Agent SDK: one-shot, no-tools, structured-output call.

    This is the seam tests mock — see tests/conftest.py:mock_claude_client. Duck-types on
    ``structured_output``/``subtype`` instead of isinstance-checking ResultMessage, so a
    fake in tests only needs those two attributes, not every field of the real dataclass.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        options = ClaudeAgentOptions(
            model=self._settings.llm_model,
            system_prompt=system_prompt,
            output_format={"type": "json_schema", "schema": json_schema},
            tools=[],
            permission_mode="dontAsk",
            max_turns=self._settings.llm_max_turns,
            setting_sources=[],  # do NOT load repo CLAUDE.md/settings into extraction calls
            stderr=lambda line: logger.debug("claude-cli: %s", line),
        )

        async def _stdin_messages() -> AsyncIterator[dict[str, Any]]:
            yield {"type": "user", "message": {"role": "user", "content": user_prompt}}

        # query() is a real async generator at runtime (has aclose()); its declared
        # return type is the plain AsyncIterator protocol, which mypy doesn't consider
        # aclosing()-compatible.
        async with aclosing(query(prompt=_stdin_messages(), options=options)) as stream:  # type: ignore[type-var]
            async for message in stream:
                # Only ResultMessage carries `structured_output` — SystemMessage also has
                # a `subtype` attribute (e.g. "init"), so checking hasattr() here (rather
                # than isinstance(message, ResultMessage), which would make this harder to
                # fake in tests) is what keeps us from treating the initial system message
                # as if it were the final result.
                if not hasattr(message, "structured_output"):
                    continue
                structured = message.structured_output
                if structured is not None:
                    return structured
                subtype = getattr(message, "subtype", None)
                raise LLMExtractionError(f"run ended with subtype={subtype!r}")
        raise LLMExtractionError("stream ended without a result message")


class MeetingSummaryExtractor:
    """Domain seam the service depends on. Owns timeout, bounded retry, and validation."""

    def __init__(self, agent: ClaudeStructuredAgent, settings: Settings) -> None:
        self._agent = agent
        self.settings = settings

    async def extract(
        self,
        *,
        client_name: str,
        meeting_title: str,
        meeting_date: date | None,
        transcript_text: str,
    ) -> MeetingSummaryLLMOutput:
        schema = MeetingSummaryLLMOutput.model_json_schema()
        user_prompt = build_extraction_prompt(
            client_name=client_name,
            meeting_title=meeting_title,
            meeting_date=meeting_date,
            transcript_text=transcript_text,
        )

        last_error: LLMError | None = None
        for attempt in range(1, self.settings.llm_max_attempts + 1):
            try:
                raw = await asyncio.wait_for(
                    self._agent.run(
                        system_prompt=SYSTEM_PROMPT,
                        user_prompt=user_prompt,
                        json_schema=schema,
                    ),
                    timeout=self.settings.llm_timeout_seconds,
                )
                return MeetingSummaryLLMOutput.model_validate(raw)
            except TimeoutError as exc:
                last_error = LLMTimeoutError(
                    f"LLM call timed out after {self.settings.llm_timeout_seconds}s "
                    f"(attempt {attempt}/{self.settings.llm_max_attempts})"
                )
                last_error.__cause__ = exc
            except (CLINotFoundError, ProcessError, CLIConnectionError) as exc:
                raise LLMUnavailableError("Claude Agent SDK/CLI is unavailable") from exc
            except ValidationError as exc:
                # The SDK already re-prompted internally on schema mismatch; retrying
                # here would just pay for the same failure again.
                raise LLMExtractionError("LLM output failed schema validation") from exc

            if attempt < self.settings.llm_max_attempts:
                await asyncio.sleep(1.0 * attempt)

        assert last_error is not None
        raise last_error
