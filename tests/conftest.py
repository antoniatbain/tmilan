from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import get_settings
from app.db import get_db_session
from app.features.meeting_notes.llm.agent import ClaudeStructuredAgent, MeetingSummaryExtractor
from app.features.meeting_notes.router import get_extractor
from app.main import app


def _test_database_url() -> str:
    url = get_settings().test_database_url
    if not url:
        pytest.exit("TEST_DATABASE_URL is not set. See CLAUDE.md > Local setup.", returncode=1)
    return url


@pytest.fixture(scope="session", autouse=True)
def _migrated_test_db() -> Iterator[None]:
    """Run the real Alembic migrations once against the dedicated test database.

    Deliberately a *sync* fixture invoking a subprocess: alembic's async env.py
    calls asyncio.run(), which cannot nest inside pytest-asyncio's own loop.
    """
    env = {**os.environ, "DATABASE_URL": _test_database_url()}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
    yield


@pytest_asyncio.fixture
async def test_engine() -> AsyncIterator[Any]:
    """Function-scoped, matching this repo's function-scoped asyncio loop per test
    (see asyncio_default_fixture_loop_scope in pyproject.toml) — an engine/connection
    created on one event loop cannot be reused from another."""
    engine = create_async_engine(_test_database_url(), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: Any) -> AsyncIterator[AsyncSession]:
    """Rollback-per-test isolation. THE ONLY DB isolation pattern in this repo."""
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()


CANNED_SUMMARY: dict[str, Any] = {
    "executive_summary": (
        "Acme wants to consolidate three regional ERP instances into one EU instance."
    ),
    "key_decisions": [
        "Consolidate onto the EU instance",
        "Defer the CRM migration to phase 2",
    ],
    "action_items": [
        {
            "description": "Draft the phase-1 cutover plan",
            "owner": "Priya Raman",
            "due_date": "next Friday",
        },
        {
            "description": "Confirm data-residency constraints",
            "owner": "unassigned",
            "due_date": None,
        },
    ],
    "risks": [
        "No named owner for data residency",
        "Phase-2 scope is not yet agreed",
    ],
}


@pytest.fixture
def mock_claude_client() -> AsyncMock:
    """Stand-in for ClaudeStructuredAgent. Shared by unit AND e2e tests."""
    agent = AsyncMock(spec=ClaudeStructuredAgent)
    agent.run.return_value = CANNED_SUMMARY
    return agent


@pytest.fixture(autouse=True)
def _forbid_real_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Safety net: no test can reach the real Claude Agent SDK, even by accident."""

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Tests must never call the real Claude Agent SDK.")

    monkeypatch.setattr("app.features.meeting_notes.llm.agent.query", _boom)


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession, mock_claude_client: AsyncMock
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_extractor] = lambda: MeetingSummaryExtractor(
        agent=mock_claude_client, settings=get_settings()
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
