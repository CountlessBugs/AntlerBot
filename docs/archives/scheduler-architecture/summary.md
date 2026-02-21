## Summary

Extracted queue, batching, priority, and dispatch logic from `message_handler.py` into a new `src/core/scheduler.py` module. All task sources now route through the scheduler.

## Deviations from Plan

- `_on_trigger` in `scheduled_tasks.py` was initially left calling `agent.invoke()` directly; caught in code review and fixed to use `scheduler.enqueue(PRIORITY_SCHEDULED, ...)`.

## Key Decisions

- `asyncio.PriorityQueue` replaces the old `_pending` list + `_current_source` priority-boost heuristic.
- `scheduled_tasks.py` imports `scheduler` at module level (not deferred) to allow patching in tests.

## Follow-ups

- `auto_conversation.py` (future) will also enqueue via `scheduler.enqueue(PRIORITY_AUTO_CONVERSATION, ...)`.
