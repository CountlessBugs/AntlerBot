# Scheduled Tasks Implementation Plan

Design doc: `docs/plans/scheduled-tasks-design.md`

## Step 1: Add dependencies

Add to `requirements.in`:
```
apscheduler
lunardate
```

Run:
```
pip-compile --index-url=https://mirrors.aliyun.com/pypi/simple/ --output-file=requirements.txt requirements.in
pip install -r requirements.txt
```

## Step 2: Extend agent.py to support tools and a bare workflow

`agent.py` needs two new capabilities:

1. **Tool registration** — `register_tools(tools: list)` stores tools on the LLM via `_llm.bind_tools(tools)` and wires tool execution into the graph. The normal `invoke()` uses this tool-enabled LLM.

2. **Bare invoke** — `invoke_bare(messages: list[BaseMessage]) -> str` runs the LLM with no system prompt, no history, no tools, and no history mutation. Used by the complex repeat rescheduling workflow.

Changes to `agent.py`:
- Add `_tools: list = []` module-level variable
- Add `register_tools(tools)` that sets `_tools` and invalidates `_graph` (sets to `None`) so it rebuilds on next call
- In `_ensure_initialized`, if `_tools` is non-empty, bind them to `_llm` and add a tool execution node to the graph
- Add `async invoke_bare(messages) -> str` — acquires `_lock`, calls `_llm.invoke(messages)` directly (no graph, no history), returns content

The graph with tools needs a conditional edge: after `llm_node`, if the response has `tool_calls`, route to a `tools_node` that executes them and loops back; otherwise go to END.

## Step 3: Create src/core/scheduled_tasks.py

### 3a: Data layer

- `TASKS_PATH = config/tasks.json`
- `_load_tasks() -> list[dict]` — reads JSON, returns `[]` if missing
- `_save_tasks(tasks)` — writes JSON atomically
- `_unique_name(name, tasks) -> str` — returns `name`, `name(1)`, `name(2)`, etc.

### 3b: APScheduler setup

- Module-level `_scheduler = AsyncIOScheduler()`
- `_bot` module-level reference (set during `register()`)
- `_register_apscheduler_job(task: dict)` — parses `task["trigger"]`:
  - If starts with `cron:` → `CronTrigger.from_crontab(...)`
  - Else → `DateTrigger` with ISO datetime
  - Adds job with `id=task["task_id"]`, calls `_on_trigger(task_id)`

### 3c: Tool implementations

`create_task(type, name, content, trigger, source, max_runs, end_date, original_prompt)`:
- Load tasks, compute unique name, build task dict with new UUID, append, save
- Register APScheduler job
- Return `{"task_id": ..., "name": ...}`

`cancel_task(task_id, name)`:
- Load tasks, find by `task_id` (preferred) or `name`
- Remove from list, save, remove APScheduler job
- Return `{"cancelled": name}`

### 3d: Trigger workflow

`async _on_trigger(task_id)`:
1. Load tasks, find task; if not found return
2. `task["run_count"] += 1`, `task["last_run"] = now.isoformat()`
3. Check limits: if `once` or `max_runs` reached or `end_date` passed → remove task and APScheduler job
4. Save tasks
5. Build system message:
   - `repeat`: `<scheduled_task>{name}-第{run_count}次</scheduled_task>\n{content}`
   - others: `<scheduled_task>{name}</scheduled_task>\n{content}`
6. Call `agent.invoke(system_message)` — this injects as a human message into shared history
7. Send reply to source via `_bot.api`
8. If `complex_repeat` and task still exists → call `_reschedule(task)`

### 3e: Rescheduling workflow

`async _reschedule(task)`:
- Build messages: `[SystemMessage(TIMER_PROMPT), HumanMessage(rescheduling_context)]`
  - `rescheduling_context` includes `original_prompt`, `name`, `content`, `run_count`
- Call `agent.invoke_bare(messages)` — structured output via `with_structured_output`
- If `action == "cancel"` → remove task and job
- If `action == "reschedule"` → merge non-null fields, update trigger, re-register job, save

`TIMER_PROMPT` (hardcoded): instructs LLM to output next trigger time for the task, or cancel it.

### 3f: Startup recovery

`async _recover_missed(tasks)`:
- For each task, compute expected next trigger time from `trigger` and `last_run`
- Collect tasks where expected time < now
- If any missed: build single system message listing all, call `agent.invoke()`
- For `once` missed tasks: remove from list
- For `repeat`/`complex_repeat` missed tasks: keep (APScheduler will schedule next occurrence)

### 3g: register()

`async def register(bot)`:
- Set `_bot = bot`
- Register `create_task` and `cancel_task` tools into `agent.register_tools([...])`
- Load tasks, call `_recover_missed(tasks)`, save updated tasks
- For each non-expired task, call `_register_apscheduler_job(task)`
- Start `_scheduler`

## Step 4: Wire into main.py

In `main.py`, after `message_handler.register(bot)`:
```python
from src.core import scheduled_tasks
await scheduled_tasks.register(bot)
```

Since `bot.run()` is synchronous and blocks, `register()` must be called before it. Check how NcatBot handles async startup — may need to use `asyncio.get_event_loop().run_until_complete(scheduled_tasks.register(bot))` or a startup hook.

## Step 5: Tests

- `tests/test_scheduled_tasks.py`:
  - `_unique_name` deduplication logic
  - `_recover_missed` correctly identifies missed tasks
  - `create_task` / `cancel_task` tool logic (mock APScheduler and file I/O)

## File changes summary

| File | Change |
|------|--------|
| `requirements.in` | Add `apscheduler`, `lunardate` |
| `src/core/agent.py` | Add `register_tools()`, `invoke_bare()`, tool graph support |
| `src/core/scheduled_tasks.py` | New file — all scheduled task logic |
| `main.py` | Call `scheduled_tasks.register(bot)` on startup |
| `tests/test_scheduled_tasks.py` | New test file |
