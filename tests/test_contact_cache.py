import pytest
import src.core.contact_cache as contact_cache
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def reset_cache():
    contact_cache._friends = {}
    contact_cache._groups = {}
    yield
    contact_cache._friends = {}
    contact_cache._groups = {}


@pytest.mark.anyio
async def test_refresh_friends_stores_filtered_fields():
    raw = [{"user_id": 123, "nickname": "Alice", "remark": "Dev", "sex": "female",
            "birthday_year": 2000, "birthday_month": 1, "birthday_day": 1,
            "phone_num": "secret", "email": "secret@example.com"}]
    mock_api = AsyncMock(get_friend_list=AsyncMock(return_value=raw))
    mock_module = MagicMock(status=MagicMock(global_api=mock_api))
    with patch.dict("sys.modules", {"ncatbot.utils": mock_module}):
        await contact_cache.refresh_friends()
    f = contact_cache._friends["123"]
    assert f["nickname"] == "Alice"
    assert f["remark"] == "Dev"
    assert "phone_num" not in f
    assert "email" not in f


@pytest.mark.anyio
async def test_refresh_groups_stores_all_fields():
    raw = [{"group_id": 456, "group_name": "Dev Group", "group_remark": "Test",
            "member_count": 3, "max_member_count": 200, "group_all_shut": 0}]
    mock_api = AsyncMock(get_group_list=AsyncMock(return_value=raw))
    mock_module = MagicMock(status=MagicMock(global_api=mock_api))
    with patch.dict("sys.modules", {"ncatbot.utils": mock_module}):
        await contact_cache.refresh_groups()
    g = contact_cache._groups["456"]
    assert g["group_name"] == "Dev Group"
    assert g["group_remark"] == "Test"


def test_get_remark_returns_remark():
    contact_cache._friends["123"] = {"remark": "Dev"}
    assert contact_cache.get_remark("123") == "Dev"


def test_get_remark_returns_empty_for_unknown():
    assert contact_cache.get_remark("999") == ""


def test_get_group_display_name_prefers_remark():
    contact_cache._groups["456"] = {"group_name": "Dev Group", "group_remark": "Test"}
    assert contact_cache.get_group_display_name("456") == "Test"


def test_get_group_display_name_falls_back_to_name():
    contact_cache._groups["456"] = {"group_name": "Dev Group", "group_remark": ""}
    assert contact_cache.get_group_display_name("456") == "Dev Group"


def test_get_group_display_name_returns_empty_for_unknown():
    assert contact_cache.get_group_display_name("999") == ""
