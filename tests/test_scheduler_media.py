import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.message_parser import ParsedMessage, MediaTask
import src.core.scheduler as scheduler


# --- _build_agent_content ---

def test_build_content_text_only():
    """No content_blocks → plain string."""
    from src.core.scheduler import _build_agent_content
    pm = ParsedMessage(text="hello world", content_blocks=[])
    result = _build_agent_content("formatted msg", pm)
    assert result == "formatted msg"


def test_build_content_with_blocks():
    """With content_blocks → list[dict] with text + media blocks."""
    from src.core.scheduler import _build_agent_content
    pm = ParsedMessage(
        text="look at this",
        content_blocks=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}],
    )
    result = _build_agent_content("formatted msg", pm)
    assert isinstance(result, list)
    assert result[0] == {"type": "text", "text": "formatted msg"}
    assert result[1]["type"] == "image_url"


def test_build_content_no_parsed_message():
    """None parsed_message → plain string."""
    from src.core.scheduler import _build_agent_content
    result = _build_agent_content("formatted msg", None)
    assert result == "formatted msg"


# --- _resolve_media_tasks ---

@pytest.mark.anyio
async def test_resolve_media_tasks_success():
    from src.core.scheduler import _resolve_media_tasks
    task = AsyncMock(return_value='<image filename="cat.jpg">a cat</image>')()
    tag = '<image status="downloading" filename="cat.jpg" />'
    pm = ParsedMessage(
        text=f'look {tag} nice',
        media_tasks=[MediaTask(placeholder_id="id1", task=task, media_type="image",
                               filename="cat.jpg", placeholder_tag=tag)],
    )
    results = await _resolve_media_tasks(pm, timeout=10)
    assert results["id1"] == '<image filename="cat.jpg">a cat</image>'


@pytest.mark.anyio
async def test_resolve_media_tasks_timeout():
    from src.core.scheduler import _resolve_media_tasks

    async def slow():
        await asyncio.sleep(100)

    task = asyncio.create_task(slow())
    tag = '<image status="downloading" filename="cat.jpg" />'
    pm = ParsedMessage(
        text=f'see {tag} here',
        media_tasks=[MediaTask(placeholder_id="id1", task=task, media_type="image",
                               filename="cat.jpg", placeholder_tag=tag)],
    )
    results = await _resolve_media_tasks(pm, timeout=0.01)
    assert '<image error="处理超时" />' in results["id1"]


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
async def test_enqueue_with_media_enqueues_immediately():
    """Messages with media tasks should be enqueued immediately with downloading placeholders."""
    media_gate = asyncio.Event()

    async def slow_media():
        await media_gate.wait()
        return '<image filename="cat.jpg">a cat</image>'

    media_task = asyncio.create_task(slow_media())
    tag = '<image status="downloading" filename="cat.jpg" />'
    pm = ParsedMessage(
        text=f'look {tag}',
        media_tasks=[MediaTask(placeholder_id="id1", task=media_task, media_type="image",
                               filename="cat.jpg", placeholder_tag=tag)],
    )

    replies = []
    async def reply_fn(text):
        replies.append(text)

    async def fake_invoke(*a, **kw):
        yield "response"

    with patch.object(scheduler.agent, "_invoke", fake_invoke), \
         patch.object(scheduler.agent, "load_settings", return_value={"media": {"timeout": 60}}), \
         patch.object(scheduler.agent, "has_history", return_value=False):
        # Enqueue a media message — should enqueue immediately with downloading placeholder
        await scheduler.enqueue(1, "src_a", f'<sender>A</sender>look {tag}', reply_fn, parsed_message=pm)

        # Wait for the first reply (placeholder message processed)
        for _ in range(100):
            if replies:
                break
            await asyncio.sleep(0.01)
        assert replies == ["response"]

        # Release the media task and wait for the resolved message to be enqueued and processed
        media_gate.set()
        for _ in range(100):
            if len(replies) >= 2:
                break
            await asyncio.sleep(0.01)

        assert len(replies) == 2


@pytest.mark.anyio
async def test_resolve_media_and_enqueue_puts_resolved_msg():
    """_resolve_media_and_enqueue should resolve media and enqueue a follow-up message."""
    task = AsyncMock(return_value='<image>a cat</image>')()
    tag = '<image status="downloading" filename="cat.jpg" />'
    pm = ParsedMessage(
        text=f'see {tag}',
        media_tasks=[MediaTask(placeholder_id="id1", task=task, media_type="image",
                               filename="cat.jpg", placeholder_tag=tag)],
    )

    with patch.object(scheduler.agent, "load_settings", return_value={"media": {"timeout": 60}}):
        await scheduler._resolve_media_and_enqueue(1, "src_a", AsyncMock(), pm)

    assert not scheduler._queue.empty()
    item = scheduler._queue.get_nowait()
    msg = item[3]
    assert "<image>a cat</image>" in msg
