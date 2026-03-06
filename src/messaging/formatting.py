import logging

logger = logging.getLogger(__name__)



def format_message(content: str, nickname: str, group_name: str | None = None) -> str:
    if group_name:
        return f"<sender>{nickname} [群聊-{group_name}]</sender>{content}"
    return f"<sender>{nickname}</sender>{content}"


async def get_sender_name(user_id: str, nickname: str, card: str = "") -> str:
    from src.runtime import contact_cache

    remark = contact_cache.get_remark(user_id)
    if card:
        return f"{card} ({remark})" if remark else card
    return remark or nickname
