# Agent Concurrency Protection

## Goal

Add a concurrency lock to `agent.py` so that at most one LangGraph workflow runs at a time. Callers that arrive while a workflow is running will wait and execute sequentially.

## Changes

### `src/core/agent.py`

- Add `_lock = asyncio.Lock()` module-level variable
- Wrap the body of `invoke()` with `async with _lock`
- Reset `_lock` in tests via `reset_agent_state` fixture

### `tests/test_agent.py`

- Reset `agent_mod._lock` in the existing `reset_agent_state` fixture
- Add one test: two concurrent `invoke()` calls must execute sequentially (second starts only after first completes)

## Non-changes

`message_handler.py` — no changes. Its queue/batching logic is unaffected.
