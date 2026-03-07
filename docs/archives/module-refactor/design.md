# Module Refactor Design

## Overview

This design refactors AntlerBot's current `src/core/` package into responsibility-oriented modules. The goal is to reduce concentration of unrelated logic in a single package while keeping runtime behavior stable.

This refactor is intentionally scoped as a medium-strength structural change:
- reorganize modules and imports
- keep public behavior stable
- avoid unnecessary architectural rewrites
- use existing configuration files outside `src/`

## Goals

- Split the current `src/core/` package by responsibility
- Make the codebase easier to navigate and extend
- Avoid creating another large catch-all package
- Keep the scheduler as the sole runtime entrypoint for agent invocation
- Preserve current behavior for message flow, commands, scheduled tasks, and session timeout handling
- Keep completion criteria focused on structural clarity and passing tests

## Non-Goals

- No plugin architecture
- No multi-session architecture redesign
- No scheduler model rewrite
- No new config abstraction inside `src/`
- No broad function renaming unrelated to the refactor
- No opportunistic business logic changes

## Target Module Structure

```text
src/
  agent/
    agent.py
    __init__.py
  messaging/
    handlers.py
    parser.py
    media.py
    formatting.py
    __init__.py
  runtime/
    scheduler.py
    scheduled_tasks.py
    contact_cache.py
    __init__.py
  commands/
    handlers.py
    __init__.py
  data/
    face_map.py
```

## Module Responsibilities

### `src/agent/`

`src/agent/agent.py` is the home for generation-related logic migrated from the current core agent module.

Responsibilities:
- prompt loading
- settings loading
- LLM initialization
- LangGraph construction
- tool registration
- shared history state
- summarization and full-session summarization
- invoke entrypoints

This refactor does **not** introduce `history.py`, `config.py`, or `session.py`. Those splits would increase file count without enough architectural payoff for the current scope.

### `src/messaging/`

This package handles message ingestion and normalization.

#### `handlers.py`
Migrated from the current message handler module.

Responsibilities:
- register NcatBot event handlers
- process startup, notice, group, and private events
- route private slash commands
- parse incoming messages and enqueue them into runtime scheduling

It should not own queue logic or agent workflow details.

#### `parser.py`
Migrated from the current message parser module.

Responsibilities:
- parse NcatBot message segments
- build structured LLM-facing text/content representations
- coordinate reply parsing and media parsing entrypoints

#### `media.py`
Migrated from the current media processor module.

Responsibilities:
- media download
- ffmpeg trimming
- transcription
- passthrough/base64 handling

#### `formatting.py`
New helper module extracted from the current message handler module.

Responsibilities:
- message display formatting
- sender name formatting helpers

This extraction keeps event handlers focused on integration logic instead of presentation-oriented helpers.

### `src/runtime/`

This package owns runtime orchestration and stateful coordination.

#### `scheduler.py`
Migrated from the current scheduler module.

Responsibilities:
- priority queue management
- batching
- current source tracking
- media follow-up enqueue flow
- session timeout scheduling
- the sole runtime path that invokes the agent main flow

`scheduler.py` belongs in `runtime`, not `agent`, because it orchestrates execution rather than implementing generation logic.

#### `scheduled_tasks.py`
Migrated from the current scheduled tasks module.

Responsibilities:
- APScheduler task management
- persisted task CRUD tools
- startup recovery
- scheduled execution workflows

#### `contact_cache.py`
Migrated from the current contact cache module.

Responsibilities:
- friend/group/contact display cache
- cache refresh and lookup

`contact_cache.py` is placed in `runtime` because it is shared runtime state used by message handling and operational flows.

### `src/commands/`

#### `handlers.py`
Migrated from the current commands module.

Responsibilities:
- command registry
- permission checks
- command dispatch

If command complexity grows later, it can be split further. That is outside the scope of this refactor.

### `main.py`

`main.py` remains the single startup entrypoint.

Responsibilities:
- startup wiring
- module registration
- bot/scheduler/tool initialization
- application start

This design does **not** introduce `bootstrap.py`. For the current codebase, that would add an extra layer with limited benefit.

## Dependency Rules

The refactor should preserve a clear dependency direction:

- `main.py` is the assembly point
- `messaging` may depend on `runtime`, `commands`, and `agent`
- `runtime` may depend on `agent`
- `commands` should avoid depending on `messaging`
- `agent` should not depend on `messaging` or `commands`

Additional constraints:
- `contact_cache` is used by `messaging`, but does not know about event handlers
- `scheduler` remains the only runtime component that directly drives the agent main flow
- module connections should be solved at the composition layer rather than by introducing bidirectional imports
- the refactor must not recreate a new cross-cutting “mega module” in another package

## Migration Strategy

The migration should prioritize stable mechanics over aggressive redesign.

Principles:
- move files first
- update imports second
- make only the minimum necessary interface adjustments
- preserve existing function signatures where practical
- only perform targeted boundary cleanup when migration reveals obvious coupling issues

Recommended sequence:
1. create target packages and files
2. move `src/core/` modules into their new locations
3. update internal imports across the project
4. extract formatting helpers from `messaging.handlers` into `messaging.formatting`
5. repair tests and module references
6. run tests and fix only refactor-relevant failures
7. remove old `src/core/` remnants after the new structure is stable

## Decisions on Proposed Modules

### Why no `bootstrap.py`?

A dedicated bootstrap module is not necessary in this refactor. `main.py` already acts as the natural startup composition point. Adding `bootstrap.py` now would mostly add indirection without solving a real complexity problem.

### Why no `session.py`?

Session-related logic exists, but it is currently too thin and too coupled to existing scheduler and agent behavior to justify a separate module. Session timeout scheduling should remain in runtime scheduling logic, while history summarization stays in the agent flow.

### Why is `scheduler.py` in `runtime` instead of `agent`?

Because the scheduler is responsible for runtime orchestration:
- queueing
- batching
- timeout scheduling
- follow-up processing
- controlling when the agent is invoked

That makes it runtime coordination, not generation logic.

### Why no `history.py`?

History exists as a clear concern, but it is still tightly coupled with summarization and LangGraph execution flow. Splitting it into a new module during this refactor would add file boundaries without enough benefit for the current completion criteria.

## Testing and Acceptance Criteria

This refactor is complete when all of the following are true:

- the new module structure is in place
- project imports are updated to the new paths
- the code no longer relies on the old `src/core/` layout for execution
- message flow behavior remains stable
- slash command behavior remains stable
- scheduled task behavior remains stable
- contact cache behavior remains stable
- tests pass after refactor-related updates

Primary tests to update and run:
- `tests/test_agent.py`
- `tests/test_message_handler.py`
- `tests/test_message_parser.py`
- `tests/test_media_processor.py`
- `tests/test_scheduler.py`
- `tests/test_scheduler_media.py`
- `tests/test_scheduled_tasks.py`
- `tests/test_commands.py`
- `tests/test_contact_cache.py`

Verification should cover three levels:
