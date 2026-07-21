# Codex2API GPT-5.5 Stream Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every Shannon model tier through Codex2API `gpt-5.5` and terminate successful SSE streams without a false connection error.

**Architecture:** Keep the existing OpenAI provider and add a deployment-level `OPENAI_BASE_URL` override that takes precedence over YAML defaults. Route all model tiers explicitly to the same catalogued `gpt-5.5` model. Centralize frontend terminal-signal classification in a pure helper and use one completion path for `[DONE]`, `done`, and `STREAM_END`.

**Tech Stack:** Python 3.12, pytest, OpenAI Python SDK, YAML, Docker Compose, Next.js 16, TypeScript 5.9, Node.js 22 test runner, Server-Sent Events.

---

### Task 1: Make the OpenAI Base URL Configurable

**Files:**
- Create: `python/llm-service/tests/test_openai_base_url.py`
- Modify: `python/llm-service/llm_provider/openai_provider.py:20-39`
- Modify: `python/llm-service/llm_provider/manager.py:421-425`

- [ ] **Step 1: Write the failing tests**

```python
from types import SimpleNamespace

from llm_provider.manager import LLMManager
from llm_provider.openai_provider import OpenAIProvider


MODEL_CONFIG = {
    "api_key": "test-key",
    "models": {
        "gpt-5.5": {
            "model_id": "gpt-5.5",
            "tier": "medium",
            "context_window": 400000,
            "max_tokens": 128000,
        }
    },
}


def capture_client(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("llm_provider.openai_provider.AsyncOpenAI", fake_client)
    return captured


def test_environment_base_url_overrides_provider_config(monkeypatch):
    captured = capture_client(monkeypatch)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://www.codex2api.com/v1/")
    OpenAIProvider({**MODEL_CONFIG, "base_url": "https://api.openai.com/v1"})
    assert captured["base_url"] == "https://www.codex2api.com/v1"


def test_provider_config_base_url_is_used_without_environment(monkeypatch):
    captured = capture_client(monkeypatch)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    OpenAIProvider({**MODEL_CONFIG, "base_url": "https://example.test/v1/"})
    assert captured["base_url"] == "https://example.test/v1"


def test_sdk_default_is_preserved_without_any_base_url(monkeypatch):
    captured = capture_client(monkeypatch)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    OpenAIProvider(MODEL_CONFIG)
    assert "base_url" not in captured


def test_unified_config_passes_openai_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    manager = LLMManager.__new__(LLMManager)
    config = {
        "model_catalog": {"openai": MODEL_CONFIG["models"]},
        "model_tiers": {},
        "provider_settings": {
            "openai": {"base_url": "https://api.openai.com/v1"}
        },
    }
    providers, _, _ = manager._translate_unified_config(config)
    assert providers["openai"]["base_url"] == "https://api.openai.com/v1"
```

- [ ] **Step 2: Verify RED**

Run from `python/llm-service`:

```powershell
D:\Software\anaconda\python.exe -m pytest tests/test_openai_base_url.py -q
```

Expected: four failures because the SDK receives no `base_url` and the translator drops it for provider type `openai`.

- [ ] **Step 3: Implement Base URL resolution**

Replace direct SDK construction in `OpenAIProvider.__init__` with:

```python
        client_options = {
            "api_key": api_key,
            "organization": self.organization,
            "timeout": timeout,
        }
        base_url = (
            os.getenv("OPENAI_BASE_URL") or config.get("base_url") or ""
        ).strip().rstrip("/")
        if base_url:
            client_options["base_url"] = base_url
        self.client = AsyncOpenAI(**client_options)
```

Allow the unified translator to retain OpenAI's configured URL:

```python
            if ptype in (
                "openai",
                "openai_compatible",
                "xai",
                "anthropic",
                "minimax",
            ):
```

- [ ] **Step 4: Verify GREEN and commit**

```powershell
D:\Software\anaconda\python.exe -m pytest tests/test_openai_base_url.py -q
git add python/llm-service/tests/test_openai_base_url.py python/llm-service/llm_provider/openai_provider.py python/llm-service/llm_provider/manager.py
git commit -m "fix: support OpenAI-compatible base URL override"
```

Expected: `4 passed` before the commit.

### Task 2: Route All Tiers to GPT-5.5

**Files:**
- Create: `python/llm-service/tests/test_codex2api_model_config.py`
- Modify: `config/models.yaml`
- Modify: `.env.example`
- Modify: `.env` (local only; never commit)
- Modify: `deploy/compose/docker-compose.yml`
- Modify: `deploy/compose/docker-compose.release.yml`

- [ ] **Step 1: Write the failing configuration tests**

```python
from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "models.yaml"


def load_models_config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_all_tiers_prefer_openai_gpt_55():
    config = load_models_config()
    for tier in ("small", "medium", "large"):
        first = config["model_tiers"][tier]["providers"][0]
        assert first["provider"] == "openai"
        assert first["model"] == "gpt-5.5"


def test_gpt_55_exists_in_openai_catalog():
    config = load_models_config()
    model = config["model_catalog"]["openai"]["gpt-5.5"]
    assert model["model_id"] == "gpt-5.5"
    assert model["supports_streaming"] is True
```

- [ ] **Step 2: Verify RED**

```powershell
D:\Software\anaconda\python.exe -m pytest tests/test_codex2api_model_config.py -q
```

Expected: two failures because the tiers use unavailable defaults and the catalog lacks `gpt-5.5`.

- [ ] **Step 3: Add and select GPT-5.5**

Make the first provider for `small`, `medium`, and `large`:

```yaml
      - provider: openai
        model: gpt-5.5
        priority: 1
```

Add under `model_catalog.openai`:

```yaml
    gpt-5.5:
      model_id: gpt-5.5
      tier: medium
      context_window: 400000
      max_tokens: 128000
      supports_functions: true
      supports_streaming: true
      supports_vision: true
```

Do not add guessed pricing; existing default pricing handles the unlisted model.

- [ ] **Step 4: Pass the endpoint through environment and Compose**

Add beside `OPENAI_API_KEY` in `.env` and `.env.example`:

```dotenv
OPENAI_BASE_URL=https://www.codex2api.com/v1
```

Add immediately after `OPENAI_API_KEY` in both Compose files:

```yaml
      - OPENAI_BASE_URL=${OPENAI_BASE_URL:-}
```

Preserve all existing user path and port changes in `docker-compose.release.yml`.

- [ ] **Step 5: Verify tests and Compose parsing**

Run from `python/llm-service`, then from the repository root:

```powershell
D:\Software\anaconda\python.exe -m pytest tests/test_codex2api_model_config.py tests/test_openai_base_url.py -q
docker compose -f deploy/compose/docker-compose.yml config --quiet
docker compose -f deploy/compose/docker-compose.release.yml config --quiet
```

Expected: `6 passed`; both Compose commands exit `0`.

- [ ] **Step 6: Stage only intended configuration and commit**

```powershell
git add .env.example config/models.yaml deploy/compose/docker-compose.yml python/llm-service/tests/test_codex2api_model_config.py
git diff --cached
git commit -m "fix: route Shannon tiers to gpt-5.5"
```

Do not add `.env`. Because `docker-compose.release.yml` already contains user changes, leave that file unstaged unless only the new line can be staged without including unrelated edits.

### Task 3: Close Successful SSE Streams Cleanly

**Files:**
- Create: `desktop/lib/shannon/stream-lifecycle.ts`
- Create: `desktop/lib/shannon/stream-lifecycle.test.ts`
- Modify: `desktop/lib/shannon/stream.ts:4-5,74-84,197-245`

- [ ] **Step 1: Write failing lifecycle tests**

```typescript
import assert from "node:assert/strict";
import test from "node:test";

import {
    isTerminalStreamEvent,
    shouldReportStreamError,
} from "./stream-lifecycle.ts";

test("plain DONE payload is terminal", () => {
    assert.equal(isTerminalStreamEvent("[DONE]"), true);
});

test("named done event is terminal", () => {
    assert.equal(isTerminalStreamEvent(undefined, "done"), true);
});

test("STREAM_END event is terminal", () => {
    assert.equal(isTerminalStreamEvent(undefined, "STREAM_END"), true);
});

test("ordinary message is not terminal", () => {
    assert.equal(isTerminalStreamEvent('{"type":"PROGRESS"}'), false);
});

test("stopped stream does not report a transport error", () => {
    assert.equal(shouldReportStreamError(false), false);
});

test("active stream reports a transport error", () => {
    assert.equal(shouldReportStreamError(true), true);
});
```

- [ ] **Step 2: Verify RED**

Run from `desktop`:

```powershell
node --test lib/shannon/stream-lifecycle.test.ts
```

Expected: `ERR_MODULE_NOT_FOUND` because the helper does not exist.

- [ ] **Step 3: Implement the pure lifecycle helper**

```typescript
const TERMINAL_EVENT_TYPES = new Set(["done", "STREAM_END"]);

export function isTerminalStreamEvent(data?: string, eventType?: string): boolean {
    return TERMINAL_EVENT_TYPES.has(eventType ?? "") || data?.trim() === "[DONE]";
}

export function shouldReportStreamError(shouldReconnect: boolean): boolean {
    return shouldReconnect;
}
```

- [ ] **Step 4: Verify the helper GREEN**

```powershell
node --test lib/shannon/stream-lifecycle.test.ts
```

Expected: `6` tests pass.

- [ ] **Step 5: Use one terminal path in `useRunStream`**

Import the helper:

```typescript
import { isTerminalStreamEvent, shouldReportStreamError } from "./stream-lifecycle";
```

After creating `eventSource`, define:

```typescript
            const completeStream = () => {
                if (!shouldReconnectRef.current) return;
                if (deltaBufferRef.current.size > 0) flushDeltaBuffer();
                dispatch({
                    type: "run/addEvent",
                    payload: {
                        type: "done",
                        workflow_id: workflowId,
                        timestamp: new Date().toISOString(),
                    },
                });
                dispatch(setConnectionState("idle"));
                shouldReconnectRef.current = false;
                eventSource.close();
            };
```

At the start of `handleEvent`, replace the current `[DONE]` return with:

```typescript
                    if (isTerminalStreamEvent(event.data, eventType)) {
                        completeStream();
                        return;
                    }
```

Use the same function for named terminal events:

```typescript
                    if (isTerminalStreamEvent(undefined, type)) {
                        completeStream();
                    } else {
                        handleEvent(event as MessageEvent, type);
                    }
```

Guard `eventSource.onerror` before it flushes or dispatches an error:

```typescript
                if (!shouldReportStreamError(shouldReconnectRef.current)) return;
```

- [ ] **Step 6: Verify frontend tests, lint, and build**

```powershell
node --test lib/shannon/stream-lifecycle.test.ts
npm run lint
npm run build
```

Expected: six lifecycle tests pass, ESLint exits `0`, and Next.js builds successfully.

- [ ] **Step 7: Commit the frontend fix**

```powershell
git add desktop/lib/shannon/stream-lifecycle.ts desktop/lib/shannon/stream-lifecycle.test.ts desktop/lib/shannon/stream.ts
git commit -m "fix: close completed SSE streams cleanly"
```

### Task 4: Regression and End-to-End Verification

**Files:**
- Runtime verification only.

- [ ] **Step 1: Run neighboring backend tests and inspect the diff**

Run from `python/llm-service`:

```powershell
D:\Software\anaconda\python.exe -m pytest tests/test_openai_base_url.py tests/test_codex2api_model_config.py tests/test_manager.py tests/test_provider_selection.py -q
```

Then from the root:

```powershell
git diff --check
git status --short
```

Expected: all selected tests pass, no whitespace errors, and no API key appears in tracked changes.

- [ ] **Step 2: Recreate the LLM service**

```powershell
docker compose -f deploy/compose/docker-compose.release.yml up -d --force-recreate llm-service
docker compose -f deploy/compose/docker-compose.release.yml ps llm-service
```

Expected: `llm-service` becomes healthy. A restart is insufficient because it does not reload `.env`.

- [ ] **Step 3: Verify non-secret runtime configuration**

```powershell
docker compose -f deploy/compose/docker-compose.release.yml exec -T llm-service sh -lc 'test "$OPENAI_BASE_URL" = "https://www.codex2api.com/v1" && grep -q "gpt-5.5" /app/config/models.yaml'
```

Expected: exit `0`; never print `OPENAI_API_KEY`.

- [ ] **Step 4: Submit and stream a real task**

POST `{"query":"请只回复：测试成功","session_id":"<new UUID>"}` to `http://localhost:8080/api/v1/tasks`. Read its workflow ID and connect to `http://localhost:8080/api/v1/stream/sse?workflow_id=<id>` until `[DONE]`, `event: done`, or `event: STREAM_END`.

Expected: a non-empty answer containing `测试成功`, followed by a normal terminal signal.

- [ ] **Step 5: Check state, logs, and browser behavior**

```powershell
docker compose -f deploy/compose/docker-compose.release.yml logs --since 10m llm-service agent-core orchestrator gateway
```

Expected: the task reaches `COMPLETED`; logs show `gpt-5.5`; the request has no `401`, `invalid_api_key`, `No models available`, or new HTTP 500. Repeating the prompt in the running frontend renders the answer and `Task Done` without `Stream connection error`.
