# Scheduler Architecture

## Implementation

Commit: 261af6f

Extracted scheduling logic from `message_handler.py` into a new `src/core/scheduler.py` module.

## Architecture

```
message_handler.py  →  scheduler.py  →  agent.py
(NcatBot callbacks,    (priority queue,   (LLM call,
 format messages,       batching,          concurrency lock)
 enqueue tasks)         dispatch)

scheduled_tasks.py  →  scheduler.py
auto_conversation.py → scheduler.py  (future)
```

## What Was Done

- Created `src/core/scheduler.py` with `asyncio.PriorityQueue`, priority constants, `_batch()`, `enqueue()`, `_process_loop()`, `get_current_source()`
- `message_handler.py` reduced to: `format_message`, `get_group_name`, `register()`
- `scheduled_tasks._on_trigger` routes through `scheduler.enqueue(PRIORITY_SCHEDULED, ...)` instead of calling `agent.invoke()` directly
- `scheduled_tasks.create_task` uses `scheduler.get_current_source()` (was `message_handler.get_current_source()`)
- Tests updated: `test_scheduler.py` created, `test_message_handler.py` stripped of scheduling tests

## Priority Constants

```python
PRIORITY_SCHEDULED = 0       # highest
PRIORITY_USER_MESSAGE = 1
PRIORITY_AUTO_CONVERSATION = 2  # future use
```
