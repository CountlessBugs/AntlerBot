# Message Splitting Design

## Overview

Split LLM replies into multiple QQ messages on newlines using streaming output. A `<no-split>` tag lets the LLM send multi-line content as a single message. All XML tags are stripped from output.

## Behavior

- Each `\n` outside `<no-split>` triggers a new message
- `<no-split>content</no-split>` is sent as one atomic message; tags are stripped
- All XML tags (`<...>`) are stripped from every segment before sending
- Empty/whitespace-only segments (after stripping) are discarded

## Implementation

### `agent._invoke` → async generator

Change `_invoke` from returning `str` to an async generator yielding `str` segments.

Uses `graph.astream_events(version="v2")`, filtering `on_chat_model_stream` events where `metadata["langgraph_node"] == "llm"`.

**Split algorithm** (stateful per invocation):
- State: `buffer: str`, `in_no_split: bool`
- On each token chunk: append to buffer, then loop:
  - If not in no-split:
    - Find earliest `\n` or `<no-split>` in buffer
    - `\n` first → emit segment before it, advance past `\n`
    - `<no-split>` first → emit each line before it, set `in_no_split = True`, advance past tag
    - Neither → break (wait for more tokens)
  - If in no-split:
    - Find `</no-split>` → emit content, set `in_no_split = False`, advance past tag
    - Not found → break
- On stream end: flush remaining buffer (split by `\n` if not in no-split, else emit whole)
- Before emitting: `re.sub(r'<[^>]+>', '', segment).strip()`, discard if empty

### `scheduler.py` call site changes

| Location | Before | After |
|----------|--------|-------|
| `_process_loop` | `response = await _invoke(...)` then `reply_fn(response)` | `async for seg in _invoke(...): reply_fn(seg)` |
| `_on_session_summarize` | `await _invoke("session_timeout")` | `async for _ in _invoke("session_timeout"): pass` |
| `invoke()` wrapper | `return await _invoke(...)` | `return "".join([s async for s in _invoke(...)])` |

### `prompt.txt.example`

Add to the message format section: explain that `<no-split>...</no-split>` wraps content that should be sent as a single message with newlines preserved; tags are removed automatically.

## Files Changed

- `src/core/agent.py`: `_invoke` → async generator with streaming + split logic
- `src/core/scheduler.py`: update 3 call sites
- `config/agent/prompt.txt.example`: add `<no-split>` usage docs
