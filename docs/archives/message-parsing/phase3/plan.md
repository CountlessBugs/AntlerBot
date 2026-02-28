# Phase 3 Implementation Plan: Media Passthrough

**Goal:** Add direct media input to the LLM via LangChain's multimodal `content` list. When `passthrough=true` (and `transcribe=false`) for a media type, the media file is downloaded, trimmed (if audio/video), base64-encoded, and sent as a content block alongside the text — so the LLM sees the actual image/audio/video instead of a text description.

**Priority rule:** `transcribe > passthrough`. If both are true, transcribe wins (already enforced by the existing `if transcribe` check in `parse_message`).

**Architecture:** `ParsedMessage` gains a `content_blocks` list. When passthrough media exists, `scheduler.py` builds a `list[dict]` content (text + media blocks) instead of a plain string. `agent.py` accepts `HumanMessage(content=list)` when content is a list.

Design doc: `docs/plans/message-parsing-design.md` — Phase 3 section (lines 143-181)

---

### Task 1: Add passthrough support to media_processor.py

**Files:**
- Modify: `src/core/media_processor.py`
- Modify: `tests/test_media_processor.py`

**Step 1: Write failing tests**

Add to `tests/test_media_processor.py`:

```python
from src.core.media_processor import passthrough_media_segment

@pytest.mark.anyio
async def test_passthrough_image():
    seg = MagicMock()
    seg.url = "https://example.com/cat.jpg"
    seg.get_file_name.return_value = "cat.jpg"
    seg.download = AsyncMock(return_value="/tmp/cat.jpg")
    settings = {"media": {"image": {"passthrough": True}}}
    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    mock_file.read.return_value = b"fake image bytes"
    with patch("builtins.open", return_value=mock_file), \
         patch("src.core.media_processor._cleanup_temp"):
        result = await passthrough_media_segment(seg, "image", settings)
        assert result is not None
        assert result["type"] == "image_url"
        assert result["image_url"]["url"].startswith("data:image/")

@pytest.mark.anyio
async def test_passthrough_disabled():
    seg = MagicMock()
    seg.get_file_name.return_value = "cat.jpg"
    settings = {"media": {"image": {"passthrough": False}}}
    result = await passthrough_media_segment(seg, "image", settings)
    assert result is None

@pytest.mark.anyio
async def test_passthrough_download_failure():
    seg = MagicMock()
    seg.get_file_name.return_value = "cat.jpg"
    seg.download = AsyncMock(side_effect=Exception("network error"))
    settings = {"media": {"image": {"passthrough": True}}}
    result = await passthrough_media_segment(seg, "image", settings)
    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_media_processor.py -k "passthrough" -v`
Expected: FAIL with `ImportError: cannot import name 'passthrough_media_segment'`

**Step 3: Write implementation**

Add to `src/core/media_processor.py`:

```python
_MIME_MAP = {
    "image": "image/png",
    "audio": "audio/mpeg",
    "video": "video/mp4",
}

async def passthrough_media_segment(seg, media_type: str, settings: dict, source: str = "") -> dict | None:
    """Download media, base64-encode, return a content_block dict for LLM input. Returns None on failure or if disabled."""
    type_cfg = settings.get("media", {}).get(media_type, {})
    if not type_cfg.get("passthrough", False):
        return None

    path = await download_media(seg, source)
    if not path:
        return None

    try:
        # Trim audio/video if needed
        if media_type in ("audio", "video"):
            max_dur = type_cfg.get("max_duration", 0)
            if max_dur > 0:
                trimmed = await trim_media(path, max_dur)
                if trimmed is None:
                    return None
                if trimmed != path:
                    _cleanup_temp(path)
                    path = trimmed

        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

        mime = _MIME_MAP.get(media_type, "application/octet-stream")
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}
    finally:
        _cleanup_temp(path)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_media_processor.py -k "passthrough" -v`
Expected: All 3 passthrough tests PASS

**Step 5: Commit**

```bash
git add src/core/media_processor.py tests/test_media_processor.py
git commit -m "feat(media): add passthrough_media_segment for direct LLM input"
```

---

### Task 2: Add ContentBlock to ParsedMessage and update parse_message

**Files:**
- Modify: `src/core/message_parser.py`
- Modify: `tests/test_message_parser.py`

**Step 1: Write failing tests**

Add to `tests/test_message_parser.py`:

```python
@pytest.mark.anyio
async def test_parse_image_passthrough_creates_content_block():
    settings = {**DEFAULT_SETTINGS, "media": {
        "image": {"transcribe": False, "passthrough": True},
        "timeout": 60, "sync_process_threshold_mb": 1,
    }}
    seg = _make_seg("Image", file="pic.jpg", file_name="pic.jpg", file_size=500_000)
    seg.get_file_name = MagicMock(return_value="pic.jpg")
    msg = [_make_seg("Text", text="look at this "), seg]
    with patch("src.core.message_parser.media_processor") as mock_mp:
        mock_mp.passthrough_media_segment = AsyncMock(
            return_value={"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}
        )
        mock_mp._MEDIA_TAG = {"image": "image", "audio": "audio", "video": "video", "document": "file"}
        result = await parse_message(msg, settings)
    assert result.text == "look at this "
    assert len(result.content_blocks) == 1
    assert result.content_blocks[0]["type"] == "image_url"

@pytest.mark.anyio
async def test_parse_image_transcribe_overrides_passthrough():
    """transcribe=true takes priority over passthrough=true."""
    settings = {**DEFAULT_SETTINGS, "media": {
        "image": {"transcribe": True, "passthrough": True},
        "timeout": 60, "sync_process_threshold_mb": 1,
    }}
    seg = _make_seg("Image", file="pic.jpg", file_name="pic.jpg", file_size=500_000)
    seg.get_file_name = MagicMock(return_value="pic.jpg")
    msg = [seg]
    with patch("src.core.message_parser.media_processor") as mock_mp:
        mock_mp.process_media_segment = AsyncMock(return_value='<image filename="pic.jpg">a cat</image>')
        mock_mp._MEDIA_TAG = {"image": "image", "audio": "audio", "video": "video", "document": "file"}
        result = await parse_message(msg, settings)
    assert result.content_blocks == []
    assert "a cat" in result.text

@pytest.mark.anyio
async def test_parse_passthrough_failure_falls_back_to_placeholder():
    settings = {**DEFAULT_SETTINGS, "media": {
        "image": {"transcribe": False, "passthrough": True},
        "timeout": 60, "sync_process_threshold_mb": 1,
    }}
    seg = _make_seg("Image", file="pic.jpg", file_name="pic.jpg", file_size=500_000)
    seg.get_file_name = MagicMock(return_value="pic.jpg")
    msg = [seg]
    with patch("src.core.message_parser.media_processor") as mock_mp:
        mock_mp.passthrough_media_segment = AsyncMock(return_value=None)
        mock_mp._MEDIA_TAG = {"image": "image", "audio": "audio", "video": "video", "document": "file"}
        result = await parse_message(msg, settings)
    assert result.content_blocks == []
    assert "<image" in result.text
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_message_parser.py -k "passthrough" -v`
Expected: FAIL — `ParsedMessage` has no `content_blocks` attribute

**Step 3: Update ParsedMessage and parse_message**

In `src/core/message_parser.py`:

1. Add `content_blocks: list[dict]` field to `ParsedMessage` (default empty list)
2. In `parse_message()`, after the `if type_cfg.get("transcribe", False):` block, add an `elif type_cfg.get("passthrough", False):` branch that:
   - For small files: awaits `media_processor.passthrough_media_segment()` inline
   - For large files: creates a MediaTask for async passthrough (reuse existing placeholder flow)
   - On success: appends the content_block dict to `content_blocks` list
   - On failure: falls back to the static `<tag />` placeholder

**Step 4: Run all tests**

Run: `pytest tests/test_message_parser.py -v`
Expected: All tests PASS (existing + new)

**Step 5: Commit**

```bash
git add src/core/message_parser.py tests/test_message_parser.py
git commit -m "feat(parser): add passthrough content_blocks to ParsedMessage"
```

---

### Task 3: Update scheduler to build multimodal content list

**Files:**
- Modify: `src/core/scheduler.py`
- Modify: `tests/test_scheduler_media.py`

**Step 1: Write failing tests**

Add to `tests/test_scheduler_media.py`:

```python
def test_build_content_text_only():
    """No content_blocks → plain string."""
    from src.core.scheduler import _build_agent_content
    pm = ParsedMessage(text="hello world", content_blocks=[])
    result = _build_agent_content("formatted msg", pm)
    assert result == "formatted msg"

def test_build_content_with_blocks():
    """With content_blocks → list[dict] with text + media blocks."""
    from src.core.scheduler import _build_agent_content
    pm = ParsedMessage(
        text="look at this",
        content_blocks=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}],
    )
    result = _build_agent_content("formatted msg", pm)
    assert isinstance(result, list)
    assert result[0] == {"type": "text", "text": "formatted msg"}
    assert result[1]["type"] == "image_url"

def test_build_content_no_parsed_message():
    """None parsed_message → plain string."""
    from src.core.scheduler import _build_agent_content
    result = _build_agent_content("formatted msg", None)
    assert result == "formatted msg"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scheduler_media.py -v`
Expected: FAIL with `ImportError: cannot import name '_build_agent_content'`

**Step 3: Write implementation**

Add to `src/core/scheduler.py`:

```python
def _build_agent_content(msg: str, parsed_message: ParsedMessage | None) -> str | list:
    """Build agent input content. Returns a list if there are passthrough content blocks, else a string."""
    if not parsed_message or not parsed_message.content_blocks:
        return msg
    return [
        {"type": "text", "text": msg},
        *parsed_message.content_blocks,
    ]
```

Update `_batch` to carry `parsed_message` through the batch pipeline. Update `_process_loop` to merge content_blocks from all parsed messages in a batch and pass multimodal content to `agent._invoke`.

**Step 4: Run tests**

Run: `pytest tests/test_scheduler_media.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/core/scheduler.py tests/test_scheduler_media.py
git commit -m "feat(scheduler): build multimodal content list for passthrough media"
```

---

### Task 4: Update agent._invoke to accept list content

**Files:**
- Modify: `src/core/agent.py`
- Modify: `tests/test_agent.py`

**Step 1: Write failing test**

Add to `tests/test_agent.py`:

```python
def test_human_message_with_list_content():
    """When message is a list, HumanMessage should use content=list."""
    from langchain_core.messages import HumanMessage
    content = [
        {"type": "text", "text": "look at this"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]
    msg = HumanMessage(content=content)
    assert isinstance(msg.content, list)
    assert len(msg.content) == 2
```

**Step 2: Update agent._invoke**

In `src/core/agent.py`, update the `_invoke` method to accept `str | list` for the `message` parameter:

```python
async def _invoke(
    reason: ...,
    message: str | list = "",
    ...
) -> AsyncGenerator[str, None]:
    ...
    if reason == "session_timeout":
        initial = list(_history)
    elif reason == "complex_reschedule":
        initial = list(messages)
    else:
        initial = _history + [HumanMessage(content=message if message else "")]
```

This works because `HumanMessage(content=...)` already accepts both `str` and `list[dict]`.

**Step 3: Update scheduler to pass list content**

In `src/core/scheduler.py`, update `_process_loop` to build content via `_build_agent_content` and pass it to `agent._invoke`:

```python
for source_key, msgs, reply_fns, parsed_msgs in batches:
    _current_source = source_key
    # Build content (may be str or list if passthrough blocks exist)
    content = _build_batch_content(msgs, parsed_msgs)
    async for seg in agent._invoke("user_message", content):
        await reply_fns[-1](seg)
```

**Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/core/agent.py src/core/scheduler.py tests/test_agent.py
git commit -m "feat(agent): accept multimodal content list in _invoke"
```

---

### Task 5: Handle passthrough in async (large file) flow

**Files:**
- Modify: `src/core/message_parser.py`
- Modify: `src/core/scheduler.py`
- Modify: `tests/test_message_parser.py`

**Step 1: Write failing tests for large-file passthrough**

```python
@pytest.mark.anyio
async def test_large_file_passthrough_uses_placeholder():
    """Large passthrough file uses placeholder + async MediaTask."""
    settings = {**DEFAULT_SETTINGS, "media": {
        "image": {"transcribe": False, "passthrough": True},
        "timeout": 60, "sync_process_threshold_mb": 1,
    }}
    seg = _make_seg("Image", file="pic.jpg", file_name="pic.jpg", file_size=5_000_000)
    seg.get_file_name = MagicMock(return_value="pic.jpg")
    msg = [seg]
    with patch("src.core.message_parser.media_processor") as mock_mp:
        mock_mp.passthrough_media_segment = AsyncMock(
            return_value={"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}
        )
        mock_mp._MEDIA_TAG = {"image": "image", "audio": "audio", "video": "video", "document": "file"}
        result = await parse_message(msg, settings)
    assert len(result.media_tasks) == 1
    assert result.media_tasks[0].media_type == "image"
```

**Step 2: Update _resolve_media_and_enqueue for passthrough results**

In `scheduler.py`, update `_resolve_media_and_enqueue` to detect when a resolved media task returns a `dict` (content block) vs a `str` (transcription text), and handle accordingly — content blocks get added to the follow-up message as multimodal content.

**Step 3: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/core/message_parser.py src/core/scheduler.py tests/
git commit -m "feat(media): support async passthrough for large files"
```

---

### Task 6: Full integration test and verification

**Files:**
- Modify: `tests/test_message_handler.py`

**Step 1: Write integration test**

```python
@pytest.mark.anyio
async def test_group_message_with_passthrough_image():
    """Full flow: group message with passthrough image → parse → enqueue with content_blocks."""
    fake_pm = ParsedMessage(
        text="look at this",
        content_blocks=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}],
    )
    # ... (mock parse_message, scheduler.enqueue, verify content_blocks passed through)
```

**Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_message_handler.py
git commit -m "test: add integration test for media passthrough flow"
```

---

## Review Checkpoints

- After Task 1: Review `passthrough_media_segment` — download, trim, base64, content_block format
- After Task 2: Review `ParsedMessage.content_blocks` and passthrough branch in `parse_message`
- After Task 4: Review full pipeline — parser → scheduler → agent with multimodal content
- After Task 6: Review all tests pass, full integration verified
