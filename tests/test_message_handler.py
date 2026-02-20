import pytest
import src.core.message_handler as mh
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.message_handler import format_message, _batch_pending


@pytest.fixture(autouse=True)
def reset_mh_state():
    mh._processing = False
    mh._current_source = None
    mh._pending = []
    mh._group_name_cache = {}
    yield
    mh._processing = False
    mh._current_source = None
    mh._pending = []
    mh._group_name_cache = {}


def test_format_message_group():
    assert format_message("hello", "Alice", "TestGroup") == "<sender>Alice [群聊-TestGroup]</sender>hello"


def test_format_message_private():
    assert format_message("hello", "Alice") == "<sender>Alice</sender>hello"


def test_batch_pending_current_source_first():
    fn = lambda r: None
    pending = [
        ("src_b", "msg_b1", fn),
        ("src_a", "msg_a1", fn),
    ]
    batches = _batch_pending("src_a", pending)
    assert batches[0][0] == "src_a"


def test_batch_pending_groups_by_source():
    fn = lambda r: None
    pending = [
        ("src_a", "msg1", fn),
        ("src_b", "msg2", fn),
        ("src_a", "msg3", fn),
    ]
    batches = _batch_pending(None, pending)
    src_a = next(b for b in batches if b[0] == "src_a")
    assert src_a[1] == ["msg1", "msg3"]


def test_batch_pending_preserves_order():
    fn = lambda r: None
    pending = [("src_a", m, fn) for m in ["first", "second", "third"]]
    batches = _batch_pending("src_a", pending)
    assert batches[0][1] == ["first", "second", "third"]


def test_batch_pending_empty():
    assert _batch_pending(None, []) == []


def test_batch_pending_current_source_not_in_pending():
    fn = lambda r: None
    pending = [("src_b", "m1", fn), ("src_c", "m2", fn)]
    batches = _batch_pending("src_a", pending)
    assert [b[0] for b in batches] == ["src_b", "src_c"]


@pytest.mark.anyio
async def test_get_group_name_calls_api_on_miss():
    mock_info = MagicMock(group_name="TestGroup")
    mock_api = AsyncMock()
    mock_api.get_group_info.return_value = mock_info
    mock_module = MagicMock(status=MagicMock(global_api=mock_api))
    with patch.dict("sys.modules", {"ncatbot.utils": mock_module}):
        result = await mh.get_group_name("123")
    assert result == "TestGroup"
    mock_api.get_group_info.assert_called_once_with("123")


@pytest.mark.anyio
async def test_get_group_name_uses_cache():
    mh._group_name_cache["123"] = "CachedGroup"
    mock_api = AsyncMock()
    mock_module = MagicMock(status=MagicMock(global_api=mock_api))
    with patch.dict("sys.modules", {"ncatbot.utils": mock_module}):
        result = await mh.get_group_name("123")
    assert result == "CachedGroup"
    mock_api.get_group_info.assert_not_called()


@pytest.mark.anyio
async def test_process_loop_empty_pending_stops():
    mh._processing = True
    await mh._process_loop()
    assert mh._processing is False


@pytest.mark.anyio
async def test_process_loop_calls_invoke_and_reply():
    replies = []
    async def reply_fn(text): replies.append(text)
    mh._pending = [("src_a", "hello", reply_fn)]
    mh._processing = True
    with patch.object(mh.agent, "invoke", AsyncMock(return_value="response")):
        await mh._process_loop()
    assert replies == ["response"]
    assert mh._processing is False


@pytest.mark.anyio
async def test_process_loop_exception_resets_processing():
    async def reply_fn(text): pass
    mh._pending = [("src_a", "hello", reply_fn)]
    mh._processing = True
    with patch.object(mh.agent, "invoke", AsyncMock(side_effect=RuntimeError("fail"))):
        await mh._process_loop()
    assert mh._processing is False
