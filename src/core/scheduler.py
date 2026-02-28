import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from apscheduler.triggers.date import DateTrigger
from src.core import agent
from src.core.message_parser import MediaTask, ParsedMessage
from src.core.media_processor import _MEDIA_TAG

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


def _batch(items: list) -> list[tuple[str, list[str], list, list]]:
    groups: dict[str, tuple[list, list, list]] = {}
    order: list[str] = []
    for _, _, source_key, msg, reply_fn, parsed_msg in items:
        if source_key not in groups:
            groups[source_key] = ([], [], [])
            order.append(source_key)
        groups[source_key][0].append(msg)
        groups[source_key][1].append(reply_fn)
        groups[source_key][2].append(parsed_msg)
    return [(k, groups[k][0], groups[k][1], groups[k][2]) for k in order]


def init_timeout(apscheduler) -> None:
    global _apscheduler
    _apscheduler = apscheduler


async def invoke(message: str, reason: str = "user_message", **kwargs) -> str:
    return "".join([s async for s in agent._invoke(reason, message, **kwargs)])


async def enqueue(priority: int, source_key: str, msg: str, reply_fn,
                  parsed_message: ParsedMessage | None = None) -> None:
    # Always enqueue immediately — media placeholders are already visible as
    # <tag status="downloading" id="..." /> in the message text.
    await _enqueue_ready(priority, source_key, msg, reply_fn, parsed_message)
    if parsed_message and parsed_message.media_tasks:
        asyncio.create_task(
            _resolve_media_and_enqueue(priority, source_key, reply_fn, parsed_message)
        )


async def _resolve_media_and_enqueue(
    priority: int,
    source_key: str,
    reply_fn,
    parsed_message: ParsedMessage,
) -> None:
    """Resolve media in the background, then enqueue resolved content to trigger a reply."""
    settings = agent.load_settings()
    timeout = settings.get("media", {}).get("timeout", 60)
    results = await _resolve_media_tasks(parsed_message, timeout)
    if not results:
        return
    parts: list[str] = []
    content_blocks: list[dict] = []
    for mt in parsed_message.media_tasks:
        if mt.placeholder_id not in results:
            continue
        result = results[mt.placeholder_id]
        if mt.passthrough and isinstance(result, dict):
            content_blocks.append(result)
        elif isinstance(result, str):
            parts.append(result)
    if parts or content_blocks:
        follow_up_pm = ParsedMessage(text="", content_blocks=content_blocks) if content_blocks else None
        await _enqueue_ready(priority, source_key, "\n".join(parts) if parts else "", reply_fn,
                             parsed_message=follow_up_pm)


def _build_agent_content(msg: str, parsed_message: ParsedMessage | None) -> str | list:
    """Build agent input content. Returns a list if there are passthrough content blocks, else a string."""
    if not parsed_message or not parsed_message.content_blocks:
        return msg
    return [
        {"type": "text", "text": msg},
        *parsed_message.content_blocks,
    ]


async def _enqueue_ready(priority: int, source_key: str, msg: str, reply_fn,
                         parsed_message: ParsedMessage | None = None) -> None:
    """Enqueue a message that is ready to be processed (no pending media)."""
    global _processing, _counter
    async with _lock:
        _counter += 1
        await _queue.put((priority, _counter, source_key, msg, reply_fn, parsed_message))
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
            for source_key, msgs, reply_fns, parsed_msgs in batches:
                _current_source = source_key
                logger.info("processing | source=%s batch=%d", source_key, len(msgs))
                combined_msg = "\n".join(msgs)
                # Merge content_blocks from all parsed messages in the batch
                all_blocks = []
                for pm in parsed_msgs:
                    if pm and pm.content_blocks:
                        all_blocks.extend(pm.content_blocks)
                if all_blocks:
                    content = [{"type": "text", "text": combined_msg}, *all_blocks]
                else:
                    content = combined_msg
                async for seg in agent._invoke("user_message", content):
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


async def _resolve_media_tasks(pm: ParsedMessage, timeout: float) -> dict[str, str | dict]:
    """Await all media tasks in parallel and return {placeholder_id: result} mapping."""
    if not pm.media_tasks:
        return {}

    async def _resolve_one(mt: MediaTask) -> tuple[str, str | dict]:
        tag = _MEDIA_TAG.get(mt.media_type, mt.media_type)
        try:
            result = await asyncio.wait_for(mt.task, timeout=timeout)
            return mt.placeholder_id, result
        except asyncio.TimeoutError:
            mt.task.cancel()
            return mt.placeholder_id, f'<{tag} error="处理超时" />'
        except Exception:
            return mt.placeholder_id, f'<{tag} error="处理失败" />'

    pairs = await asyncio.gather(*[_resolve_one(mt) for mt in pm.media_tasks])
    return dict(pairs)
