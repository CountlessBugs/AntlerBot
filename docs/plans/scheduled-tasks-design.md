# Scheduled Tasks Design

## Background

This document extends the scheduler architecture plan (`scheduler-architecture.md`) with a concrete design for scheduled task functionality.

## Requirements

Users can create scheduled tasks via natural language QQ messages. The bot supports:

- One-time reminders ("remind me in 30 minutes")
- Simple repeating tasks ("every day at 7pm", "every weekend this year")
- Complex repeating tasks with LLM-driven rescheduling ("first Sunday of every month", "lunar calendar birthdays")

Tasks persist across restarts. Users can cancel pending tasks by name.

## Architecture

Follows the planned scheduler architecture:

```
message_handler.py  →  scheduler.py  →  agent.py
scheduled_tasks.py  →  scheduler.py
```

`scheduled_tasks.py` manages APScheduler (memory mode) and task persistence. It registers tools into `agent.py` and handles all three workflows below.

## Task Data Structure

Stored in `config/tasks.json` as a list of task objects:

```json
{
  "task_id": "uuid",
  "type": "once | repeat | complex_repeat",
  "name": "每日新闻",
  "content": "现在是每日新闻时间，请为用户总结今天的热点新闻。",
  "trigger": "2026-02-21T18:00:00 | cron:0 19 * * *",
  "source": {"type": "group|private", "id": "12345"},
  "run_count": 0,
  "last_run": null,
  "max_runs": null,
  "end_date": null,
  "original_prompt": null
}
```

- `trigger`: ISO datetime string for `once`; `cron:` prefixed cron expression for `repeat`/`complex_repeat`
- `content`: Written by LLM in system voice ("请为用户..."), not user's original words
- `original_prompt`: Only for `complex_repeat`, written by LLM in system voice, used for rescheduling
- `last_run`: Updated after each execution; used to detect missed triggers on restart
- `max_runs` / `end_date`: Optional limits for repeat tasks (e.g. "next 5 weekends", "every weekend this year")

## Task Naming

Duplicate names get auto-suffixed: `买菜提醒`, `买菜提醒(1)`, `买菜提醒(2)`, etc.

## Tools Registered in agent.py

### `create_task`

```json
{
  "type": "once | repeat | complex_repeat",
  "name": "string",
  "content": "string (system voice)",
  "trigger": "string",
  "max_runs": "int | null",
  "end_date": "YYYY-MM-DD | null",
  "original_prompt": "string | null (complex_repeat only, system voice)"
}
```

Returns `{"task_id": "...", "name": "..."}` (with suffix if renamed).

### `cancel_task`

```json
{
  "task_id": "string | null",
  "name": "string | null"
}
```

Either field may be used. If both provided, `task_id` takes precedence.

## Workflows

### 1. Normal Conversation

User sends a message → `agent.py` processes with full context and system prompt → LLM decides whether to call `create_task` or `cancel_task` → tool execution registers/removes task in APScheduler and persists to JSON.

### 2. Task Trigger

APScheduler fires → `scheduled_tasks.py`:

1. Increments `run_count`, sets `last_run`, saves JSON
2. Removes task if `once`, or if `max_runs`/`end_date` limit reached
3. Constructs system message and calls `agent.invoke()`:

```
<scheduled_task>任务名称</scheduled_task>          # once / complex_repeat
<scheduled_task>任务名称-第n次</scheduled_task>     # repeat
{content}
```

4. Sends LLM reply to original `source`
5. If `complex_repeat`: triggers rescheduling workflow after reply

### 3. Complex Repeat Rescheduling

Called after step 4 above. Uses an independent workflow — no conversation history, no default system prompt.

Sends to LLM:
- Hardcoded "task timer" system prompt
- `original_prompt`, `name`, `content`, `run_count`

LLM returns structured output:

```json
{
  "action": "reschedule | cancel",
  "trigger": "ISO datetime or cron string",
  "name": "string | null",
  "content": "string | null",
  "original_prompt": "string | null"
}
```

If `reschedule`: re-registers task with new trigger (merging non-null fields over existing task).
If `cancel`: removes task from JSON and APScheduler.

## Startup: Missed Task Recovery

On startup, `scheduled_tasks.py`:

1. Loads all tasks from JSON
2. Identifies missed triggers: tasks where the expected next trigger time (based on `trigger` and `last_run`) is in the past
3. Batches all missed tasks into a single system message sent to `agent.invoke()`:

```
以下定时任务在机器人离线期间已到期：
- 任务名称（原定时间：...）：{content}
- ...
```

4. For `repeat`/`complex_repeat` tasks: reschedules next occurrence normally after recovery
5. For `once` tasks: removes after recovery message

## File Layout

```
src/core/scheduled_tasks.py   # APScheduler setup, tool implementations, workflows
config/tasks.json             # persisted task list (created on first task)
```

## Dependencies

- `apscheduler` — scheduling engine (memory store, asyncio executor)
- `lunardate` — lunar calendar date conversion (for complex_repeat tasks involving lunar dates)

Both added to `requirements.in`.
