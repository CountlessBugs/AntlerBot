# Phase 1 Implementation Plan: Basic Segment Parsing

Design doc: `docs/plans/message-parsing-design.md`

## Summary

Replace `raw_message` usage with structured `MessageArray` parsing for Text, At, Face, Reply segments. Media segments render as placeholders for now.

## Steps

### Step 1: Create face_map.py

Create `src/data/__init__.py` and `src/data/face_map.py` with a `FACE_MAP: dict[int, str]` mapping ~200 QQ face IDs to Chinese names.

Source: https://github.com/kyubotics/coolq-http-api/wiki/Face-ID

Files:
- NEW `src/data/__init__.py`
- NEW `src/data/face_map.py`

### Step 2: Create message_parser.py

Create `src/core/message_parser.py` with the core `parse_message()` function. It iterates over `MessageArray` segments and converts each to readable text.

```python
async def parse_message(message_array, settings: dict) -> str:
```

Segment handling:
- `Text` → append `seg.text` directly
- `At` → look up `contact_cache.get_remark(user_id)`, fall back to nickname; AtAll → `@全体成员`
- `Face` → look up `FACE_MAP[int(seg.id)]`; if found render as `<face name="..." />`, if not found render as `<face />`
- `Reply` → call `status.global_api.get_msg(seg.id)` to fetch original message, truncate to `reply_max_length`, wrap in `<reply_to>...</reply_to>`; on failure → `<reply_to>无法获取原消息</reply_to>`
- `Image` → `<image />`
- `Record` → `<audio />`
- `Video` → `<video />`
- `File` → `<file />`
- Other → `seg.get_summary()` or `<unsupported type="type_name" />`

Files:
- NEW `src/core/message_parser.py`

### Step 3: Add reply_max_length to settings.yaml

Add `reply_max_length: 50` as a top-level setting in `config/agent/settings.yaml`. Update `_SETTINGS_DEFAULTS` in `agent.py` to include the new default.

Files:
- EDIT `config/agent/settings.yaml`
- EDIT `src/core/agent.py` — add `reply_max_length` to `_SETTINGS_DEFAULTS`

### Step 4: Update message_handler.py to use message_parser

Replace `e.raw_message` with `await message_parser.parse_message(e.message, settings)` in both `on_group` and `on_private` handlers.

Key changes in `on_group`:
- Call `agent.load_settings()` to get settings
- Call `await message_parser.parse_message(e.message, settings)` instead of using `e.raw_message`
- Pass parsed string to `format_message()`

Key changes in `on_private`:
- Same as above
- For command detection: still check `e.raw_message.startswith("/")` since commands use raw text

Files:
- EDIT `src/core/message_handler.py`

### Step 5: Write tests for message_parser

Create `tests/test_message_parser.py` with unit tests covering:

- Text segment: plain text passthrough
- At segment: remark found in cache, remark not found (fallback to nickname), AtAll
- Face segment: known face_id, unknown face_id
- Reply segment: successful API fetch + truncation, API failure fallback
- Media segments: Image/Record/Video/File render as placeholders
- Unsupported segments: get_summary() fallback
- Mixed message: multiple segment types in one message

Mock `contact_cache`, `status.global_api.get_msg`, and NcatBot segment objects.

Files:
- NEW `tests/test_message_parser.py`

### Step 6: Update existing tests

Update `tests/test_message_handler.py` to account for the new `parse_message` call. The handler tests that call `on_group`/`on_private` will need to mock `message_parser.parse_message` since the event object now needs a `message` attribute (MessageArray) instead of just `raw_message`.

Files:
- EDIT `tests/test_message_handler.py`

### Step 7: Run tests and verify

Run the full test suite to ensure all existing and new tests pass. Fix any issues.

## Review Checkpoints

- After Step 2: Review `message_parser.py` for correctness of segment handling logic
- After Step 5: Review test coverage before proceeding to integration
