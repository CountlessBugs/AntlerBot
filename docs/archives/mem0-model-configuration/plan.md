# Mem0 Model Configuration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add environment-variable-based Mem0 model configuration so users can override Mem0's LLM and embedder while preserving fallback behavior to the main model and OpenAI small embeddings.

**Architecture:** Keep Mem0 model selection entirely inside `src/agent/memory.py`. Replace the current bare `Memory()` initialization with a `MemoryConfig` assembled from environment variables, using transcription-style fallback rules for the Mem0 LLM and OpenAI defaults for the Mem0 embedder. Update `.env.example`, `README.md`, and focused unit tests to document and verify the behavior.

**Tech Stack:** Python, mem0ai, pytest, python-dotenv, project `.env` configuration

---

### Task 1: Add failing tests for Mem0 config resolution

**Files:**
- Modify: `tests/test_memory.py`
- Reference: `src/agent/memory.py`

**Step 1: Write the failing tests**

Add focused tests that patch Mem0 imports and inspect the configuration passed into `Memory(...)`:

```python
from types import SimpleNamespace


def test_get_memory_store_uses_main_llm_when_mem0_llm_env_is_unset(monkeypatch):
    captured = {}

    class FakeMemory:
        def __init__(self, config=None):
            captured["config"] = config

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("MEM0_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("MEM0_LLM_MODEL", raising=False)

    with patch.dict("sys.modules", {
        "mem0": SimpleNamespace(Memory=FakeMemory),
        "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
    }):
        store = memory.get_memory_store({"memory": {}})

    assert store is not None
    assert captured["config"]["llm"]["provider"] == "openai"
    assert captured["config"]["llm"]["config"]["model"] == "gpt-4o"
```

Also add tests for:
- dedicated `MEM0_LLM_*` override
- default embedder provider/model (`openai` + `text-embedding-3-small`)
- dedicated `MEM0_EMBEDDER_*` override
- embedder API/base URL fallback to `OPENAI_*`

**Step 2: Run tests to verify they fail**

Run:
```bash
pytest tests/test_memory.py -v
```

Expected: FAIL because `src/agent/memory.py` still calls bare `Memory()` and does not construct Mem0 config from env vars.

**Step 3: Commit the failing tests**

```bash
git add tests/test_memory.py
git commit -m "test: define mem0 model configuration behavior"
```

---

### Task 2: Implement Mem0 config resolution helpers

**Files:**
- Modify: `src/agent/memory.py`
- Reference: `docs/frameworks/Mem0.md:97-109`

**Step 1: Add minimal helper functions**

Add private helpers in `src/agent/memory.py` to keep the fallback logic local and explicit:

```python
import os


def _get_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def _resolve_mem0_llm_config() -> dict:
    provider = _get_env("MEM0_LLM_PROVIDER") or _get_env("LLM_PROVIDER")
    model = _get_env("MEM0_LLM_MODEL") or _get_env("LLM_MODEL")
    api_key = _get_env("MEM0_LLM_API_KEY") or _get_env("OPENAI_API_KEY")
    base_url = _get_env("MEM0_LLM_BASE_URL") or _get_env("OPENAI_BASE_URL")

    config = {"model": model}
    if api_key:
        config["api_key"] = api_key
    if base_url:
        config["base_url"] = base_url
    return {"provider": provider, "config": config}


def _resolve_mem0_embedder_config() -> dict:
    provider = _get_env("MEM0_EMBEDDER_PROVIDER") or "openai"
    model = _get_env("MEM0_EMBEDDER_MODEL") or "text-embedding-3-small"
    api_key = _get_env("MEM0_EMBEDDER_API_KEY") or _get_env("OPENAI_API_KEY")
    base_url = _get_env("MEM0_EMBEDDER_BASE_URL") or _get_env("OPENAI_BASE_URL")

    config = {"model": model}
    if api_key:
        config["api_key"] = api_key
    if base_url:
        config["base_url"] = base_url
    return {"provider": provider, "config": config}
```

**Step 2: Add minimal validation**

Add a small validator that raises clear errors only when required resolved values are missing:

```python
def _require_mem0_field(value: str | None, env_name: str) -> str:
    if value:
        return value
    raise RuntimeError(f"{env_name} is required to initialize Mem0.")
```

Use it for the final required provider/model values after fallback resolution.

**Step 3: Run targeted tests**

Run:
```bash
pytest tests/test_memory.py -v
```

Expected: some failures may remain until `get_memory_store()` is updated to use the helpers.

**Step 4: Commit the helper implementation**

```bash
git add src/agent/memory.py
git commit -m "refactor: centralize mem0 env resolution"
```

---

### Task 3: Initialize Mem0 with explicit `MemoryConfig`

**Files:**
- Modify: `src/agent/memory.py`
- Reference: `docs/frameworks/Mem0.md:103-109`

**Step 1: Replace bare `Memory()` initialization**

Change `get_memory_store(settings)` so it imports both `Memory` and `MemoryConfig`, builds explicit config, and constructs the store once:

```python
def get_memory_store(settings: dict):
    global _MEMORY_STORE
    if _MEMORY_STORE is None:
        from mem0 import Memory
        from mem0.configs.base import MemoryConfig

        config = MemoryConfig(
            llm=_resolve_mem0_llm_config(),
            embedder=_resolve_mem0_embedder_config(),
        )
        _MEMORY_STORE = Memory(config)
    return _MEMORY_STORE
```

**Step 2: Keep scope narrow**

Do not change:
- search behavior
- recall filtering
- metadata update logic
- `settings.yaml`

Only touch the initialization path and the helper code needed to support it.

**Step 3: Run targeted tests to verify they pass**

Run:
```bash
pytest tests/test_memory.py -v
```

Expected: PASS for the new config-resolution coverage and existing memory tests.

**Step 4: Commit the initialization change**

```bash
git add src/agent/memory.py tests/test_memory.py
git commit -m "feat: allow mem0 model overrides via env"
```

---

### Task 4: Document the new environment variables

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Step 1: Update `.env.example`**

Add the new optional Mem0 variables near the existing model configuration:

```dotenv
MEM0_LLM_PROVIDER=
MEM0_LLM_MODEL=
MEM0_LLM_API_KEY=
MEM0_LLM_BASE_URL=

MEM0_EMBEDDER_PROVIDER=
MEM0_EMBEDDER_MODEL=
MEM0_EMBEDDER_API_KEY=
MEM0_EMBEDDER_BASE_URL=
```

**Step 2: Update `README.md`**

Add concise documentation near the environment variable table describing:
- Mem0 LLM override env vars
- fallback to `LLM_PROVIDER` / `LLM_MODEL`
- default Mem0 embedder `openai` + `text-embedding-3-small`
- embedder API/base URL fallback to `OPENAI_*`

Use project-appropriate Chinese wording in the user-facing explanation.

**Step 3: Run a focused verification pass**

Run:
```bash
pytest tests/test_memory.py -v
```

Expected: PASS, confirming docs-only edits did not disturb behavior.

**Step 4: Commit the documentation update**

```bash
git add .env.example README.md
git commit -m "docs: document mem0 model environment variables"
```

---

### Task 5: Run final verification

**Files:**
- Verify: `src/agent/memory.py`
- Verify: `tests/test_memory.py`
- Verify: `.env.example`
- Verify: `README.md`

**Step 1: Run focused tests**

Run:
```bash
pytest tests/test_memory.py -v
```

Expected: PASS.

**Step 2: Run the broader relevant suite**

Run:
```bash
pytest tests/test_agent.py tests/test_memory.py -v
```

Expected: PASS, ensuring the Mem0 initialization change does not regress agent integration.

**Step 3: Inspect the diff**

Run:
```bash
git diff -- src/agent/memory.py tests/test_memory.py .env.example README.md
```

Expected: only the planned Mem0 env/config, tests, and documentation changes are present.

**Step 4: Commit the final verified state if any fixes were needed**

```bash
git add src/agent/memory.py tests/test_memory.py .env.example README.md
git commit -m "chore: finalize mem0 model configuration"
```

Only do this step if verification required follow-up edits after the earlier commits.
