# Message Splitting Implementation Plan

Design doc: [message-splitting-design.md](message-splitting-design.md)

## Steps

### Step 1 — `agent.py`: change `_invoke` to async generator

- Add `import re` and `from typing import AsyncGenerator` (update existing import)
- Replace `async def _invoke(...) -> str:` with `async def _invoke(...) -> AsyncGenerator[str, None]:`
- Replace `result = await _graph.ainvoke(...)` + `return result[...].content` with:
  - `buffer = ""; in_no_split = False`
  - `async for event in _graph.astream_events({...}, version="v2"):` loop
  - Filter: `event["event"] == "on_chat_model_stream"` and `event.get("metadata", {}).get("langgraph_node") == "llm"`
  - Extract chunk content, append to buffer, run split loop (see design)
  - After loop: flush remaining buffer
- Helper: inline `_emit(text)` → `re.sub(r'<[^>]+>', '', text).strip()`, yield if non-empty

### Step 2 — `scheduler.py`: update 3 call sites

- `invoke()` wrapper (line 47): `return "".join([s async for s in agent._invoke(reason, message, **kwargs)])`
- `_process_loop` (line 87–88): replace with `async for seg in agent._invoke(...): await reply_fns[-1](seg)`
- `_on_session_summarize` (line 97): `async for _ in agent._invoke("session_timeout"): pass`

### Step 3 — `prompt.txt.example`: add `<no-split>` docs

Add one bullet to the 消息格式 section explaining `<no-split>...</no-split>` usage.

## Verification

- Run `python -m pytest tests/` after implementation
- Manual test: send a message that should produce multi-line reply; verify multiple QQ messages are sent
