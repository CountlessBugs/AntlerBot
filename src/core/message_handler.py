import asyncio
import logging
from src.core import agent

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()
_processing = False
_current_source: str | None = None
_pending: list[tuple[str, str, callable]] = []
_group_name_cache: dict[str, str] = {}


def get_current_source() -> dict | None:
    if _current_source is None:
        return None
    type_, id_ = _current_source.split("_", 1)
    return {"type": type_, "id": id_}


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


def _batch_pending(
    current_source: str | None,
    pending: list[tuple[str, str, callable]],
) -> list[tuple[str, list[str], list[callable]]]:
    groups: dict[str, tuple[list[str], list[callable]]] = {}
    order: list[str] = []
    for source_key, msg, reply_fn in pending:
        if source_key not in groups:
            groups[source_key] = ([], [])
            order.append(source_key)
        groups[source_key][0].append(msg)
        groups[source_key][1].append(reply_fn)
    if current_source in groups:
        sorted_keys = [current_source] + [k for k in order if k != current_source]
    else:
        sorted_keys = order
    return [(k, groups[k][0], groups[k][1]) for k in sorted_keys]


async def _enqueue(source_key: str, msg: str, reply_fn) -> None:
    global _processing
    async with _lock:
        _pending.append((source_key, msg, reply_fn))
        should_start = not _processing
        if should_start:
            _processing = True
    if should_start:
        asyncio.create_task(_process_loop())


async def _process_loop():
    global _processing, _current_source, _pending
    try:
        while True:
            async with _lock:
                if not _pending:
                    _processing = False
                    _current_source = None
                    return
                items = _pending[:]
                _pending = []
            batches = _batch_pending(_current_source, items)
            for source_key, msgs, reply_fns in batches:
                _current_source = source_key
                response = await agent.invoke("\n".join(msgs))
                for reply_fn in reply_fns:
                    await reply_fn(response)
    except Exception:
        # Messages currently being processed are dropped on error.
        logger.exception("Error in process loop")
        async with _lock:
            _processing = False
        _current_source = None


def register(bot) -> None:
    from ncatbot.core import GroupMessageEvent, PrivateMessageEvent

    @bot.on_group_message()
    async def on_group(e: GroupMessageEvent):
        group_name = await get_group_name(str(e.group_id))
        msg = format_message(e.raw_message, e.sender.nickname, group_name)
        await _enqueue(f"group_{e.group_id}", msg, lambda text: bot.api.post_group_msg(e.group_id, text=text))

    @bot.on_private_message()
    async def on_private(e: PrivateMessageEvent):
        msg = format_message(e.raw_message, e.sender.nickname)
        await _enqueue(f"private_{e.user_id}", msg, lambda text: bot.api.post_private_msg(e.user_id, text=text))
