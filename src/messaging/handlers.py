import logging
from src.runtime import scheduler, contact_cache
from src.commands import handlers as commands
from src.messaging import parser as message_parser
from src.agent.agent import load_settings
from src.messaging.formatting import format_message, get_sender_name

logger = logging.getLogger(__name__)



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
        settings = load_settings()
        source_key = f"group_{e.group_id}"
        parsed = await message_parser.parse_message(e.message, settings, source_key)
        msg = format_message(parsed.text, sender_name, group_name)
        await scheduler.enqueue(
            scheduler.PRIORITY_USER_MESSAGE,
            source_key,
            msg,
            lambda text: bot.api.post_group_msg(e.group_id, text=text),
            parsed_message=parsed,
            reason="user_message",
        )

    @bot.on_private_message()
    async def on_private(e: PrivateMessageEvent):
        if e.raw_message.startswith("/"):
            if await commands.handle_command(str(e.sender.user_id), e.raw_message, bot.api, e):
                return
        sender_name = await get_sender_name(str(e.sender.user_id), e.sender.nickname)
        settings = load_settings()
        source_key = f"private_{e.user_id}"
        parsed = await message_parser.parse_message(e.message, settings, source_key)
        msg = format_message(parsed.text, sender_name)
        await scheduler.enqueue(
            scheduler.PRIORITY_USER_MESSAGE,
            source_key,
            msg,
            lambda text: bot.api.post_private_msg(e.user_id, text=text),
            parsed_message=parsed,
            reason="user_message",
        )
