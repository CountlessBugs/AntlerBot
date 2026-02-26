import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.message_parser import ParsedMessage, MediaTask
import src.core.scheduler as scheduler


@pytest.mark.anyio
async def test_resolve_media_tasks_success():
    from src.core.scheduler import _resolve_media
    task = AsyncMock(return_value='<image filename="cat.jpg">a cat</image>')()
    pm = ParsedMessage(
        text="look {{media:id1}} nice",
        media_tasks=[MediaTask(placeholder_id="id1", task=task, media_type="image")],
    )
    result = await _resolve_media(pm, timeout=10)
    assert result == 'look <image filename="cat.jpg">a cat</image> nice'


@pytest.mark.anyio
async def test_resolve_media_tasks_timeout():
    from src.core.scheduler import _resolve_media

    async def slow():
        await asyncio.sleep(100)

    task = asyncio.create_task(slow())
    pm = ParsedMessage(
        text="see {{media:id1}} here",
        media_tasks=[MediaTask(placeholder_id="id1", task=task, media_type="image")],
    )
    result = await _resolve_media(pm, timeout=0.01)
    assert '<image error="处理超时" />' in result


@pytest.mark.anyio
async def test_resolve_no_media_tasks():
    from src.core.scheduler import _resolve_media
    pm = ParsedMessage(text="hello world", media_tasks=[])
    result = await _resolve_media(pm, timeout=10)
    assert result == "hello world"


@pytest.fixture(autouse=True)
def reset_scheduler_state():
    scheduler._processing = False
    scheduler._current_source = None
    scheduler._counter = 0
    while not scheduler._queue.empty():
        scheduler._queue.get_nowait()
    yield
    scheduler._processing = False
    scheduler._current_source = None
    scheduler._counter = 0
    while not scheduler._queue.empty():
        scheduler._queue.get_nowait()


@pytest.mark.anyio
async def test_enqueue_with_media_does_not_block_queue():
    """Messages with media tasks should not block other messages from processing."""
    media_started = asyncio.Event()
    media_gate = asyncio.Event()

    async def slow_media():
        media_started.set()
        await media_gate.wait()
        return '<image filename="cat.jpg">a cat</image>'

    media_task = asyncio.create_task(slow_media())
    pm = ParsedMessage(
        text="look {{media:id1}}",
        media_tasks=[MediaTask(placeholder_id="id1", task=media_task, media_type="image")],
    )

    replies = []
    async def reply_fn(text):
        replies.append(text)

    async def fake_invoke(*a, **kw):
        yield "response"

    with patch.object(scheduler.agent, "_invoke", fake_invoke), \
         patch.object(scheduler.agent, "load_settings", return_value={"media": {"timeout": 60}}), \
         patch.object(scheduler.agent, "has_history", return_value=False):
        # Enqueue a media message — should NOT start _process_loop yet
        await scheduler.enqueue(1, "src_a", "<sender>A</sender>look {{media:id1}}", reply_fn, parsed_message=pm)
        # Enqueue a plain text message — should start processing immediately
        await scheduler.enqueue(1, "src_b", "plain hello", reply_fn)

        # Wait for the plain message to be processed
        for _ in range(100):
            if replies:
                break
            await asyncio.sleep(0.01)

        # Plain message was processed while media is still pending
        assert replies == ["response"]
        assert media_started.is_set()

        # Now release the media task
        media_gate.set()
        for _ in range(100):
            if len(replies) >= 2:
                break
            await asyncio.sleep(0.01)

        assert len(replies) == 2


@pytest.mark.anyio
async def test_resolve_then_enqueue_puts_resolved_msg():
    """_resolve_then_enqueue should resolve media and enqueue the final message."""
    task = AsyncMock(return_value='<image>a cat</image>')()
    pm = ParsedMessage(
        text="see {{media:id1}}",
        media_tasks=[MediaTask(placeholder_id="id1", task=task, media_type="image")],
    )

    with patch.object(scheduler.agent, "load_settings", return_value={"media": {"timeout": 60}}):
        await scheduler._resolve_then_enqueue(1, "src_a", "<sender>A</sender>see {{media:id1}}", AsyncMock(), pm)

    assert not scheduler._queue.empty()
    item = scheduler._queue.get_nowait()
    # item is (priority, counter, source_key, msg, reply_fn, None)
    assert "see <image>a cat</image>" in item[3]
    assert item[5] is None  # no more pending media
