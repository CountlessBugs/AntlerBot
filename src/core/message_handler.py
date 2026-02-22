import logging
from src.core import scheduler, contact_cache, commands

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
    async def on_startup(event):
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
        if e.raw_message.startswith("/"):
            if await commands.handle_command(str(e.sender.user_id), e.raw_message, bot.api, e):
                return
        sender_name = await get_sender_name(str(e.sender.user_id), e.sender.nickname)
        msg = format_message(e.raw_message, sender_name)
        await scheduler.enqueue(
            scheduler.PRIORITY_USER_MESSAGE,
            f"private_{e.user_id}",
            msg,
            lambda text: bot.api.post_private_msg(e.user_id, text=text),
        )
