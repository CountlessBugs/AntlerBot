import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from apscheduler.triggers.date import DateTrigger
from src.core import agent

logger = logging.getLogger(__name__)

PRIORITY_SCHEDULED = 0
PRIORITY_USER_MESSAGE = 1
PRIORITY_AUTO_CONVERSATION = 2

_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
_processing = False
_current_source: str | None = None
_lock = asyncio.Lock()
_counter = 0
_apscheduler = None


def get_current_source() -> dict | None:
    if _current_source is None:
        return None
    type_, id_ = _current_source.split("_", 1)
    return {"type": type_, "id": id_}


def _batch(items: list) -> list[tuple[str, list[str], list]]:
    groups: dict[str, tuple[list, list]] = {}
    order: list[str] = []
    for _, _, source_key, msg, reply_fn in items:
        if source_key not in groups:
            groups[source_key] = ([], [])
            order.append(source_key)
        groups[source_key][0].append(msg)
        groups[source_key][1].append(reply_fn)
    return [(k, groups[k][0], groups[k][1]) for k in order]


def init_timeout(apscheduler) -> None:
    global _apscheduler
    _apscheduler = apscheduler


async def invoke(message: str, reason: str = "user_message", **kwargs) -> str:
    return "".join([s async for s in agent._invoke(reason, message, **kwargs)])


async def enqueue(priority: int, source_key: str, msg: str, reply_fn) -> None:
    global _processing, _counter
    async with _lock:
        _counter += 1
        await _queue.put((priority, _counter, source_key, msg, reply_fn))
        should_start = not _processing
        if should_start:
            _processing = True
        else:
            logger.info("queued | source=%s priority=%d depth=%d", source_key, priority, _queue.qsize())
    if should_start:
        asyncio.create_task(_process_loop())


async def _process_loop():
    global _processing, _current_source
    try:
        while True:
            async with _lock:
                if _queue.empty():
                    _processing = False
                    _current_source = None
                    return
                items = []
                while not _queue.empty():
                    items.append(_queue.get_nowait())
            batches = _batch(items)
            for source_key, msgs, reply_fns in batches:
                _current_source = source_key
                logger.info("processing | source=%s batch=%d", source_key, len(msgs))
                async for seg in agent._invoke("user_message", "\n".join(msgs)):
                    await reply_fns[-1](seg)
            if _apscheduler is not None and agent.has_history():
                settings = agent.load_settings()
                _apscheduler.add_job(
                    _on_session_summarize,
                    DateTrigger(run_date=datetime.now() + timedelta(seconds=settings["timeout_summarize_seconds"])),
                    id="session_summarize",
                    replace_existing=True,
                )
                with contextlib.suppress(Exception):
                    _apscheduler.remove_job("session_clear")
    except Exception:
        logger.exception("Error in process loop")
        async with _lock:
            _processing = False
        _current_source = None


async def _on_session_summarize() -> None:
    async for _ in agent._invoke("session_timeout"):
        pass
    if _apscheduler is None:
        return
    settings = agent.load_settings()
    _apscheduler.add_job(
        _on_session_clear,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=settings["timeout_clear_seconds"])),
        id="session_clear",
        replace_existing=True,
    )


async def _on_session_clear() -> None:
    agent.clear_history()
    from src.core import contact_cache
    await contact_cache.refresh_all()
