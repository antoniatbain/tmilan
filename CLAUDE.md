# tmilan / ConsultNotes

Internal API: FastAPI + PostgreSQL (SQLAlchemy 2.0 async + Alembic) + LLM calls via the
**Claude Agent SDK** (`claude-agent-sdk` on PyPI). Dependency management via `uv`.

This repo also holds a reusable spec template for briefing coding agents on new backend
features: `docs/templates/backend-feature-spec-template.md`. `meeting_notes` (below) is the
first feature built from it — see `docs/specs/meeting-notes-poc.md` for the filled spec,
Definition of Done, and the combined kickoff prompt used to build it.

## Conventions established by the first feature (`meeting_notes`) — follow these for new features

- **Directory pattern**, one module per feature:
  ```
  app/features/<feature_name>/
    router.py      # FastAPI routes only — no business logic
    schemas.py      # Pydantic request/response models + the LLM output contract model
    models.py        # SQLAlchemy models
    service.py         # orchestration; owns transaction boundaries
    llm/
      prompts.py           # all prompt strings live here, never inline in service.py
      agent.py               # thin SDK transport + a domain extractor class
    CLAUDE.md
  ```
- **Async only.** No sync SQLAlchemy sessions anywhere.
- **Service owns transactions.** `app/db.py:get_db_session` only yields a session; `begin()`
  calls happen in `service.py`.
- **Domain exceptions live in the feature module** (e.g. `llm/agent.py`'s `LLMTimeoutError`
  etc.); **HTTP mapping lives in `app/main.py`** via `@app.exception_handler(...)`.
- **LLM access only through an injected extractor class** (`Depends(get_extractor)` in the
  router) — never instantiate an SDK client inline inside business logic. This is what makes
  it mockable.
- **`setting_sources=[]`** on every `ClaudeAgentOptions` used for a feature call — otherwise
  the SDK loads this repo's own CLAUDE.md files into the conversation, which you do not want
  for a narrow extraction call.
- **Tests never call the real Anthropic API or a shared/production database.** Shared
  fixtures live in `tests/conftest.py`: `db_session` (rollback-per-test-transaction against a
  dedicated `consultnotes_test` database — **the only DB isolation pattern in this repo**,
  don't introduce a second one), `mock_claude_client` (`AsyncMock(spec=ClaudeStructuredAgent)`),
  and an autouse `_forbid_real_llm` fixture that makes any real SDK call raise even if a test
  forgets to mock it.
- Test files mirror source: `tests/unit/<feature_name>/`, `tests/e2e/<feature_name>/`.

## Local setup

```bash
# 1. Start Postgres (this sandbox has no systemd/Docker daemon; adjust if yours does)
pg_ctlcluster 16 main start
su postgres -c "psql -c \"ALTER USER postgres PASSWORD 'postgres';\""
su postgres -c "createdb consultnotes"
su postgres -c "createdb consultnotes_test"

# 2. Install deps
uv sync

# 3. Copy env and adjust if needed
cp .env.example .env

# 4. Migrate both databases
uv run alembic upgrade head
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/consultnotes_test \
  uv run alembic upgrade head

# 5. Run the app
uv run uvicorn app.main:app --reload

# 6. Run tests / lint / types
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

## Known environment limitation (this sandbox)

No `ANTHROPIC_API_KEY` is set here — this sandbox's Claude Code session brokers Anthropic
access itself, and a live Claude Agent SDK call from this repo's code worked anyway (see
`docs/specs/meeting-notes-poc.md`). That is specific to this sandbox. In any other
environment, set `ANTHROPIC_API_KEY` (or another Claude Agent SDK-supported auth method) for
LLM calls to work — the automated test suite never depends on it either way, since LLM calls
are always mocked in tests.

## Reusing this workflow for a new feature

1. Copy `docs/templates/backend-feature-spec-template.md`, fill it in for the new feature
   (business case, inputs, workflow, outputs, constraints, acceptance criteria), then fill in
   its Definition of Done section.
2. Combine both into a single kickoff prompt exactly as done in
   `docs/specs/meeting-notes-poc.md` (the "Kickoff prompt" section at the bottom is the
   literal text used) and paste it as the first message to a fresh agent session.
3. The agent resolves the spec's Open Questions table first (stop-and-ask on blocking gaps,
   flag-and-proceed on non-blocking ones), then builds following the directory pattern and
   testing conventions above — it doesn't need to re-derive them, they're already documented
   here and demonstrated end-to-end by `meeting_notes`.
4. Save the filled spec + DoD + kickoff prompt as `docs/specs/<feature-name>.md` in the same
   change, the same way this one was — that's what keeps the "what was asked for" record next
   to the code it produced.

## Features

- `meeting_notes` — see `app/features/meeting_notes/CLAUDE.md` and
  `docs/specs/meeting-notes-poc.md`.
