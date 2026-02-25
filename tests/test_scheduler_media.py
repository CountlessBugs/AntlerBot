import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.message_parser import ParsedMessage, MediaTask


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
