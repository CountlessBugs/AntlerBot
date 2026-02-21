# Auto-Summarization Implementation Plan

Reference design: `docs/plans/auto-summarization-design.md`

---

## Task 1 — Config file + `load_settings()`

**Files:** `config/agent/settings.yaml.example` (new), `src/core/agent.py`

Create `config/agent/settings.yaml.example`:
```yaml
context_limit_tokens: 8000
timeout_summarize_seconds: 1800
timeout_clear_seconds: 3600
```

Add to `agent.py`:
```python
SETTINGS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "agent", "settings.yaml")
)
_SETTINGS_DEFAULTS = {
    "context_limit_tokens": 8000,
    "timeout_summarize_seconds": 1800,
    "timeout_clear_seconds": 3600,
}

def load_settings() -> dict:
    if not os.path.exists(SETTINGS_PATH):
        return dict(_SETTINGS_DEFAULTS)
    import yaml
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {**_SETTINGS_DEFAULTS, **data}
```

Add `pyyaml` to `requirements.in` and recompile.

**Tests:** `tests/test_agent.py`
- `test_load_settings_defaults_when_missing`: patch `SETTINGS_PATH` to nonexistent path, assert returns defaults
- `test_load_settings_reads_file`: write a yaml file with one override, assert that key is overridden and others are defaults

---

## Task 2 — `clear_history()`

**File:** `src/core/agent.py`

```python
def clear_history() -> None:
    global _history
    _history = []
```

**Test:** `tests/test_agent.py`
- `test_clear_history`: set `agent_mod._history = [HumanMessage("x")]`, call `clear_history()`, assert `_history == []`

---

## Task 3 — Refactor `_invoke` signature; update `scheduler.py` and `scheduled_tasks.py`

This is a breaking refactor. Do all three files atomically.

### `agent.py`

Rename `_invoke` → `_invoke` (keep private), update signature:
```python
async def _invoke(
    reason: Literal["user_message", "scheduled_task", "complex_reschedule", "session_timeout"],
    message: str = "",
    *,
    messages: list[BaseMessage] | None = None,
    schema: type | None = None,
) -> str:
```

Remove `_invoke_bare`.

State initialization inside `_invoke`:
```python
if reason == "session_timeout":
    initial = list(_history)
elif reason == "complex_reschedule":
    initial = list(messages)
else:
    initial = _history + [HumanMessage(message)]
```

`_invoke` no longer updates `_history` after `ainvoke` — nodes handle that (see Task 4).

### `scheduler.py`

```python
async def invoke(message: str, reason: str = "user_message", **kwargs) -> str:
    return await agent._invoke(reason, message, **kwargs)

# remove invoke_bare
```

### `scheduled_tasks.py`

In `_reschedule`, replace:
```python
result = await scheduler.invoke_bare([SystemMessage(timer_prompt), HumanMessage(context)], schema=_RescheduleOutput)
```
with:
```python
result_str = await scheduler.invoke(
    "",
    reason="complex_reschedule",
    messages=[SystemMessage(timer_prompt), HumanMessage(context)],
    schema=_RescheduleOutput,
)
result = _RescheduleOutput.model_validate_json(result_str)
```

In `register()`, add `scheduler.init_timeout(_scheduler)` after `_scheduler.start()` (see Task 5).

**Tests:** Run existing tests; update any that call `invoke_bare` or use the old `_invoke` signature.

---

## Task 4 — Graph restructuring

**File:** `src/core/agent.py`

### `_State`

```python
class _State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    reason: Literal["user_message", "scheduled_task", "complex_reschedule", "session_timeout"]
```

### New nodes (defined inside `_ensure_initialized`)

**`finalize_node`** — writes accumulated messages back to `_history`:
```python
def finalize_node(state: _State) -> dict:
    global _history
    _history = list(state["messages"])
    return {}
```

**`summarize_node`** — context-limit triggered; keeps last human+AI turn:
```python
def summarize_node(state: _State) -> dict:
    global _history
    msgs = state["messages"]
    last_turn = msgs[-2:] if len(msgs) >= 2 else msgs
    to_summarize = msgs[:-2] if len(msgs) >= 2 else []
    summary = _llm.invoke([SystemMessage("请总结以下对话，保留关键信息："), *to_summarize])
    from langchain_core.messages import RemoveMessage
    new_msgs = (
        [RemoveMessage(id=m.id) for m in msgs]
        + [SystemMessage(f"对话历史摘要：{summary.content}")]
        + list(last_turn)
    )
    _history = [SystemMessage(f"对话历史摘要：{summary.content}")] + list(last_turn)
    return {"messages": new_msgs}
```

**`summarize_all_node`** — session-timeout triggered; summarizes everything:
```python
def summarize_all_node(state: _State) -> dict:
    global _history
    msgs = state["messages"]
    summary = _llm.invoke([SystemMessage("请总结以下对话，保留关键信息："), *msgs])
    from langchain_core.messages import RemoveMessage
    summary_msg = SystemMessage(f"对话历史摘要：{summary.content}")
    _history = [summary_msg]
    return {"messages": [RemoveMessage(id=m.id) for m in msgs] + [summary_msg]}
```

**`utility_node`** — for `complex_reschedule`; does not touch `_history`:
```python
def utility_node(state: _State) -> dict:
    llm = _llm.with_structured_output(state.get("schema")) if state.get("schema") else _llm
    response = llm.invoke(state["messages"])
    content = response.json() if hasattr(response, "json") else response.content
    return {"messages": [AIMessage(content)]}
```

Note: `schema` cannot be stored in `_State` (TypedDict doesn't support runtime-injected types). Pass it via a closure instead — store it in a module-level `_pending_schema: type | None = None`, set before `ainvoke`, read inside `utility_node`.

### Routing functions

```python
def route_by_reason(state: _State) -> str:
    return state["reason"]

def route_after_llm(state: _State) -> str:
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    tokens = (last.usage_metadata or {}).get("input_tokens", 0)
    settings = load_settings()
    if tokens > settings["context_limit_tokens"]:
        return "summarize"
    return "finalize"
```

### Graph wiring

```python
builder.add_node("llm", llm_node)
builder.add_node("finalize", finalize_node)
builder.add_node("summarize", summarize_node)
builder.add_node("summarize_all", summarize_all_node)
builder.add_node("utility", utility_node)

builder.add_conditional_edges(START, route_by_reason, {
    "user_message": "llm",
    "scheduled_task": "llm",
    "complex_reschedule": "utility",
    "session_timeout": "summarize_all",
})
builder.add_conditional_edges("llm", route_after_llm, {
    "tools": "tools",
    "summarize": "summarize",
    "finalize": "finalize",
})
builder.add_edge("tools", "llm")
builder.add_edge("summarize", END)
builder.add_edge("summarize_all", END)
builder.add_edge("finalize", END)
builder.add_edge("utility", END)
```

**Tests:** `tests/test_agent.py`
- `test_invoke_user_message_updates_history`: mock graph returns messages, assert `_history` updated by `finalize_node`
- `test_invoke_session_timeout_calls_summarize_all`: mock `_llm.invoke`, call `_invoke("session_timeout")`, assert `_history` replaced with summary
- `test_invoke_complex_reschedule_does_not_touch_history`: set `_history`, call `_invoke("complex_reschedule", ...)`, assert `_history` unchanged
- `test_route_after_llm_over_limit`: mock last message with `usage_metadata={"input_tokens": 99999}`, assert routes to `"summarize"`

---

## Task 5 — `scheduler.py` timeout via APScheduler

**File:** `src/core/scheduler.py`

Add module-level:
```python
from datetime import datetime, timedelta
_apscheduler = None
```

New function:
```python
def init_timeout(apscheduler) -> None:
    global _apscheduler
    _apscheduler = apscheduler
```

In `enqueue`, after acquiring lock and putting item in queue, add:
```python
if _apscheduler is not None:
    settings = agent.load_settings()
    _apscheduler.add_job(
        _on_session_summarize,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=settings["timeout_summarize_seconds"])),
        id="session_summarize",
        replace_existing=True,
    )
    with contextlib.suppress(Exception):
        _apscheduler.remove_job("session_clear")
```

Add callbacks:
```python
async def _on_session_summarize() -> None:
    await agent._invoke("session_timeout")
    if _apscheduler is None:
        return
    settings = agent.load_settings()
    _apscheduler.add_job(
        _on_session_clear,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=settings["timeout_clear_seconds"])),
        id="session_clear",
        replace_existing=True,
    )

async def _on_session_clear() -> None:
    agent.clear_history()
```

Add imports: `from apscheduler.triggers.date import DateTrigger`, `import contextlib`.

In `scheduled_tasks.register()`, after `_scheduler.start()`:
```python
scheduler.init_timeout(_scheduler)
```

**Tests:** `tests/test_scheduler.py` (new file or existing)
- `test_enqueue_schedules_summarize_job`: mock APScheduler, call `enqueue`, assert `add_job` called with `id="session_summarize"`
- `test_enqueue_cancels_clear_job`: mock APScheduler, call `enqueue`, assert `remove_job("session_clear")` attempted

---

## Task 6 — Run all tests and fix regressions

```bash
pytest tests/ -v
```

Fix any failures from the refactor (signature changes, removed `invoke_bare`, etc.).
