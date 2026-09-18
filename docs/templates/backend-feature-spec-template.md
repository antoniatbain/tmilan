# Feature Spec: <FEATURE_NAME>

> Fill in every `<...>` placeholder, delete these italic guidance notes, then paste the
> whole document as the kickoff prompt to the agent in a fresh session.
>
> Stack conventions referenced below (directory layout, fixture names, tooling commands) are
> not yet established in this repo. Until a real feature has been implemented and these are
> confirmed against actual code, treat the defaults here as the convention to establish — the
> first agent to use this template should follow them as-is rather than re-deciding them from
> scratch, and should flag in "Assumptions Made" if it had to deviate.

## 0. Agent operating rules (do not delete)

- Stack: FastAPI (async), PostgreSQL (via `<ORM/driver — e.g. SQLAlchemy 2.0 async + Alembic>`),
  pytest, LLM calls via the **Claude Agent SDK**.
- Before writing any code, complete Section 2 (Inputs & Requirements), including the
  **Open Questions** table.
  - **Blocking gap** — anything that changes the API contract, the data model, or the
    security posture: STOP and ask the human. Do not guess.
  - **Non-blocking gap** — naming, a minor default value, internal helper shape: proceed,
    but record the assumption explicitly in an "Assumptions Made" list at the top of your
    final response, so it can be reviewed and corrected.
- Do not start implementation until Sections 1–5 are either filled in by the human or
  explicitly confirmed/completed by you with assumptions flagged.
- The outputs listed in Section 4 are mandatory, not optional: code, tests, and
  CLAUDE.md/rules updates all ship together in the same change.

## 1. Context

- **One-line description:** `<what this feature does>`
- **Why now / problem it solves:** `<business or product driver>`
- **Primary consumer(s):** `<frontend app / another internal service / external API client>`
- **Relevant existing systems it touches:** `<endpoints, tables, LLM prompts already in repo>`
- **Links:** `<ticket/issue, design doc, related PRs>`

## 2. Inputs & Requirements (preliminary stage — complete before coding)

- **Functional requirements:** `<bullet list, plain language>`
- **Data inputs:**
  - Request payload(s) / query params: `<shape, or link to schema>`
  - Existing DB tables/models read or written: `<names, or "none — new table(s)">`
  - External/LLM inputs: `<what context the LLM call needs, and where that context comes from>`
- **Non-goals / explicitly out of scope:** `<list>`
- **Open Questions** *(the agent fills this in as part of its first response; the human
  resolves every blocking row before implementation proceeds)*:

  | # | Question | Why it matters | Blocking? | Assumption if non-blocking |
  |---|----------|-----------------|-----------|------------------------------|
  | 1 | … | … | Y/N | … |

## 3. Workflow

Describe the pipeline as an ordered list. For each step give: trigger/input, what happens,
output, and error handling.

1. **`<Step, e.g. "Request received">`** — input: …; action: …; output: …; errors: …
2. **`<Step, e.g. "Validation">`** — …
3. **`<Step, e.g. "DB read">`** — …
4. **`<Step, e.g. "Prompt construction + Claude Agent SDK call">`** — model: `<model id>`;
   tools exposed to the agent: `<list, or "none">`; expected structured output: `<pydantic
   model/schema>`; timeout/retry policy: `<...>`.
5. **`<Step, e.g. "DB write">`** — transaction boundaries: `<...>`.
6. **`<Step, e.g. "Response returned">`** — response schema: `<...>`.

## 4. Outputs & Deliverables (files this feature must produce)

- **Directory pattern** (one module per feature):

  ```
  app/features/<feature_name>/
    router.py            # FastAPI route(s)
    schemas.py           # Pydantic request/response models
    models.py            # SQLAlchemy models (if new tables)
    service.py           # business logic, orchestrates DB + LLM
    llm/
      prompts.py         # prompt templates — no inline prompt strings in service.py
      agent.py            # Claude Agent SDK client/tool wiring
    CLAUDE.md             # see below

  migrations/versions/<rev>_<feature_name>.py   # if schema changes (Alembic)

  tests/
    unit/<feature_name>/...   # LLM + DB mocked
    e2e/<feature_name>/...    # LLM patched, DB isolated (see §6)
    conftest.py                # shared fixtures live here, not duplicated per feature
  ```

- **CLAUDE.md / rules updates (mandatory):**
  - Add or update `app/features/<feature_name>/CLAUDE.md` documenting: what the module does,
    key conventions/gotchas, how to run it locally, how to run its tests.
  - Update the root `CLAUDE.md` (create it if it doesn't exist yet) to list the new feature
    and any repo-wide convention this feature establishes or relies on.
- **API docs:** docstrings/OpenAPI metadata on the router so `/docs` stays accurate.
- **Migration file** if the DB schema changes — must be reversible (include a working
  `downgrade()`).

## 5. Constraints & Standards

- Follow existing repo patterns for async endpoint style, dependency injection, Pydantic
  model conventions, and error/exception handling — `<link to example file once one exists>`.
  If none exist yet, this feature sets the pattern; say so explicitly in your output.
- **LLM usage constraints:** model = `<e.g. claude-sonnet-5>`; keep prompts in
  `llm/prompts.py`; wrap Claude Agent SDK calls behind a function/class that tests can
  mock/patch (no client instantiated inline and unmockable inside business logic); define an
  explicit timeout and a bounded retry policy; parse/validate all LLM output through a
  Pydantic model — never write raw LLM text into the DB unvalidated.
- **DB constraints:** all writes inside explicit transactions; no destructive migrations
  (dropping a column/table) without an explicit human go-ahead flagged as a blocking Open
  Question; follow existing naming conventions for tables/columns, or establish and document
  one if none exists.
- **Security:** validate all external input at the router boundary; secrets (API keys, DB
  credentials) only via environment variables/secret manager, never hardcoded or logged.
- **Must NOT:**
  - Add a new third-party dependency without flagging it as an Open Question first.
  - Call the real Anthropic API or a real/shared Postgres database from any test.

## 6. Acceptance Criteria & Test Plan (definition of done)

- [ ] Functional criteria met — list as Given/When/Then, one per requirement in §2.
- [ ] **Lint / format / type-check pass:** `<ruff check>` / `<ruff format --check>` /
      `<mypy>` (fill in the actual repo commands once tooling is chosen) all green.
- [ ] **Unit tests (mandatory):**
  - Cover service/business logic in isolation.
  - LLM calls mocked — patch the Claude Agent SDK client via the shared
    `mock_claude_client` fixture in `tests/conftest.py` (add it there if it doesn't exist
    yet; don't redefine it locally).
  - DB mocked, or exercised via a transactional test-session fixture (reuse `db_session`
    from `tests/conftest.py`; don't hand-roll DB setup per test file).
- [ ] **E2E tests (mandatory):**
  - Exercise the endpoint end-to-end through the FastAPI test client (`TestClient` /
    `AsyncClient`).
  - LLM calls still patched to canned, deterministic responses — never hit the real API,
    even in an "integration" test. Reuse the same `mock_claude_client` fixture/plugin.
  - DB isolated so no test pollutes shared state: use a rollback-per-test transaction
    fixture, or a dedicated ephemeral test database/schema created per test run. Pick one
    pattern in `tests/conftest.py` the first time and reuse it everywhere after — don't
    introduce a second isolation strategy later.
  - Any new fixture this feature needs is added to `tests/conftest.py` (or a shared
    fixtures/plugins module) and documented there, not duplicated inside the feature's own
    test folder.
- [ ] Test files mirror source structure: `tests/unit/<feature_name>/...`,
      `tests/e2e/<feature_name>/...`.
- [ ] CLAUDE.md/rules updates from §4 are included in the same change.
- [ ] No secrets committed; no direct calls to real external services from any test.

## 7. Definition of Done

Before declaring the feature done, review your own output against these four checks. They
are subjective/qualitative gates on top of the objective §6 checklist — §6 tells you *what*
must be true, this tells you whether the result actually *feels right* for a production
backend feature.

- [ ] **Relevant** — every file touched (router, service, models, prompts, tests,
      CLAUDE.md) maps directly to a requirement in §2 or a step in §3. No unrelated
      refactors, no files touched outside declared scope, nothing added that isn't traceable
      back to a stated requirement or a flagged, non-blocking assumption.
- [ ] **Sensible** — the design choices (endpoint shape, DB schema, transaction
      boundaries, prompt structure, which tools the LLM agent is given) are ones an
      engineer fluent in FastAPI + SQLAlchemy/Postgres + the Claude Agent SDK would
      recognize as idiomatic for this stack, not a bespoke pattern invented for this one
      feature. Any deviation from an existing repo convention is called out and justified
      in "Assumptions Made", not introduced silently.
- [ ] **Effective** — the feature actually solves the problem in §1 end-to-end, not just
      in isolated unit tests: a human can exercise the golden path described in §3 (call
      the endpoint → see the DB state change → see the LLM-informed result in the
      response) and confirm it behaves as intended, including the primary failure modes
      named in §3/§5 (bad input, LLM timeout, DB conflict).
- [ ] **Complete** — every checkbox in §6 is checked, every blocking row in the §2 Open
      Questions table is resolved (not just flagged), and the CLAUDE.md/rules updates from
      §4 describe the feature accurately enough that another engineer (or agent) could
      extend it without re-reading the full diff.
