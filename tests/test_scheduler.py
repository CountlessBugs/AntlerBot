import asyncio
import pytest
import src.core.scheduler as scheduler
from unittest.mock import AsyncMock, MagicMock, patch


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
    async def fake_invoke(*a, **kw):
        yield "response"
    with patch.object(scheduler.agent, "_invoke", fake_invoke):
        await scheduler._process_loop()
    assert replies == ["response"]
    assert scheduler._processing is False


@pytest.mark.anyio
async def test_process_loop_exception_resets_processing():
    async def reply_fn(text): pass
    await scheduler._queue.put((1, 1, "src_a", "hello", reply_fn))
    scheduler._processing = True
    async def fail_invoke(*a, **kw):
        raise RuntimeError("fail")
        yield  # make it an async generator
    with patch.object(scheduler.agent, "_invoke", fail_invoke):
        await scheduler._process_loop()
    assert scheduler._processing is False


@pytest.mark.anyio
async def test_enqueue_schedules_summarize_job():
    mock_apscheduler = MagicMock()
    scheduler._apscheduler = mock_apscheduler
    async def reply_fn(text): pass
    async def fake_invoke(*a, **kw):
        yield "response"
    with patch.object(scheduler.agent, "load_settings", return_value={"timeout_summarize_seconds": 1800, "timeout_clear_seconds": 3600}), \
         patch.object(scheduler.agent, "_invoke", fake_invoke), \
         patch.object(scheduler.agent, "has_history", return_value=True):
        await scheduler.enqueue(1, "src_a", "hello", reply_fn)
        while scheduler._processing:
            await asyncio.sleep(0.01)
    mock_apscheduler.add_job.assert_called_once()
    assert mock_apscheduler.add_job.call_args[1]["id"] == "session_summarize"
    scheduler._apscheduler = None


@pytest.mark.anyio
async def test_enqueue_cancels_clear_job():
    mock_apscheduler = MagicMock()
    scheduler._apscheduler = mock_apscheduler
    async def reply_fn(text): pass
    async def fake_invoke(*a, **kw):
        yield "response"
    with patch.object(scheduler.agent, "load_settings", return_value={"timeout_summarize_seconds": 1800, "timeout_clear_seconds": 3600}), \
         patch.object(scheduler.agent, "_invoke", fake_invoke), \
         patch.object(scheduler.agent, "has_history", return_value=True):
        await scheduler.enqueue(1, "src_a", "hello", reply_fn)
        while scheduler._processing:
            await asyncio.sleep(0.01)
    mock_apscheduler.remove_job.assert_called_once_with("session_clear")
    scheduler._apscheduler = None


@pytest.mark.anyio
async def test_enqueue_logs_when_already_processing(caplog):
    import logging
    scheduler._processing = True
    async def reply_fn(text): pass
    with patch("asyncio.create_task"), \
         caplog.at_level(logging.INFO, logger="src.core.scheduler"):
        await scheduler.enqueue(1, "src_a", "hello", reply_fn)
    assert any("queued" in r.message and "src_a" in r.message for r in caplog.records)
    scheduler._processing = False


@pytest.mark.anyio
async def test_process_loop_logs_processing(caplog):
    import logging
    async def reply_fn(text): pass
    await scheduler._queue.put((1, 1, "src_a", "hello", reply_fn))
    scheduler._processing = True
    async def fake_invoke(*a, **kw):
        yield "response"
    with patch.object(scheduler.agent, "_invoke", fake_invoke), \
         caplog.at_level(logging.INFO, logger="src.core.scheduler"):
        await scheduler._process_loop()
    assert any("processing" in r.message and "src_a" in r.message for r in caplog.records)
