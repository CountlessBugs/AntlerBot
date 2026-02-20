# Project Overview

AntlerBot is a Python-based QQ bot that uses NapCat/NcatBot to interact with QQ, with LangGraph driving LLM replies.

# Framework Documentation

Core framework docs are in `docs/frameworks/`. Read relevant files before implementing features.

NcatBot is the core framework for interacting with QQ. Docs: `docs/frameworks/NcatBot.md`.

# Project Structure

```
main.py                        # entry point: load_dotenv, register handlers, bot.run()
src/
  core/
    agent.py                   # LangGraph workflow, LLM init, shared history, load_prompt()
    message_handler.py         # NcatBot callbacks, format_message, queue, priority batching
config/
  agent/
    prompt.txt.example         # copy to prompt.txt to set system prompt
tests/
  test_agent.py
  test_message_handler.py
```

# Current State

Core LLM reply feature is implemented:
- Receives QQ group/private messages via NcatBot callbacks
- Formats messages with sender info, queues with priority batching (current source first)
- All sources share one conversation history
- LLM initialized via `init_chat_model(LLM_MODEL, model_provider=LLM_PROVIDER)`

# Configuration

Copy `.env.example` → `.env` and `config/agent/prompt.txt.example` → `config/agent/prompt.txt`.

Key env vars: `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`.

Non-OpenAI providers require their langchain package (e.g. `langchain-anthropic`). A friendly error message guides installation if missing.

# Future Architecture Plans

See `docs/plans/scheduler-architecture.md` for the planned refactoring to introduce a `scheduler.py` module that centralizes queue, priority, and batching logic across all task sources (user messages, scheduled tasks, auto-initiated conversations).

# Dependency Management

Uses pip-tools. Direct deps in `requirements.in`, locked deps in `requirements.txt`.

To add a dependency:
1. Add it to `requirements.in`
2. Run: `pip-compile --index-url=https://mirrors.aliyun.com/pypi/simple/ --output-file=requirements.txt requirements.in`
3. Run: `pip install -r requirements.txt`
