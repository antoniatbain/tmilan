# ConsultNotes — Feature Spec: meeting_notes

> This is the filled-in output of `docs/templates/backend-feature-spec-template.md`,
> combined with its Definition of Done, for the first real feature built with that
> template: **ConsultNotes**, an internal API for a consulting team. This whole document is
> what got pasted as the kickoff prompt to build the feature (see "Kickoff prompt" at the
> bottom) — the sections above it are the filled template itself, kept as the traceable
> record of what was asked for.

## 0. Agent operating rules

- Stack: FastAPI (async), PostgreSQL via SQLAlchemy 2.0 async + Alembic, pytest, LLM calls
  via the Claude Agent SDK.
- Blocking gaps require a stop-and-ask; non-blocking gaps may proceed with a flagged
  assumption. See "Assumptions Made" below for every non-blocking call made on this feature.
- Outputs (code + tests + CLAUDE.md/rules) ship together in the same change — done below.

## 1. Context

- **One-line description:** A consultant submits the raw transcript of a client call or
  workshop; the API persists it, uses an LLM to extract a structured record (executive
  summary, key decisions, action items with owners, risks), persists that record, and
  returns it.
- **Why now / problem it solves:** Consulting teams currently write up meeting notes by
  hand after every client session — slow, inconsistent in structure, and easy to lose action
  items in. This automates the first draft so a human only has to review and correct it.
- **Primary consumer(s):** Internal tooling used by consultants on an engagement (a future
  frontend or Slack bot would call this API; out of scope here).
- **Relevant existing systems it touches:** None — this is the first feature in the repo, so
  it establishes the conventions (directory layout, DB isolation pattern, LLM wrapper shape)
  documented in the root `CLAUDE.md`.
- **Links:** N/A (proof-of-concept, no ticket).

## 2. Inputs & Requirements

- **Functional requirements:**
  - Accept `{client_name, meeting_title, meeting_date?, transcript_text}` and persist the
    transcript.
  - Call an LLM to extract `{executive_summary, key_decisions[], action_items[{description,
    owner, due_date?}], risks[]}` from the transcript.
  - Persist the structured result linked to the transcript and return the combined record.
  - Allow fetching a previously generated summary by transcript id.
- **Data inputs:**
  - Request payload: see above; `transcript_text` bounded 50–200,000 characters.
  - Existing DB tables/models read or written: none existing — new tables `transcripts` and
    `meeting_summaries`.
  - LLM input: the transcript text plus client/meeting metadata, per `llm/prompts.py`.
- **Non-goals / explicitly out of scope:** re-summarizing an existing transcript; editing a
  generated summary; authentication/authorization (internal PoC); listing/searching past
  transcripts; any frontend.
- **Open Questions — resolved:**

  | # | Question | Why it matters | Blocking? | Resolution |
  |---|----------|-----------------|-----------|------------|
  | 1 | One summary per transcript, or allow re-runs? | Affects schema (unique constraint vs. history table) | N | Non-blocking — assumed one-summary-per-transcript for this walking skeleton; re-summarization is a documented non-goal. |
  | 2 | Structured LLM fields as JSONB or child tables? | Affects schema complexity | N | Non-blocking — JSONB, since the shape is already owned and validated by the `MeetingSummaryLLMOutput` Pydantic model; three extra tables would be scope creep. |
  | 3 | `due_date` as a real date or free text? | Affects schema type and LLM reliability | N | Non-blocking — free text. Forcing ISO dates from phrases like "next Friday" was judged the most likely cause of a structured-output retry failure. |
  | 4 | Which model, and what timeout/retry budget? | Cost/latency | N | Non-blocking — `claude-opus-5`, 120s per-attempt timeout, 2 attempts total, linear backoff; retries only on timeout/transport errors, never on schema-validation failure (the SDK already re-prompts internally on that). |
  | 5 | Hold one DB transaction across the whole request, or split around the LLM call? | Connection-pool/consistency trade-off | **Y** | Resolved: two transactions (transcript insert, then summary insert), LLM call outside any transaction. Trade-off documented in `service.py` and the feature CLAUDE.md: an LLM failure leaves a transcript row with no summary rather than pinning a pool connection for a ~2-minute call. |

## 3. Workflow

1. **Request received** — `POST /transcripts` with the JSON payload above; FastAPI/Pydantic
   validate shape and bounds; invalid input → 422.
2. **Persist transcript** — insert into `transcripts`, commit, capture its id.
3. **LLM extraction** — build the system + user prompt (`llm/prompts.py`), call the Claude
   Agent SDK with `output_format` set to the `MeetingSummaryLLMOutput` JSON schema, no tools,
   `setting_sources=[]` (so this repo's own CLAUDE.md files are never injected into the
   extraction call). Timeout 120s per attempt, up to 2 attempts total.
4. **Validate output** — the SDK's structured-output loop already re-prompts internally on
   schema mismatch; the returned dict is validated again through `MeetingSummaryLLMOutput`
   before anything touches the DB.
5. **Persist summary** — insert into `meeting_summaries`, linked to the transcript, commit.
6. **Response returned** — combined transcript + summary fields as `MeetingSummaryResponse`.
   Failure modes map to HTTP: LLM timeout → 504, LLM/CLI unavailable → 503, schema validation
   failure → 502.

## 4. Outputs & Deliverables

```
app/
  config.py, db.py, main.py
  features/meeting_notes/
    router.py, schemas.py, models.py, service.py
    llm/{prompts.py, agent.py}
    CLAUDE.md
migrations/versions/0001_meeting_notes.py
tests/
  conftest.py
  unit/meeting_notes/{test_schemas,test_agent,test_service}.py
  e2e/meeting_notes/test_ingest_endpoint.py
CLAUDE.md (root)
docs/specs/meeting-notes-poc.md   (this file)
```

All delivered in the `claude/meeting-notes-poc` branch alongside this spec.

## 5. Constraints & Standards

- Async-only DB access; service owns transaction boundaries, the FastAPI dependency only
  yields the session.
- All prompts in `llm/prompts.py`; all LLM access through `MeetingSummaryExtractor`, injected
  via `Depends`, never instantiated inline in business logic.
- LLM output is never trusted into the DB unvalidated — always through the Pydantic contract.
- No destructive migrations without explicit sign-off (n/a here — additive only).
- Secrets (Anthropic auth) only via environment, never hardcoded/logged.
- Tests never call the real Anthropic API or a shared/production database.

## 6. Acceptance Criteria & Test Plan

- [x] Functional criteria met (ingest → extract → persist → return; fetch by id).
- [x] `ruff check .`, `ruff format --check .`, `mypy app` all pass.
- [x] Unit tests: schema validation, LLM transport + extractor (timeout retry, no-retry on
      validation/CLI errors, regression test for the leading-`SystemMessage` bug found during
      the live smoke test), service (DB writes, partial-state-on-LLM-failure behavior).
- [x] E2E tests: full request/response cycle through the FastAPI test client, LLM mocked,
      422/502/504/404 paths, `/healthz` and `/openapi.json` sanity checks.
- [x] DB isolation verified empirically: ran the suite twice, confirmed zero rows left in
      `consultnotes_test` afterward.
- [x] Migration reversibility verified empirically: ran `upgrade → downgrade → upgrade`, not
      just eyeballed `downgrade()`.
- [x] CLAUDE.md (root + feature) shipped in the same change.
- [x] No secrets committed; automated tests never call the real API or a shared DB.

## 7. Definition of Done — self-check

- **Relevant** — every file above maps to a requirement in §2 or a step in §3; nothing was
  added outside that scope.
- **Sensible** — the design (two-transaction service, JSONB for the LLM-shaped fields,
  duck-typed `ClaudeStructuredAgent` transport, rollback-per-test DB isolation) matches
  idiomatic FastAPI/SQLAlchemy/pytest-asyncio practice; every deviation from a "default"
  choice is logged as a non-blocking Open Question above, not introduced silently.
- **Effective** — the golden path was exercised for real, not just in mocked tests: a live
  server call with a real, realistic transcript produced a genuinely useful structured
  summary via a real Claude Agent SDK call (see "Live run result" below), and the 422/404/
  502/504 failure paths were also verified live or in e2e tests.
- **Complete** — every §6 box is checked, both Open Questions marked blocking were resolved
  before merge, and root + feature CLAUDE.md describe the feature and its gotchas well enough
  to extend without re-reading the diff.

## Assumptions Made (non-blocking Open Questions, resolved unilaterally)

1. One summary per transcript (no re-summarization) — see Open Question #1.
2. JSONB for `key_decisions`/`action_items`/`risks` instead of child tables — Open Question #2.
3. `due_date` as free text, not a date type — Open Question #3.
4. Model `claude-opus-5`, 120s timeout, 2 attempts, linear backoff, no retry on schema-
   validation failure — Open Question #4.
5. Ruff + mypy chosen as the repo's lint/type-check tooling (none existed before this PoC).
6. `tests/conftest.py`'s rollback-per-test-transaction pattern (over an ephemeral DB per
   test) — chosen because no Docker daemon is reachable in this environment and a single
   fast, reusable isolation pattern was required for the whole repo, not just this feature.

## Known environment note

This PoC ran in a sandbox where Postgres 16 had to be started manually (`pg_ctlcluster 16
main start` — no systemd, no Docker daemon), and no `ANTHROPIC_API_KEY` is configured.
Despite that, a real, live Claude Agent SDK call succeeded (see "Live run result" below) —
this sandbox's Claude Code session brokers Anthropic access without a discrete API key. That
is a property of this sandbox, not of the code: anywhere else, `ANTHROPIC_API_KEY` (or
another supported Claude Agent SDK auth method) must be configured for LLM calls to work.

## Live run result

`POST /transcripts` against the running server, with a realistic ~450-word supply-chain
discovery-workshop transcript, returned (in ~23s) a real LLM-generated executive summary, 6
key decisions, 5 action items (each with an owner — including correctly leaving one
unassigned where the transcript named no owner), and 8 risks — all grounded in the transcript
text, not fabricated. `GET /transcripts/{id}` round-tripped the same record. This was a real
Claude Agent SDK call, not a mock.

---

## Kickoff prompt (as combined and used to drive this build)

I am a tech lead who frequently briefs coding agents to build backend features for our
internal tools. I want to create a **backend-feature implementation agent** that I can call
on whenever I need to build a new feature for one of these apps. Here is the full brief,
combining our reusable spec template and its Definition of Done, filled in for our first
real case:

**[SPEC]** — Sections 1–6 above (Feature Spec: meeting_notes).

**[DOD]** — Section 7 above (Definition of Done — self-check).

Before presenting your outputs, review them against this Definition of Done and address any
gaps.

Once you create the workflow, please also create a set of sample data (a realistic
transcript) that I can use to test the output. *(Done — see the live-run transcript used
above, and reusable as a fixture for future manual smoke tests.)*

Additionally, please explain to me how I can make this agent easily accessible and reusable
every time I need to run this workflow on a different feature with different business
context. *(See "Reusing this workflow" in the root `CLAUDE.md`.)*
