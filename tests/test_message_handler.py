import pytest
import src.core.message_handler as mh
import src.core.contact_cache as contact_cache
from src.core.message_handler import format_message


@pytest.fixture(autouse=True)
def reset_cache():
    contact_cache._friends = {}
    contact_cache._groups = {}
    yield
    contact_cache._friends = {}
    contact_cache._groups = {}


def test_format_message_group():
    assert format_message("hello", "Alice", "TestGroup") == "<sender>Alice [群聊-TestGroup]</sender>hello"


def test_format_message_private():
    assert format_message("hello", "Alice") == "<sender>Alice</sender>hello"


@pytest.mark.anyio
async def test_get_sender_name_private_uses_remark():
    contact_cache._friends["123"] = {"remark": "Dev"}
    assert await mh.get_sender_name("123", "Alice") == "Dev"


@pytest.mark.anyio
async def test_get_sender_name_private_falls_back_to_nickname():
    assert await mh.get_sender_name("123", "Alice") == "Alice"


@pytest.mark.anyio
async def test_get_sender_name_group_card_and_remark():
    contact_cache._friends["123"] = {"remark": "Dev"}
    assert await mh.get_sender_name("123", "Alice", "CardName") == "CardName (Dev)"


@pytest.mark.anyio
async def test_get_sender_name_group_card_no_remark():
    assert await mh.get_sender_name("123", "Alice", "CardName") == "CardName"


@pytest.mark.anyio
async def test_get_sender_name_group_no_card_with_remark():
    contact_cache._friends["123"] = {"remark": "Dev"}
    assert await mh.get_sender_name("123", "Alice", "") == "Dev"


@pytest.mark.anyio
async def test_get_sender_name_group_no_card_no_remark_uses_nickname():
    assert await mh.get_sender_name("123", "Alice", "") == "Alice"
