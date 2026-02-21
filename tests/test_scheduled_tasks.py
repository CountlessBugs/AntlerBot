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


# --- _parse_cron ---

def test_parse_cron_5_fields():
    trig = st._parse_cron("0 9 * * *")
    assert trig is not None


def test_parse_cron_6_fields():
    trig = st._parse_cron("0 0 9 * * *")
    assert trig is not None


def test_parse_cron_question_mark_replaced():
    trig = st._parse_cron("0 0 9 * * ?")
    assert trig is not None


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


def test_create_task_repeat_type(mock_io):
    result = st.create_task.invoke({
        "type": "repeat", "name": "每日", "content": "c",
        "trigger": "cron:0 9 * * *", "source": {"type": "group", "id": "1"},
    })
    assert result["name"] == "每日"
    assert st._load_tasks()[0]["type"] == "repeat"


def test_create_task_complex_repeat_type(mock_io):
    result = st.create_task.invoke({
        "type": "complex_repeat", "name": "农历生日", "content": "c",
        "trigger": "cron:0 9 * * *", "source": {"type": "group", "id": "1"},
        "original_prompt": "每年农历生日提醒",
    })
    assert result["name"] == "农历生日"
    task = st._load_tasks()[0]
    assert task["type"] == "complex_repeat"
    assert task["original_prompt"] == "每年农历生日提醒"


def test_create_task_default_source(mock_io):
    import src.core.scheduler as sched
    sched._current_source = "group_99"
    try:
        result = st.create_task.invoke({
            "type": "once", "name": "默认源", "content": "c",
            "trigger": "2026-03-01T10:00:00",
        })
    finally:
        sched._current_source = None
    assert result["name"] == "默认源"
    assert st._load_tasks()[0]["source"] == {"type": "group", "id": "99"}


def test_create_task_saves_and_returns(mock_io):
    result = st.create_task.invoke({
        "type": "once",
        "name": "买菜",
        "content": "提醒买菜",
        "trigger": "2026-03-01T10:00:00",
        "source": {"type": "group", "id": "123"},
    })
    assert result["name"] == "买菜"
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
    st.create_task.invoke({
        "type": "once", "name": "任务", "content": "c",
        "trigger": "2026-03-01T10:00:00", "source": {"type": "group", "id": "1"},
    })
    task_id = st._load_tasks()[0]["task_id"]
    with patch.object(st._scheduler, "remove_job"):
        result = st.cancel_task.invoke({"task_id": task_id, "name": "不存在"})
    assert result["cancelled"] == "任务"


# --- _on_trigger ---

@pytest.mark.anyio
async def test_on_trigger_once_removes_task(mock_io):
    st.create_task.invoke({
        "type": "once", "name": "提醒", "content": "内容",
        "trigger": "2026-03-01T10:00:00", "source": {"type": "group", "id": "1"},
    })
    task_id = st._load_tasks()[0]["task_id"]
    with patch("src.core.scheduled_tasks.scheduler") as mock_sched, \
         patch.object(st._scheduler, "remove_job"):
        mock_sched.enqueue = AsyncMock()
        mock_sched.PRIORITY_SCHEDULED = 0
        await st._on_trigger(task_id)
    assert st._load_tasks() == []


@pytest.mark.anyio
async def test_on_trigger_repeat_kept_and_uses_run_count(mock_io):
    st.create_task.invoke({
        "type": "repeat", "name": "每日", "content": "内容",
        "trigger": "cron:0 9 * * *", "source": {"type": "group", "id": "1"},
    })
    task_id = st._load_tasks()[0]["task_id"]
    with patch("src.core.scheduled_tasks.scheduler") as mock_sched:
        mock_sched.enqueue = AsyncMock()
        mock_sched.PRIORITY_SCHEDULED = 0
        await st._on_trigger(task_id)
    tasks = st._load_tasks()
    assert len(tasks) == 1
    assert tasks[0]["run_count"] == 1
    call_msg = mock_sched.enqueue.call_args[0][2]
    assert "第1次" in call_msg


@pytest.mark.anyio
async def test_on_trigger_max_runs_removes_task(mock_io):
    st.create_task.invoke({
        "type": "repeat", "name": "限次", "content": "内容",
        "trigger": "cron:0 9 * * *", "source": {"type": "group", "id": "1"},
        "max_runs": 1,
    })
    task_id = st._load_tasks()[0]["task_id"]
    with patch("src.core.scheduled_tasks.scheduler") as mock_sched, \
         patch.object(st._scheduler, "remove_job"):
        mock_sched.enqueue = AsyncMock()
        mock_sched.PRIORITY_SCHEDULED = 0
        await st._on_trigger(task_id)
    assert st._load_tasks() == []


# --- _reschedule ---

@pytest.mark.anyio
async def test_reschedule_cancel_removes_task(mock_io):
    st.create_task.invoke({
        "type": "complex_repeat", "name": "农历", "content": "内容",
        "trigger": "cron:0 9 * * *", "source": {"type": "group", "id": "1"},
        "original_prompt": "农历提醒",
    })
    task = st._load_tasks()[0]
    output = st._RescheduleOutput(action="cancel")
    with patch("src.core.scheduled_tasks.agent") as mock_agent, \
         patch.object(st._scheduler, "remove_job"):
        mock_agent.invoke_bare = AsyncMock(return_value=output)
        await st._reschedule(task)
    assert st._load_tasks() == []


@pytest.mark.anyio
async def test_reschedule_reschedule_updates_trigger(mock_io):
    st.create_task.invoke({
        "type": "complex_repeat", "name": "农历", "content": "内容",
        "trigger": "cron:0 9 * * *", "source": {"type": "group", "id": "1"},
        "original_prompt": "农历提醒",
    })
    task = st._load_tasks()[0]
    new_trigger = "2026-04-01T09:00:00"
    output = st._RescheduleOutput(action="reschedule", trigger=new_trigger)
    with patch("src.core.scheduled_tasks.agent") as mock_agent, \
         patch("src.core.scheduled_tasks._register_apscheduler_job") as mock_reg:
        mock_agent.invoke_bare = AsyncMock(return_value=output)
        await st._reschedule(task)
    saved = st._load_tasks()[0]
    assert saved["trigger"] == new_trigger
    mock_reg.assert_called_once()



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
