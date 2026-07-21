# Codex2API GPT-5.5 Stream Fix Design

## Problem

The frontend can submit a task and establish the SSE connection, but the task
fails when the LLM service calls OpenAI. The configured key belongs to
Codex2API, while `OpenAIProvider` always uses the official OpenAI endpoint.
OpenAI therefore returns `401 invalid_api_key`.

The configured fallback also fails because no enabled fallback provider has a
model for the requested `small` tier. The resulting HTTP 500 closes the SSE
response. The frontend then reports the close as `Stream connection error`,
which hides the actual model-provider failure. It also ignores a plain
`[DONE]` message instead of closing the stream cleanly.

Read-only verification established that:

- `https://www.codex2api.com/v1/models` accepts the configured key.
- `gpt-5.5` is available from Codex2API.
- The repository defaults `gpt-5-nano-2025-08-07`,
  `gpt-5-mini-2025-08-07`, and `gpt-5.1` are not available there.
- Gateway, orchestrator, agent-core, Redis, Postgres, Temporal, and llm-service
  containers are healthy.

## Selected Approach

Keep the existing `openai` provider name, but make its base URL configurable.
This is smaller than adding a Codex2API-specific provider and keeps the same
configuration usable with official OpenAI or another compatible endpoint.

Set all three Shannon model tiers to `gpt-5.5`, as requested. Use environment
configuration for the endpoint and secret so neither value is hard-coded into
provider logic.

## Backend Changes

1. Add `OPENAI_BASE_URL=https://www.codex2api.com/v1` to the local `.env`.
2. Pass `OPENAI_BASE_URL` from Compose to `llm-service`.
3. Make `OpenAIProvider` construct `AsyncOpenAI` with a base URL whose
   precedence is:
   - `OPENAI_BASE_URL` environment variable;
   - explicit provider configuration;
   - OpenAI SDK default.
4. Permit the unified model configuration translator to pass an OpenAI base
   URL to `OpenAIProvider`.
5. Add `gpt-5.5` to the OpenAI model catalog and select it for `small`,
   `medium`, and `large` tiers. Do not invent provider pricing; unlisted-model
   default pricing remains in effect until Codex2API pricing is supplied.

## Frontend Changes

Treat plain `[DONE]`, named `done`, and `STREAM_END` as successful terminal
events through one shared terminal path. That path must:

- flush pending text deltas;
- dispatch one terminal `done` event;
- set the connection state to `idle`;
- disable reconnects;
- close the `EventSource`.

`EventSource.onerror` must first check whether the stream was deliberately
terminated. A deliberate terminal close must not dispatch a synthetic
`Stream connection error`. Genuine transport failures continue to use the
existing retry and error behavior.

Server-sent `error` and `WORKFLOW_FAILED` events remain task failures and are
shown by the existing Redux/task-detail logic. They are not reclassified as
transport failures.

## Testing

Backend unit tests will verify that:

- `OPENAI_BASE_URL` reaches `AsyncOpenAI`;
- `OPENAI_BASE_URL` takes precedence over explicit provider configuration;
- absence of both preserves the SDK default behavior;
- unified configuration retains the OpenAI base URL.

Frontend tests will exercise a small extracted stream-terminal helper so the
behavior can be tested without a browser-owned `EventSource` implementation.
They will verify that `[DONE]` is terminal and that a close after terminal
completion is not treated as a connection failure.

After unit tests and builds pass, recreate `llm-service` so it reads the new
environment variable. Submit a real task through the gateway and consume its
SSE stream. Success requires:

- the LLM request uses Codex2API and `gpt-5.5`;
- the task returns a non-empty answer;
- the task reaches `COMPLETED`;
- the stream ends without `Stream connection error`;
- backend logs contain no OpenAI `401 invalid_api_key` for the verification
  request.

## Scope

This change does not introduce a new provider abstraction, alter authentication,
change existing local port mappings, or modify unrelated Compose volume paths.
It does not expose or commit the API key.
