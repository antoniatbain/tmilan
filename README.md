# tmilan / ConsultNotes

An internal API for a consulting team: submit a raw client-call transcript, get back an
LLM-generated structured summary (executive summary, key decisions, action items, risks).

Stack: FastAPI (async) + PostgreSQL (SQLAlchemy 2.0 async + Alembic) + LLM calls via the
Claude Agent SDK, managed with `uv`.

This repo also hosts a reusable spec template for briefing coding agents on new backend
features (`docs/templates/backend-feature-spec-template.md`), and the filled example built
from it (`docs/specs/meeting-notes-poc.md`).

## Setup

```bash
pg_ctlcluster 16 main start   # or however Postgres runs in your environment
su postgres -c "psql -c \"ALTER USER postgres PASSWORD 'postgres';\""
su postgres -c "createdb consultnotes"
su postgres -c "createdb consultnotes_test"

uv sync
cp .env.example .env

uv run alembic upgrade head
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/consultnotes_test \
  uv run alembic upgrade head

uv run uvicorn app.main:app --reload
```

## Tests / lint / types

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

See [`CLAUDE.md`](./CLAUDE.md) for repo conventions and
[`app/features/meeting_notes/CLAUDE.md`](./app/features/meeting_notes/CLAUDE.md) for the
first feature's design notes.
