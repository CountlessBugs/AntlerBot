## Summary

Phase 3 (media passthrough) Tasks 1-3 completed. Added `passthrough_media_segment()` for downloading, trimming, base64-encoding media files and returning content_block dicts. Added `content_blocks` field to `ParsedMessage` with a passthrough branch in `parse_message()`. Updated scheduler to carry parsed_message through the queue and build multimodal content lists for the agent.

Tasks 4-6 (agent list content, large-file async passthrough, integration tests) not yet implemented.

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

## Tasks Remaining

- Task 4: Update `agent._invoke` message parameter type to `str | list`
- Task 5: Large-file async passthrough (placeholder + MediaTask flow)
- Task 6: Full integration test and verification

## Deviations from Plan

- None — implementation matches plan

## Key Decisions

- Passthrough uses `image_url` type content_block (LangChain standard multimodal format), even for audio/video
- Batch processing merges content_blocks from all parsed messages, not just the last one
- `_build_agent_content` is a standalone function (not inlined in `_process_loop`) for testability

## Follow-ups

- Tasks 4-6 pending
- Large-file passthrough async flow needs `_resolve_media_and_enqueue` to handle dict return values
- Document type does not support passthrough (cannot send PDF as base64 image_url to LLMs)
