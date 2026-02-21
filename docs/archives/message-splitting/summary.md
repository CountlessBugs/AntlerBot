## Summary

`agent._invoke` was changed from a coroutine returning `str` to an async generator yielding `str` segments, streaming LLM output via `astream_events` and splitting on newlines so each line is sent as a separate QQ message. `<no-split>...</no-split>` tags keep multi-line blocks together; all XML tags are stripped from emitted segments.

## Deviations from Plan

- None

## Key Decisions

- Used `MagicMock` (not `AsyncMock`) for graph mock in tests — `AsyncMock` wraps `astream_events` as a coroutine, breaking `async for`
- `_emit` strips all XML tags (not just `<no-split>`) — intentional, to clean any stray tags from output

## Lessons Learned

- `event.get("metadata", )` (trailing comma, no default) silently differs from `event.get("metadata", {})` and crashes on missing key — caught in code review
- When mocking async generators, define a plain `async def` with `yield` rather than using `AsyncMock`

## Follow-ups

- No tests for the `<no-split>` split path or newline-splitting behavior (suggested in review, deferred)
