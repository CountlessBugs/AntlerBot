# Scheduler Architecture Plan

## Background

During the design of agent concurrency protection, a future refactoring direction was identified.

## Current Architecture

```
NcatBot callbacks → message_handler.py → agent.py
                    (format, queue,        (LLM call)
                     batch, priority)
```

`message_handler.py` currently handles both message formatting and scheduling (queue, batching, priority). This works for now but will become problematic when new task sources are added.

## Problem

When scheduled tasks and auto-initiated conversations are added, they are fundamentally different trigger sources from QQ messages. Putting all scheduling logic in `message_handler.py` would make it responsible for unrelated concerns.

## Future Architecture

```
message_handler.py  →  scheduler.py  →  agent.py
(NcatBot callbacks,    (priority queue,   (LLM call,
 format messages,       batching,          concurrency lock)
 enqueue tasks)         dispatch)

scheduled_tasks.py  →  scheduler.py
auto_conversation.py → scheduler.py
```

## Priority Order (planned)

```python
# Lower number = higher priority
PRIORITY_SCHEDULED = 0
PRIORITY_USER_MESSAGE = 1
PRIORITY_AUTO_CONVERSATION = 2
```

Use `asyncio.PriorityQueue`. Each task carries a priority value. Scheduler always processes the highest-priority pending task next.

## Migration Notes

- `message_handler.py` becomes thin: receive callback → format → enqueue to scheduler
- Batch processing logic moves from `message_handler.py` to `scheduler.py`
- `agent.py` concurrency lock remains; scheduler serializes at a higher level
- `_current_source` priority heuristic in `_batch_pending` can be replaced by explicit priority values