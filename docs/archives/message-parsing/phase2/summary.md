## Summary

Added `ParsedMessage` and `MediaTask` dataclasses to the message parser, and media transcription settings to the configuration system (Tasks 1-2). Then built the complete `media_processor.py` module with ffmpeg check, media download, duration-based trimming, LLM multimodal transcription, and a full orchestrator pipeline (Tasks 3-6). 16 unit tests for media_processor, 5 for ParsedMessage.

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

### Task 4: ffmpeg-based media trimming

- Added `trim_media()`, `_get_duration()` (ffprobe JSON parsing), and `_run_ffmpeg_trim()` (ffmpeg `-t` with `-c copy`)
- Handles: under-limit passthrough, over-limit trim, no-ffmpeg skip, unlimited (`max_duration=0`)
- 4 unit tests covering each branch

### Task 5: LLM-based media transcription

- Added `transcribe_media()` and `_get_transcription_llm()` with lazy init and caching
- Supports override model/provider via settings, falls back to main LLM from `agent.py`
- Reads file as base64, sends multimodal message to LLM with per-type Chinese prompts
- 3 unit tests: image transcribe, audio transcribe, failure handling

### Task 6: process_media_segment orchestrator

- Added `process_media_segment()` that chains download → trim (audio/video) → transcribe → XML-formatted result
- Added `_MEDIA_TAG` mapping and `_cleanup_temp()` for temp file cleanup
- Error tags for each failure mode: `下载失败`, `裁剪失败`, `转述失败`
- 5 unit tests: image transcribe, disabled, audio with trim, download failure, transcription failure

## Deviations from Plan

- `settings.yaml` is gitignored, so it was not committed — the defaults in `agent.py` serve as the source of truth
- Updated `test_load_settings_defaults_when_missing` in `test_agent.py` to reference `_SETTINGS_DEFAULTS` directly instead of hardcoding the dict, making it resilient to future default additions
- Task 5 transcribe tests: plan mocked `builtins.open` with bare `MagicMock()`, but `base64.b64encode` needs real bytes — fixed by setting `mock_file.read.return_value = b"fake image bytes"` with proper context manager setup

## Key Decisions

- Used `MEDIA_PREFIX = "media:"` as a module-level constant rather than inlining the string
- Deep-merge in `load_settings()` only goes two levels deep (top-level media keys + per-type dicts), which is sufficient for the current config structure

## Lessons Learned

- None notable for these foundational tasks

## Follow-ups

- Tasks 7-9 remain: update `parse_message()` to return `ParsedMessage` with media tasks, add `_resolve_media` to scheduler, update message handler to pass `ParsedMessage` through
- Task 10: full integration test
