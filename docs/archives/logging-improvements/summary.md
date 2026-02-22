## Summary

Added structured `key=value` INFO-level logging to key operational events in `agent.py`, `scheduler.py`, and `scheduled_tasks.py`, plus 5 new tests.

## Deviations from Plan

- Used `object.__setattr__(t, 'ainvoke', logged)` instead of `t.ainvoke = logged` because `StructuredTool` is a Pydantic v2 model that rejects arbitrary attribute assignment via `__setattr__`.
- Log format for tool calls changed from `"tool: %s"` to `"tool | name=%s"` to match the `key=value` style used by all other log lines.

## Key Decisions

- `object.__setattr__` bypasses Pydantic's `__setattr__` validation without requiring a proxy wrapper or subclass, keeping the change minimal.
- `t0` is placed after `_ensure_initialized()` so elapsed time measures only the actual invocation, not graph compilation.

## Lessons Learned

- Pydantic v2 models used as LangChain tools cannot have instance attributes set directly; `object.__setattr__` is the correct bypass.

## Follow-ups

- None
