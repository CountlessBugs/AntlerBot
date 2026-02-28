import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import src.core.contact_cache as contact_cache
from src.core.message_parser import parse_message, ParsedMessage, MediaTask


@pytest.fixture(autouse=True)
def reset_cache():
    contact_cache._friends = {}
    contact_cache._groups = {}
    yield
    contact_cache._friends = {}
    contact_cache._groups = {}


DEFAULT_SETTINGS = {"reply_max_length": 50}


def _make_seg(cls_name, **attrs):
    """Create a mock segment with the given class identity and attributes."""
    from ncatbot.core.event.message_segment import (
        Text, At, AtAll, Face, Reply, Image, Record, Video, File,
    )
    cls_map = {
        "Text": Text, "At": At, "AtAll": AtAll, "Face": Face,
        "Reply": Reply, "Image": Image, "Record": Record,
        "Video": Video, "File": File,
    }
    real_cls = cls_map.get(cls_name)
    seg = MagicMock(spec=real_cls)
    seg.__class__ = real_cls
    for k, v in attrs.items():
        setattr(seg, k, v)
    return seg


# --- Text ---

@pytest.mark.anyio
async def test_text_passthrough():
    msg = [_make_seg("Text", text="hello world")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "hello world"


@pytest.mark.anyio
async def test_text_empty():
    msg = [_make_seg("Text", text="")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == ""


# --- At ---

@pytest.mark.anyio
async def test_at_with_remark():
    contact_cache._friends["123"] = {"remark": "小明"}
    msg = [_make_seg("At", qq="123")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "@小明"


@pytest.mark.anyio
async def test_at_no_remark_falls_back_to_id():
    msg = [_make_seg("At", qq="456")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "@456"


@pytest.mark.anyio
async def test_at_all():
    msg = [_make_seg("AtAll", qq="all")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "@全体成员"


# --- Face ---

@pytest.mark.anyio
async def test_face_known_id():
    msg = [_make_seg("Face", id="14")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == '<face name="微笑" />'


@pytest.mark.anyio
async def test_face_unknown_id():
    msg = [_make_seg("Face", id="9999")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "<face />"


@pytest.mark.anyio
async def test_face_invalid_id():
    msg = [_make_seg("Face", id="abc")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "<face />"


# --- Reply ---

@pytest.mark.anyio
async def test_reply_success():
    mock_evt = MagicMock(raw_message="原始消息内容")
    mock_api = AsyncMock(get_msg=AsyncMock(return_value=mock_evt))
    with patch("ncatbot.utils.status") as mock_status:
        mock_status.global_api = mock_api
        msg = [_make_seg("Reply", id="12345")]
        result = await parse_message(msg, DEFAULT_SETTINGS)
        assert result.text == "<reply_to>原始消息内容</reply_to>"


@pytest.mark.anyio
async def test_reply_truncation():
    long_text = "a" * 100
    mock_evt = MagicMock(raw_message=long_text)
    mock_api = AsyncMock(get_msg=AsyncMock(return_value=mock_evt))
    with patch("ncatbot.utils.status") as mock_status:
        mock_status.global_api = mock_api
        msg = [_make_seg("Reply", id="12345")]
        result = await parse_message(msg, DEFAULT_SETTINGS)
        assert result.text == f"<reply_to>{'a' * 50}...</reply_to>"


@pytest.mark.anyio
async def test_reply_api_failure():
    mock_api = AsyncMock(get_msg=AsyncMock(side_effect=Exception("API error")))
    with patch("ncatbot.utils.status") as mock_status:
        mock_status.global_api = mock_api
        msg = [_make_seg("Reply", id="12345")]
        result = await parse_message(msg, DEFAULT_SETTINGS)
        assert result.text == "<reply_to>无法获取原消息</reply_to>"


# --- Media placeholders ---

@pytest.mark.anyio
async def test_image_placeholder():
    msg = [_make_seg("Image", file="pic.jpg")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "<image />"


@pytest.mark.anyio
async def test_record_placeholder():
    msg = [_make_seg("Record", file="voice.amr")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "<audio />"


@pytest.mark.anyio
async def test_video_placeholder():
    msg = [_make_seg("Video", file="clip.mp4")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "<video />"


@pytest.mark.anyio
async def test_file_placeholder():
    msg = [_make_seg("File", file="doc.pdf")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "<file />"


# --- Unsupported segments ---

@pytest.mark.anyio
async def test_unsupported_with_get_summary():
    seg = MagicMock()
    seg.__class__ = type("Unknown", (), {})
    seg.get_summary.return_value = "转发消息"
    seg.type = "forward"
    msg = [seg]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == "转发消息"


@pytest.mark.anyio
async def test_unsupported_get_summary_fails():
    seg = MagicMock()
    seg.__class__ = type("Unknown", (), {})
    seg.get_summary.side_effect = Exception("no summary")
    seg.type = "location"
    msg = [seg]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == '<unsupported type="location" />'


# --- Mixed message ---

@pytest.mark.anyio
async def test_mixed_message():
    contact_cache._friends["789"] = {"remark": "老王"}
    msg = [
        _make_seg("Text", text="你好 "),
        _make_seg("At", qq="789"),
        _make_seg("Text", text=" "),
        _make_seg("Face", id="14"),
        _make_seg("Image", file="pic.jpg"),
    ]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert result.text == '你好 @老王 <face name="微笑" /><image />'


# --- ParsedMessage dataclass ---

def test_parsed_message_no_media():
    pm = ParsedMessage(text="hello world", media_tasks=[])
    assert pm.text == "hello world"
    assert pm.media_tasks == []


def test_parsed_message_with_placeholder():
    pm = ParsedMessage(text='look <image status="downloading" filename="cat.jpg" /> nice', media_tasks=[])
    assert 'status="downloading"' in pm.text


def test_parsed_message_resolve_no_tasks():
    pm = ParsedMessage(text="hello world", media_tasks=[])
    assert pm.resolve() == "hello world"


def test_parsed_message_resolve_replaces_placeholders():
    tag = '<image status="downloading" filename="cat.jpg" />'
    mt = MediaTask(placeholder_id="id1", task=AsyncMock()(), media_type="image",
                   filename="cat.jpg", placeholder_tag=tag)
    pm = ParsedMessage(text=f'look {tag} nice', media_tasks=[mt])
    assert pm.resolve({"id1": '<image filename="cat.jpg">a cat</image>'}) == 'look <image filename="cat.jpg">a cat</image> nice'


def test_parsed_message_resolve_failed_placeholder():
    tag = '<image status="downloading" filename="cat.jpg" />'
    mt = MediaTask(placeholder_id="id1", task=AsyncMock()(), media_type="image",
                   filename="cat.jpg", placeholder_tag=tag)
    pm = ParsedMessage(text=f'see {tag} here', media_tasks=[mt])
    assert pm.resolve({"id1": '<image error="处理失败" />'}) == 'see <image error="处理失败" /> here'


# --- parse_message returns ParsedMessage ---

@pytest.mark.anyio
async def test_parse_returns_parsed_message():
    msg = [_make_seg("Text", text="hello")]
    result = await parse_message(msg, DEFAULT_SETTINGS)
    assert isinstance(result, ParsedMessage)
    assert result.text == "hello"
    assert result.media_tasks == []


@pytest.mark.anyio
async def test_parse_image_transcribe_creates_task():
    settings = {**DEFAULT_SETTINGS, "media": {"image": {"transcribe": True}, "timeout": 60}}
    msg = [_make_seg("Image", file="pic.jpg", file_name="pic.jpg")]
    with patch("src.core.message_parser.media_processor") as mock_mp:
        mock_mp.process_media_segment = AsyncMock(return_value='<image filename="pic.jpg">a cat</image>')
        mock_mp._MEDIA_TAG = {"image": "image", "audio": "audio", "video": "video", "document": "file"}
        result = await parse_message(msg, settings)
        assert isinstance(result, ParsedMessage)
        assert len(result.media_tasks) == 1
        assert 'status="downloading"' in result.text


@pytest.mark.anyio
async def test_parse_image_no_transcribe_placeholder():
    settings = {**DEFAULT_SETTINGS, "media": {"image": {"transcribe": False}}}
    msg = [_make_seg("Image", file="pic.jpg")]
    result = await parse_message(msg, settings)
    assert isinstance(result, ParsedMessage)
    assert result.text == "<image />"
    assert result.media_tasks == []


# --- Small file direct wait ---

@pytest.mark.anyio
async def test_small_file_direct_wait():
    """Small file (file_size <= max_direct_size) should be awaited inline, no MediaTask."""
    settings = {**DEFAULT_SETTINGS, "media": {
        "image": {"transcribe": True}, "timeout": 60, "sync_process_threshold_mb": 1,
    }}
    msg = [_make_seg("Image", file="pic.jpg", file_name="pic.jpg", file_size=500_000)]
    with patch("src.core.message_parser.media_processor") as mock_mp:
        mock_mp.process_media_segment = AsyncMock(return_value='<image filename="pic.jpg">a cat</image>')
        mock_mp._MEDIA_TAG = {"image": "image", "audio": "audio", "video": "video", "document": "file"}
        result = await parse_message(msg, settings)
    assert result.media_tasks == []
    assert '<image filename="pic.jpg">a cat</image>' in result.text
    assert "loading" not in result.text


@pytest.mark.anyio
async def test_large_file_uses_placeholder():
    """Large file (file_size > max_direct_size) should use placeholder + MediaTask."""
    settings = {**DEFAULT_SETTINGS, "media": {
        "image": {"transcribe": True}, "timeout": 60, "sync_process_threshold_mb": 1,
    }}
    msg = [_make_seg("Image", file="pic.jpg", file_name="pic.jpg", file_size=5_000_000)]
    with patch("src.core.message_parser.media_processor") as mock_mp:
        mock_mp.process_media_segment = AsyncMock(return_value='<image filename="pic.jpg">a cat</image>')
        mock_mp._MEDIA_TAG = {"image": "image", "audio": "audio", "video": "video", "document": "file"}
        result = await parse_message(msg, settings)
    assert len(result.media_tasks) == 1
    assert 'status="loading"' in result.text


@pytest.mark.anyio
async def test_unknown_file_size_uses_placeholder():
    """file_size=None should be treated as large file (placeholder flow)."""
    settings = {**DEFAULT_SETTINGS, "media": {
        "image": {"transcribe": True}, "timeout": 60, "sync_process_threshold_mb": 1,
    }}
    msg = [_make_seg("Image", file="pic.jpg", file_name="pic.jpg", file_size=None)]
    with patch("src.core.message_parser.media_processor") as mock_mp:
        mock_mp.process_media_segment = AsyncMock(return_value='<image filename="pic.jpg">a cat</image>')
        mock_mp._MEDIA_TAG = {"image": "image", "audio": "audio", "video": "video", "document": "file"}
        result = await parse_message(msg, settings)
    assert len(result.media_tasks) == 1
    assert 'status="loading"' in result.text


@pytest.mark.anyio
async def test_small_file_processing_failure():
    """Small file that fails processing should produce an error tag inline."""
    settings = {**DEFAULT_SETTINGS, "media": {
        "image": {"transcribe": True}, "timeout": 60, "sync_process_threshold_mb": 1,
    }}
    msg = [_make_seg("Image", file="pic.jpg", file_name="pic.jpg", file_size=500_000)]
    with patch("src.core.message_parser.media_processor") as mock_mp:
        mock_mp.process_media_segment = AsyncMock(side_effect=Exception("download failed"))
        mock_mp._MEDIA_TAG = {"image": "image", "audio": "audio", "video": "video", "document": "file"}
        result = await parse_message(msg, settings)
    assert result.media_tasks == []
    assert '<image error="处理失败" />' in result.text
