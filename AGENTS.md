# Project Overview

AntlerBot is a Python-based QQ bot that uses NapCat/NcatBot to interact with QQ, with LangGraph driving LLM replies.

# Coding Standards

- LLM system prompts and tool descriptions must be written in Chinese.

# Framework Documentation

Core framework docs are in `docs/frameworks/`. Read relevant files before implementing features.

NcatBot is the core framework for interacting with QQ. Docs: `docs/frameworks/NcatBot.md`.

Mem0 is the core framework for long-term memory system. Docs: `docs/frameworks/Mem0.md`. This project uses the local `mem0.Memory` implementation only, not `MemoryClient`.

# Plans and Archives

- `docs/plans/` contains detailed design docs for planned features and architecture changes.
- `docs/archives/` contains design docs and summaries for features that were implemented.

# Project Structure

```
main.py                        # entry point: load_dotenv, set NCATBOT_CONFIG_PATH, register handlers, bot.run()
src/
  agent/
    agent.py                   # LangGraph workflow, LLM init, shared history, load_prompt(), load_settings(), auto-summarization
  messaging/
    handlers.py                # NcatBot callbacks, intercepts private /commands, parses messages, formats sender info, enqueues to scheduler
    formatting.py              # format_message(), get_sender_name()
    parser.py                  # structured message parsing: Text/At/Face/Reply/media segments → XML tags
    media.py                   # media download, ffmpeg trim, LLM transcription, base64 passthrough
  runtime/
    scheduler.py               # centralized queue, priority batching, sole caller of agent; session timeout via APScheduler
    scheduled_tasks.py         # APScheduler jobs, task CRUD tools, startup recovery
    contact_cache.py           # QQ contact info cache
  commands/
    handlers.py                # command registry, permission checks, command handlers
  data/
    face_map.py                # QQ face emoji ID → name mapping
config/
  agent/
    prompt.txt.example         # copy to prompt.txt to set system prompt
    settings.yaml              # runtime settings (context limits, timeouts, media processing, etc.)
  ncatbot.yaml                 # NcatBot runtime configuration
  permissions.yaml             # 3-tier permissions: developer/admin QQ UID lists (auto-created if missing)
  tasks.json                   # persisted scheduled task definitions
docs/
  frameworks/
    NcatBot.md
    Mem0.md                    # Mem0 long-term memory framework documentation
tests/
  test_agent.py
  test_message_handler.py
  test_message_parser.py
  test_media_processor.py
  test_scheduler.py
  test_scheduler_media.py
  test_scheduled_tasks.py
  test_commands.py
  test_contact_cache.py
```

# Current State

Core features implemented:
- Receives QQ group/private messages via `src/messaging/handlers.py` NcatBot callbacks
- Formats sender/group context in `src/messaging/formatting.py`, parses message segments in `src/messaging/parser.py`, and enqueues work to `src/runtime/scheduler.py` with priority batching (current source first)
- All sources share one conversation history managed by `src/agent/agent.py`
- `src/messaging/parser.py` parses QQ MessageArray segments (Text, At, Face, Reply, media) into LLM-readable XML tags; Reply parsing is async (requires API call)
- `src/messaging/media.py` handles media download, ffmpeg trim, base64 passthrough (≤ threshold) and LLM transcription (> threshold); supports separate transcription model via `TRANSCRIPTION_*` env vars
- `src/runtime/scheduler.py` centralizes queue, priority, and batching; is the sole caller of `agent._invoke`; manages session timeout via APScheduler (`init_timeout`, `enqueue` reschedules `session_summarize` job); builds multimodal content lists from parsed messages
- `src/runtime/scheduled_tasks.py` manages APScheduler jobs, exposes LangChain tools for task CRUD, handles startup recovery
- Auto-summarization: `src/agent/agent.py` summarizes history when `input_tokens > context_limit_tokens`; session timeout triggers `summarize_all` then `clear_history()`
- `src/commands/handlers.py` handles private-chat `/commands`: permission checks against `config/permissions.yaml` (re-read each call), 8 developer commands, 3 admin commands; command messages bypass scheduler and LLM context entirely

# Adding Configuration Items

When adding new configuration items to `settings.yaml`, update all three locations:
1. `config/agent/settings.yaml` - add the config item with appropriate value
2. `config/agent/settings.yaml.example` - add the config item with default value and comment
3. `README.md` - add documentation in the settings table (around line 60)
4. `src/agent/agent.py` - add default value to `_SETTINGS_DEFAULTS` dict

# Dependency Management

Uses pip-tools. Direct deps in `requirements.in`, locked deps in `requirements.txt`.

To add a dependency:
1. Add it to `requirements.in`
2. Run: `pip-compile --index-url=https://mirrors.aliyun.com/pypi/simple/ --output-file=requirements.txt requirements.in`
3. Run: `pip install -r requirements.txt`
