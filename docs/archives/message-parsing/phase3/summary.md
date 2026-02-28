## Summary

Phase 3 (media passthrough) fully implemented. Added `passthrough_media_segment()` for downloading, trimming, base64-encoding media files and returning content_block dicts. Added `content_blocks` field to `ParsedMessage` with a passthrough branch in `parse_message()`. Updated scheduler to build multimodal content lists, agent to accept `str | list` content, and large-file passthrough via async MediaTask flow. Fixed non-blocking media resolution so large files don't block subsequent messages. 173 tests, 0 warnings.

## Tasks Completed

### Task 1: passthrough_media_segment

- Added `_MIME_MAP` and `passthrough_media_segment()` to `src/core/media_processor.py`
- Pipeline: check `passthrough` config → download → trim audio/video → base64 encode → return `{"type": "image_url", "image_url": {"url": "data:mime;base64,..."}}`
- Returns `None` on failure or when disabled
- 4 new tests: image passthrough, disabled, download failure, audio with trim

### Task 2: ParsedMessage.content_blocks and parse_message passthrough branch

- Added `content_blocks: list[dict]` field to `ParsedMessage` (default empty list)
- Added `elif passthrough` branch in `parse_message()` after the `transcribe` branch
- Small files call `passthrough_media_segment()` inline; success appends to `content_blocks`, failure falls back to static `<tag />` placeholder
- `transcribe > passthrough` priority enforced naturally by if/elif structure
- 3 new tests: passthrough creates content_block, transcribe overrides passthrough, passthrough failure fallback

### Task 3: Scheduler multimodal content building

- Extended `_batch()` to 4-tuple carrying `parsed_msgs`
- `_enqueue_ready()` accepts and passes `parsed_message`
- `enqueue()` passes `parsed_message` through to `_enqueue_ready()`
- Added `_build_agent_content()` helper: returns `[text_block, *media_blocks]` when content_blocks exist, plain string otherwise
- `_process_loop()` merges content_blocks from all parsed messages in a batch, builds multimodal content for `agent._invoke()`
- 3 new tests: text-only, with blocks, no parsed_message

### Task 4: Agent accepts multimodal content list

- Updated `_invoke` type annotation from `message: str` to `message: str | list`
- `HumanMessage(content=...)` already accepts both types natively in LangChain
- 1 new test: verifies list content flows through to HumanMessage

### Task 5: Large-file async passthrough

- Added `passthrough: bool = False` field to `MediaTask` dataclass
- Updated passthrough branch in `parse_message()` with size-based routing (mirrors transcribe branch): small files inline, large files create `MediaTask(passthrough=True)` with placeholder
- Updated `_resolve_media_tasks` return type to `dict[str, str | dict]` for passthrough dict results
- Updated `_resolve_media_and_enqueue` to separate passthrough content_blocks from transcription text results
- Fixed pre-existing `test_batch_groups_by_source` assertion (3-tuple → 4-tuple)
- 2 new tests: large-file passthrough creates MediaTask, passthrough resolve enqueues with content_blocks

### Task 6: Integration test

- Added `test_group_message_with_passthrough_image` to `test_message_handler.py`
- Full flow: group message → parse → enqueue with content_blocks verified

### Post-implementation fix: Non-blocking media resolution

The initial implementation enqueued placeholder messages immediately, causing two problems: (1) wasted LLM round-trip on `<image status="loading" />`, (2) subsequent user messages blocked behind the placeholder's LLM call. This was the same issue fixed in Phase 2 (see phase2/summary.md lines 90-97) but re-introduced by Phase 3.

- `enqueue()` now skips `_enqueue_ready` when `media_tasks` exist — only fires background resolve task
- `_resolve_media_and_enqueue()` now receives the full formatted message (`msg`), replaces placeholder tags with resolved content, and enqueues the complete message when ready
- Other messages arriving during media processing flow through the queue normally
- Updated 3 tests: `test_enqueue_with_media_does_not_block_queue` (renamed), resolve tests updated for new signature

### Post-implementation fix 2: Restore loading placeholder flow and add filename tags

Reverted the "resolve first" approach — large files now enqueue immediately with `<image status="loading" />` placeholder so the LLM sees the loading state. Resolved media is enqueued as a separate follow-up message (not a placeholder replacement). Also added filename tags for small-file passthrough.

- `_resolve_media_and_enqueue()` rewritten: step 1 enqueues message with loading placeholder immediately, step 2 resolves media in background, step 3 enqueues each result as a new follow-up message
- Small-file passthrough now adds `<image filename="xxx" />` tag to text alongside the content_block, so the LLM sees the filename in the text stream
- Removed `ParsedMessage.resolve()` method (no longer used — placeholder replacement eliminated)
- Removed 3 `resolve()` tests, updated 3 scheduler media tests to verify two-message flow (placeholder + follow-up)

## Deviations from Plan

- Phase 3 plan didn't account for non-blocking media resolution; the initial implementation re-introduced the "enqueue placeholder immediately" pattern that Phase 2 had already fixed. Required a post-implementation fix.
- The "resolve first" fix was later reverted — loading placeholders are intentionally shown to the LLM so it knows a file is being processed. Resolved media is sent as a follow-up message instead of replacing the placeholder.

## Key Decisions

- Passthrough uses `image_url` type content_block (LangChain standard multimodal format), even for audio/video
- Batch processing merges content_blocks from all parsed messages, not just the last one
- Large-file flow: enqueue loading placeholder immediately → resolve in background → enqueue result as new message (no placeholder replacement)
- Small-file passthrough adds `<image filename="xxx" />` to text so the LLM sees the filename alongside the content_block

## Follow-ups

- Document type does not support passthrough (cannot send PDF as base64 image_url to LLMs)
- `_build_agent_content` is now dead code (logic inlined in `_process_loop`) — could be removed or wired up
