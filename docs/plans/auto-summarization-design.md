# Auto-Summarization & Unified Invoke Design

## Overview

Two related changes:

1. **Auto-summarization**: Compress `_history` when context grows too large or the session goes idle.
2. **Unified `_invoke`**: Remove `_invoke_bare`; route all LLM calls through `_invoke(reason, ...)`, with the graph branching by reason.

---

## Configuration

New file `config/agent/settings.yaml` (copy from `settings.yaml.example`):

```yaml
context_limit_tokens: 8000       # input_tokens threshold to trigger mid-conversation summarization
timeout_summarize_seconds: 1800  # idle seconds before summarizing the full session
timeout_clear_seconds: 3600      # idle seconds after summarization before clearing history
```

`agent.py` exposes `load_settings() -> dict` to read this file (with hardcoded defaults if absent).

---

## `agent.py`

### State

```python
class _State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    reason: Literal["user_message", "scheduled_task", "complex_reschedule", "session_timeout"]
```

No extra field for structured output — `utility_node` serializes its result to JSON in the last message's `content`; the caller parses it with `Model.model_validate_json(result)`.

### `_invoke` signature

```python
async def _invoke(
    reason: Literal["user_message", "scheduled_task", "complex_reschedule", "session_timeout"],
    message: str = "",
    *,
    messages: list[BaseMessage] | None = None,  # complex_reschedule: full custom message list
    schema: type | None = None,                 # complex_reschedule: Pydantic schema
) -> str
```

State initialization by reason:
- `user_message` / `scheduled_task`: `_history + [HumanMessage(message)]`
- `session_timeout`: `_history` only (no new message)
- `complex_reschedule`: `messages` directly (no `_history`)

`_invoke_bare` is removed.

### History management

Nodes write to `_history` directly (`global _history`). `_invoke` does **not** update `_history` after the graph completes.

| Node | `_history` effect |
|---|---|
| `llm_node` | appends AI response |
| `summarize_node` | replaces with `[SystemMessage(summary)] + last_turn` |
| `summarize_all_node` | replaces with `[SystemMessage(summary)]` |
| `utility_node` | no change |

### Graph structure

```
START → route_by_reason
  ├─ user_message / scheduled_task
  │     → llm_node → route_after_llm
  │                    ├─ tool_calls → tools → llm_node
  │                    ├─ over_limit → summarize_node → END
  │                    └─ done       → END
  ├─ complex_reschedule → utility_node → END
  └─ session_timeout    → summarize_all_node → END
```

### `route_after_llm`

```python
def route_after_llm(state):
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    if (last.usage_metadata or {}).get("input_tokens", 0) > settings["context_limit_tokens"]:
        return "summarize"
    return END
```

### New public function

```python
def clear_history() -> None:
    global _history
    _history = []
```

---

## `scheduler.py`

### `init_timeout(apscheduler)`

Called once at startup by `scheduled_tasks.register()`. Stores the APScheduler instance.

### Timeout logic in `enqueue`

On every `enqueue`, reschedule the `session_summarize` job and cancel any pending `session_clear` job:

```python
_apscheduler.add_job(
    _on_session_summarize,
    DateTrigger(run_date=now + timedelta(seconds=settings["timeout_summarize_seconds"])),
    id="session_summarize",
    replace_existing=True,
)
with contextlib.suppress(Exception):
    _apscheduler.remove_job("session_clear")
```

### Timeout callbacks

```python
async def _on_session_summarize():
    await agent._invoke("session_timeout")
    _apscheduler.add_job(
        _on_session_clear,
        DateTrigger(run_date=now + timedelta(seconds=settings["timeout_clear_seconds"])),
        id="session_clear",
        replace_existing=True,
    )

async def _on_session_clear():
    agent.clear_history()
```

### API changes

```python
# updated
async def invoke(message: str, reason: str = "user_message", **kwargs) -> str:
    return await agent._invoke(reason, message, **kwargs)

# removed
# invoke_bare
```

---

## `scheduled_tasks.py`

Two changes only:

1. `register()` calls `scheduler.init_timeout(_scheduler)` after `_scheduler.start()`.
2. `_reschedule()` replaces `scheduler.invoke_bare(messages, schema=...)` with:
   ```python
   await scheduler.invoke("", reason="complex_reschedule", messages=messages, schema=_RescheduleOutput)
   ```
