# Multi-Type Message Parsing Design

## Overview

AntlerBot currently reads messages via the `raw_message` field, where all @mentions, replies, QQ faces, and media files are converted to unreadable CQ codes. This design introduces structured message parsing that converts NcatBot's `MessageArray` into LLM-friendly formats.

## Phases

- **Phase 1**: Basic segment parsing — Text, At, Face, Reply
- **Phase 2**: Media transcription — download, trim, transcribe for Image/Audio/Video/Document
- **Phase 3**: Media passthrough — content_blocks, base64 encoding, direct LLM input

## Architecture

New module: `src/core/message_parser.py` — responsible for converting `MessageArray` into LLM-readable formats.

### Message Flow

```
NcatBot Event
    ├─ message: MessageArray  (replaces raw_message)
    └─ sender, group_name
    ↓
message_handler.py
    ├─ Extract sender info (nickname/card, group_name)
    ├─ Call message_parser.parse_message(event.message, settings)
    ├─ Wrap with sender info via format_message
    └─ Enqueue to scheduler
    ↓
scheduler.py
    ├─ Receive ParsedMessage (may contain pending media tasks)
    ├─ Await media tasks before invoking agent (with timeout)
    └─ Pass final str | list to agent
    ↓
agent.py
    └─ Build HumanMessage(content=str or content=list)
```

## Phase 1: Basic Segment Parsing

Parse Text, At, Face, and Reply segments into readable text with XML tags. No media handling, no async tasks.

### Segment Rules

**Text**: Concatenate directly, no transformation.

**At**: Look up `user_id` in `contact_cache`. Use remark if available, otherwise nickname. If not found in cache, fall back to nickname from the event context. AtAll becomes `@全体成员`.
```
@备注或昵称
```

**Face**: Use a built-in `face_id → name` mapping dict (~200 entries). Unknown IDs render as `<face />`.
```
<face name="微笑" />
```

**Reply**: Call NcatBot API with `message_id` to fetch the original message content. Truncate to `reply_max_length` characters (default 50, configurable). On API failure: `<reply_to>无法获取原消息</reply_to>`.
```
<reply_to>被引用消息内容前50字...</reply_to>
```

**Unsupported segments** (Forward, Share, Contact, Location, etc.): Use the segment's `get_summary()` method, or `<unsupported type="type_name" />`.

**Media segments** (Image, Record, Video, File): In Phase 1, render as `<image />` / `<audio />` / `<video />` / `<file />` placeholders. Full media handling is deferred to Phase 2 and 3.

### Phase 1 Changes

- `message_handler.py`: Pass `event.message` (MessageArray) instead of `event.raw_message` to the parser
- New `src/core/message_parser.py`: `parse_message(message_array, settings) -> str`
- `format_message()`: Accept parsed string instead of raw_message
- New `src/data/face_map.py`: Built-in face_id → name mapping dict
- `settings.yaml`: Add `reply_max_length` (default 50)

## Phase 2: Media Transcription

Add download, trim, and transcription support for Image, Audio, Video, and Document segments. Introduces async media tasks and the `ParsedMessage` data structure.

### Data Structures

```python
@dataclass
class MediaTask:
    placeholder_id: str          # unique ID for placeholder replacement, e.g. "{{media:uuid}}"
    task: asyncio.Task           # async task handle
    media_type: str              # "image" / "audio" / "video" / "document"

@dataclass
class ParsedMessage:
    content_parts: list          # text parts with placeholders
    media_tasks: list[MediaTask] # pending media tasks
```

### Sync vs Async Processing (Size-Based)

Not all media files need the two-phase placeholder flow. Small files process quickly, so waiting inline avoids a redundant LLM round-trip.

The `sync_process_threshold_mb` setting (under `media:`) controls the cutoff:

- `file_size <= threshold`: `parse_message()` awaits `process_media_segment()` directly and inlines the result into the text. No `MediaTask` is created, no placeholder is emitted.
- `file_size > threshold` or `file_size is None`: the existing two-phase flow applies (placeholder → background task → follow-up message).
- `threshold = 0`: always use the two-phase placeholder flow.

File size is read from `DownloadableMessageSegment.file_size` (populated by NcatBot on message receipt). If the sync path raises an exception, an error tag is inlined instead (e.g. `<image error="处理失败" />`).

This logic lives entirely in `message_parser.py`; `scheduler.py` and `media_processor.py` are unchanged.

### Transcription Flow

1. `parse_message()` encounters a media segment with `transcribe=true`
2. Insert placeholder `{{media:uuid}}` into content_parts
3. Launch async task: download → (trim if audio/video) → send to transcription model → return description text
4. Return `ParsedMessage` with pending tasks
5. Scheduler awaits all media tasks before invoking agent (timeout: configurable, default 60s)
6. Replace placeholders with results: `<image filename="pic.jpg">description</image>`
7. On failure/timeout: replace with `<image error="处理失败" />` or `<image error="处理超时" />`

### Audio/Video Trimming

- Use ffmpeg for trimming files that exceed `max_duration`
- `trim_over_limit=true` (default): trim to max_duration; if ffmpeg unavailable, log error and skip file
- `trim_over_limit=false`: skip the entire file
- Check ffmpeg availability at startup, cache the result

### Transcription Model

- Default: reuse main LLM (LLM_MODEL / LLM_PROVIDER)
- Override via `settings.yaml`: `media.transcription_model` and `media.transcription_provider`
- API key/endpoint override via env vars: `TRANSCRIPTION_API_KEY`, `TRANSCRIPTION_BASE_URL` (fall back to `OPENAI_API_KEY` / `OPENAI_BASE_URL`)

### Temp File Management

- Use Python `tempfile` module for downloads
- Each media task operates in its own temp file
- Clean up immediately after processing (success or failure)

### Phase 2 Changes

- `message_parser.py`: Return `ParsedMessage` instead of `str`; add async media task launching
- `scheduler.py`: Await media tasks before invoking agent; placeholder replacement logic
- `settings.yaml`: Add full `media` config block
- `.env.example`: Add `TRANSCRIPTION_API_KEY`, `TRANSCRIPTION_BASE_URL`

## Phase 3: Media Passthrough

Add direct media input to LLM via LangChain's content_blocks. Requires the LLM to support multimodal input.

### Passthrough Flow

When `passthrough=true` and `transcribe=false` for a media type:

1. Download media file (trim if audio/video over limit)
2. Read file as base64
3. Build content_block: `{"type": "image", "source_type": "base64", "data": "...", "mime_type": "image/png"}`
4. Delete local file
5. The final message becomes a list (not a string): text parts + media content_blocks

### Message Format with Passthrough

```python
# Pure text (Phase 1 / transcription mode)
HumanMessage("<sender>UserA</sender>hello <face name=\"微笑\" />")

# Transcription mode
HumanMessage("<sender>UserA</sender><image filename=\"cat.jpg\">an orange cat on a sofa</image> look at my cat")

# Passthrough mode (content_blocks list)
HumanMessage(content=[
    {"type": "text", "text": "<sender>UserA</sender>look at my cat"},
    {"type": "image", "source_type": "base64", "data": "iVBOR...", "mime_type": "image/png"}
])
```

### Priority: transcribe > passthrough

If both `transcribe` and `passthrough` are true, `transcribe` takes precedence.

### Phase 3 Changes

- `message_parser.py`: Add base64 encoding logic; return content_blocks list when passthrough media exists
- `scheduler.py`: Handle `list` type message content in batching (cannot simply join strings)
- `agent.py`: Build `HumanMessage(content=list)` when content is a list

## Configuration

### settings.yaml additions

```yaml
# Reply truncation (top-level)
reply_max_length: 50

media:
  # Transcription model (empty = reuse main LLM)
  transcription_model: ""
  transcription_provider: ""

  # Files at or below this threshold are processed inline (sync).
  # Files above this threshold use the two-phase placeholder flow.
  # Set to 0 to always use placeholder flow.
  sync_process_threshold_mb: 1

  # Per-type config
  image:
    transcribe: false
    passthrough: false

  audio:
    transcribe: false
    passthrough: false
    max_duration: 60           # seconds, 0 = unlimited
    trim_over_limit: true      # true=trim, false=skip file

  video:
    transcribe: false
    passthrough: false
    max_duration: 30
    trim_over_limit: true

  document:
    transcribe: false
    passthrough: false
```

### Environment Variables

```
TRANSCRIPTION_API_KEY=        # Transcription model API key (falls back to OPENAI_API_KEY)
TRANSCRIPTION_BASE_URL=       # Transcription model endpoint (falls back to OPENAI_BASE_URL)
```

## Error Handling

- **Media download failure**: Replace with `<image error="下载失败" />` etc., log error. Does not affect other segments in the same message.
- **Transcription model failure**: Replace with `<image error="转述失败" />`, log error. Bad config logs warning at startup.
- **ffmpeg unavailable**: Detected and cached at startup. If `trim_over_limit=true` and file exceeds limit, log error and skip file. If file is within limit, process normally.
- **Reply API failure**: Render as `<reply_to>无法获取原消息</reply_to>`.
- **Media task timeout**: Cancel task, replace with `<media_type error="处理超时" />`, clean up temp files.

## Testing Strategy

### Unit Tests (`tests/test_message_parser.py`)

- Each segment type: Text, At, Face, Reply, Image, Record, Video, File
- Config combinations: transcribe / passthrough / disabled
- Edge cases: unknown face_id, Reply API failure, media download failure
- ParsedMessage placeholder replacement logic

### Integration Tests

- Full message flow: MessageArray → parse_message → scheduler → agent HumanMessage
- Async media task timeout and cancellation
- Settings hot-reload (settings.yaml changes take effect without restart)

All external calls (NcatBot API, transcription model, ffmpeg, file download) are mocked in tests.
