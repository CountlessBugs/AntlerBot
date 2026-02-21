## Summary

Implemented scheduled tasks with APScheduler: LLM-driven `create_task`/`cancel_task` tools, three task types (once/repeat/complex_repeat), startup missed-task recovery, and complex repeat rescheduling via structured LLM output.

## Deviations from Plan

- `invoke_bare` gained an optional `schema` parameter for structured output, rather than being a plain bare invoke
- `source` in `create_task` made optional, defaulting to current chat via `message_handler.get_current_source()`
- `_parse_cron` helper added to handle LLM-generated 6-field cron and Quartz-style `?` wildcard

## Key Decisions

- Used `add_messages` reducer on `_State` to fix tool message ordering errors with `ToolNode`
- NcatBot startup handler must accept an `event` argument
- APScheduler returns timezone-aware datetimes; comparisons strip tzinfo with `.replace(tzinfo=None)`

## Lessons Learned

- LLMs generate 6-field cron (with seconds) and Quartz `?` wildcards — normalize before passing to APScheduler
- `patch(target, return_value=...)` works for module-level functions but direct module variable manipulation is more reliable for testing internal state

## Follow-ups

- `scheduler-architecture.md` describes a planned refactor to centralize queue/priority/batching into a `scheduler.py` module — not yet implemented
