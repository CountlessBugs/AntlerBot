# Logging Improvements

## Goal

Add structured INFO-level logging to key operational events across `agent.py`, `scheduler.py`, and `scheduled_tasks.py`.

## Log Format

All log lines use `key=value` style for easy filtering.

## Changes

### 1. `src/core/agent.py`

**Add `import time` at top.**

**`_invoke()` — log reason at start, elapsed at end:**

```python
# after _pending_schema = schema (line 223):
logger.info("agent invoke | reason=%s schema=%s", reason, schema.__name__ if schema else None)
t0 = time.monotonic()

# after final buffer processing (after line 283, still inside async with _lock):
logger.info("agent done | reason=%s elapsed=%.2fs", reason, time.monotonic() - t0)
```

**`register_tools()` — wrap each tool's `ainvoke` to log tool name:**

```python
def _with_tool_logging(t):
    orig = t.ainvoke
    async def logged(input, config=None, **kwargs):
        logger.info("tool: %s", t.name)
        return await orig(input, config, **kwargs)
    t.ainvoke = logged
    return t

def register_tools(tools: list) -> None:
    global _tools, _graph
    _tools = [_with_tool_logging(t) for t in tools]
    _graph = None
```

**`route_after_llm()` — log when routing to summarize:**

```python
if tokens > load_settings()["context_limit_tokens"]:
    logger.info("auto-summarize | tokens=%d", tokens)
    return "summarize"
```

**`summarize_all_node()` — log session timeout summarization:**

```python
def summarize_all_node(state: _State) -> dict:
    logger.info("session summarize triggered")
    # ... existing code unchanged
```

---

### 2. `src/core/scheduler.py`

**`enqueue()` — log when task is queued but loop already running:**

```python
async with _lock:
    _counter += 1
    await _queue.put((priority, _counter, source_key, msg, reply_fn))
    should_start = not _processing
    if should_start:
        _processing = True
    else:
        logger.info("queued | source=%s priority=%d depth=%d", source_key, priority, _queue.qsize())
```

**`_process_loop()` — log batch size per source:**

```python
for source_key, msgs, reply_fns in batches:
    _current_source = source_key
    logger.info("processing | source=%s batch=%d", source_key, len(msgs))
    async for seg in agent._invoke("user_message", "\n".join(msgs)):
        ...
```

---

### 3. `src/core/scheduled_tasks.py`

**`_register_apscheduler_job()` — log name, type, trigger (covers LLM-created tasks and startup recovery):**

```python
def _register_apscheduler_job(task: dict) -> None:
    trigger_str = task["trigger"]
    ...
    logger.info("job registered | name=%s type=%s trigger=%s", task["name"], task["type"], trigger_str)
    _scheduler.add_job(...)
```

## Implementation Steps

1. `agent.py`: add `import time`, add logging to `_invoke`, add `_with_tool_logging` helper, update `register_tools`, add logging to `route_after_llm` and `summarize_all_node`
2. `scheduler.py`: add logging to `enqueue` (else branch) and `_process_loop`
3. `scheduled_tasks.py`: add logging to `_register_apscheduler_job`
