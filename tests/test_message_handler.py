import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import src.core.message_handler as mh
import src.core.contact_cache as contact_cache
from src.core.message_handler import format_message
from src.core.message_parser import ParsedMessage, MediaTask


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


@pytest.mark.anyio
async def test_group_message_with_media_transcription():
    """Full flow: group message with image → parse → enqueue with ParsedMessage."""
    mock_task = AsyncMock(return_value='<image filename="pic.jpg">a cat</image>')()
    fake_pm = ParsedMessage(
        text="look {{media:abc123}} nice",
        media_tasks=[MediaTask(placeholder_id="abc123", task=mock_task, media_type="image")],
    )

    with patch("src.core.message_handler.message_parser") as mock_parser, \
         patch("src.core.message_handler.scheduler") as mock_sched, \
         patch("src.core.message_handler.load_settings", return_value={}), \
         patch("src.core.message_handler.contact_cache") as mock_cc:
        mock_parser.parse_message = AsyncMock(return_value=fake_pm)
        mock_sched.enqueue = AsyncMock()
        mock_sched.PRIORITY_USER_MESSAGE = 1
        mock_cc.get_group_display_name.return_value = "TestGroup"

        event = MagicMock()
        event.group_id = 12345
        event.message = []
        event.sender.user_id = 99
        event.sender.nickname = "Alice"
        event.sender.card = ""

        # Simulate calling on_group by registering handlers on a mock bot
        mock_bot = MagicMock()
        handlers = {}

        def capture_handler(name):
            def decorator(fn):
                handlers[name] = fn
                return fn
            return decorator

        mock_bot.on_group_message.return_value = lambda fn: (handlers.__setitem__("on_group", fn), fn)[1]
        mock_bot.on_private_message.return_value = lambda fn: (handlers.__setitem__("on_private", fn), fn)[1]
        mock_bot.on_startup.return_value = lambda fn: fn
        mock_bot.on_notice.return_value = lambda fn: fn

        mh.register(mock_bot)
        await handlers["on_group"](event)

        mock_sched.enqueue.assert_awaited_once()
        call_kwargs = mock_sched.enqueue.call_args
        assert call_kwargs.kwargs.get("parsed_message") is fake_pm


@pytest.mark.anyio
async def test_group_message_with_passthrough_image():
    """Full flow: group message with passthrough image → parse → enqueue with content_blocks."""
    fake_pm = ParsedMessage(
        text="look at this",
        content_blocks=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}],
    )

    with patch("src.core.message_handler.message_parser") as mock_parser, \
         patch("src.core.message_handler.scheduler") as mock_sched, \
         patch("src.core.message_handler.load_settings", return_value={}), \
         patch("src.core.message_handler.contact_cache") as mock_cc:
        mock_parser.parse_message = AsyncMock(return_value=fake_pm)
        mock_sched.enqueue = AsyncMock()
        mock_sched.PRIORITY_USER_MESSAGE = 1
        mock_cc.get_group_display_name.return_value = "TestGroup"

        event = MagicMock()
        event.group_id = 12345
        event.message = []
        event.sender.user_id = 99
        event.sender.nickname = "Alice"
        event.sender.card = ""

        mock_bot = MagicMock()
        handlers = {}
        mock_bot.on_group_message.return_value = lambda fn: (handlers.__setitem__("on_group", fn), fn)[1]
        mock_bot.on_private_message.return_value = lambda fn: (handlers.__setitem__("on_private", fn), fn)[1]
        mock_bot.on_startup.return_value = lambda fn: fn
        mock_bot.on_notice.return_value = lambda fn: fn

        mh.register(mock_bot)
        await handlers["on_group"](event)

        mock_sched.enqueue.assert_awaited_once()
        call_kwargs = mock_sched.enqueue.call_args
        pm = call_kwargs.kwargs.get("parsed_message")
        assert pm is fake_pm
        assert len(pm.content_blocks) == 1
        assert pm.content_blocks[0]["type"] == "image_url"
