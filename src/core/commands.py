import logging
import os
import tempfile
from datetime import datetime

import yaml

from src.core import agent, scheduler, scheduled_tasks, contact_cache

logger = logging.getLogger(__name__)

ROLE_USER = 0
ROLE_DEVELOPER = 1
ROLE_ADMIN = 2

PERMISSIONS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "permissions.yaml")
)

_ROLE_MAP = {"admin": ROLE_ADMIN, "developer": ROLE_DEVELOPER}


def load_permissions() -> dict[str, int]:
    if not os.path.exists(PERMISSIONS_PATH):
        return {}
    with open(PERMISSIONS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    result = {}
    for role_name, ids in data.items():
        level = _ROLE_MAP.get(role_name, ROLE_USER)
        for uid in ids or []:
            result[str(uid)] = level
    return result


def get_role(user_id: str) -> int:
    return load_permissions().get(user_id, ROLE_USER)


# Registry: name → (min_role, handler, description, usage)
_COMMANDS: dict[str, tuple[int, callable, str, str]] = {}


def _register(name: str, min_role: int, description: str, usage: str = ""):
    def decorator(fn):
        _COMMANDS[name] = (min_role, fn, description, usage)
        return fn
    return decorator


async def handle_command(user_id: str, text: str, bot_api, event) -> bool:
    if not text.startswith("/"):
        return False
    role = get_role(user_id)
    if role == ROLE_USER:
        return False
    parts = text[1:].split(None, 1)
    cmd_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""
    if cmd_name not in _COMMANDS:
        await bot_api.post_private_msg(user_id=event.user_id, text=f"未知指令: /{cmd_name}")
        return True
    min_role, handler, _, _ = _COMMANDS[cmd_name]
    if role < min_role:
        await bot_api.post_private_msg(user_id=event.user_id, text="权限不足")
        return True
    await handler(user_id, args, bot_api, event)
    return True


# --- Developer commands ---

@_register("help", ROLE_DEVELOPER, "列出可用指令或查看指令详情", "/help [指令名]")
async def _cmd_help(user_id, args, bot_api, event):
    role = get_role(user_id)
    if args:
        cmd = _COMMANDS.get(args.strip("/"))
        if not cmd:
            await bot_api.post_private_msg(user_id=event.user_id, text=f"未知指令: /{args}")
            return
        _, _, desc, usage = cmd
        await bot_api.post_private_msg(user_id=event.user_id, text=f"/{args.strip('/')} - {desc}\n用法: {usage or '无参数'}")
        return
    lines = []
    for name, (min_role, _, desc, _) in _COMMANDS.items():
        if role >= min_role:
            lines.append(f"/{name} - {desc}")
    await bot_api.post_private_msg(user_id=event.user_id, text="\n".join(lines))


@_register("token", ROLE_DEVELOPER, "显示当前上下文token数")
async def _cmd_token(user_id, args, bot_api, event):
    count = sum(len(m.content) // 2 for m in agent._history)
    if agent._llm and hasattr(agent._llm, "get_num_tokens"):
        try:
            count = agent._llm.get_num_tokens("".join(m.content for m in agent._history if isinstance(m.content, str)))
        except Exception:
            pass
    await bot_api.post_private_msg(user_id=event.user_id, text=f"当前上下文token估算: {count}")


@_register("raw", ROLE_DEVELOPER, "显示最后一轮对话")
async def _cmd_raw(user_id, args, bot_api, event):
    from langchain_core.messages import HumanMessage, AIMessage
    history = agent._history
    if not history:
        await bot_api.post_private_msg(user_id=event.user_id, text="该轮对话在上下文历史中已被清除")
        return
    last_human = last_ai = None
    for m in reversed(history):
        if not last_ai and isinstance(m, AIMessage):
            last_ai = m
        if not last_human and isinstance(m, HumanMessage):
            last_human = m
        if last_human and last_ai:
            break
    parts = []
    if last_human:
        parts.append(f"[Human] {last_human.content}")
    if last_ai:
        parts.append(f"[AI] {last_ai.content}")
    await bot_api.post_private_msg(user_id=event.user_id, text="\n".join(parts) or "无内容")


@_register("status", ROLE_DEVELOPER, "显示Bot状态")
async def _cmd_status(user_id, args, bot_api, event):
    active = agent.has_history()
    msg_count = len(agent._history)
    task_count = len(scheduled_tasks._load_tasks())
    queue_depth = scheduler._queue.qsize()
    timeout = "N/A"
    if scheduler._apscheduler:
        job = scheduler._apscheduler.get_job("session_summarize")
        if job and job.next_run_time:
            remaining = (job.next_run_time.replace(tzinfo=None) - datetime.now()).total_seconds()
            timeout = f"{int(remaining)}s" if remaining > 0 else "即将触发"
    lines = [
        f"会话活跃: {'是' if active else '否'}",
        f"上下文消息数: {msg_count}",
        f"活跃任务数: {task_count}",
        f"超时倒计时: {timeout}",
        f"队列深度: {queue_depth}",
    ]
    await bot_api.post_private_msg(user_id=event.user_id, text="\n".join(lines))


@_register("tasks", ROLE_DEVELOPER, "列出活跃的定时任务")
async def _cmd_tasks(user_id, args, bot_api, event):
    tasks = scheduled_tasks._load_tasks()
    if not tasks:
        await bot_api.post_private_msg(user_id=event.user_id, text="无活跃任务")
        return
    lines = []
    for t in tasks:
        lines.append(f"{t['name']} [{t['type']}] trigger={t['trigger']} runs={t.get('run_count', 0)}")
    await bot_api.post_private_msg(user_id=event.user_id, text="\n".join(lines))


@_register("context", ROLE_DEVELOPER, "导出当前上下文历史")
async def _cmd_context(user_id, args, bot_api, event):
    text = "\n".join(f"[{type(m).__name__}] {m.content}" for m in agent._history)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = f.name
    await bot_api.upload_private_file(user_id=event.user_id, file=path, name="context.txt")


@_register("prompt", ROLE_DEVELOPER, "导出当前系统提示词")
async def _cmd_prompt(user_id, args, bot_api, event):
    await bot_api.upload_private_file(user_id=event.user_id, file=agent.PROMPT_PATH, name="prompt.txt")


LOG_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "logs"))


@_register("log", ROLE_DEVELOPER, "导出日志文件", "/log [YYYY-MM-DD]")
async def _cmd_log(user_id, args, bot_api, event):
    if args.strip():
        path = os.path.join(LOG_DIR, f"bot.log.{args.strip().replace('-', '_')}")
    else:
        path = os.path.join(LOG_DIR, "bot.log")
    if not os.path.isfile(path):
        await bot_api.post_private_msg(user_id=event.user_id, text=f"未找到日志: {path}")
        return
    await bot_api.upload_private_file(user_id=event.user_id, file=path, name=os.path.basename(path))


# --- Admin commands ---

@_register("reload", ROLE_ADMIN, "重载配置", "/reload <config|contact>")
async def _cmd_reload(user_id, args, bot_api, event):
    target = args.strip()
    if target == "config":
        agent._graph = None
        await bot_api.post_private_msg(user_id=event.user_id, text="配置已重载")
    elif target == "contact":
        contact_cache.refresh_all()
        await bot_api.post_private_msg(user_id=event.user_id, text="联系人缓存已刷新")
    else:
        await bot_api.post_private_msg(user_id=event.user_id, text="用法: /reload <config|contact>")


@_register("summarize", ROLE_ADMIN, "立即总结上下文")
async def _cmd_summarize(user_id, args, bot_api, event):
    async for _ in agent._invoke("session_timeout"):
        pass
    await bot_api.post_private_msg(user_id=event.user_id, text="上下文已总结")


@_register("clear_context", ROLE_ADMIN, "清空上下文历史")
async def _cmd_clear_context(user_id, args, bot_api, event):
    agent.clear_history()
    await bot_api.post_private_msg(user_id=event.user_id, text="上下文已清空")
