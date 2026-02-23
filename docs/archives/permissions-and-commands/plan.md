# Permissions & Command System

## Overview

Add a user permission system (3 tiers) and private-chat command system to AntlerBot. Commands only work in private chat for authorized users. Unauthorized `/` messages are treated as normal text. Command messages are NOT added to LLM context.

## Permission Model

Config file: `config/permissions.yaml`

```yaml
admin:
  - 123456789
developer:
  - 987654321
```

- Users not listed → normal user (no command access)
- File re-read on every command check (small file, no caching needed)
- Higher roles inherit lower role permissions (admin can use developer commands)

## Command List

### Developer (read-only)

| Command | Args | Description |
|---------|------|-------------|
| `/help` | `[cmd_name]` | List available commands, or show details for a specific command |
| `/token` | — | Show current context token count |
| `/context` | — | Send full context as txt file |
| `/prompt` | — | Send current system prompt as txt file |
| `/raw` | — | Show last conversation turn (HumanMessage + AIMessage from agent history) |
| `/log` | `[YYYY-MM-DD]` | Send log file, defaults to today |
| `/status` | — | Bot status: session state, message count, task count, timeout countdown, queue depth |
| `/tasks` | — | List active scheduled tasks |

### Admin (read-write)

| Command | Args | Description |
|---------|------|-------------|
| `/reload` | `config` / `contact` | Hot-reload config or contact cache |
| `/summarize` | — | Trigger session summarization immediately |
| `/clear_context` | — | Clear context history |

## Architecture

### New Files

- `src/core/commands.py` — command parsing, permission checks, command registry & execution
- `config/permissions.yaml` — permission config (with `.example`)

### Modified Files

- `src/core/message_handler.py` — intercept `/` messages in `on_private` callback

### Message Flow

```
Private message arrives
  ↓
Starts with "/"?
  ├─ No → normal flow (format_message → scheduler.enqueue)
  └─ Yes → read permissions.yaml, check user_id role
        ├─ No permission (normal user) → treat as normal text, normal flow
        └─ Has permission → parse command name + args
              ├─ Insufficient role → reply "权限不足"
              ├─ Unknown command → reply "未知指令"
              └─ Execute → reply directly (bypasses scheduler/agent entirely)
```

Key: command messages are NEVER added to LLM context, never pass through scheduler.

### commands.py Design

```python
ROLE_USER = 0
ROLE_DEVELOPER = 1
ROLE_ADMIN = 2

def load_permissions() -> dict[str, int]:
    """Read permissions.yaml, return {qq_id_str: role_level}."""

def get_role(user_id: str) -> int:
    """Get user role. Returns ROLE_USER if not in config."""

async def handle_command(user_id: str, text: str, bot_api, event) -> bool:
    """
    Try to handle a command. Returns True if handled (was a valid command
    from an authorized user), False if not a command or user has no permission.
    """
```

Commands registered via a dict mapping name → (min_role, handler, description, usage).

### message_handler.py Change

In `on_private`, before the existing logic:

```python
if e.raw_message.startswith("/"):
    handled = await commands.handle_command(str(e.sender.user_id), e.raw_message, bot.api, e)
    if handled:
        return  # command handled, skip LLM
# ... existing logic unchanged
```

### File Sending

`/context`, `/prompt`, `/log` send files via:
```python
await bot.api.upload_private_file(user_id, file_path, filename)
```

Other commands reply with text via:
```python
await bot.api.post_private_msg(user_id, text=result)
```

## Command Implementation Notes

### /help
- No args: list commands available to the user's role, with short descriptions
- With arg: show detailed usage for that command

### /token
- Estimate from `agent._history` — use `_llm.get_num_tokens()` if available, else character-based estimate

### /context
- Format `agent._history` as readable text, write to temp file, send via `upload_private_file`

### /prompt
- Read `config/agent/prompt.txt`, write to temp file, send via `upload_private_file`

### /raw
- Extract last HumanMessage + AIMessage from `agent._history`
- If history empty: reply "该轮对话在上下文历史中已被清除"

### /log
- Current day: `logs/bot.log`
- Past dates: `logs/bot.log.YYYY_MM_DD` (e.g. `bot.log.2026_02_20`)
- Arg format: `YYYY-MM-DD` (converted to `YYYY_MM_DD` for filename lookup)
- No arg → send today's `bot.log`
- File not found → reply "未找到该日期的日志文件"
- Send via `upload_private_file`

### /status
- Session active: `agent.has_history()`
- Context message count: `len(agent._history)`
- Active tasks: `len(scheduled_tasks._load_tasks())`
- Timeout countdown: remaining time from APScheduler `session_summarize` job
- Queue depth: `scheduler._queue.qsize()`

### /tasks
- Read `scheduled_tasks._load_tasks()`, format as list with name, type, trigger, run_count

### /reload config
- Set `agent._graph = None` to force re-init on next invoke

### /reload contact
- Call `contact_cache.refresh_all()`

### /summarize
- Call `agent._invoke("session_timeout")` and consume the generator

### /clear_context
- Call `agent.clear_history()`
