# Project Overview

AntlerBot is a Python-based QQ bot that uses NapCat/NcatBot to interact with QQ, with LangGraph driving LLM replies.

# Framework Documentation

Core framework docs are in `docs/frameworks/`. Read relevant files before implementing features.

NcatBot is the core framework for interacting with QQ. Docs: `docs/frameworks/NcatBot.md`.

# Plans and Archives

- `docs/plans/` contains detailed design docs for planned features and architecture changes.
- `docs/archives/` contains design docs and summaries for features that were implemented.

# Project Structure

```
main.py                        # entry point: load_dotenv, register handlers, bot.run()
src/
  core/
    agent.py                   # LangGraph workflow, LLM init, shared history, load_prompt(), load_settings(), auto-summarization
    message_handler.py         # NcatBot callbacks, format_message, intercepts private /commands, enqueues to scheduler
    scheduler.py               # centralized queue, priority batching, sole caller of agent; session timeout via APScheduler
    scheduled_tasks.py         # APScheduler jobs, task CRUD tools, startup recovery
    commands.py                # command registry, permission checks, command handlers
config/
  agent/
    prompt.txt.example         # copy to prompt.txt to set system prompt
    settings.yaml              # auto-summarization settings (context_limit_tokens, session_timeout_minutes, etc.)
  permissions.yaml             # 3-tier permissions: developer/admin QQ UID lists (auto-created if missing)
tests/
  test_agent.py
  test_message_handler.py
```

# Current State

Core features implemented:
- Receives QQ group/private messages via NcatBot callbacks
- Formats messages with sender info, enqueues to `scheduler.py` with priority batching (current source first)
- All sources share one conversation history
- LLM initialized via `init_chat_model(LLM_MODEL, model_provider=LLM_PROVIDER)`
- `scheduler.py` centralizes queue, priority, and batching; is the sole caller of `agent._invoke`; manages session timeout via APScheduler (`init_timeout`, `enqueue` reschedules `session_summarize` job)
- `scheduled_tasks.py` manages APScheduler jobs, exposes LangChain tools for task CRUD, handles startup recovery
- Auto-summarization: `agent.py` summarizes history when `input_tokens > context_limit_tokens`; session timeout triggers `summarize_all` then `clear_history()`
- `load_settings()` reads `config/agent/settings.yaml` at routing time (no restart needed for changes)
- `commands.py` handles private-chat `/commands`: permission checks against `config/permissions.yaml` (re-read each call), 8 developer commands, 3 admin commands; command messages bypass scheduler and LLM context entirely

# Configuration

Copy `.env.example` → `.env` and `config/agent/prompt.txt.example` → `config/agent/prompt.txt`.

Key env vars: `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`.

Non-OpenAI providers require their langchain package (e.g. `langchain-anthropic`). A friendly error message guides installation if missing.

# Dependency Management

Uses pip-tools. Direct deps in `requirements.in`, locked deps in `requirements.txt`.

To add a dependency:
1. Add it to `requirements.in`
2. Run: `pip-compile --index-url=https://mirrors.aliyun.com/pypi/simple/ --output-file=requirements.txt requirements.in`
3. Run: `pip install -r requirements.txt`
