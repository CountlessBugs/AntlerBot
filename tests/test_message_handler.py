import pytest
import src.core.message_handler as mh
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.message_handler import format_message


@pytest.fixture(autouse=True)
def reset_mh_state():
    mh._group_name_cache = {}
    yield
    mh._group_name_cache = {}


def test_format_message_group():
    assert format_message("hello", "Alice", "TestGroup") == "<sender>Alice [群聊-TestGroup]</sender>hello"


def test_format_message_private():
    assert format_message("hello", "Alice") == "<sender>Alice</sender>hello"


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
