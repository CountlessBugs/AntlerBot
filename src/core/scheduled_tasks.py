import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel

from src.core import agent

logger = logging.getLogger(__name__)

TASKS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "tasks.json")
)

_scheduler = AsyncIOScheduler()
_bot = None


# --- Data layer ---

def _load_tasks() -> list[dict]:
    if not os.path.exists(TASKS_PATH):
        return []
    with open(TASKS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_tasks(tasks: list[dict]) -> None:
    os.makedirs(os.path.dirname(TASKS_PATH), exist_ok=True)
    tmp = TASKS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TASKS_PATH)


def _unique_name(name: str, tasks: list[dict]) -> str:
    existing = {t["name"] for t in tasks}
    if name not in existing:
        return name
    i = 1
    while f"{name}({i})" in existing:
        i += 1
    return f"{name}({i})"


# --- APScheduler ---

def _register_apscheduler_job(task: dict) -> None:
    trigger_str = task["trigger"]
    if trigger_str.startswith("cron:"):
        trigger = CronTrigger.from_crontab(trigger_str[5:])
    else:
        trigger = DateTrigger(run_date=datetime.fromisoformat(trigger_str))
    _scheduler.add_job(
        _on_trigger,
        trigger,
        args=[task["task_id"]],
        id=task["task_id"],
        replace_existing=True,
    )


# --- Tools ---

@tool
def create_task(
    type: str,
    name: str,
    content: str,
    trigger: str,
    source: Optional[dict] = None,
    max_runs: Optional[int] = None,
    end_date: Optional[str] = None,
    original_prompt: Optional[str] = None,
) -> dict:
    """Create a scheduled task.
    type: once|repeat|complex_repeat.
    trigger: timezone-naive ISO datetime (e.g. 2026-03-01T10:00:00) for once, or cron:EXPR for repeat/complex_repeat.
    source: {"type": "group|private", "id": "chat_id"}. Omit to use the current chat.
    content: task prompt in system voice.
    original_prompt: only for complex_repeat, in system voice.
    """
    if source is None:
        from src.core import message_handler
        source = message_handler.get_current_source()
    tasks = _load_tasks()
    unique = _unique_name(name, tasks)
    task = {
        "task_id": str(uuid.uuid4()),
        "type": type,
        "name": unique,
        "content": content,
        "trigger": trigger,
        "source": source,
        "run_count": 0,
        "last_run": None,
        "max_runs": max_runs,
        "end_date": end_date,
        "original_prompt": original_prompt,
    }
    tasks.append(task)
    _save_tasks(tasks)
    _register_apscheduler_job(task)
    return {"name": unique}


@tool
def cancel_task(task_id: Optional[str] = None, name: Optional[str] = None) -> dict:
    """Cancel a scheduled task by task_id (preferred) or name."""
    tasks = _load_tasks()
    target = None
    if task_id:
        target = next((t for t in tasks if t["task_id"] == task_id), None)
    if target is None and name:
        target = next((t for t in tasks if t["name"] == name), None)
    if target is None:
        return {"error": "Task not found"}
    tasks = [t for t in tasks if t["task_id"] != target["task_id"]]
    _save_tasks(tasks)
    try:
        _scheduler.remove_job(target["task_id"])
    except Exception:
        pass
    return {"cancelled": target["name"]}


# --- Trigger workflow ---

async def _send_reply(source: dict, text: str) -> None:
    if _bot is None:
        return
    if source["type"] == "group":
        await _bot.api.post_group_msg(group_id=source["id"], text=text)
    else:
        await _bot.api.post_private_msg(user_id=source["id"], text=text)


async def _on_trigger(task_id: str) -> None:
    tasks = _load_tasks()
    task = next((t for t in tasks if t["task_id"] == task_id), None)
    if task is None:
        return

    now = datetime.now()
    task["run_count"] += 1
    task["last_run"] = now.isoformat()

    expired = (
        task["type"] == "once"
        or (task["max_runs"] and task["run_count"] >= task["max_runs"])
        or (task["end_date"] and now.date().isoformat() > task["end_date"])
    )

    if expired:
        tasks = [t for t in tasks if t["task_id"] != task_id]
        try:
            _scheduler.remove_job(task_id)
        except Exception:
            pass
    else:
        tasks = [task if t["task_id"] == task_id else t for t in tasks]
    _save_tasks(tasks)

    if task["type"] == "repeat":
        header = f"<scheduled_task>{task['name']}-第{task['run_count']}次</scheduled_task>"
    else:
        header = f"<scheduled_task>{task['name']}</scheduled_task>"

    reply = await agent.invoke(f"{header}\n{task['content']}")
    await _send_reply(task["source"], reply)

    if task["type"] == "complex_repeat" and not expired:
        current = _load_tasks()
        if any(t["task_id"] == task_id for t in current):
            await _reschedule(task)


# --- Rescheduling ---

class _RescheduleOutput(BaseModel):
    action: str
    trigger: Optional[str] = None
    name: Optional[str] = None
    content: Optional[str] = None
    original_prompt: Optional[str] = None


async def _reschedule(task: dict) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    timer_prompt = (
        f"你是一个定时任务调度器。今天是{today}。"
        "根据任务信息决定下次触发时间或取消任务。"
        "reschedule时提供trigger（ISO datetime或cron:表达式），其余字段如需更新则填写否则为null；"
        "cancel时其余字段为null。"
    )
    context = (
        f"任务名称：{task['name']}\n"
        f"已执行次数：{task['run_count']}\n"
        f"原始提示：{task['original_prompt']}\n"
        f"当前内容：{task['content']}\n"
        f"当前触发器：{task['trigger']}"
    )
    result = await agent.invoke_bare(
        [SystemMessage(timer_prompt), HumanMessage(context)],
        schema=_RescheduleOutput,
    )

    tasks = _load_tasks()
    if result.action == "cancel":
        tasks = [t for t in tasks if t["task_id"] != task["task_id"]]
        _save_tasks(tasks)
        try:
            _scheduler.remove_job(task["task_id"])
        except Exception:
            pass
    elif result.action == "reschedule":
        target = next((t for t in tasks if t["task_id"] == task["task_id"]), None)
        if target is None:
            return
        for field in ("trigger", "name", "content", "original_prompt"):
            val = getattr(result, field)
            if val is not None:
                target[field] = val
        _save_tasks(tasks)
        _register_apscheduler_job(target)


# --- Startup recovery ---

async def _recover_missed(tasks: list[dict]) -> list[dict]:
    now = datetime.now()
    missed = []
    for task in tasks:
        trigger_str = task["trigger"]
        if trigger_str.startswith("cron:"):
            trig = CronTrigger.from_crontab(trigger_str[5:])
            ref = datetime.fromisoformat(task["last_run"]) if task["last_run"] else None
            min_time = ref if ref else datetime(2000, 1, 1)
            next_time = trig.get_next_fire_time(ref, min_time)
            if next_time and next_time.replace(tzinfo=None) < now:
                missed.append(task)
        else:
            run_time = datetime.fromisoformat(trigger_str)
            if run_time.replace(tzinfo=None) < now and task["last_run"] is None:
                missed.append(task)

    if missed:
        lines = "\n".join(
            f"- {t['name']} (原定时间：{t['trigger']}): {t['content']}"
            for t in missed
        )
        await agent.invoke(f"以下定时任务在离线期间已到期：\n{lines}")

    once_missed = {t["task_id"] for t in missed if t["type"] == "once"}
    return [t for t in tasks if t["task_id"] not in once_missed]


# --- Register ---

async def register(bot) -> None:
    global _bot
    _bot = bot
    agent.register_tools([create_task, cancel_task])

    tasks = _load_tasks()
    tasks = await _recover_missed(tasks)
    _save_tasks(tasks)

    for task in tasks:
        _register_apscheduler_job(task)

    _scheduler.start()
