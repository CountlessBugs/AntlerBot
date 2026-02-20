# AntlerBot LLM Reply Feature — Implementation Plan

## Overview

Implement basic LLM reply functionality: receive QQ messages → call LLM via LangGraph → reply. All sources share one context. Messages are queued with priority batching.

## File Structure

```
main.py                          # entry point
src/
  __init__.py
  core/
    __init__.py
    agent.py                     # LangGraph workflow, LLM init, history, prompt loading
    message_handler.py           # NcatBot callbacks, formatting, group cache, queue
config/
  agent/
    prompt.txt.example
.env.example
.gitignore                       # add config/agent/prompt.txt
requirements.in                  # add langchain, langchain-openai, python-dotenv
```

---

## Step 1 — Dependencies

**File: `requirements.in`** — append:
```
langchain
langchain-openai
python-dotenv
```

Run:
```bash
pip-compile --index-url=https://mirrors.aliyun.com/pypi/simple/ --output-file=requirements.txt requirements.in
pip install -r requirements.txt
```

---

## Step 2 — Config files

**File: `config/agent/prompt.txt.example`**
```
你是一个QQ机器人
```

**File: `.env.example`**
```
# LLM model identifier, e.g. openai:gpt-4o, anthropic:claude-3-5-sonnet-20241022
LLM_MODEL=openai:gpt-4o

# Provider-specific keys (set whichever your provider requires)
OPENAI_API_KEY=
OPENAI_BASE_URL=        # optional, for custom endpoints
```

**File: `.gitignore`** — append:
```
config/agent/prompt.txt
.env
```

---

## Step 3 — `src/core/agent.py`

Responsibilities:
- Load system prompt from `config/agent/prompt.txt`
  - File missing → `logging.warning` + create file with default `"你是一个QQ机器人"`
  - File exists but empty → `logging.warning` only, system_prompt stays `None`
- Initialize LLM via `init_chat_model(os.environ["LLM_MODEL"])`
- Build minimal LangGraph `StateGraph`:
  - State: `{"messages": list[BaseMessage]}`
  - Single node `"llm"`: invoke model with system prompt prepended (if any) + history
  - Edge: `START → "llm" → END`
- Shared in-memory history: `list[BaseMessage]` (module-level)
- Expose `async def invoke(human_message: str) -> str`:
  - Append `HumanMessage(human_message)` to history
  - Run graph
  - Append `AIMessage(response)` to history
  - Return response text

---

## Step 4 — `src/core/message_handler.py`

### 4a. Group name cache + fetch

```python
_group_name_cache: dict[str, str] = {}

async def get_group_name(group_id: str) -> str:
    # check cache, else call status.global_api.get_group_info(group_id)
    # cache and return group name
```

### 4b. Message formatting

```python
def format_message(content: str, nickname: str, group_name: str | None = None) -> str:
    # group: f"<sender>{nickname} [群聊-{group_name}]</sender>{content}"
    # private: f"<sender>{nickname}</sender>{content}"
```

### 4c. Queue + priority batching

Data structures (module-level):
```python
_lock = asyncio.Lock()
_processing = False
_current_source: str | None = None          # source key of message being processed
_pending: list[tuple[str, str, callable]]   # (source_key, formatted_msg, reply_fn)
```

Priority batching logic (called after each message finishes):
1. Collect all pending items
2. Extract current_source items first (in order)
3. Then remaining sources in first-appearance order, grouped by source
4. For each batch (same source): merge formatted messages into one string, call `agent.invoke()`, call `reply_fn(response)`

### 4d. NcatBot callback registration

```python
def register(bot: BotClient) -> None:
    @bot.on_group_message()
    async def on_group(e: GroupMessageEvent): ...

    @bot.on_private_message()
    async def on_private(e: PrivateMessageEvent): ...
```

Each callback:
1. Format message (fetch group name if needed)
2. Build `reply_fn` (calls `bot.api.post_group_msg` or `post_private_msg`)
3. Acquire lock, append to `_pending`, release lock
4. If not processing, trigger processing loop

---

## Step 5 — `main.py`

```python
from dotenv import load_dotenv
load_dotenv()

from ncatbot.core import BotClient
from src.core.message_handler import register

bot = BotClient()
register(bot)
bot.run_frontend()
```

---

## Step 6 — Package `__init__.py` files

- `src/__init__.py` — empty
- `src/core/__init__.py` — empty

---

## Checklist

- [ ] Step 1: Update requirements.in, compile, install
- [ ] Step 2: Create config/agent/prompt.txt.example, .env.example, update .gitignore
- [ ] Step 3: Implement src/core/agent.py
- [ ] Step 4: Implement src/core/message_handler.py
- [ ] Step 5: Implement main.py
- [ ] Step 6: Create __init__.py files
