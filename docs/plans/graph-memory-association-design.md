# Graph Memory Association Design

## Overview

This document defines the next evolution of AntlerBot's long-term memory system: enable Mem0 native graph memory on top of the existing vector-based long-term memory so that both automatic recall and manual recall gain relationship-based associative recall. The goal is not to build a general-purpose knowledge graph QA system, but to make the bot's long-term memory behave more like human associative recall: first retrieve the core memory, then follow related people, events, projects, and preferences to recall adjacent context.

This design keeps the core boundaries of the current long-term memory system:
- Continue using local OSS Mem0, not the hosted platform.
- Continue using summaries as the only long-term memory write input.
- Continue using the existing automatic recall path and the existing `recall_memory` tool.
- Do not add any new memory tool names.
- Treat graph capability as an enhancement layer that can fall back to the current vector-only mode on failure.

## Background and Current State

The current long-term memory system already provides:
- Asynchronous Mem0 writes after summarization.
- Automatic recall before user-message reply generation.
- Manual long-term recall through the `recall_memory` tool.
- Temporary automatic recall injection that does not persist into `_history`.

Relevant code locations:
- Automatic recall and manual recall are implemented in `src/agent/memory.py`.
- Agent orchestration is implemented in `src/agent/agent.py`.

The current implementation only uses Mem0's vector memory capability. The previous project design explicitly left graph-based recall out of version 1, while also keeping space for future graph-memory expansion. This design builds on the existing Mem0-based architecture instead of replacing it.

## Goals

- Add relationship-based associative recall to long-term memory without changing the existing tool interface.
- Keep Mem0 responsible for long-term memory extraction, update, search, and graph relationship storage.
- Let both automatic recall and `recall_memory` consume Mem0's `results + relations` output.
- Keep the long-term memory main path stable and automatically degrade to vector-only memory when graph capability fails.
- Preserve room for future emotional modeling, relationship strength, temporal decay, and multi-hop association.

## Non-Goals

This version explicitly does not include:
- Building a graph database abstraction layer outside Mem0.
- Implementing custom entity extraction, relation extraction, or graph writes in project code.
- Adding a new graph-specific recall tool.
- Switching from summary-only writes to per-message graph writes.
- Implementing multi-hop reasoning or relationship-weight ranking.
- Building graph-write compensation queues or vector/graph consistency machinery.

## Core Decisions

### 1. Use Mem0 native graph memory

The project will continue integrating only with Mem0. Graph database adaptation, relation extraction, and graph-store writes remain Mem0's responsibility. The project layer only:
- reads configuration,
- builds `MemoryConfig`,
- calls `Memory.add(...)` and `Memory.search(...)`,
- formats Mem0 `results` and `relations` into model-facing text.

### 2. Recommend Neo4j as the default graph store

Neo4j is the recommended default graph store for this project because:
- it matches the Mem0 graph memory examples,
- it is easier to inspect and debug entities, relationships, and recall paths,
- it has mature query, visualization, and troubleshooting tooling,
- it is a strong long-term fit for human-like associative memory behavior.

However, the project does not hardcode Neo4j-only support. The graph backend is passed through via `memory.graph.provider` and `memory.graph.config`, and the project does not implement provider-specific branches.

### 3. Use one unified enhancement strategy

Both automatic recall and `recall_memory` keep their current entry points, but their internal flow is upgraded to:
1. call Mem0 search,
2. read `results`,
3. if graph memory is enabled and Mem0 returns `relations`, read those relations,
4. trim `results` and `relations` separately,
5. format them into one model-facing Chinese memory block.

This keeps the two recall paths aligned and avoids long-term divergence between automatic and manual recall.

## Architecture Design

### Storage architecture

Long-term memory still has only one backend entry point: Mem0. When graph memory is enabled, a single write allows Mem0 to perform:
- text memory extraction and update,
- graph entity and relation extraction,
- graph database persistence.

The project layer does not create a second graph-store client and does not manage graph lifecycle independently.

### Retrieval architecture

The retrieval path for both automatic recall and `recall_memory` becomes:
- vector memory remains the retrieval foundation,
- graph relations provide associative enhancement,
- the final content returned to the model remains text, not raw graph JSON.

### Module boundaries

Most changes remain concentrated in `src/agent/memory.py`:
- extend Mem0 initialization to optionally include `graph_store`,
- add graph configuration parsing and fallback logic,
- add relation formatting and trimming logic,
- upgrade automatic and manual recall to consume `results + relations`.

`src/agent/agent.py` remains the orchestration layer and continues to own:
- `_history` management,
- summarization triggers,
- automatic recall injection timing,
- async summary-storage scheduling.

## Configuration Design

This version uses nested `memory.graph.*` configuration so it aligns with Mem0's `graph_store = { provider, config }` structure.

Suggested configuration shape:

```yaml
memory:
  enabled: false
  agent_id: antlerbot
  auto_recall_enabled: true
  auto_store_enabled: true
  auto_recall_query_token_limit: 400
  auto_recall_score_threshold: 0.75
  auto_recall_max_memories: 5
  auto_recall_system_prefix: "以下是可能与当前对话相关的长期记忆。仅在相关时使用，不要机械复述。"
  recall_low_score_threshold: 0.85
  recall_low_max_memories: 3
  recall_medium_score_threshold: 0.70
  recall_medium_max_memories: 6
  recall_high_score_threshold: 0.55
  recall_high_max_memories: 10
  reset_seen_on_summary: true

  graph:
    enabled: false
    provider: neo4j
    config:
      url: bolt://localhost:7687
      username: neo4j
      password: password
      database: neo4j
    auto_recall_enabled: true
    manual_recall_enabled: true
    context_max_relations: 8
    max_hops: 1
    context_prefix: "以下是与当前长期记忆相关的关系联想。仅在相关时使用，不要机械复述。"
```

### Configuration semantics

- `memory.graph.enabled`: graph-memory master switch. When false, the system fully falls back to the current vector-only mode.
- `memory.graph.provider`: graph-store provider passed through to Mem0. The project does not special-case providers.
- `memory.graph.config`: provider-specific graph configuration passed through to Mem0.
- `memory.graph.auto_recall_enabled`: whether automatic recall should include relation-based enhancement.
- `memory.graph.manual_recall_enabled`: whether `recall_memory` should include relation-based enhancement.
- `memory.graph.context_max_relations`: maximum number of relation entries included in model-facing context for a single recall.
- `memory.graph.max_hops`: this version should only support `1`.
- `memory.graph.context_prefix`: prefix for the relation-association text block.

### Backward compatibility and migration semantics

Existing deployments that only have legacy `memory.*` settings and no `memory.graph` block must keep the current behavior unchanged.

Required migration semantics:
- If the `memory.graph` block is absent, treat graph memory as disabled by default.
- The absence of `memory.graph` must not change current vector-memory retrieval or write behavior.
- Users should be able to opt into graph memory incrementally by adding only a partial `memory.graph` block without having to redefine every graph setting.
- Graph capability must remain an additive enhancement, not a required part of existing Mem0 usage.

### Required settings merge behavior

The current settings-loading architecture already deep-merges `memory` one level, but this feature adds a nested `memory.graph` structure. The implementation must therefore deep-merge `memory.graph` defaults with user overrides instead of replacing the whole nested object when only one graph field is set.

Required merge behavior:
- `_SETTINGS_DEFAULTS["memory"]` must include a nested `graph` default object.
- `load_settings()` must deep-merge `memory.graph` so partial user configuration only overrides specified graph keys.
- A config file containing only `memory.graph.enabled: true` must preserve the default values of the other graph settings.
- This behavior must be covered by tests because shallow replacement would silently clobber nested defaults.

## Retrieval Behavior Design

### Automatic recall

Automatic recall keeps the current timing and temporary-context semantics, but its internal flow becomes:
1. build the query,
2. call Mem0 `search(...)`,
3. read `results`,
4. if graph memory is enabled and configured for auto recall, read `relations`,
5. filter `results` using the current logic,
6. trim `relations` using `context_max_relations`,
7. build one temporary `SystemMessage`,
8. inject it into the prompt without persisting it into `_history`.

Suggested injected format:

```text
以下是可能与当前对话相关的长期记忆。仅在相关时使用，不要机械复述。

记忆：
- ...
- ...

联想关系：
- ...
- ...
```

If there are no `relations`, only the `记忆` section is included.

### Manual recall: `recall_memory`

The tool name, inputs, and invocation stay unchanged:
- `query`
- `effort`

Its internal flow becomes:
1. call Mem0 search using the effort-specific settings,
2. filter `results`,
3. if graph memory is enabled and `manual_recall_enabled` is true, read and trim `relations`,
4. return one Chinese text block containing both memory items and associative relations.

Suggested returned format:

```text
已按中等努力程度检索到以下长期记忆：

记忆：
- ...
- ...

联想关系：
- ...
- ...
```

### Trimming rules

`results` and `relations` are controlled separately:
- `results` continue using the current thresholds, max-memory limits, session deduplication, and context-lock behavior.
- `relations` are enhancement-only and are limited separately by `context_max_relations`.
- This version only supports `max_hops = 1` and does not attempt multi-hop expansion.

The core principle is: first ensure the memory items themselves are relevant, then add a small amount of associative relation context.

## Write-Side Behavior Design

### Write trigger timing

No change:
- write on context-limit summarization,
- write on session-timeout summarization,
- execute via background async task without blocking the main path.

### Write input

No change: only summary text is sent to Mem0:

```python
store.add(
    [{"role": "user", "content": summary_text}],
    agent_id=settings.get("memory", {}).get("agent_id", "antlerbot"),
)
```

The difference is:
- when `memory.graph.enabled = false`, Mem0 behaves like the current vector-only long-term memory system,
- when `memory.graph.enabled = true`, the same `add(...)` call lets Mem0 extract both text memories and graph relationships and persist them into the graph store.

The project does not implement custom entity extraction, relation extraction, or graph writes.

### Initialization logic

`get_memory_store(settings)` currently builds only `llm` and `embedder`. After this change it should:
- always build `llm`,
- always build `embedder`,
- build `graph_store` only when `memory.graph.enabled` is true.

This should follow the Mem0 graph-memory configuration shape directly.

## Fallback and Error Handling

### Initialization stage

If graph configuration is invalid, graph-store connection fails, or Mem0 graph initialization fails:
- log a warning or exception,
- fall back to Mem0 without `graph_store`,
- keep text long-term memory available.

### Retrieval stage

- If the whole `search(...)` call fails: skip recall injection for that turn and continue normal reply generation.
- If only relation parsing or formatting fails: keep `results` and drop only the relation section.

### Write stage

- If `add(...)` fails: log a warning and skip that long-term-memory write.
- Do not affect the user-visible conversation flow.
- Do not add a graph-write compensation queue in this version.

## Logging Strategy

Add graph-memory-related logs, but only record structural information:
- whether graph memory is enabled,
- provider name,
- initialization success or fallback,
- per-recall counts for `results`, raw `relations`, and trimmed `relations`,
- whether graph memory was enabled during summary storage and whether `add(...)` succeeded.

Do not log:
- plaintext passwords,
- full provider-specific config payloads,
- large raw relation content blocks.

## Validation Strategy

### 1. Configuration and fallback tests

Verify:
- behavior remains unchanged when `memory.graph.enabled = false`,
- graph config maps correctly into `MemoryConfig(graph_store=...)`,
- graph initialization failure falls back to vector-only mode.

### 2. Retrieval-format tests

Verify:
- output remains compatible when only `results` exist,
- a `联想关系` section appears when `relations` exist,
- `context_max_relations` is enforced,
- malformed `relations` drop only the relation section, not the memory section,
- `recall_memory` keeps the same tool name and inputs.

### 3. Association-quality sample validation

Use stable examples to validate human-like association. For example, if long-term memory already contains:
- the user is building AntlerBot's long-term memory system,
- the user wants the bot to be more like a real person with thought, emotion, and memory,
- the current focus is graph-memory association,

then when the user asks "what directions can this project expand into next", the ideal result should not only retrieve the directly similar memory but also surface related ideas such as long-term memory evolution, human-like behavior goals, and associative-memory expansion.

## Recommended Implementation Scope

This implementation should focus on:
1. upgrade configuration structure to `memory.graph.*`,
2. let `get_memory_store(settings)` optionally include `graph_store`,
3. let automatic recall consume and format `relations`,
4. let `recall_memory` consume and format `relations`,
5. add graph-initialization fallback behavior and tests,
6. update all repository-required configuration touch points: `config/agent/settings.yaml`, `config/agent/settings.yaml.example`, `README.md`, and `_SETTINGS_DEFAULTS` in `src/agent/agent.py`.

The following remain future work:
- multi-hop association,
- relation-strength ranking,
- temporal decay for graph relations,
- emotional modeling and affective relation states,
- graph-write compensation mechanisms.

## Conclusion

This design adds Mem0 native graph memory to the current long-term memory architecture without disrupting the existing main path. The project continues to integrate only with Mem0, does not directly adapt graph databases, and does not create a parallel graph-storage system. By making graph memory a configurable, degradable, and rate-limited enhancement layer, this design allows AntlerBot to evolve from semantic retrieval alone toward semantic retrieval plus relationship-based association, which better matches the intended human-like memory behavior.
