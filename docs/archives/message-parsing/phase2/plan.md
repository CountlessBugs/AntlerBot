# Phase 2 Implementation Plan: Media Transcription

**Goal:** Add download, trim, and transcription support for Image, Audio, Video, and Document segments so the LLM receives text descriptions of media instead of empty placeholders.

**Architecture:** `parse_message()` returns a `ParsedMessage` dataclass containing text parts with `{{media:uuid}}` placeholders and a list of async `MediaTask`s. The scheduler awaits all media tasks (with timeout), replaces placeholders with transcription results, then passes the final string to the agent. A dedicated `media_processor.py` module handles download, ffmpeg trim, and LLM transcription.

**Tech Stack:** Python asyncio, aiohttp (download), ffmpeg (audio/video trim), langchain `init_chat_model` (transcription), Python `tempfile` (temp files)

Design doc: `docs/plans/message-parsing-design.md` — Phase 2 section

---

### Task 1: Add ParsedMessage and MediaTask dataclasses

**Files:**
- Modify: `src/core/message_parser.py`
- Test: `tests/test_message_parser.py`

**Step 1: Write the failing test**

Add to `tests/test_message_parser.py`:

```python
from src.core.message_parser import ParsedMessage, MediaTask

def test_parsed_message_no_media():
    pm = ParsedMessage(text="hello world", media_tasks=[])
    assert pm.text == "hello world"
    assert pm.media_tasks == []

def test_parsed_message_with_placeholder():
    pm = ParsedMessage(text="look {{media:abc123}} nice", media_tasks=[])
    assert "{{media:abc123}}" in pm.text

def test_parsed_message_resolve_no_tasks():
    pm = ParsedMessage(text="hello world", media_tasks=[])
    assert pm.resolve() == "hello world"

def test_parsed_message_resolve_replaces_placeholders():
    pm = ParsedMessage(text="look {{media:id1}} nice", media_tasks=[])
    assert pm.resolve({"id1": '<image filename="cat.jpg">a cat</image>'}) == 'look <image filename="cat.jpg">a cat</image> nice'

def test_parsed_message_resolve_failed_placeholder():
    pm = ParsedMessage(text="see {{media:id1}} here", media_tasks=[])
    assert pm.resolve({"id1": '<image error="处理失败" />'}) == 'see <image error="处理失败" /> here'
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_message_parser.py::test_parsed_message_no_media -v`
Expected: FAIL with `ImportError: cannot import name 'ParsedMessage'`

**Step 3: Write minimal implementation**

Add to top of `src/core/message_parser.py`, after imports:

```python
import uuid
from dataclasses import dataclass, field

@dataclass
class MediaTask:
    placeholder_id: str
    task: asyncio.Task
    media_type: str  # "image" / "audio" / "video" / "document"

@dataclass
class ParsedMessage:
    text: str
    media_tasks: list[MediaTask] = field(default_factory=list)

    def resolve(self, results: dict[str, str] | None = None) -> str:
        if not results:
            return self.text
        out = self.text
        for pid, replacement in results.items():
            out = out.replace(f"{{{{{media_prefix}{pid}}}}}", replacement)
        return out
```

Where `media_prefix = "media:"` is a module-level constant.

Also add `import asyncio` to the imports.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_message_parser.py -k "parsed_message" -v`
Expected: All 5 new tests PASS

**Step 5: Commit**

```bash
git add src/core/message_parser.py tests/test_message_parser.py
git commit -m "feat(parser): add ParsedMessage and MediaTask dataclasses"
```

---

### Task 2: Add media settings to configuration

**Files:**
- Modify: `config/agent/settings.yaml`
- Modify: `src/core/agent.py` — `_SETTINGS_DEFAULTS`
- Modify: `.env.example`

**Step 1: Add media config block to settings.yaml**

Append to `config/agent/settings.yaml`:

```yaml
media:
  transcription_model: ""
  transcription_provider: ""
  timeout: 60

  image:
    transcribe: false
    passthrough: false

  audio:
    transcribe: false
    passthrough: false
    max_duration: 60
    trim_over_limit: true

  video:
    transcribe: false
    passthrough: false
    max_duration: 30
    trim_over_limit: true

  document:
    transcribe: false
    passthrough: false
```

**Step 2: Add media defaults to agent.py**

In `src/core/agent.py`, update `_SETTINGS_DEFAULTS`:

```python
_SETTINGS_DEFAULTS = {
    "context_limit_tokens": 8000,
    "timeout_summarize_seconds": 1800,
    "timeout_clear_seconds": 3600,
    "reply_quote_truncate_length": 50,
    "media": {
        "transcription_model": "",
        "transcription_provider": "",
        "timeout": 60,
        "image": {"transcribe": False, "passthrough": False},
        "audio": {"transcribe": False, "passthrough": False, "max_duration": 60, "trim_over_limit": True},
        "video": {"transcribe": False, "passthrough": False, "max_duration": 30, "trim_over_limit": True},
        "document": {"transcribe": False, "passthrough": False},
    },
}
```

Also update `load_settings()` to deep-merge the `media` key:

```python
def load_settings() -> dict:
    if not os.path.exists(SETTINGS_PATH):
        return dict(_SETTINGS_DEFAULTS)
    import yaml
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = {**_SETTINGS_DEFAULTS, **data}
    # Deep-merge media config
    default_media = _SETTINGS_DEFAULTS.get("media", {})
    user_media = data.get("media", )
    merged_media = {**default_media, **user_media}
    for key in ("image", "audio", "video", "document"):
        merged_media[key] = {**default_media.get(key, {}), **user_media.get(key, {})}
    merged["media"] = merged_media
    return merged
```

**Step 3: Add transcription env vars to .env.example**

Append to `.env.example`:

```
TRANSCRIPTION_API_KEY=
TRANSCRIPTION_BASE_URL=
```

**Step 4: Commit**

```bash
git add config/agent/settings.yaml src/core/agent.py .env.example
git commit -m "feat(config): add media transcription settings and env vars"
```

---

### Task 3: Create media_processor.py — ffmpeg check and download

**Files:**
- Create: `src/core/media_processor.py`
- Test: `tests/test_media_processor.py`

**Step 1: Write the failing tests for ffmpeg check and download**

Create `tests/test_media_processor.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.core.media_processor import check_ffmpeg, download_media


@pytest.fixture(autouse=True)
def reset_ffmpeg_cache():
    import src.core.media_processor as mp
    mp._ffmpeg_available = None
    yield
    mp._ffmpeg_available = None


def test_check_ffmpeg_available():
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        assert check_ffmpeg() is True


def test_check_ffmpeg_unavailable():
    with patch("shutil.which", return_value=None):
        assert check_ffmpeg() is False


def test_check_ffmpeg_caches_result():
    with patch("shutil.which", return_value="/usr/bin/ffmpeg") as mock_which:
        check_ffmpeg()
        check_ffmpeg()
        mock_which.assert_called_once()


@pytest.mark.anyio
async def test_download_media_from_url():
    seg = MagicMock()
    seg.url = "https://example.com/pic.jpg"
    seg.file_name = "pic.jpg"
    seg.download = AsyncMock(return_value="/tmp/pic.jpg")
    result = await download_media(seg)
    seg.download.assert_awaited_once()
    assert result is not None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_media_processor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.media_processor'`

**Step 3: Write minimal implementation**

Create `src/core/media_processor.py`:

```python
import logging
import os
import shutil
import tempfile

logger = logging.getLogger(__name__)

_ffmpeg_available: bool | None = None


def check_ffmpeg() -> bool:
    global _ffmpeg_available
    if _ffmpeg_available is None:
        _ffmpeg_available = shutil.which("ffmpeg") is not None
        if _ffmpeg_available:
            logger.info("ffmpeg found")
        else:
            logger.warning("ffmpeg not found; audio/video trimming disabled")
    return _ffmpeg_available


async def download_media(seg) -> str | None:
    """Download a media segment to a temp file. Returns the file path or None on failure."""
    try:
        tmp_dir = tempfile.mkdtemp(prefix="antlerbot_media_")
        path = await seg.download(tmp_dir)
        return path
    except Exception:
        logger.warning("Failed to download media: %s", getattr(seg, "file_name", "unknown"), exc_info=True)
        return None
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_media_processor.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/core/media_processor.py tests/test_media_processor.py
git commit -m "feat(media): add ffmpeg check and media download"
```

---

### Task 4: Add ffmpeg trim to media_processor.py

**Files:**
- Modify: `src/core/media_processor.py`
- Modify: `tests/test_media_processor.py`

**Step 1: Write the failing tests for trim**

Add to `tests/test_media_processor.py`:

```python
from src.core.media_processor import trim_media


@pytest.mark.anyio
async def test_trim_media_under_limit():
    """File under max_duration is returned as-is."""
    with patch("src.core.media_processor._get_duration", return_value=30.0):
        result = await trim_media("/tmp/voice.amr", max_duration=60)
        assert result == "/tmp/voice.amr"


@pytest.mark.anyio
async def test_trim_media_over_limit_trims():
    """File over max_duration gets trimmed via ffmpeg."""
    with patch("src.core.media_processor._get_duration", return_value=120.0), \
         patch("src.core.media_processor.check_ffmpeg", return_value=True), \
         patch("src.core.media_processor._run_ffmpeg_trim", new_callable=AsyncMock, return_value="/tmp/trimmed.amr"):
        result = await trim_media("/tmp/voice.amr", max_duration=60)
        assert result == "/tmp/trimmed.amr"


@pytest.mark.anyio
async def test_trim_media_over_limit_no_ffmpeg():
    """File over limit with no ffmpeg returns None."""
    with patch("src.core.media_processor._get_duration", return_value=120.0), \
         patch("src.core.media_processor.check_ffmpeg", return_value=False):
        result = await trim_media("/tmp/voice.amr", max_duration=60)
        assert result is None


@pytest.mark.anyio
async def test_trim_media_zero_max_duration():
    """max_duration=0 means unlimited, no trim."""
    with patch("src.core.media_processor._get_duration", return_value=9999.0):
        result = await trim_media("/tmp/voice.amr", max_duration=0)
        assert result == "/tmp/voice.amr"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_media_processor.py -k "trim" -v`
Expected: FAIL with `ImportError: cannot import name 'trim_media'`

**Step 3: Write minimal implementation**

Add to `src/core/media_processor.py`:

```python
import asyncio
import json


async def _get_duration(path: str) -> float:
    """Get media duration in seconds using ffprobe."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        info = json.loads(stdout)
        return float(info["format"]["duration"])
    except Exception:
        logger.warning("ffprobe failed for %s", path, exc_info=True)
        return 0.0


async def _run_ffmpeg_trim(input_path: str, max_duration: int) -> str | None:
    """Trim media to max_duration seconds. Returns output path or None."""
    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_trimmed{ext}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", input_path,
            "-t", str(max_duration),
            "-c", "copy", output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode == 0:
            return output_path
        logger.warning("ffmpeg trim failed with code %d", proc.returncode)
        return None
    except Exception:
        logger.warning("ffmpeg trim error for %s", input_path, exc_info=True)
        return None


async def trim_media(path: str, max_duration: int) -> str | None:
    """Trim media if over max_duration. Returns path (original or trimmed) or None if skip."""
    if max_duration <= 0:
        return path
    duration = await _get_duration(path)
    if duration <= max_duration:
        return path
    if not check_ffmpeg():
        logger.warning("File %s exceeds %ds but ffmpeg unavailable, skipping", path, max_duration)
        return None
    return await _run_ffmpeg_trim(path, max_duration)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_media_processor.py -k "trim" -v`
Expected: All 4 trim tests PASS

**Step 5: Commit**

```bash
git add src/core/media_processor.py tests/test_media_processor.py
git commit -m "feat(media): add ffmpeg-based media trimming"
```

---

### Task 5: Add transcription to media_processor.py

**Files:**
- Modify: `src/core/media_processor.py`
- Modify: `tests/test_media_processor.py`

**Step 1: Write the failing tests for transcription**

Add to `tests/test_media_processor.py`:

```python
from src.core.media_processor import transcribe_media


@pytest.mark.anyio
async def test_transcribe_image():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="一只橘猫趴在沙发上")
    with patch("src.core.media_processor._get_transcription_llm", return_value=mock_llm):
        result = await transcribe_media("/tmp/cat.jpg", "image")
        assert result == "一只橘猫趴在沙发上"


@pytest.mark.anyio
async def test_transcribe_audio():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="用户说了你好")
    with patch("src.core.media_processor._get_transcription_llm", return_value=mock_llm):
        result = await transcribe_media("/tmp/voice.amr", "audio")
        assert result == "用户说了你好"


@pytest.mark.anyio
async def test_transcribe_failure():
    with patch("src.core.media_processor._get_transcription_llm", side_effect=Exception("no model")):
        result = await transcribe_media("/tmp/cat.jpg", "image")
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_media_processor.py -k "transcribe" -v`
Expected: FAIL with `ImportError: cannot import name 'transcribe_media'`

**Step 3: Write minimal implementation**

Add to `src/core/media_processor.py`:

```python
import base64
import os

_transcription_llm = None

_TRANSCRIPTION_PROMPTS = {
    "image": "请简要描述这张图片的内容，用一两句话概括。",
    "audio": "请转述这段音频的内容。",
    "video": "请简要描述这段视频的内容，用一两句话概括。",
    "document": "请简要概括这份文档的内容。",
}


def _get_transcription_llm(settings: dict):
    """Get or create the transcription LLM. Uses main LLM if no override configured."""
    global _transcription_llm
    if _transcription_llm is not None:
        return _transcription_llm

    media_cfg = settings.get("media", {})
    model = media_cfg.get("transcription_model", "")
    provider = media_cfg.get("transcription_provider", "")

    if model and provider:
        # Use override model
        api_key = os.environ.get("TRANSCRIPTION_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        base_url = os.environ.get("TRANSCRIPTION_BASE_URL", os.environ.get("OPENAI_BASE_URL", ""))
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        from langchain.chat_models import init_chat_model
        _transcription_llm = init_chat_model(model, model_provider=provider, **kwargs)
    else:
        # Reuse main LLM
        from src.core.agent import _llm, _ensure_initialized
        _ensure_initialized()
        _transcription_llm = _llm

    return _transcription_llm
```

Also add the `transcribe_media` function:

```python
async def transcribe_media(path: str, media_type: str, settings: dict | None = None) -> str | None:
    """Transcribe a media file using the configured LLM. Returns description text or None."""
    try:
        llm = _get_transcription_llm(settings or {})
        prompt = _TRANSCRIPTION_PROMPTS.get(media_type, "请描述这个文件的内容。")

        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

        mime_map = {
            "image": "image/png",
            "audio": "audio/mpeg",
            "video": "video/mp4",
            "document": "application/pdf",
        }
        mime = mime_map.get(media_type, "application/octet-stream")

        from langchain_core.messages import HumanMessage
        msg = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
        ])
        response = llm.invoke([msg])
        return response.content
    except Exception:
        logger.warning("Transcription failed for %s (%s)", path, media_type, exc_info=True)
        return None
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_media_processor.py -k "transcribe" -v`
Expected: All 3 transcribe tests PASS

**Step 5: Commit**

```bash
git add src/core/media_processor.py tests/test_media_processor.py
git commit -m "feat(media): add LLM-based media transcription"
```

---

### Task 6: Add process_media_segment orchestrator to media_processor.py

**Files:**
- Modify: `src/core/media_processor.py`
- Modify: `tests/test_media_processor.py`

**Step 1: Write the failing tests**

Add to `tests/test_media_processor.py`:

```python
from src.core.media_processor import process_media_segment


@pytest.mark.anyio
async def test_process_image_transcribe():
    seg = MagicMock()
    seg.url = "https://example.com/cat.jpg"
    seg.file_name = "cat.jpg"
    seg.download = AsyncMock(return_value="/tmp/cat.jpg")
    settings = {"media": {"image": {"transcribe": True}}}
    with patch("src.core.media_processor.transcribe_media", new_callable=AsyncMock, return_value="一只猫"):
        result = await process_media_segment(seg, "image", settings)
        assert result == '<image filename="cat.jpg">一只猫</image>'


@pytest.mark.anyio
async def test_process_image_disabled():
    seg = MagicMock()
    seg.file_name = "cat.jpg"
    settings = {"media": {"image": {"transcribe": False}}}
    result = await process_media_segment(seg, "image", settings)
    assert result == "<image />"


@pytest.mark.anyio
async def test_process_audio_transcribe_with_trim():
    seg = MagicMock()
    seg.file_name = "voice.amr"
    seg.download = AsyncMock(return_value="/tmp/voice.amr")
    settings = {"media": {"audio": {"transcribe": True, "max_duration": 60, "trim_over_limit": True}}}
    with patch("src.core.media_processor.trim_media", new_callable=AsyncMock, return_value="/tmp/voice.amr"), \
         patch("src.core.media_processor.transcribe_media", new_callable=AsyncMock, return_value="你好"), \
         patch("src.core.media_processor._cleanup_temp"):
        result = await process_media_segment(seg, "audio", settings)
        assert result == '<audio filename="voice.amr">你好</audio>'


@pytest.mark.anyio
async def test_process_download_failure():
    seg = MagicMock()
    seg.file_name = "pic.jpg"
    seg.download = AsyncMock(side_effect=Exception("network error"))
    settings = {"media": {"image": {"transcribe": True}}}
    result = await process_media_segment(seg, "image", settings)
    assert result == '<image error="下载失败" />'


@pytest.mark.anyio
async def test_process_transcription_failure():
    seg = MagicMock()
    seg.file_name = "pic.jpg"
    seg.download = AsyncMock(return_value="/tmp/pic.jpg")
    settings = {"media": {"image": {"transcribe": True}}}
    with patch("src.core.media_processor.transcribe_media", new_callable=AsyncMock, return_value=None), \
         patch("src.core.media_processor._cleanup_temp"):
        result = await process_media_segment(seg, "image", settings)
        assert result == '<image error="转述失败" />'
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_media_processor.py -k "process_" -v`
Expected: FAIL with `ImportError: cannot import name 'process_media_segment'`

**Step 3: Write minimal implementation**

Add to `src/core/media_processor.py`:

```python
_MEDIA_TAG = {
    "image": "image",
    "audio": "audio",
    "video": "video",
    "document": "file",
}


def _cleanup_temp(path: str) -> None:
    """Remove a temp file and its parent dir if empty."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
            parent = os.path.dirname(path)
            if parent and not os.listdir(parent):
                os.rmdir(parent)
    except Exception:
        logger.debug("Cleanup failed for %s", path, exc_info=True)
```

Also add the `process_media_segment` function:

```python
async def process_media_segment(seg, media_type: str, settings: dict) -> str:
    """Full pipeline: download → trim → transcribe → format result."""
    tag = _MEDIA_TAG.get(media_type, media_type)
    type_cfg = settings.get("media", {}).get(media_type, {})
    filename = getattr(seg, "file_name", "") or ""

    if not type_cfg.get("transcribe", False):
        return f"<{tag} />"

    # Download
    path = await download_media(seg)
    if not path:
        return f'<{tag} error="下载失败" />'

    try:
        # Trim (audio/video only)
        if media_type in ("audio", "video"):
            max_dur = type_cfg.get("max_duration", 0)
            if max_dur > 0:
                trimmed = await trim_media(path, max_dur)
                if trimmed is None:
                    if type_cfg.get("trim_over_limit", True):
                        return f'<{tag} error="裁剪失败" />'
                    else:
                        return f"<{tag} />"
                if trimmed != path:
                    _cleanup_temp(path)
                    path = trimmed

        # Transcribe
        desc = await transcribe_media(path, media_type, settings)
        if desc:
            fn_attr = f' filename="{filename}"' if filename else ""
            return f"<{tag}{fn_attr}>{desc}</{tag}>"
        return f'<{tag} error="转述失败" />'
    finally:
        _cleanup_temp(path)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_media_processor.py -k "process_" -v`
Expected: All 5 process tests PASS

**Step 5: Commit**

```bash
git add src/core/media_processor.py tests/test_media_processor.py
git commit -m "feat(media): add process_media_segment orchestrator"
```

---

### Task 7: Update parse_message() to return ParsedMessage with media tasks

**Files:**
- Modify: `src/core/message_parser.py`
- Modify: `tests/test_message_parser.py`

**Step 1: Write the failing tests**

Add to `tests/test_message_parser.py`:

```python
from src.core.message_parser import ParsedMessage


@pytest.mark.anyio
async def test_parse_returns_parsed_message():
    msg = [_make_seg("Text", text="hello")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert isinstance(result, ParsedMessage)
    assert result.text == "hello"
    assert result.media_tasks == []
```

Also add tests for media task launching:

```python
@pytest.mark.anyio
async def test_parse_image_transcribe_creates_task():
    settings = {**DEFAULT_SETTINGS, "media": {"image": {"transcribe": True}, "timeout": 60}}
    msg = [_make_seg("Image", file="pic.jpg", file_name="pic.jpg")]
    with patch("src.core.message_parser.media_processor") as mock_mp:
        mock_mp.process_media_segment = AsyncMock(return_value='<image filename="pic.jpg">a cat</image>')
        result = await parse_message(msg, settings)
        assert isinstance(result, ParsedMessage)
        assert len(result.media_tasks) == 1
        assert "{{media:" in result.text


@pytest.mark.anyio
async def test_parse_image_no_transcribe_placeholder():
    settings = {**DEFAULT_SETTINGS, "media": {"image": {"transcribe": False}}}
    msg = [_make_seg("Image", file="pic.jpg")]
    result = await parse_message(msg, settings)
    assert isinstance(result, ParsedMessage)
    assert result.text == "<image />"
    assert result.media_tasks == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_message_parser.py -k "parse_returns_parsed_message" -v`
Expected: FAIL — `parse_message` currently returns `str`, not `ParsedMessage`

**Step 3: Update parse_message() implementation**

Modify `src/core/message_parser.py`. Change the return type and add media task launching:

```python
from src.core import media_processor

_MEDIA_TYPE_MAP = {
    Image: "image",
    Record: "audio",
    Video: "video",
    File: "document",
}
```

Update the `parse_message` function signature and body:

```python
async def parse_message(message_array, settings: dict) -> ParsedMessage:
    parts: list[str] = []
    media_tasks: list[MediaTask] = []
    for seg in message_array:
        if isinstance(seg, Text):
            parts.append(seg.text)
        elif isinstance(seg, (At, AtAll)):
            parts.append(await _parse_at(seg))
        elif isinstance(seg, Face):
            parts.append(_parse_face(seg))
        elif isinstance(seg, Reply):
            parts.append(await _parse_reply(seg, settings))
        else:
            media_type = next(
                (mt for cls, mt in _MEDIA_TYPE_MAP.items() if isinstance(seg, cls)),
                None,
            )
            if media_type:
                type_cfg = settings.get("media", {}).get(media_type, {})
                if type_cfg.get("transcribe", False):
                    pid = uuid.uuid4().hex[:12]
                    parts.append(f"{{{{media:{pid}}}}}")
                    task = asyncio.create_task(
                        media_processor.process_media_segment(seg, media_type, settings)
                    )
                    media_tasks.append(MediaTask(placeholder_id=pid, task=task, media_type=media_type))
                else:
                    tag = media_processor._MEDIA_TAG.get(media_type, media_type)
                    parts.append(f"<{tag} />")
            else:
                try:
                    summary = seg.get_summary()
                except Exception:
                    summary = None
                parts.append(summary or f'<unsupported type="{seg.type}" />')
    return ParsedMessage(text="".join(parts), media_tasks=media_tasks)
```

Also remove the old `_MEDIA_PLACEHOLDERS` dict since it's replaced by `_MEDIA_TYPE_MAP` + `media_processor._MEDIA_TAG`.

**Step 4: Update existing tests**

All existing tests that assert `== "some string"` need updating to assert `result.text == "some string"` since `parse_message` now returns `ParsedMessage`. Update each test, e.g.:

```python
# Before:
assert await parse_message(msg, DEFAULT_SETTINGS) == "hello world"

# After:
result = await parse_message(msg, DEFAULT_SETTINGS)
assert result.text == "hello world"
```

**Step 5: Run all tests to verify they pass**

Run: `pytest tests/test_message_parser.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/core/message_parser.py tests/test_message_parser.py
git commit -m "feat(parser): return ParsedMessage with async media tasks"
```

---

### Task 8: Update scheduler to await media tasks and resolve placeholders

**Files:**
- Modify: `src/core/scheduler.py`
- Test: `tests/test_scheduler_media.py`

**Step 1: Write the failing tests**

Create `tests/test_scheduler_media.py`:

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.message_parser import ParsedMessage, MediaTask


@pytest.mark.anyio
async def test_resolve_media_tasks_success():
    from src.core.scheduler import _resolve_media
    task = AsyncMock(return_value='<image filename="cat.jpg">a cat</image>')()
    pm = ParsedMessage(
        text="look {{media:id1}} nice",
        media_tasks=[MediaTask(placeholder_id="id1", task=task, media_type="image")],
    )
    result = await _resolve_media(pm, timeout=10)
    assert result == 'look <image filename="cat.jpg">a cat</image> nice'


@pytest.mark.anyio
async def test_resolve_media_tasks_timeout():
    from src.core.scheduler import _resolve_media

    async def slow():
        await asyncio.sleep(100)

    task = asyncio.create_task(slow())
    pm = ParsedMessage(
        text="see {{media:id1}} here",
        media_tasks=[MediaTask(placeholder_id="id1", task=task, media_type="image")],
    )
    result = await _resolve_media(pm, timeout=0.01)
    assert '<image error="处理超时" />' in result


@pytest.mark.anyio
async def test_resolve_no_media_tasks():
    from src.core.scheduler import _resolve_media
    pm = ParsedMessage(text="hello world", media_tasks=[])
    result = await _resolve_media(pm, timeout=10)
    assert result == "hello world"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scheduler_media.py -v`
Expected: FAIL with `ImportError: cannot import name '_resolve_media'`

**Step 3: Write minimal implementation**

Add to `src/core/scheduler.py`:

```python
from src.core.message_parser import ParsedMessage
from src.core.media_processor import _MEDIA_TAG


async def _resolve_media(pm: ParsedMessage, timeout: float) -> str:
    """Await all media tasks and replace placeholders."""
    if not pm.media_tasks:
        return pm.text

    results: dict[str, str] = {}
    for mt in pm.media_tasks:
        tag = _MEDIA_TAG.get(mt.media_type, mt.media_type)
        try:
            result = await asyncio.wait_for(mt.task, timeout=timeout)
            results[mt.placeholder_id] = result
        except asyncio.TimeoutError:
            mt.task.cancel()
            results[mt.placeholder_id] = f'<{tag} error="处理超时" />'
        except Exception:
            results[mt.placeholder_id] = f'<{tag} error="处理失败" />'

    return pm.resolve(results)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scheduler_media.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/core/scheduler.py tests/test_scheduler_media.py
git commit -m "feat(scheduler): add _resolve_media for awaiting media tasks"
```

---

### Task 9: Update message_handler to pass ParsedMessage through scheduler

**Files:**
- Modify: `src/core/message_handler.py`
- Modify: `src/core/scheduler.py`
- Modify: `tests/test_message_handler.py`

**Step 1: Update message_handler.py**

The handler currently does:
```python
parsed = await message_parser.parse_message(e.message, settings)
msg = format_message(parsed, sender_name, group_name)
```

Now `parsed` is a `ParsedMessage`. Change to pass it along with the formatted text prefix:

```python
parsed = await message_parser.parse_message(e.message, settings)
msg = format_message(parsed.text, sender_name, group_name)
await scheduler.enqueue(
    scheduler.PRIORITY_USER_MESSAGE,
    f"group_{e.group_id}",
    msg,
    lambda text: bot.api.post_group_msg(e.group_id, text=text),
    parsed_message=parsed,
)
```

Same change for `on_private`.

**Step 2: Update scheduler.enqueue to accept parsed_message**

In `src/core/scheduler.py`, update `enqueue` and `_batch` to carry the `ParsedMessage`:

```python
async def enqueue(priority: int, source_key: str, msg: str,
                  reply_fn, parsed_message=None) -> None:
    global _processing, _counter
    async with _lock:
        _counter += 1
        await _queue.put((priority, _counter, source_key,
                          msg, reply_fn, parsed_message))
        # ... rest unchanged
```

Update `_batch` to carry `parsed_message` through:

```python
def _batch(items: list) -> list[tuple[str, list[str], list, list]]:
    groups: dict[str, tuple[list, list, list]] = {}
    order: list[str] = []
    for _, _, source_key, msg, reply_fn, parsed_msg in items:
        if source_key not in groups:
            groups[source_key] = ([], [], [])
            order.append(source_key)
        groups[source_key][0].append(msg)
        groups[source_key][1].append(reply_fn)
        groups[source_key][2].append(parsed_msg)
    return [(k, groups[k][0], groups[k][1], groups[k][2])
            for k in order]
```

Update `_process_loop` to resolve media before invoking agent:

```python
for source_key, msgs, reply_fns, parsed_msgs in batches:
    _current_source = source_key
    # Resolve media tasks for all messages in batch
    settings = agent.load_settings()
    timeout = settings.get("media", {}).get("timeout", 60)
    resolved_msgs = []
    for msg, pm in zip(msgs, parsed_msgs):
        if pm and pm.media_tasks:
            resolved = await _resolve_media(pm, timeout)
            # Re-wrap with sender prefix (already in msg)
            resolved_msgs.append(msg.replace(pm.text, resolved))
        else:
            resolved_msgs.append(msg)
    logger.info("processing | source=%s batch=%d",
                source_key, len(resolved_msgs))
    async for seg in agent._invoke(
        "user_message", "\n".join(resolved_msgs)
    ):
        await reply_fns[-1](seg)
```

**Step 3: Update tests**

Update `tests/test_message_handler.py` to mock `parse_message` returning `ParsedMessage` instead of `str`. Ensure `enqueue` calls include the `parsed_message` kwarg.

**Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/core/message_handler.py src/core/scheduler.py tests/test_message_handler.py
git commit -m "feat(scheduler): resolve media tasks before invoking agent"
```

---

### Task 10: Full integration test and final verification

**Files:**
- Modify: `tests/test_message_handler.py`

**Step 1: Write integration test for full media flow**

Add to `tests/test_message_handler.py`:

```python
@pytest.mark.anyio
async def test_group_message_with_media_transcription():
    """Full flow: group message with image
    → parse → enqueue with ParsedMessage."""
    # Verify on_group passes ParsedMessage to scheduler.enqueue
    # Mock parse_message to return a ParsedMessage with media_tasks
    # Assert enqueue is called with parsed_message kwarg
```

**Step 2: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_message_handler.py
git commit -m "test: add integration test for media transcription flow"
```

---

## Review Checkpoints

- After Task 1: Review `ParsedMessage` / `MediaTask` dataclass design
- After Task 6: Review full `media_processor.py` — download, trim, transcribe, orchestrator
- After Task 7: Review updated `parse_message()` return type change and existing test updates
- After Task 9: Review full integration — handler → parser → scheduler → agent pipeline
