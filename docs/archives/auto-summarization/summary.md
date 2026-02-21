## Summary

Added auto-summarization and unified `_invoke` to `agent.py`, with APScheduler-driven session timeout in `scheduler.py`.

## What Was Built

- `load_settings()` reads `config/agent/settings.yaml` (with hardcoded defaults if absent)
- `clear_history()` resets `_history`
- `_invoke(reason, message, *, messages, schema)` replaces both old `_invoke` and `_invoke_bare`
- New graph nodes: `finalize_node`, `summarize_node`, `summarize_all_node`, `utility_node`
- `route_by_reason` dispatches on `reason`; `route_after_llm` triggers summarization when `input_tokens > context_limit_tokens`
- `scheduler.init_timeout(apscheduler)` + `enqueue` reschedules `session_summarize` job on every message
- `_on_session_summarize` → `_invoke("session_timeout")` → schedules `session_clear`
- `_on_session_clear` → `clear_history()`

## Deviations from Plan

- `summarize_node` returns `{}` instead of using `RemoveMessage` + re-add. The plan's `RemoveMessage` approach is unreliable: LangGraph's `add_messages` reducer doesn't guarantee stable behavior when removing and re-adding messages with the same ID. Since `summarize_node` goes directly to END, the graph state is discarded anyway — only `_history` matters.
- Summary format uses `<context_summary summary_time=...>` XML wrapper instead of plain `"对话历史摘要：..."` prefix, for cleaner LLM parsing.
- `summarize_all_node` still uses `RemoveMessage` (for `session_timeout` path) since it needs to clear the graph state before adding the summary message — this is safe because it's a full replacement, not a partial remove-and-re-add.

## Key Decisions

- `_pending_schema` module-level variable threads the Pydantic schema into `utility_node` without polluting `_State` (TypedDict can't hold runtime types).
- `_history` is written directly by nodes (`global _history`), not by `_invoke` after `ainvoke` returns. This keeps the update logic co-located with each node's semantics.
- `load_settings()` is called at routing time (not cached at init) so settings changes take effect without restart.

## Lessons Learned

**Don't do unnecessary state manipulation in nodes that go directly to END.** `summarize_node` exits to END immediately, so the graph state is discarded after `ainvoke` returns — only `_history` persists. The more you touch graph state in such nodes, the more you risk hitting reducer edge cases.

**`RemoveMessage` + re-adding with the same ID is a dangerous pattern.** LangGraph docs don't guarantee stable behavior for this use case. If you need to replace messages, create new message objects without an ID rather than reusing the original.

## Follow-ups

- `test_invoke_session_timeout_calls_summarize_all` not written — would require mocking `_llm` inside a compiled graph, which is more integration than unit. Cover with an integration test if needed.
