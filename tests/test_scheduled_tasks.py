import asyncio
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import src.core.scheduled_tasks as st


@pytest.fixture(autouse=True)
def reset_state():
    st._bot = None
    yield


# --- _unique_name ---

def test_unique_name_no_conflict():
    assert st._unique_name("提醒", []) == "提醒"


def test_unique_name_conflict_appends_suffix():
    tasks = [{"name": "提醒"}, {"name": "提醒(1)"}]
    assert st._unique_name("提醒", tasks) == "提醒(2)"


def test_unique_name_no_conflict_with_others():
    tasks = [{"name": "其他任务"}]
    assert st._unique_name("提醒", tasks) == "提醒"


# --- create_task / cancel_task ---

def _make_task(**kwargs):
    base = {
        "task_id": "tid-1",
        "type": "once",
        "name": "测试",
        "content": "内容",
        "trigger": "2026-03-01T10:00:00",
        "source": {"type": "group", "id": "123"},
        "run_count": 0,
        "last_run": None,
        "max_runs": None,
        "end_date": None,
        "original_prompt": None,
    }
    base.update(kwargs)
    return base


@pytest.fixture
def mock_io(tmp_path):
    tasks_path = str(tmp_path / "tasks.json")
    with patch("src.core.scheduled_tasks.TASKS_PATH", tasks_path), \
         patch("src.core.scheduled_tasks._register_apscheduler_job"):
        yield tasks_path


def test_create_task_saves_and_returns(mock_io):
    result = st.create_task.invoke({
        "type": "once",
        "name": "买菜",
        "content": "提醒买菜",
        "trigger": "2026-03-01T10:00:00",
        "source": {"type": "group", "id": "123"},
    })
    assert result["name"] == "买菜"
    assert "task_id" in result
    tasks = st._load_tasks()
    assert len(tasks) == 1
    assert tasks[0]["name"] == "买菜"


def test_create_task_deduplicates_name(mock_io):
    st.create_task.invoke({
        "type": "once", "name": "买菜", "content": "c",
        "trigger": "2026-03-01T10:00:00", "source": {"type": "group", "id": "1"},
    })
    result = st.create_task.invoke({
        "type": "once", "name": "买菜", "content": "c",
        "trigger": "2026-03-01T11:00:00", "source": {"type": "group", "id": "1"},
    })
    assert result["name"] == "买菜(1)"


def test_cancel_task_by_name(mock_io):
    st.create_task.invoke({
        "type": "once", "name": "提醒", "content": "c",
        "trigger": "2026-03-01T10:00:00", "source": {"type": "group", "id": "1"},
    })
    with patch.object(st._scheduler, "remove_job"):
        result = st.cancel_task.invoke({"name": "提醒"})
    assert result["cancelled"] == "提醒"
    assert st._load_tasks() == []


def test_cancel_task_not_found(mock_io):
    result = st.cancel_task.invoke({"name": "不存在"})
    assert "error" in result


def test_cancel_task_by_id_preferred(mock_io):
    r = st.create_task.invoke({
        "type": "once", "name": "任务", "content": "c",
        "trigger": "2026-03-01T10:00:00", "source": {"type": "group", "id": "1"},
    })
    with patch.object(st._scheduler, "remove_job"):
        result = st.cancel_task.invoke({"task_id": r["task_id"], "name": "不存在"})
    assert result["cancelled"] == "任务"


# --- _recover_missed ---

@pytest.mark.anyio
async def test_recover_missed_once_removes_task(tmp_path):
    past = (datetime.now() - timedelta(hours=1)).isoformat()
    tasks = [_make_task(trigger=past)]
    with patch("src.core.scheduled_tasks.agent") as mock_agent:
        mock_agent.invoke = AsyncMock(return_value="ok")
        result = await st._recover_missed(tasks)
    assert result == []
    mock_agent.invoke.assert_called_once()


@pytest.mark.anyio
async def test_recover_missed_once_already_run_not_missed(tmp_path):
    past = (datetime.now() - timedelta(hours=1)).isoformat()
    tasks = [_make_task(trigger=past, last_run=past)]
    with patch("src.core.scheduled_tasks.agent") as mock_agent:
        mock_agent.invoke = AsyncMock(return_value="ok")
        result = await st._recover_missed(tasks)
    assert len(result) == 1
    mock_agent.invoke.assert_not_called()


@pytest.mark.anyio
async def test_recover_missed_future_not_missed():
    future = (datetime.now() + timedelta(hours=1)).isoformat()
    tasks = [_make_task(trigger=future)]
    with patch("src.core.scheduled_tasks.agent") as mock_agent:
        mock_agent.invoke = AsyncMock(return_value="ok")
        result = await st._recover_missed(tasks)
    assert len(result) == 1
    mock_agent.invoke.assert_not_called()


@pytest.mark.anyio
async def test_recover_missed_repeat_kept_after_recovery():
    past_last_run = (datetime.now() - timedelta(days=2)).isoformat()
    tasks = [_make_task(type="repeat", trigger="cron:0 9 * * *", last_run=past_last_run)]
    with patch("src.core.scheduled_tasks.agent") as mock_agent:
        mock_agent.invoke = AsyncMock(return_value="ok")
        result = await st._recover_missed(tasks)
    # repeat tasks are kept even if missed
    assert len(result) == 1
    mock_agent.invoke.assert_called_once()
