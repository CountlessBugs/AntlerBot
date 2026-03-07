# Module Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the current `src/core/` package into responsibility-oriented modules while preserving runtime behavior and passing tests.

**Architecture:** Move generation logic into `src/agent/`, message ingress and normalization into `src/messaging/`, runtime coordination into `src/runtime/`, and private command handling into `src/commands/`. Keep `main.py` as the single composition entrypoint, keep `scheduler.py` as the sole runtime caller of the agent flow, and avoid introducing new abstraction-only modules.

**Tech Stack:** Python, pytest, NcatBot, LangGraph, LangChain, APScheduler

---

### Task 1: Create the new package skeleton

**Files:**
- Create: `src/agent/__init__.py`
- Create: `src/messaging/__init__.py`
- Create: `src/runtime/__init__.py`
- Create: `src/commands/__init__.py`
- Test: `tests/test_agent.py`

**Step 1: Write the failing test**

Add a small import smoke test near the top of `tests/test_agent.py`:

```python
def test_new_agent_package_importable():
    import src.agent.agent as agent_mod
    assert agent_mod is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent.py::test_new_agent_package_importable -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agent'`

**Step 3: Write minimal implementation**

Create the four package directories with empty `__init__.py` files:

```python
# src/agent/__init__.py
# src/messaging/__init__.py
# src/runtime/__init__.py
# src/commands/__init__.py
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent.py::test_new_agent_package_importable -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent/__init__.py src/messaging/__init__.py src/runtime/__init__.py src/commands/__init__.py tests/test_agent.py
git commit -m "refactor: add package skeleton for module split"
```

### Task 2: Migrate the agent and runtime modules

**Files:**
- Create: `src/agent/agent.py`
- Create: `src/runtime/scheduler.py`
- Create: `src/runtime/scheduled_tasks.py`
- Create: `src/runtime/contact_cache.py`
- Modify: `src/core/agent.py`
- Modify: `src/core/scheduler.py`
- Modify: `src/core/scheduled_tasks.py`
- Modify: `src/core/contact_cache.py`
- Test: `tests/test_agent.py`
- Test: `tests/test_scheduler.py`
- Test: `tests/test_scheduler_media.py`
- Test: `tests/test_scheduled_tasks.py`
- Test: `tests/test_contact_cache.py`

**Step 1: Write the failing tests**

Update the runtime-facing test imports first so they target the new package paths:

```python
# tests/test_scheduler.py
import src.runtime.scheduler as scheduler

# tests/test_scheduler_media.py
from src.messaging.parser import ParsedMessage, MediaTask
import src.runtime.scheduler as scheduler

# tests/test_scheduled_tasks.py
import src.runtime.scheduled_tasks as st

# tests/test_contact_cache.py
import src.runtime.contact_cache as contact_cache

# tests/test_agent.py
import src.agent.agent as agent_mod
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_agent.py tests/test_scheduler.py tests/test_scheduler_media.py tests/test_scheduled_tasks.py tests/test_contact_cache.py -v`
Expected: FAIL with missing module errors for `src.agent.agent` and `src.runtime.*`

**Step 3: Write minimal implementation**

Copy the current core modules into their new locations and update imports to the new dependency graph:

```python
# src/runtime/scheduler.py
from src.agent import agent
from src.messaging.parser import MediaTask, ParsedMessage
from src.messaging.media import _MEDIA_TAG

# src/runtime/scheduled_tasks.py
from src.agent import agent
from src.runtime import scheduler

# src/agent/agent.py
# copy current src/core/agent.py contents first, then keep public names stable
```

Keep function names and behavior unchanged during the move. Do not extract `history.py`, `config.py`, `bootstrap.py`, or `session.py`.

**Step 4: Add temporary compatibility re-exports**

Replace the old core modules with thin forwarding shims so the codebase can migrate incrementally:

```python
# src/core/agent.py
from src.agent.agent import *

# src/core/scheduler.py
from src.runtime.scheduler import *

# src/core/scheduled_tasks.py
from src.runtime.scheduled_tasks import *

# src/core/contact_cache.py
from src.runtime.contact_cache import *
```

This keeps the project runnable while later tasks update all imports.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_agent.py tests/test_scheduler.py tests/test_scheduler_media.py tests/test_scheduled_tasks.py tests/test_contact_cache.py -v`
Expected: PASS, or only remaining failures caused by still-unmigrated messaging/command imports

**Step 6: Commit**

```bash
git add src/agent/agent.py src/runtime/scheduler.py src/runtime/scheduled_tasks.py src/runtime/contact_cache.py src/core/agent.py src/core/scheduler.py src/core/scheduled_tasks.py src/core/contact_cache.py tests/test_agent.py tests/test_scheduler.py tests/test_scheduler_media.py tests/test_scheduled_tasks.py tests/test_contact_cache.py
git commit -m "refactor: move agent and runtime modules"
```

### Task 3: Migrate the messaging modules and extract formatting helpers

**Files:**
- Create: `src/messaging/handlers.py`
- Create: `src/messaging/parser.py`
- Create: `src/messaging/media.py`
- Create: `src/messaging/formatting.py`
- Modify: `src/core/message_handler.py`
- Modify: `src/core/message_parser.py`
- Modify: `src/core/media_processor.py`
- Test: `tests/test_message_handler.py`
- Test: `tests/test_message_parser.py`
- Test: `tests/test_media_processor.py`

**Step 1: Write the failing tests**

Update the messaging-related test imports to point at their target homes:

```python
# tests/test_message_handler.py
import src.messaging.handlers as mh
import src.runtime.contact_cache as contact_cache
from src.messaging.formatting import format_message
from src.messaging.parser import ParsedMessage, MediaTask

# tests/test_message_parser.py
import src.runtime.contact_cache as contact_cache
from src.messaging.parser import parse_message, ParsedMessage, MediaTask

# tests/test_media_processor.py
from src.messaging.media import ...
import src.messaging.media as mp
```

Add one focused formatting smoke test if needed:

```python
def test_format_message_import_from_formatting_module():
    from src.messaging.formatting import format_message
    assert format_message("hello", "Alice") == "<sender>Alice</sender>hello"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_message_handler.py tests/test_message_parser.py tests/test_media_processor.py -v`
Expected: FAIL with missing module errors for `src.messaging.*`

**Step 3: Write minimal implementation**

Copy the current modules into the new package and extract formatting helpers out of handlers:

```python
# src/messaging/formatting.py
def format_message(content: str, nickname: str, group_name: str | None = None) -> str:
    if group_name:
        return f"<sender>{nickname} [群聊-{group_name}]</sender>{content}"
    return f"<sender>{nickname}</sender>{content}"


async def get_sender_name(user_id: str, nickname: str, card: str = "") -> str:
    ...
```

Update `src/messaging/handlers.py` imports so it uses:

```python
from src.runtime import scheduler, contact_cache
from src.commands import handlers as commands
from src.messaging import parser as message_parser
from src.agent.agent import load_settings
from src.messaging.formatting import format_message, get_sender_name
```

Also move parser/media imports to `src.messaging.parser` and `src.messaging.media`.

**Step 4: Add temporary compatibility re-exports**

```python
# src/core/message_handler.py
from src.messaging.handlers import *

# src/core/message_parser.py
from src.messaging.parser import *

# src/core/media_processor.py
from src.messaging.media import *
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_message_handler.py tests/test_message_parser.py tests/test_media_processor.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/messaging/handlers.py src/messaging/parser.py src/messaging/media.py src/messaging/formatting.py src/core/message_handler.py src/core/message_parser.py src/core/media_processor.py tests/test_message_handler.py tests/test_message_parser.py tests/test_media_processor.py
git commit -m "refactor: move messaging modules and extract formatting"
```

### Task 4: Migrate command handling and rewire the application entrypoint

**Files:**
- Create: `src/commands/handlers.py`
- Modify: `src/core/commands.py`
- Modify: `main.py`
- Test: `tests/test_commands.py`
- Test: `tests/test_message_handler.py`

**Step 1: Write the failing tests**

Update command test imports and patch targets:

```python
# tests/test_commands.py
import src.commands.handlers as commands

# patch targets
patch("src.commands.handlers.agent")
patch("src.commands.handlers.scheduler")
patch("src.commands.handlers.scheduled_tasks")
```

Update `tests/test_message_handler.py` patch targets as well:

```python
patch("src.messaging.handlers.scheduler")
patch("src.messaging.handlers.contact_cache")
patch("src.messaging.handlers.load_settings", return_value={})
patch("src.messaging.handlers.message_parser")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_commands.py tests/test_message_handler.py -v`
Expected: FAIL with missing module or patch target errors for `src.commands.handlers`

**Step 3: Write minimal implementation**

Copy `src/core/commands.py` into `src/commands/handlers.py` and update imports:

```python
from src.agent import agent
from src.runtime import scheduler, scheduled_tasks, contact_cache
from src.messaging import media
```

Then update `main.py` to assemble the new modules directly:

```python
from ncatbot.core import BotClient
from src.messaging import handlers as message_handlers
from src.runtime import scheduled_tasks

bot = BotClient()
message_handlers.register(bot)

@bot.on_startup()
async def on_startup(event):
    await scheduled_tasks.register(bot)
```

Keep behavior identical: `main.py` stays the only startup/composition entrypoint.

**Step 4: Add temporary compatibility re-export**

```python
# src/core/commands.py
from src.commands.handlers import *
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_commands.py tests/test_message_handler.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/commands/handlers.py src/core/commands.py main.py tests/test_commands.py tests/test_message_handler.py
git commit -m "refactor: move commands module and rewire entrypoint"
```

### Task 5: Remove project-internal `src.core` imports and delete compatibility shims

**Files:**
- Modify: `main.py`
- Modify: `src/agent/agent.py`
- Modify: `src/messaging/handlers.py`
- Modify: `src/messaging/parser.py`
- Modify: `src/messaging/media.py`
- Modify: `src/runtime/scheduler.py`
- Modify: `src/runtime/scheduled_tasks.py`
- Modify: `src/commands/handlers.py`
- Delete: `src/core/agent.py`
- Delete: `src/core/message_handler.py`
- Delete: `src/core/message_parser.py`
- Delete: `src/core/media_processor.py`
- Delete: `src/core/scheduler.py`
- Delete: `src/core/scheduled_tasks.py`
- Delete: `src/core/commands.py`
- Delete: `src/core/contact_cache.py`
- Modify: `src/core/__init__.py`

**Step 1: Write the failing test**

Add one structural test, for example in `tests/test_agent.py` or a new `tests/test_structure.py`:

```python
from pathlib import Path


def test_core_runtime_modules_removed():
    assert not Path("src/core/agent.py").exists()
    assert not Path("src/core/scheduler.py").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent.py::test_core_runtime_modules_removed -v`
Expected: FAIL because the shim files still exist

**Step 3: Write minimal implementation**

Update every remaining project import away from `src.core.*` to its final home, then delete the shim modules.

Target import pattern:

```python
from src.agent import agent
from src.messaging import handlers, parser, media, formatting
from src.runtime import scheduler, scheduled_tasks, contact_cache
from src.commands import handlers as commands
```

If `src/core/__init__.py` becomes unnecessary after deletion, either delete it or leave it empty with no public exports.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent.py::test_core_runtime_modules_removed -v`
Expected: PASS

**Step 5: Commit**

```bash
git add main.py src tests
git commit -m "refactor: remove legacy core module paths"
```

### Task 6: Run the full verification pass and make only refactor-scoped fixes

**Files:**
- Test: `tests/test_agent.py`
- Test: `tests/test_message_handler.py`
- Test: `tests/test_message_parser.py`
- Test: `tests/test_media_processor.py`
- Test: `tests/test_scheduler.py`
- Test: `tests/test_scheduler_media.py`
- Test: `tests/test_scheduled_tasks.py`
- Test: `tests/test_commands.py`
- Test: `tests/test_contact_cache.py`
- Modify: any files directly required to fix refactor-caused failures

**Step 1: Run the focused suite**

Run:

```bash
pytest tests/test_agent.py tests/test_message_handler.py tests/test_message_parser.py tests/test_media_processor.py tests/test_scheduler.py tests/test_scheduler_media.py tests/test_scheduled_tasks.py tests/test_commands.py tests/test_contact_cache.py -v
```

Expected: PASS

**Step 2: If failures occur, fix only refactor-related breakage**

Allowed fixes:
- import path corrections
- patch target updates
- logger name expectation updates
- direct references to moved modules

Avoid unrelated cleanup, renaming, or behavior changes.

**Step 3: Run the full test suite**

Run: `pytest -v`
Expected: PASS

**Step 4: Run a minimal startup verification**

Run: `python main.py`
Expected: startup completes far enough to load modules and register handlers without import errors. If local bot runtime cannot fully connect in the environment, at minimum confirm there is no immediate traceback from the refactor.

**Step 5: Commit**

```bash
git add main.py src tests
git commit -m "refactor: finalize responsibility-based module split"
```

## Notes for Execution

- Keep function signatures stable unless a signature change is required to complete the move.
- Do not introduce `bootstrap.py`, `session.py`, `history.py`, or `config.py`.
- Keep `contact_cache.py` under `src/runtime/`.
- Keep `scheduler.py` as the only runtime path that drives the main agent invocation flow.
- Prefer small commits exactly at the task boundaries above.
- If a circular import appears, fix it by narrowing imports or moving helper imports inside functions, not by inventing a new abstraction layer.
