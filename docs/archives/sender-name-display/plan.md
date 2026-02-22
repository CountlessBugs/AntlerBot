# Sender Name Display

## Goal

Improve sender name display so the LLM sees meaningful identifiers:
- **Private**: friend remark → nickname
- **Group**: `card (remark)` → `card` → `remark` → nickname
- **Group display name**: group remark → group name

## Design

### New module: `src/core/contact_cache.py`

Holds friend and group caches. Refresh triggers:
- Bot startup
- `friend_add` notice → refresh friends
- `group_increase` where `user_id == self_id` (bot joined group) → refresh groups
- Session full timeout (`_on_session_clear`) → refresh all

Friend cache stores only: `user_id`, `nickname`, `remark`, `sex`, `birthday_year/month/day`.
Group cache stores all fields from `get_group_list(info=True)`: `group_id`, `group_name`, `group_remark`, `member_count`, `max_member_count`, `group_all_shut`.

### Changes to existing files

- `message_handler.py`: remove `_group_name_cache` / `get_group_name`; add `get_sender_name`; add startup + notice handlers; use `contact_cache` module
- `scheduler.py`: call `contact_cache.refresh_all()` in `_on_session_clear`
- `tests/test_message_handler.py`: replace old cache tests with `get_sender_name` tests

## Tasks

### Task 1 — Create `src/core/contact_cache.py`

Write `tests/test_contact_cache.py` first, then implement.

**`tests/test_contact_cache.py`**:
```python
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
```

**`src/core/contact_cache.py`**:
```python
import logging

logger = logging.getLogger(__name__)

_FRIEND_FIELDS = {"user_id", "nickname", "remark", "sex", "birthday_year", "birthday_month", "birthday_day"}
_GROUP_FIELDS = {"group_id", "group_name", "group_remark", "member_count", "max_member_count", "group_all_shut"}

_friends: dict[str, dict] = {}
_groups: dict[str, dict] = {}


async def refresh_friends() -> None:
    global _friends
    from ncatbot.utils import status
    friends = await status.global_api.get_friend_list()
    _friends = {str(f["user_id"]): {k: f.get(k, "") for k in _FRIEND_FIELDS} for f in friends}
    logger.info("friend cache refreshed | count=%d", len(_friends))


async def refresh_groups() -> None:
    global _groups
    from ncatbot.utils import status
    groups = await status.global_api.get_group_list(info=True)
    _groups = {str(g["group_id"]): {k: g.get(k, "") for k in _GROUP_FIELDS} for g in groups}
    logger.info("group cache refreshed | count=%d", len(_groups))


async def refresh_all() -> None:
    await refresh_friends()
    await refresh_groups()


def get_remark(user_id: str) -> str:
    return _friends.get(user_id, {}).get("remark", "")


def get_group_display_name(group_id: str) -> str:
    g = _groups.get(group_id, {})
    return g.get("group_remark") or g.get("group_name", "")
```

### Task 2 — Update `message_handler.py` and its tests

**`tests/test_message_handler.py`** (replace entirely):
```python
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
    cache_module._friends["123"] = {"remark": "Dev"}
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
```

**`src/core/message_handler.py`** (replace entirely):
```python
import logging
from src.core import scheduler, contact_cache

logger = logging.getLogger(__name__)


def format_message(content: str, nickname: str, group_name: str | None = None) -> str:
    if group_name:
        return f"<sender>{nickname} [群聊-{group_name}]</sender>{content}"
    return f"<sender>{nickname}</sender>{content}"


async def get_sender_name(user_id: str, nickname: str, card: str = "") -> str:
    remark = contact_cache.get_remark(user_id)
    if card:
        return f"{card} ({remark})" if remark else card
    return remark or nickname


def register(bot) -> None:
    from ncatbot.core import GroupMessageEvent, PrivateMessageEvent, NoticeEvent

    @bot.on_startup()
    async def on_startup():
        await contact_cache.refresh_all()

    @bot.on_notice()
    async def on_notice(e: NoticeEvent):
        if e.notice_type == "friend_add":
            await contact_cache.refresh_friends()
        elif e.notice_type == "group_increase" and str(e.user_id) == str(e.self_id):
            await contact_cache.refresh_groups()

    @bot.on_group_message()
    async def on_group(e: GroupMessageEvent):
        group_name = contact_cache.get_group_display_name(str(e.group_id))
        sender_name = await get_sender_name(str(e.sender.user_id), e.sender.nickname, e.sender.card or "")
        msg = format_message(e.raw_message, sender_name, group_name)
        await scheduler.enqueue(
            scheduler.PRIORITY_USER_MESSAGE,
            f"group_{e.group_id}",
            msg,
            lambda text: bot.api.post_group_msg(e.group_id, text=text),
        )

    @bot.on_private_message()
    async def on_private(e: PrivateMessageEvent):
        sender_name = await get_sender_name(str(e.sender.user_id), e.sender.nickname)
        msg = format_message(e.raw_message, sender_name)
        await scheduler.enqueue(
            scheduler.PRIORITY_USER_MESSAGE,
            f"private_{e.user_id}",
            msg,
            lambda text: bot.api.post_private_msg(e.user_id, text=text),
        )
```

### Task 3 — Update `scheduler.py`

In `_on_session_clear`, add cache refresh after clearing history:

```python
async def _on_session_clear() -> None:
    agent.clear_history()
    from src.core import contact_cache
    await contact_cache.refresh_all()
```