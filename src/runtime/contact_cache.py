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
