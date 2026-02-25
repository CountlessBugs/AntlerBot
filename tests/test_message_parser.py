import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import src.core.contact_cache as contact_cache
from src.core.message_parser import parse_message


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
    assert await parse_message(msg, DEFAULT_SETTINGS) == "hello world"


@pytest.mark.anyio
async def test_text_empty():
    msg = [_make_seg("Text", text="")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == ""


# --- At ---

@pytest.mark.anyio
async def test_at_with_remark():
    contact_cache._friends["123"] = {"remark": "小明"}
    msg = [_make_seg("At", qq="123")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "@小明"


@pytest.mark.anyio
async def test_at_no_remark_falls_back_to_id():
    msg = [_make_seg("At", qq="456")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "@456"


@pytest.mark.anyio
async def test_at_all():
    msg = [_make_seg("AtAll", qq="all")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "@全体成员"


# --- Face ---

@pytest.mark.anyio
async def test_face_known_id():
    msg = [_make_seg("Face", id="14")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == '<face name="微笑" />'


@pytest.mark.anyio
async def test_face_unknown_id():
    msg = [_make_seg("Face", id="9999")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "<face />"


@pytest.mark.anyio
async def test_face_invalid_id():
    msg = [_make_seg("Face", id="abc")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "<face />"


# --- Reply ---

@pytest.mark.anyio
async def test_reply_success():
    mock_evt = MagicMock(raw_message="原始消息内容")
    mock_api = AsyncMock(get_msg=AsyncMock(return_value=mock_evt))
    with patch("ncatbot.utils.status") as mock_status:
        mock_status.global_api = mock_api
        msg = [_make_seg("Reply", id="12345")]
        assert await parse_message(msg, DEFAULT_SETTINGS) == "<reply_to>原始消息内容</reply_to>"


@pytest.mark.anyio
async def test_reply_truncation():
    long_text = "a" * 100
    mock_evt = MagicMock(raw_message=long_text)
    mock_api = AsyncMock(get_msg=AsyncMock(return_value=mock_evt))
    with patch("ncatbot.utils.status") as mock_status:
        mock_status.global_api = mock_api
        msg = [_make_seg("Reply", id="12345")]
        result = await parse_message(msg, DEFAULT_SETTINGS)
        assert result == f"<reply_to>{'a' * 50}...</reply_to>"


@pytest.mark.anyio
async def test_reply_api_failure():
    mock_api = AsyncMock(get_msg=AsyncMock(side_effect=Exception("API error")))
    with patch("ncatbot.utils.status") as mock_status:
        mock_status.global_api = mock_api
        msg = [_make_seg("Reply", id="12345")]
        assert await parse_message(msg, DEFAULT_SETTINGS) == "<reply_to>无法获取原消息</reply_to>"


# --- Media placeholders ---

@pytest.mark.anyio
async def test_image_placeholder():
    msg = [_make_seg("Image", file="pic.jpg")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "[image]"


@pytest.mark.anyio
async def test_record_placeholder():
    msg = [_make_seg("Record", file="voice.amr")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "[audio]"


@pytest.mark.anyio
async def test_video_placeholder():
    msg = [_make_seg("Video", file="clip.mp4")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "[video]"


@pytest.mark.anyio
async def test_file_placeholder():
    msg = [_make_seg("File", file="doc.pdf")]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "[file]"


# --- Unsupported segments ---

@pytest.mark.anyio
async def test_unsupported_with_get_summary():
    seg = MagicMock()
    seg.__class__ = type("Unknown", (), {})
    seg.get_summary.return_value = "转发消息"
    seg.type = "forward"
    msg = [seg]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "转发消息"


@pytest.mark.anyio
async def test_unsupported_get_summary_fails():
    seg = MagicMock()
    seg.__class__ = type("Unknown", (), {})
    seg.get_summary.side_effect = Exception("no summary")
    seg.type = "location"
    msg = [seg]
    assert await parse_message(msg, DEFAULT_SETTINGS) == "[unsupported: location]"


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
    assert result == '你好 @老王 <face name="微笑" />[image]'
