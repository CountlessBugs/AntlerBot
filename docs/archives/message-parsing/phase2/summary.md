## Summary

Added `ParsedMessage` and `MediaTask` dataclasses to the message parser, and media transcription settings to the configuration system (Tasks 1-2). Built the complete `media_processor.py` module with ffmpeg check, media download, duration-based trimming, LLM multimodal transcription, and a full orchestrator pipeline (Tasks 3-6). Updated `parse_message()` to return `ParsedMessage` with async media tasks (Task 7). Added `_resolve_media` to scheduler and wired the full handler → parser → scheduler → agent pipeline (Tasks 8-10). 153 tests, 0 warnings.

## Tasks Completed

### Task 1: ParsedMessage and MediaTask dataclasses

- Added `MediaTask` dataclass (`placeholder_id`, `task`, `media_type`) to `src/core/message_parser.py`
- Added `ParsedMessage` dataclass with `text`, `media_tasks`, and `resolve()` method that replaces `{{media:id}}` placeholders with transcription results
- Added `MEDIA_PREFIX` module constant for placeholder format consistency
- 5 new unit tests covering construction, placeholder detection, resolve with/without results, and error placeholders

### Task 2: Media settings configuration

- Added `media` block to `_SETTINGS_DEFAULTS` in `src/core/agent.py` with per-type config (image, audio, video, document) including transcribe, passthrough, max_duration, and trim_over_limit options
- Updated `load_settings()` with two-level deep-merge so user overrides merge correctly at the nested media type level
- Added `TRANSCRIPTION_API_KEY` and `TRANSCRIPTION_BASE_URL` to `.env.example`
- Updated local `config/agent/settings.yaml` with the full media config block (gitignored, not committed)

### Task 3: media_processor.py — ffmpeg check and download

- Created `src/core/media_processor.py` with `check_ffmpeg()` (cached `shutil.which` lookup) and `download_media()` (downloads via segment's `.download()` to a `tempfile.mkdtemp` dir)
- 4 unit tests: ffmpeg available, unavailable, caching, and download

**Post-implementation fix:** NcatBot's `File` segment often has `url=None` and `file` set to just a filename (e.g. `context.txt`), causing `seg.download()` → `get_base64()` → `NcatBotError`. The exception logs ERROR inside its own constructor before we can catch it.
- Added `_seg_can_download()` to pre-check whether `seg.download()` will succeed; skips it when it would fail, avoiding the `NcatBotError` ERROR log
- Added `_get_file_url(seg, source)` — resolves download URL via NapCat API: `get_group_file_url()` for group files, `get_private_file_url()` for private files
- Added `_download_via_url()` helper for httpx download
- `download_media()` now accepts `source` param, tries `seg.download()` only when safe, falls back to API URL resolution

### Task 4: ffmpeg-based media trimming

- Added `trim_media()`, `_get_duration()` (ffprobe JSON parsing), and `_run_ffmpeg_trim()` (ffmpeg `-t` with `-c copy`)
- Handles: under-limit passthrough, over-limit trim, no-ffmpeg skip, unlimited (`max_duration=0`)
- 4 unit tests covering each branch

### Task 5: LLM-based media transcription

- Added `transcribe_media()` and `_get_transcription_llm()` with lazy init and caching
- Supports override model/provider via settings, falls back to main LLM from `agent.py`
- Reads file as base64, sends multimodal message to LLM with per-type Chinese prompts
- 3 unit tests: image transcribe, audio transcribe, failure handling

**Post-implementation fix:** Document type (e.g. `.txt`) was sent as base64 `image_url` with mime `application/pdf`, which LLMs cannot process. Now reads file as text (UTF-8, fallback GBK) and sends inline to LLM.

### Task 6: process_media_segment orchestrator

- Added `process_media_segment()` that chains download → trim (audio/video) → transcribe → XML-formatted result
- Added `_MEDIA_TAG` mapping and `_cleanup_temp()` for temp file cleanup
- Error tags for each failure mode: `下载失败`, `裁剪失败`, `转述失败`
- 5 unit tests: image transcribe, disabled, audio with trim, download failure, transcription failure

**Post-implementation fix:** `process_media_segment()` now accepts and passes `source` param to `download_media()`.

### Task 7: Update parse_message() to return ParsedMessage with media tasks

- Changed `parse_message()` return type from `str` to `ParsedMessage`
- Replaced `_MEDIA_PLACEHOLDERS` dict with `_MEDIA_TYPE_MAP` (maps segment classes to media type strings)
- When `transcribe: True` in settings, creates `asyncio.Task` via `media_processor.process_media_segment()`, inserts `{{media:uuid}}` placeholder, appends `MediaTask` to result
- When `transcribe: False`, uses `media_processor._MEDIA_TAG` for static `<tag />` placeholders
- Added `media_processor` import to `message_parser.py`
- Updated all 18 existing tests from `assert await parse_message(...) == "string"` to `assert result.text == "string"`
- 3 new tests: `test_parse_returns_parsed_message`, `test_parse_image_transcribe_creates_task`, `test_parse_image_no_transcribe_placeholder`

**Post-implementation fix:** `parse_message()` now accepts `source` param, passes it through to `process_media_segment()`.

### Task 8: Add _resolve_media to scheduler

- Added `_resolve_media()` to `src/core/scheduler.py` that awaits all media tasks with configurable timeout
- On timeout: cancels the task, inserts `<tag error="处理超时" />` placeholder
- On exception: inserts `<tag error="处理失败" />` placeholder
- Imported `ParsedMessage` and `_MEDIA_TAG` into scheduler
- 3 new tests in `tests/test_scheduler_media.py`: success, timeout, no-media passthrough

### Task 9: Update message_handler and scheduler for ParsedMessage flow

- Updated `enqueue()` signature to accept optional `parsed_message` parameter
- Updated `_batch()` to carry 6-element tuples (added `parsed_msg`)
- Updated `_process_loop()` to call `_resolve_media()` before invoking agent, replacing placeholder text in the formatted message
- Updated `message_handler.py`: both `on_group` and `on_private` now pass `parsed.text` to `format_message` and the full `ParsedMessage` to `enqueue`
- Updated 6 existing scheduler tests for the new tuple shape

**Post-implementation fix:** Refactored to non-blocking media resolution:
- `enqueue()` now routes media messages to `_resolve_then_enqueue()` (background `asyncio.Task`) instead of passing `ParsedMessage` into the queue
- `_resolve_then_enqueue()` awaits media tasks in the background, then calls `_enqueue_ready()` with the resolved plain text
- `_process_loop()` no longer calls `_resolve_media()` — all messages in the queue are already resolved
- `_batch()` simplified to 3-tuples `(source_key, msgs, reply_fns)` since `parsed_msg` is no longer carried
- `transcribe_media()` changed from sync `llm.invoke()` to `await llm.ainvoke()` — the sync call was blocking the entire event loop, causing `_process_loop` to stall during transcription even though media resolution ran in a separate task
- 2 new tests: `test_enqueue_with_media_does_not_block_queue`, `test_resolve_then_enqueue_puts_resolved_msg`
- Updated existing scheduler tests for new tuple shape and removed media timeout mocks from `_process_loop` tests

**Post-implementation fix:** Both `on_group` and `on_private` now construct `source_key` (`group_{id}` / `private_{id}`) and pass it to `parse_message()` for file URL resolution.

### Task 10: Full integration test and final verification

- Added `test_group_message_with_media_transcription` to `tests/test_message_handler.py`
- Full suite: 151 passed, 0 warnings

### Bonus fixes

- Fixed unclosed file handle in `agent.py` `load_prompt()` (`open().close()` → `with open`)
- Fixed same issue in `tests/test_agent.py`
- Added `pytest.ini` to filter known `AsyncMock` RuntimeWarning from Python stdlib

## Deviations from Plan

- `settings.yaml` is gitignored, so it was not committed — the defaults in `agent.py` serve as the source of truth
- Updated `test_load_settings_defaults_when_missing` in `test_agent.py` to reference `_SETTINGS_DEFAULTS` directly
- Task 5 transcribe tests: fixed mock to provide real bytes for `base64.b64encode`
- Task 9: used `msg.replace(pm.text, resolved_text, 1)` with count=1 to avoid replacing duplicate substrings
- Task 9 post-fix: original design had `_resolve_media` inside `_process_loop`, which blocked the queue; refactored to resolve media before enqueue

## Key Decisions

- Used `MEDIA_PREFIX = "media:"` as a module-level constant rather than inlining the string
- Deep-merge in `load_settings()` only goes two levels deep, sufficient for current config structure

## Lessons Learned

- Sync LLM calls (`llm.invoke()`) inside async functions block the entire event loop — always use `await llm.ainvoke()` in async contexts
- Moving work to a separate `asyncio.Task` is not sufficient if the task itself contains sync blocking calls

## Follow-ups

- Phase 3: media passthrough via base64 content blocks.
