import pytest
import src.core.scheduler as scheduler
from unittest.mock import AsyncMock, patch


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


def test_batch_groups_by_source():
    fn = lambda r: None
    items = [
        (1, 1, "src_a", "msg1", fn),
        (1, 2, "src_b", "msg2", fn),
        (1, 3, "src_a", "msg3", fn),
    ]
    batches = scheduler._batch(items)
    src_a = next(b for b in batches if b[0] == "src_a")
    assert src_a[1] == ["msg1", "msg3"]


def test_batch_priority_order():
    fn = lambda r: None
    items = [
        (0, 1, "src_a", "msg_a", fn),
        (1, 2, "src_b", "msg_b", fn),
    ]
    batches = scheduler._batch(items)
    assert batches[0][0] == "src_a"


def test_batch_preserves_message_order():
    fn = lambda r: None
    items = [(1, i, "src_a", m, fn) for i, m in enumerate(["first", "second", "third"])]
    batches = scheduler._batch(items)
    assert batches[0][1] == ["first", "second", "third"]


def test_batch_empty():
    assert scheduler._batch([]) == []


def test_batch_source_not_in_items_uses_arrival_order():
    fn = lambda r: None
    items = [(1, 1, "src_b", "m1", fn), (1, 2, "src_c", "m2", fn)]
    batches = scheduler._batch(items)
    assert [b[0] for b in batches] == ["src_b", "src_c"]


@pytest.mark.anyio
async def test_process_loop_empty_queue_stops():
    scheduler._processing = True
    await scheduler._process_loop()
    assert scheduler._processing is False


@pytest.mark.anyio
async def test_process_loop_calls_invoke_and_reply():
    replies = []
    async def reply_fn(text): replies.append(text)
    await scheduler._queue.put((1, 1, "src_a", "hello", reply_fn))
    scheduler._processing = True
    with patch.object(scheduler.agent, "invoke", AsyncMock(return_value="response")):
        await scheduler._process_loop()
    assert replies == ["response"]
    assert scheduler._processing is False


@pytest.mark.anyio
async def test_process_loop_exception_resets_processing():
    async def reply_fn(text): pass
    await scheduler._queue.put((1, 1, "src_a", "hello", reply_fn))
    scheduler._processing = True
    with patch.object(scheduler.agent, "invoke", AsyncMock(side_effect=RuntimeError("fail"))):
        await scheduler._process_loop()
    assert scheduler._processing is False
