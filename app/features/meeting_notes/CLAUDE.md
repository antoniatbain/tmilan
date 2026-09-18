# meeting_notes

Ingests a raw client-call/workshop transcript and returns an LLM-generated structured
summary (executive summary, key decisions, action items with owners, risks). The first
feature built in this repo — see `docs/specs/meeting-notes-poc.md` for the full spec, and the
root `CLAUDE.md` for the conventions it established.

## Endpoint contract

- `POST /transcripts` → 201 `MeetingSummaryResponse`. 422 on invalid input (transcript text
  must be 50–200,000 chars). 502 if the LLM output fails schema validation, 503 if the
  Claude Agent SDK/CLI is unavailable, 504 on LLM timeout.
- `GET /transcripts/{transcript_id}` → the persisted summary, or 404.

## Gotchas worth knowing before touching this module

- **Two transactions, not one.** `service.py` commits the transcript insert, then calls the
  LLM *outside* any transaction, then commits the summary insert. Holding a transaction open
  across a ~2-minute LLM call would pin a pool connection per in-flight request. The
  consequence: an LLM failure leaves a `transcripts` row with no matching `meeting_summaries`
  row. That's the intended, honest partial state — the transcript *was* received — not a bug.
  Confirmed live: a failed early attempt during development left exactly this state in the DB.
- **`MeetingSummaryLLMOutput` is the schema**, not a suggestion. Its `model_json_schema()` is
  handed to `ClaudeAgentOptions(output_format=...)`, and the SDK's own structured-output loop
  re-prompts internally on mismatch before we ever see a result. We validate again with
  `model_validate()` before anything touches the DB — two independent gates.
- **`setting_sources=[]` is required** in `llm/agent.py`'s `ClaudeAgentOptions`. Without it,
  the SDK loads this repo's own CLAUDE.md files into every extraction call, which pollutes
  the prompt with irrelevant repo docs.
- **The transcript goes over stdin, not argv** (`_stdin_messages` async generator passed as
  `prompt=`). A plain string prompt is a single CLI argv entry and a full workshop transcript
  can exceed Linux's per-arg length limit.
- **`ClaudeStructuredAgent.run()` duck-types on `structured_output`, not
  `isinstance(message, ResultMessage)`** — checking `hasattr(message, "structured_output")`
  is what distinguishes the terminal `ResultMessage` from every other message type in the
  stream. **Do not "simplify" this to checking `subtype` alone**: `SystemMessage` also has a
  `subtype` (e.g. `"init"`), and treating any message with a `subtype` as terminal breaks the
  very first message of every real run — this exact bug was caught by the live smoke test
  (not by the mocked unit tests, which is why `test_ignores_leading_system_message_before_result`
  in `tests/unit/meeting_notes/test_agent.py` exists as a regression test).
- **Timeout/retry policy**: 120s per attempt (`asyncio.wait_for`), 2 attempts total, 1s
  linear backoff. Retries only happen on `TimeoutError` or SDK transport errors
  (`CLINotFoundError`/`ProcessError`/`CLIConnectionError` → raised immediately as
  non-retryable `LLMUnavailableError`, no point retrying a missing CLI). A schema-validation
  failure (`ValidationError`) is also not retried — the SDK already re-prompted once
  internally, so retrying at this layer would just pay for the same failure again.
- **`due_date` on `ActionItem` is a free-text string, not a date.** Forcing the model to
  produce ISO dates from phrases like "next Friday" was judged the likely cause of
  `error_max_structured_output_retries` failures — deliberately not attempted.

## Running just this feature

```bash
uv run pytest tests/unit/meeting_notes tests/e2e/meeting_notes
```

## Manual smoke test

```bash
uv run uvicorn app.main:app --reload
curl -X POST localhost:8000/transcripts -H "Content-Type: application/json" -d '{
  "client_name": "Acme Corp",
  "meeting_title": "Kickoff",
  "transcript_text": "... at least 50 characters of transcript ..."
}'
```
This makes a **real** Claude Agent SDK call (never mocked outside the automated test suite) —
see the root CLAUDE.md's "Known environment limitation" note on what auth this needs.
