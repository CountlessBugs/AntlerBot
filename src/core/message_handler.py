import logging
from src.core import scheduler

logger = logging.getLogger(__name__)

_group_name_cache: dict[str, str] = {}


def format_message(content: str, nickname: str, group_name: str | None = None) -> str:
    if group_name:
        return f"<sender>{nickname} [群聊-{group_name}]</sender>{content}"
    return f"<sender>{nickname}</sender>{content}"


async def get_group_name(group_id: str) -> str:
    if group_id not in _group_name_cache:
        from ncatbot.utils import status
        info = await status.global_api.get_group_info(group_id)
        _group_name_cache[group_id] = info.group_name
    return _group_name_cache[group_id]


def register(bot) -> None:
    from ncatbot.core import GroupMessageEvent, PrivateMessageEvent

    @bot.on_group_message()
    async def on_group(e: GroupMessageEvent):
        group_name = await get_group_name(str(e.group_id))
        msg = format_message(e.raw_message, e.sender.nickname, group_name)
        await scheduler.enqueue(
            scheduler.PRIORITY_USER_MESSAGE,
            f"group_{e.group_id}",
            msg,
            lambda text: bot.api.post_group_msg(e.group_id, text=text),
        )

    @bot.on_private_message()
    async def on_private(e: PrivateMessageEvent):
        msg = format_message(e.raw_message, e.sender.nickname)
        await scheduler.enqueue(
            scheduler.PRIORITY_USER_MESSAGE,
            f"private_{e.user_id}",
            msg,
            lambda text: bot.api.post_private_msg(e.user_id, text=text),
        )
