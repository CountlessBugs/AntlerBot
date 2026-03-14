# Graph Memory Association Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Mem0 native graph-memory association to AntlerBot so automatic recall and `recall_memory` can use both vector memories and relation-based associations without adding new tools or breaking vector-only fallback behavior.

**Architecture:** Keep the current Mem0-based long-term memory flow and extend it in-place. `src/agent/memory.py` remains the integration layer that initializes Mem0, formats retrieval results, and stores summaries; `src/agent/agent.py` remains the orchestration layer and only needs configuration/default-loading updates. Graph support is configured through nested `memory.graph.*` settings and degrades automatically to vector-only mode when graph initialization or relation handling fails.

**Tech Stack:** Python, LangChain, LangGraph, Mem0 OSS, YAML settings, pytest, unittest.mock

---

## File Structure

### Existing files to modify
- `src/agent/memory.py`
  - Add nested graph-settings readers.
  - Add Mem0 `graph_store` config assembly and fallback initialization.
  - Add relation extraction helpers from Mem0 `search()` payloads.
  - Add Chinese formatting helpers for `记忆` and `联想关系` sections.
  - Upgrade automatic recall and `recall_memory` to format `results + relations` together.
- `src/agent/agent.py`
  - Extend `_SETTINGS_DEFAULTS["memory"]` with nested `graph` defaults.
  - Update `load_settings()` so `memory.graph` is deep-merged instead of shallowly replaced.
- `config/agent/settings.yaml`
  - Add concrete `memory.graph` configuration block and comments.
- `config/agent/settings.yaml.example`
  - Add example/default `memory.graph` configuration block and comments.
- `README.md`
  - Document the new `memory.graph.*` settings and graph-memory behavior.
- `tests/test_memory.py`
  - Add focused tests for graph config assembly, fallback initialization, relation formatting, relation trimming, and graph-aware recall behavior.
- `tests/test_agent.py`
  - Add tests for nested `memory.graph` settings merge semantics if they belong at the agent-settings layer.

### No new runtime modules unless implementation proves necessary
The design does not require a new graph abstraction module. Keep logic inside `src/agent/memory.py` unless a tiny internal helper is needed and clearly improves readability without creating a second integration layer.

## Implementation Notes
- LLM system prompts and tool descriptions must remain in Chinese.
- Do not add a new recall tool name.
- Do not implement provider-specific graph-database branches outside Mem0.
- Do not implement custom graph extraction or graph-write compensation queues.
- Keep `max_hops` validation simple for this version: only support `1`.
- Preserve current behavior when `memory.graph` is absent or disabled.

## Chunk 1: Settings shape and configuration merge

### Task 1: Add nested graph defaults to agent settings

**Files:**
- Modify: `src/agent/agent.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write the failing test for default settings shape**

Add a test in `tests/test_agent.py` that loads defaults through `load_settings()` with no settings file and asserts:
- `settings["memory"]["graph"]["enabled"] is False`
- `settings["memory"]["graph"]["provider"] == "neo4j"`
- `settings["memory"]["graph"]["config"]` is a dict
- `settings["memory"]["graph"]["context_max_relations"] == 8`
- `settings["memory"]["graph"]["max_hops"] == 1`

- [ ] **Step 2: Run the single test to verify it fails**

Run: `pytest tests/test_agent.py::test_load_settings_includes_graph_memory_defaults -v`

Expected: FAIL because `memory.graph` does not exist yet.

- [ ] **Step 3: Add nested graph defaults to `_SETTINGS_DEFAULTS`**

Update `src/agent/agent.py` so `_SETTINGS_DEFAULTS["memory"]` includes:

```python
"graph": {
    "enabled": False,
    "provider": "neo4j",
    "config": {
        "url": "bolt://localhost:7687",
        "username": "neo4j",
        "password": "password",
        "database": "neo4j",
    },
    "auto_recall_enabled": True,
    "manual_recall_enabled": True,
    "context_max_relations": 8,
    "max_hops": 1,
    "context_prefix": "以下是与当前长期记忆相关的关系联想。仅在相关时使用，不要机械复述。",
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_agent.py::test_load_settings_includes_graph_memory_defaults -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_agent.py src/agent/agent.py
git commit -m "feat: add graph memory settings defaults"
```

### Task 2: Deep-merge `memory.graph` user overrides

**Files:**
- Modify: `src/agent/agent.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write the failing tests for nested graph merge behavior**

Add tests covering both cases:

```python
def test_load_settings_deep_merges_memory_graph_defaults(tmp_path):
    config = """
memory:
  graph:
    enabled: true
"""
    ...
    assert settings["memory"]["graph"]["enabled"] is True
    assert settings["memory"]["graph"]["provider"] == "neo4j"
    assert settings["memory"]["graph"]["context_max_relations"] == 8


def test_load_settings_preserves_graph_config_defaults_when_partially_overridden(tmp_path):
    config = """
memory:
  graph:
    config:
      url: bolt://graph.example:7687
"""
    ...
    assert settings["memory"]["graph"]["config"]["url"] == "bolt://graph.example:7687"
    assert settings["memory"]["graph"]["config"]["username"] == "neo4j"
```

Use a temporary `SETTINGS_PATH` patch exactly like existing prompt-path tests.

- [ ] **Step 2: Run the two tests to verify they fail**

Run: `pytest tests/test_agent.py::test_load_settings_deep_merges_memory_graph_defaults tests/test_agent.py::test_load_settings_preserves_graph_config_defaults_when_partially_overridden -v`

Expected: FAIL because current `load_settings()` only shallow-merges `memory`.

- [ ] **Step 3: Implement nested merge logic in `load_settings()`**

Update the `memory` merge section in `src/agent/agent.py` so it deep-merges:
- `memory` root keys
- `memory.graph`
- `memory.graph.config`

Keep the existing `media` merge behavior unchanged.

Recommended shape:

```python
default_memory = _SETTINGS_DEFAULTS.get("memory", {})
user_memory = data.get("memory", {})
default_graph = default_memory.get("graph", {})
user_graph = user_memory.get("graph", {})
merged_graph = {
    **default_graph,
    **user_graph,
    "config": {
        **default_graph.get("config", {}),
        **user_graph.get("config", {}),
    },
}
merged["memory"] = {
    **default_memory,
    **user_memory,
    "graph": merged_graph,
}
```

- [ ] **Step 4: Run the merge tests to verify they pass**

Run: `pytest tests/test_agent.py::test_load_settings_deep_merges_memory_graph_defaults tests/test_agent.py::test_load_settings_preserves_graph_config_defaults_when_partially_overridden -v`

Expected: PASS.

- [ ] **Step 5: Run the existing agent settings tests as a quick regression check**

Run: `pytest tests/test_agent.py -k "load_settings or memory_enabled" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_agent.py src/agent/agent.py
git commit -m "fix: deep merge nested graph memory settings"
```

## Chunk 2: Mem0 graph-store initialization and fallback

### Task 3: Add graph-store config assembly in memory initialization

**Files:**
- Modify: `src/agent/memory.py`
- Test: `tests/test_memory.py`

- [ ] **Step 1: Write the failing test for graph-store config pass-through**

Add a test that patches Mem0 imports with fake objects and calls `get_memory_store()` using:

```python
settings = {
    "memory": {
        "graph": {
            "enabled": True,
            "provider": "neo4j",
            "config": {
                "url": "bolt://localhost:7687",
                "username": "neo4j",
                "password": "secret",
                "database": "neo4j",
            },
        }
    }
}
```

Assert the resulting `MemoryConfig` payload includes:

```python
"graph_store": {
    "provider": "neo4j",
    "config": {
        "url": "bolt://localhost:7687",
        "username": "neo4j",
        "password": "secret",
        "database": "neo4j",
    },
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_memory.py::test_get_memory_store_includes_graph_store_when_enabled -v`

Expected: FAIL because `get_memory_store()` currently ignores graph settings.

- [ ] **Step 3: Implement graph settings readers and `graph_store` assembly**

Add a helper in `src/agent/memory.py` similar to:

```python
def _resolve_graph_store_config(settings: dict) -> dict | None:
    graph_settings = settings.get("memory", {}).get("graph", {})
    if not graph_settings.get("enabled"):
        return None
    return {
        "provider": graph_settings.get("provider", "neo4j"),
        "config": dict(graph_settings.get("config", {})),
    }
```

Then update `get_memory_store(settings)` to include `graph_store=...` only when enabled.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_memory.py::test_get_memory_store_includes_graph_store_when_enabled -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_memory.py src/agent/memory.py
git commit -m "feat: pass graph store config to mem0"
```

### Task 4: Fall back to vector-only Mem0 when graph initialization fails

**Files:**
- Modify: `src/agent/memory.py`
- Test: `tests/test_memory.py`

- [ ] **Step 1: Write the failing fallback test**

Add a test with a fake `Memory` class that:
- raises on first init when `config` contains `graph_store`
- succeeds on second init when `graph_store` is absent

Assert:
- `get_memory_store(settings)` still returns a store
- two init attempts happened
- warning logging was emitted
- second init config does not contain `graph_store`

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_memory.py::test_get_memory_store_falls_back_when_graph_init_fails -v`

Expected: FAIL because current code only initializes once.

- [ ] **Step 3: Implement fallback initialization**

Update `get_memory_store(settings)` so it:
1. builds base config with `llm` and `embedder`
2. tries to initialize Mem0 with `graph_store` when enabled
3. on failure, logs a warning and retries once without `graph_store`

Keep failure handling narrow:
- only retry the graph-enabled branch
- if the vector-only retry also fails, let the exception bubble so existing call sites can log/skip as they already do

- [ ] **Step 4: Run the fallback test to verify it passes**

Run: `pytest tests/test_memory.py::test_get_memory_store_falls_back_when_graph_init_fails -v`

Expected: PASS.

- [ ] **Step 5: Run the existing Mem0 initialization tests**

Run: `pytest tests/test_memory.py -k "get_memory_store" -v`

Expected: PASS, including the existing LLM/embedder env override tests.

- [ ] **Step 6: Commit**

```bash
git add tests/test_memory.py src/agent/memory.py
git commit -m "fix: fall back to vector-only mem0 on graph init failure"
```

## Chunk 6: Persistent vector-store configuration integration

### Task 11: Add formal `memory.vector_store` settings and deep-merge behavior

**Files:**
- Modify: `src/agent/agent.py`
- Modify: `config/agent/settings.yaml.example`
- Modify: `README.md`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write the failing tests for vector-store defaults and nested merge behavior**

Add tests in `tests/test_agent.py` that assert all of the following:

1. Default settings include:

```python
settings["memory"]["vector_store"]["provider"] == "qdrant"
settings["memory"]["vector_store"]["config"]["collection_name"] == "mem0"
settings["memory"]["vector_store"]["config"]["path"] == "data/mem0/qdrant"
settings["memory"]["vector_store"]["config"]["on_disk"] is True
```

2. Partial user override keeps missing defaults:

```python
config = """
memory:
  vector_store:
    config:
      collection_name: "custom_mem0"
"""
```

Expected assertions:

```python
settings["memory"]["vector_store"]["provider"] == "qdrant"
settings["memory"]["vector_store"]["config"]["collection_name"] == "custom_mem0"
settings["memory"]["vector_store"]["config"]["path"] == "data/mem0/qdrant"
settings["memory"]["vector_store"]["config"]["on_disk"] is True
```

3. Root-level provider override works:

```python
config = """
memory:
  vector_store:
    provider: "qdrant"
"""
```

Use the same temporary-settings-file patch pattern as the existing `load_settings()` tests.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/test_agent.py::test_load_settings_includes_vector_store_defaults tests/test_agent.py::test_load_settings_deep_merges_memory_vector_store_defaults -v
```

Expected: FAIL because `memory.vector_store` does not exist yet.

- [ ] **Step 3: Add nested vector-store defaults and merge logic**

Update `_SETTINGS_DEFAULTS["memory"]` in `src/agent/agent.py` to include:

```python
"vector_store": {
    "provider": "qdrant",
    "config": {
        "collection_name": "mem0",
        "path": "data/mem0/qdrant",
        "on_disk": True,
    },
},
```

Then update the `load_settings()` deep merge section so `memory.vector_store` is merged the same way as `memory.graph`:

```python
default_vector_store = default_memory.get("vector_store", {})
user_vector_store = user_memory.get("vector_store", {})
merged_vector_store = {
    **default_vector_store,
    **user_vector_store,
    "config": {
        **default_vector_store.get("config", {}),
        **user_vector_store.get("config", {}),
    },
}
```

And include it in the final merged `memory` mapping.

Keep existing `media` merge behavior unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
pytest tests/test_agent.py::test_load_settings_includes_vector_store_defaults tests/test_agent.py::test_load_settings_deep_merges_memory_vector_store_defaults -v
```

Expected: PASS.

- [ ] **Step 5: Update user-facing configuration docs**

Update `config/agent/settings.yaml.example` and `README.md` so they document:
- `memory.vector_store.provider`
- `memory.vector_store.config`
- default provider `qdrant`
- default persistent path `data/mem0/qdrant`
- restart reuses the same vector DB by default
- YAML-sensitive string values that could be misread should be quoted; URL defaults remain unquoted

The example YAML block should look like:

```yaml
memory:
  vector_store:
    # 向量存储后端提供者，透传给 Mem0
    provider: "qdrant"

    # 向量存储后端配置，透传给 Mem0
    config:
      collection_name: "mem0"
      path: "data/mem0/qdrant"
      on_disk: true
```

- [ ] **Step 6: Run a focused regression check**

Run:

```bash
pytest tests/test_agent.py -k "load_settings or vector_store or graph" -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_agent.py src/agent/agent.py config/agent/settings.yaml.example README.md
git commit -m "feat: add persistent mem0 vector store settings"
```

### Task 12: Make Mem0 always use the configured vector store, including graph fallback

**Files:**
- Modify: `src/agent/memory.py`
- Test: `tests/test_memory.py`

- [ ] **Step 1: Write the failing tests for vector-store config assembly**

Add focused tests that patch Mem0 imports with fake `Memory` / `MemoryConfig` objects and assert:

1. Vector-only initialization includes configured `vector_store`:

```python
settings = {
    "memory": {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "mem0",
                "path": "data/mem0/qdrant",
                "on_disk": True,
            },
        }
    }
}
```

Expected `MemoryConfig` payload contains:

```python
"vector_store": {
    "provider": "qdrant",
    "config": {
        "collection_name": "mem0",
        "path": <resolved persistent absolute path>,
        "on_disk": True,
    },
}
```

2. Graph-enabled initialization includes both `graph_store` and `vector_store`.

3. Graph-init fallback retries without `graph_store` but still includes the same `vector_store` config.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/test_memory.py -k "vector_store and get_memory_store" -v
```

Expected: FAIL because current implementation only passes `graph_store` explicitly and fallback still builds a temporary `/tmp/qdrant/...` path.

- [ ] **Step 3: Implement vector-store resolution helpers in `src/agent/memory.py`**

Add a helper such as:

```python
def _resolve_vector_store_config(settings: dict) -> dict:
    vector_settings = settings.get("memory", {}).get("vector_store", {})
    provider = vector_settings.get("provider", "qdrant")
    config = {
        key: value
        for key, value in dict(vector_settings.get("config", {})).items()
    }
    ...
    return {"provider": provider, "config": config}
```

Behavior requirements:
- default provider is `qdrant`
- default relative path is `data/mem0/qdrant`
- for qdrant `path`, convert relative project path to a stable absolute path rooted at the repository/worktree directory
- do **not** generate random directories
- do **not** use `/tmp/qdrant`
- preserve pass-through semantics for other providers/config fields

Recommended path behavior:
- if `config.path` is relative, resolve it against the project root derived from `src/agent/memory.py`
- if `config.path` is already absolute, keep it as-is

- [ ] **Step 4: Update `get_memory_store(settings)` to always pass `vector_store`**

Refactor the initialization logic to build one shared base payload:

```python
config_kwargs = {
    "llm": _resolve_mem0_llm_config(),
    "embedder": _resolve_mem0_embedder_config(),
    "vector_store": _resolve_vector_store_config(settings),
}
```

Then apply these rules:
- graph disabled or unavailable: initialize Mem0 with `config_kwargs`
- graph enabled and valid: initialize with `{**config_kwargs, "graph_store": graph_store}`
- graph init failure: log warning and retry once with the original `config_kwargs`

This preserves the existing graph fallback behavior while ensuring both branches use the same persistent vector store.

- [ ] **Step 5: Remove temporary vector-store fallback path logic**

Delete the old helper that generated `/tmp/qdrant/<agent_id>/<uuid>` fallback directories.

Also remove unused imports that only supported that temporary-path branch.

- [ ] **Step 6: Run focused tests and regressions**

Run:

```bash
pytest tests/test_memory.py -k "get_memory_store or vector_store or graph_store" -v
```

Expected: PASS.

Then run:

```bash
pytest tests/test_memory.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_memory.py src/agent/memory.py
git commit -m "fix: reuse configured vector store for mem0 fallback"
```

## Design Addendum: Persistent vector-store integration

This addendum extends the graph-memory plan without changing its overall architecture.

### Final design decisions

1. **Configuration shape**
   - Add `memory.vector_store.provider` and `memory.vector_store.config` as the formal project configuration surface.
   - Keep the shape parallel to `memory.graph.provider/config` for consistency.
   - Use complete pass-through semantics so provider-specific config keys remain controlled by Mem0 rather than AntlerBot.

2. **Default storage backend and location**
   - Default provider is `qdrant`.
   - Default config uses persistent storage under the project data directory: `data/mem0/qdrant`.
   - For qdrant local path mode, relative paths are resolved to a stable absolute path inside the current repository/worktree, so restarting `.venv/bin/python main.py` in the same checkout reuses the same vector DB.

3. **Initialization rules**
   - Mem0 should always receive an explicit `vector_store` config, regardless of whether graph memory is enabled.
   - If graph memory is enabled and graph initialization succeeds, Mem0 receives both `graph_store` and `vector_store`.
   - If graph memory is disabled, invalid, or fails to initialize, Mem0 falls back to vector-only mode using the exact same configured `vector_store`.

4. **Fallback behavior**
   - Preserve the current fallback semantics: graph issues should degrade to vector-only mode automatically.
   - Remove the previous temporary qdrant fallback path pattern because it breaks persistence and can trigger Windows file-lock conflicts.
   - Do not introduce random per-run storage directories.

5. **Documentation and YAML rules**
   - Update example/documentation to show the new nested block.
   - Quote YAML string values that are easy to misinterpret by the parser; keep URL defaults unquoted.

6. **Testing scope**
   - Add settings-layer tests for nested vector-store defaults and deep-merge semantics.
   - Add memory-layer tests for path resolution, explicit vector-store pass-through, graph+vector combined init, and graph-fallback reuse of persistent vector-store config.

### Acceptance criteria

The work is complete when all of the following are true:
- `memory.vector_store` exists in defaults, example config, and README.
- Default configuration uses qdrant persisted under `data/mem0/qdrant`.
- Restarting the bot in the same project/worktree reuses the same vector-store path.
- `get_memory_store()` always passes explicit `vector_store` config into Mem0.
- graph fallback no longer uses `/tmp/qdrant` or any random temp directory.
- Existing graph fallback behavior remains intact.
- Relevant tests pass.


### Task 5: Add relation trimming and formatting helpers

**Files:**
- Modify: `src/agent/memory.py`
- Test: `tests/test_memory.py`

- [ ] **Step 1: Write the failing tests for relation formatting**

Add focused tests for helpers such as:
- trimming relation count to `context_max_relations`
- returning no `联想关系` section when relations are empty
- formatting both sections in Chinese when results and relations both exist
- dropping malformed relations without dropping the memory section

Use small fixtures like:

```python
results = [{"memory": "用户正在做 AntlerBot 长期记忆系统"}]
relations = [
    {"source": "AntlerBot", "relationship": "关联", "destination": "长期记忆系统"},
    {"source": "长期记忆系统", "relationship": "目标", "destination": "更像真实的人"},
]
```

- [ ] **Step 2: Run the formatting tests to verify they fail**

Run: `pytest tests/test_memory.py -k "relation_format or context_max_relations or malformed_relations" -v`

Expected: FAIL because no relation helpers exist yet.

- [ ] **Step 3: Implement minimal helpers in `src/agent/memory.py`**

Add focused helpers, for example:
- `_extract_search_results(raw_search)`
- `_extract_relations(raw_search)`
- `_trim_relations(relations, max_relations)`
- `_format_relation_lines(relations)`
- `format_auto_recall_message(results, prefix, relations=None, relation_prefix=None)`
- `format_recall_result(results, effort_label, relations=None, relation_prefix=None)`

Requirements:
- Keep final output in Chinese.
- Keep `记忆：` and `联想关系：` as separate sections.
- Preserve the existing empty-result response string for manual recall.
- Ignore malformed relation items rather than crashing.

- [ ] **Step 4: Run the helper tests to verify they pass**

Run: `pytest tests/test_memory.py -k "relation_format or context_max_relations or malformed_relations" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_memory.py src/agent/memory.py
git commit -m "feat: format graph memory relations in recall output"
```

### Task 6: Upgrade `recall_memory` to consume `results + relations`

**Files:**
- Modify: `src/agent/memory.py`
- Test: `tests/test_memory.py`

- [ ] **Step 1: Write the failing tests for manual recall behavior**

Add tests covering:
- when `memory.graph.manual_recall_enabled` is true, the output includes both `记忆：` and `联想关系：`
- when graph is disabled, output remains memory-only
- when `relations` are present but malformed, memory section still returns
- `context_max_relations` is enforced for manual recall

Use a fake store whose `search()` returns:

```python
{
    "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.9}],
    "relations": [{"source": "bot", "relationship": "目标", "destination": "真实的人类式记忆"}],
}
```

- [ ] **Step 2: Run the manual recall tests to verify they fail**

Run: `pytest tests/test_memory.py -k "manual_recall and relations" -v`

Expected: FAIL because `build_recall_tool()` currently ignores `relations`.

- [ ] **Step 3: Implement the minimal manual-recall change**

Update `build_recall_tool(settings)` so it:
- reads the full search payload once
- extracts and filters `results`
- conditionally reads/trims `relations` when `memory.graph.enabled` and `memory.graph.manual_recall_enabled` are true
- formats the final text with `format_recall_result(..., relations=..., relation_prefix=...)`

Do not change:
- tool name `recall_memory`
- tool arguments `query`, `effort`
- recall metadata update behavior for memory IDs

- [ ] **Step 4: Run the manual recall tests to verify they pass**

Run: `pytest tests/test_memory.py -k "manual_recall and relations" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_memory.py src/agent/memory.py
git commit -m "feat: add graph associations to recall_memory"
```

### Task 7: Upgrade automatic recall to consume `results + relations`

**Files:**
- Modify: `src/agent/memory.py`
- Test: `tests/test_memory.py`, `tests/test_agent.py`

- [ ] **Step 1: Write the failing tests for automatic recall relation injection**

Add tests covering:
- `build_auto_recall_system_message()` includes `联想关系：` when graph auto recall is enabled and Mem0 returns relations
- no relation section appears when graph auto recall is disabled
- malformed relations do not suppress the memory section
- automatic recall still returns `None` when filtered memories are empty, even if relations exist

Also add one integration-style agent test asserting the injected `SystemMessage` contains both headings when `memory_mod.build_auto_recall_system_message()` returns the graph-aware content.

- [ ] **Step 2: Run the automatic recall tests to verify they fail**

Run: `pytest tests/test_memory.py -k "auto_recall and relations" -v && pytest tests/test_agent.py -k "auto_recall" -v`

Expected: memory-side tests FAIL first because automatic recall ignores relations.

- [ ] **Step 3: Implement the minimal automatic-recall change**

Update `build_auto_recall_system_message()` so it:
- extracts the full search payload
- filters memory results using current logic
- returns `None` when filtered results are empty
- conditionally trims and formats relations when `memory.graph.enabled` and `memory.graph.auto_recall_enabled` are true
- wraps the final `SystemMessage` with the existing temporary-marker logic

Do not persist the temporary graph-association message into `_history`.

- [ ] **Step 4: Run the automatic recall tests to verify they pass**

Run: `pytest tests/test_memory.py -k "auto_recall and relations" -v && pytest tests/test_agent.py -k "auto_recall" -v`

Expected: PASS.

- [ ] **Step 5: Run the full memory and agent test files**

Run: `pytest tests/test_memory.py tests/test_agent.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_memory.py tests/test_agent.py src/agent/memory.py
git commit -m "feat: add graph associations to automatic recall"
```

## Chunk 4: Write-path validation, docs, and final verification

### Task 8: Cover graph-enabled summary storage and logging behavior

**Files:**
- Modify: `tests/test_memory.py`
- Modify only if needed: `src/agent/memory.py`

- [ ] **Step 1: Write the failing test for graph-enabled summary storage input**

Add a test that patches `get_memory_store()` with a fake store, calls `store_summary_async()`, and asserts the store receives exactly:

```python
store.add(
    [{"role": "user", "content": "总结文本"}],
    agent_id="antlerbot",
)
```

with graph settings present in `settings`, proving the write path remains summary-only and does not branch into a second graph-write API.

- [ ] **Step 2: Run the test to verify it fails if the assertion is not yet covered**

Run: `pytest tests/test_memory.py::test_store_summary_async_uses_summary_only_with_graph_enabled -v`

Expected: FAIL if no such assertion exists yet.

- [ ] **Step 3: Implement or adjust only the minimum needed code**

If the code already behaves correctly, this step is only to keep the test. Otherwise, update `store_summary_async()` minimally so graph-enabled settings still use the same `store.add([...], agent_id=...)` call.

- [ ] **Step 4: Run the storage test to verify it passes**

Run: `pytest tests/test_memory.py::test_store_summary_async_uses_summary_only_with_graph_enabled -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_memory.py src/agent/memory.py
git commit -m "test: cover summary-only writes with graph memory enabled"
```

### Task 9: Update runtime config and README documentation

**Files:**
- Modify: `config/agent/settings.yaml`
- Modify: `config/agent/settings.yaml.example`
- Modify: `README.md`

- [ ] **Step 1: Update `config/agent/settings.yaml` with concrete graph settings**

Add a nested block under `memory:` with Chinese comments:

```yaml
  graph:
    # 是否启用图记忆联想增强
    enabled: false

    # 图存储后端提供者，透传给 Mem0
    provider: neo4j

    # 图存储后端配置，透传给 Mem0
    config:
      url: bolt://localhost:7687
      username: neo4j
      password: password
      database: neo4j

    # 是否在自动检索时追加关系联想
    auto_recall_enabled: true

    # 是否在 recall_memory 工具中追加关系联想
    manual_recall_enabled: true

    # 单次注入上下文时最多保留多少条关系联想
    context_max_relations: 8

    # 当前版本仅支持 1 跳联想
    max_hops: 1

    # 关系联想注入到模型前的提示前缀
    context_prefix: 以下是与当前长期记忆相关的关系联想。仅在相关时使用，不要机械复述。
```

- [ ] **Step 2: Mirror the same block in `config/agent/settings.yaml.example`**

Keep comments concise and aligned with the real settings file.

- [ ] **Step 3: Update the README settings table**

Add table rows for:
- `memory.graph.enabled`
- `memory.graph.provider`
- `memory.graph.config`
- `memory.graph.auto_recall_enabled`
- `memory.graph.manual_recall_enabled`
- `memory.graph.context_max_relations`
- `memory.graph.max_hops`
- `memory.graph.context_prefix`

Also add one short paragraph in the memory section explaining that Mem0 graph memory is optional, uses the same `recall_memory` tool, and falls back to vector-only behavior when disabled or unavailable.

- [ ] **Step 4: Review the changed docs for consistency**

Manually verify:
- comments are in Chinese where they configure runtime behavior
- README wording matches actual setting names exactly
- no old flat `graph_*` names appear

- [ ] **Step 5: Commit**

```bash
git add config/agent/settings.yaml config/agent/settings.yaml.example README.md
git commit -m "docs: document graph memory settings"
```

### Task 10: Run full verification and prepare execution handoff

**Files:**
- No code changes expected unless verification reveals a real defect

- [ ] **Step 1: Run focused long-term memory tests**

Run: `pytest tests/test_memory.py tests/test_agent.py -v`

Expected: PASS.

- [ ] **Step 2: Run the broader project test suite if memory changes touch shared behavior**

Run: `pytest -q`

Expected: PASS, or identify the exact unrelated failures before touching anything else.

- [ ] **Step 3: If any test fails, fix only the proven defect and rerun the affected tests**

Do not guess. Use the failing traceback to make the minimum correction.

- [ ] **Step 4: Inspect the final diff before handoff**

Run:

```bash
git status
git diff -- src/agent/agent.py src/agent/memory.py tests/test_agent.py tests/test_memory.py config/agent/settings.yaml config/agent/settings.yaml.example README.md
```

Expected: only the planned files changed, and the diff matches the graph-memory design.

- [ ] **Step 5: Create the final implementation commit**

```bash
git add src/agent/agent.py src/agent/memory.py tests/test_agent.py tests/test_memory.py config/agent/settings.yaml config/agent/settings.yaml.example README.md
git commit -m "feat: add mem0 graph memory associations"
```

- [ ] **Step 6: Request code review before merge**

Use `superpowers:requesting-code-review` after implementation is complete and verification passes.
