# Mem0 Long-Term Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate local OSS Mem0 into AntlerBot so the bot can automatically retrieve long-term memories before replies, store summary text asynchronously after summarization, and expose a manual recall tool without changing the existing short-term history model.

**Architecture:** Add a dedicated `src/agent/memory.py` integration layer that encapsulates Mem0 initialization, retrieval query construction, result formatting, seen-memory tracking, and asynchronous summary storage. Keep `src/agent/agent.py` as the orchestrator by calling this layer before user-message LLM invocations and after summary generation, while preserving the existing LangGraph flow and queue discipline.

**Tech Stack:** Python, LangGraph, LangChain, Mem0 OSS (`mem0ai`), pytest, pyyaml

---

### Task 1: Add Mem0 dependency and memory settings defaults

**Files:**
- Modify: `requirements.in`
- Modify: `src/agent/agent.py`
- Modify: `config/agent/settings.yaml`
- Modify: `config/agent/settings.yaml.example`
- Modify: `README.md`

**Step 1: Write the failing test**

Add a test in `tests/test_agent.py` that asserts `load_settings()` returns the new nested `memory` defaults when `settings.yaml` is missing, and that file-provided memory values merge with defaults.

```python
def test_load_settings_includes_memory_defaults_when_missing(tmp_path):
    with patch("src.agent.agent.SETTINGS_PATH", str(tmp_path / "settings.yaml")):
        result = agent_mod.load_settings()
    assert result["memory"]["enabled"] is False
    assert result["memory"]["agent_id"] == "antlerbot"
    assert result["memory"]["auto_recall_query_token_limit"] == 400


def test_load_settings_merges_memory_nested_config(tmp_path):
    f = tmp_path / "settings.yaml"
    f.write_text(
        "memory:\n  enabled: true\n  recall_high_max_memories: 12\n",
        encoding="utf-8",
    )
    with patch("src.agent.agent.SETTINGS_PATH", str(f)):
        result = agent_mod.load_settings()
    assert result["memory"]["enabled"] is True
    assert result["memory"]["recall_high_max_memories"] == 12
    assert result["memory"]["auto_recall_max_memories"] == 5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent.py::test_load_settings_includes_memory_defaults_when_missing tests/test_agent.py::test_load_settings_merges_memory_nested_config -v`
Expected: FAIL because the `memory` section does not exist in defaults or deep-merge logic.

**Step 3: Write minimal implementation**

- Add `mem0ai` to `requirements.in`.
- Extend `_SETTINGS_DEFAULTS` in `src/agent/agent.py` with a nested `memory` section.
- Update `load_settings()` to deep-merge `memory` just like `media`.
- Add matching config examples to `config/agent/settings.yaml` and `config/agent/settings.yaml.example`.
- Add the new settings rows to the runtime settings table in `README.md`.

Use this version-1 shape as the baseline:

```python
"memory": {
    "enabled": False,
    "agent_id": "antlerbot",
    "auto_recall_enabled": True,
    "auto_store_enabled": True,
    "auto_recall_query_token_limit": 400,
    "auto_recall_score_threshold": 0.75,
    "auto_recall_max_memories": 5,
    "auto_recall_system_prefix": "以下是可能与当前对话相关的长期记忆。仅在相关时使用，不要机械复述。",
    "recall_low_score_threshold": 0.85,
    "recall_low_max_memories": 3,
    "recall_medium_score_threshold": 0.70,
    "recall_medium_max_memories": 6,
    "recall_high_score_threshold": 0.55,
    "recall_high_max_memories": 10,
    "reset_seen_on_summary": True,
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent.py::test_load_settings_includes_memory_defaults_when_missing tests/test_agent.py::test_load_settings_merges_memory_nested_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add requirements.in src/agent/agent.py config/agent/settings.yaml config/agent/settings.yaml.example README.md tests/test_agent.py
git commit -m "feat: add mem0 memory settings"
```

### Task 2: Create memory text normalization and retrieval window helpers

**Files:**
- Create: `src/agent/memory.py`
- Create: `tests/test_memory.py`
- Check: `src/messaging/parser.py`

**Step 1: Write the failing test**

Create `tests/test_memory.py` with focused helper tests for XML stripping, whitespace joining, token-limited dynamic window construction, and media skip rules.

```python
from langchain_core.messages import AIMessage, HumanMessage
from src.agent import memory


def test_normalize_query_text_preserves_tag_contents_with_spaces():
    text = "你好<image>一只小猫趴在地上</image>它很可爱"
    assert memory.normalize_query_text(text) == "你好 一只小猫趴在地上 它很可爱"


def test_build_query_window_skips_previous_loading_media_message():
    history = [
        HumanMessage("第一句"),
        AIMessage('<image status="loading" />'),
        HumanMessage("现在继续说"),
    ]
    query = memory.build_auto_recall_query(history, 50)
    assert "第一句" in query
    assert 'status="loading"' not in query
    assert "现在继续说" in query


def test_build_query_window_returns_none_when_current_message_has_loading_media():
    history = [HumanMessage('请看这个<image status="loading" />')]
    assert memory.build_auto_recall_query(history, 50) is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory.py -v`
Expected: FAIL because `src.agent.memory` does not exist.

**Step 3: Write minimal implementation**

Create `src/agent/memory.py` and implement pure helpers first:
- `normalize_query_text(text: str) -> str`
- `message_has_untextualized_media(text: str) -> bool`
- `build_auto_recall_query(messages: list[BaseMessage], token_limit: int) -> str | None`

Rules to encode:
- Remove XML tags but keep tag contents.
- Insert spaces where adjacent preserved segments would otherwise stick together.
- Collapse repeated whitespace.
- Treat placeholders like `<image status="loading" />`, `<audio status="loading" />`, and bare self-closing media tags without textual content as non-textualized media.
- Skip prior messages with non-textualized media.
- If the current user message has non-textualized media, return `None`.
- Use `count_tokens_approximately` while walking backward through messages.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent/memory.py tests/test_memory.py
git commit -m "feat: add memory query helpers"
```

### Task 3: Add Mem0 client wrapper and seen-memory tracking

**Files:**
- Modify: `src/agent/memory.py`
- Modify: `tests/test_memory.py`

**Step 1: Write the failing test**

Add tests for the Mem0-facing wrapper behavior without touching `src/agent/agent.py` yet.

```python
class DummyMemory:
    def __init__(self, results):
        self.results = results
    def search(self, query, **kwargs):
        return {"results": self.results}


def test_filter_search_results_applies_threshold_max_count_and_seen_ids():
    results = [
        {"id": "a", "memory": "A", "score": 0.9},
        {"id": "b", "memory": "B", "score": 0.8},
        {"id": "c", "memory": "C", "score": 0.7},
    ]
    filtered = memory.filter_search_results(results, threshold=0.8, max_memories=2, seen_ids={"a"})
    assert [item["id"] for item in filtered] == ["b"]


def test_format_auto_recall_message_returns_none_for_empty_results():
    assert memory.format_auto_recall_message([], "前缀") is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory.py::test_filter_search_results_applies_threshold_max_count_and_seen_ids tests/test_memory.py::test_format_auto_recall_message_returns_none_for_empty_results -v`
Expected: FAIL because these wrapper helpers do not exist.

**Step 3: Write minimal implementation**

Extend `src/agent/memory.py` with:
- lazy Mem0 OSS initialization, e.g. `get_memory_client(settings)`
- `filter_search_results(results, threshold, max_memories, seen_ids)`
- `format_auto_recall_message(results, prefix)` returning `SystemMessage | None`
- module-level seen-memory tracking helpers:
  - `mark_seen_memory_ids(results)`
  - `reset_seen_memory_ids()`
  - `get_seen_memory_ids()` (for tests/logging)

Keep implementation simple:
- use the Mem0 OSS `Memory()` API
- pass `agent_id=settings["memory"]["agent_id"]`
- never include memory IDs in the generated `SystemMessage`
- do log IDs and scores

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory.py::test_filter_search_results_applies_threshold_max_count_and_seen_ids tests/test_memory.py::test_format_auto_recall_message_returns_none_for_empty_results -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent/memory.py tests/test_memory.py
git commit -m "feat: add mem0 result filtering"
```

### Task 4: Add automatic retrieval integration before user replies

**Files:**
- Modify: `src/agent/memory.py`
- Modify: `src/agent/agent.py`
- Modify: `tests/test_agent.py`
- Test: `tests/test_memory.py`

**Step 1: Write the failing test**

Add agent-level tests that verify one `SystemMessage` is injected before the current `HumanMessage`, and that no extra message is injected when retrieval returns nothing.

```python
@pytest.mark.anyio
async def test_invoke_injects_auto_recall_system_message_before_human_message():
    mock_graph = MagicMock()
    mock_graph.astream_events.return_value = _aiter([_make_stream_event("ok")])
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph), \
         patch("src.agent.agent.load_settings", return_value={**agent_mod._SETTINGS_DEFAULTS, "memory": {**agent_mod._SETTINGS_DEFAULTS["memory"], "enabled": True}}), \
         patch("src.agent.agent.memory_mod.build_auto_recall_system_message", return_value=SystemMessage("长期记忆")):
        async for _ in agent_mod._invoke("user_message", "你好"):
            pass
    sent = mock_graph.astream_events.call_args[0][0]["messages"]
    assert isinstance(sent[-2], SystemMessage)
    assert sent[-2].content == "长期记忆"
    assert isinstance(sent[-1], HumanMessage)


@pytest.mark.anyio
async def test_invoke_skips_auto_recall_message_when_none():
    mock_graph = MagicMock()
    mock_graph.astream_events.return_value = _aiter([_make_stream_event("ok")])
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph), \
         patch("src.agent.agent.load_settings", return_value={**agent_mod._SETTINGS_DEFAULTS, "memory": {**agent_mod._SETTINGS_DEFAULTS["memory"], "enabled": True}}), \
         patch("src.agent.agent.memory_mod.build_auto_recall_system_message", return_value=None):
        async for _ in agent_mod._invoke("user_message", "你好"):
            pass
    sent = mock_graph.astream_events.call_args[0][0]["messages"]
    assert isinstance(sent[-1], HumanMessage)
    assert not any(isinstance(msg, SystemMessage) and msg.content == "长期记忆" for msg in sent[:-1])
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent.py::test_invoke_injects_auto_recall_system_message_before_human_message tests/test_agent.py::test_invoke_skips_auto_recall_message_when_none -v`
Expected: FAIL because the agent does not call the memory layer yet.

**Step 3: Write minimal implementation**

- Import the memory module in `src/agent/agent.py` as `memory_mod`.
- Add a helper in `src/agent/memory.py`, e.g. `build_auto_recall_system_message(history, current_message, settings) -> SystemMessage | None`.
- In `_invoke(...)`, when `reason == "user_message"` and `memory.enabled` and `memory.auto_recall_enabled` are true:
  - build a temporary message list from `_history + [HumanMessage(message)]`
  - ask the memory module for an optional `SystemMessage`
  - inject it immediately before the current `HumanMessage`
- If current content is multimodal list content, skip automatic retrieval in version 1 to avoid mixed-content query ambiguity.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent.py::test_invoke_injects_auto_recall_system_message_before_human_message tests/test_agent.py::test_invoke_skips_auto_recall_message_when_none -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent/agent.py src/agent/memory.py tests/test_agent.py tests/test_memory.py
git commit -m "feat: inject long-term memory before replies"
```

### Task 5: Add asynchronous summary storage into Mem0

**Files:**
- Modify: `src/agent/memory.py`
- Modify: `src/agent/agent.py`
- Modify: `tests/test_agent.py`

**Step 1: Write the failing test**

Add tests proving summarization schedules storage asynchronously and resets seen IDs.

```python
@pytest.mark.anyio
async def test_summarize_all_schedules_async_memory_store_and_resets_seen_ids(monkeypatch):
    agent_mod._history = [HumanMessage("旧消息")]
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage("总结文本")
    scheduled = {}

    def fake_create_task(coro):
        scheduled["created"] = coro
        class DummyTask:
            pass
        return DummyTask()

    with patch.object(agent_mod, "_llm", fake_llm), \
         patch("src.agent.agent.load_settings", return_value={**agent_mod._SETTINGS_DEFAULTS, "memory": {**agent_mod._SETTINGS_DEFAULTS["memory"], "enabled": True, "auto_store_enabled": True}}), \
         patch("src.agent.agent.memory_mod.reset_seen_memory_ids") as reset_mock, \
         patch("src.agent.agent.memory_mod.store_summary_async") as store_mock, \
         patch("src.agent.agent.asyncio.create_task", side_effect=fake_create_task):
        agent_mod._ensure_initialized()
        await store_mock  # placeholder for linter in plan
```

Then simplify the actual assertion to check that:
- `reset_seen_memory_ids()` is called when summarization runs.
- `asyncio.create_task(...)` is called with the storage coroutine.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent.py -k "memory_store_and_resets_seen_ids" -v`
Expected: FAIL because summarization does not trigger any memory storage/reset hook.

**Step 3: Write minimal implementation**

- Add `store_summary_async(summary_text, settings)` to `src/agent/memory.py` that returns a coroutine which calls Mem0 `add(...)` with summary text and `agent_id`.
- In both `summarize_node` and `summarize_all_node` inside `src/agent/agent.py`:
  - call `memory_mod.reset_seen_memory_ids()` when summary is produced, if enabled
  - if memory storage is enabled and `summary.content` is non-empty, launch `asyncio.create_task(memory_mod.store_summary_async(...))`
- Keep storage best-effort and log failures inside the memory module.

When sending summary text to Mem0, use a minimal conversational wrapper so Mem0 receives a standard message list, e.g.:

```python
messages = [{"role": "user", "content": summary_text}]
```

Do not add metadata in version 1.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent.py -k "memory_store_and_resets_seen_ids" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent/agent.py src/agent/memory.py tests/test_agent.py
git commit -m "feat: store summaries in mem0 asynchronously"
```

### Task 6: Add recall tool with Chinese description and effort-based settings

**Files:**
- Modify: `src/agent/memory.py`
- Modify: `src/agent/agent.py`
- Modify: existing tool registration path (where app tools are assembled)
- Modify: `tests/test_memory.py`
- Modify: `tests/test_agent.py`

**Step 1: Write the failing test**

Add tests for the recall formatter and the tool schema/behavior.

```python
def test_recall_result_format_uses_plain_effort_label():
    text = memory.format_recall_result(
        [{"memory": "用户喜欢篮球"}, {"memory": "用户养了一只猫"}],
        effort_label="中等",
    )
    assert "已按中等努力程度检索到以下长期记忆：" in text
    assert '"中等"' not in text


def test_recall_result_format_handles_empty_results():
    assert memory.format_recall_result([], effort_label="高") == "未检索到符合条件的长期记忆。"
```

Add an agent/tool registration test that confirms the tool description is Chinese and that the tool is bound through existing registration flow.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory.py -k "recall_result_format" -v`
Expected: FAIL because recall formatting/tool helper does not exist.

**Step 3: Write minimal implementation**

In `src/agent/memory.py`:
- Add effort-level mapping helpers.
- Add `format_recall_result(results, effort_label)`.
- Add a LangChain tool factory such as `build_recall_tool(settings)`.

Requirements:
- Tool name can be `recall_memory`.
- Tool description must be written in Chinese.
- Tool arguments must include `query` and `effort`.
- Effort accepts `low | medium | high` internally, but the tool output text shown to the model should use Chinese labels like `低等`/`中等`/`高等` or preferably `低`/`中`/`高` consistently.
- The formatted output should be a plain memory block string.

Wire the tool into the existing tool registration path so it is available to the LangGraph LLM.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory.py -k "recall_result_format" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent/memory.py src/agent/agent.py tests/test_memory.py tests/test_agent.py
git commit -m "feat: add mem0 recall tool"
```

### Task 7: Add failure-path tests and logging assertions

**Files:**
- Modify: `tests/test_memory.py`
- Modify: `tests/test_agent.py`
- Modify: `src/agent/memory.py`

**Step 1: Write the failing test**

Add tests for the non-blocking failure behavior.

```python
@pytest.mark.anyio
async def test_auto_recall_failure_does_not_break_invoke(caplog):
    mock_graph = MagicMock()
    mock_graph.astream_events.return_value = _aiter([_make_stream_event("ok")])
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph), \
         patch("src.agent.agent.load_settings", return_value={**agent_mod._SETTINGS_DEFAULTS, "memory": {**agent_mod._SETTINGS_DEFAULTS["memory"], "enabled": True}}), \
         patch("src.agent.agent.memory_mod.build_auto_recall_system_message", side_effect=RuntimeError("boom")), \
         caplog.at_level(logging.WARNING):
        result = "".join([s async for s in agent_mod._invoke("user_message", "你好")])
    assert result == "ok"


def test_store_summary_async_logs_failure(caplog):
    with patch("src.agent.memory.get_memory_client", side_effect=RuntimeError("boom")), \
         caplog.at_level(logging.WARNING):
        asyncio.run(memory.store_summary_async("总结", agent_mod._SETTINGS_DEFAULTS))
    assert any("mem0" in r.message.lower() for r in caplog.records)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent.py::test_auto_recall_failure_does_not_break_invoke tests/test_memory.py::test_store_summary_async_logs_failure -v`
Expected: FAIL because exceptions currently bubble or are not logged clearly.

**Step 3: Write minimal implementation**

- Wrap automatic retrieval calls inside `src/agent/memory.py` or its caller with warning logs and `None` fallback.
- Ensure `store_summary_async()` catches exceptions and logs them.
- Keep behavior fully non-blocking and non-fatal.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent.py::test_auto_recall_failure_does_not_break_invoke tests/test_memory.py::test_store_summary_async_logs_failure -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agent/memory.py tests/test_memory.py tests/test_agent.py
git commit -m "test: cover mem0 failure paths"
```

### Task 8: Run focused verification, then full relevant test suite

**Files:**
- No code changes expected

**Step 1: Run focused memory and agent tests**

Run: `pytest tests/test_memory.py tests/test_agent.py -v`
Expected: PASS

**Step 2: Run any adjacent tests impacted by message parsing assumptions**

Run: `pytest tests/test_message_parser.py tests/test_media_processor.py -v`
Expected: PASS

**Step 3: If a failure appears, fix the minimum necessary code**

Keep fixes scoped to Mem0 integration, query normalization, or test expectations. Do not broaden refactors.

**Step 4: Run the verification commands again**

Run:
- `pytest tests/test_memory.py tests/test_agent.py -v`
- `pytest tests/test_message_parser.py tests/test_media_processor.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/agent/agent.py src/agent/memory.py tests/test_memory.py tests/test_agent.py requirements.in config/agent/settings.yaml config/agent/settings.yaml.example README.md
git commit -m "feat: integrate mem0 long-term memory"
```

### Task 9: Regenerate locked dependencies and final verification

**Files:**
- Modify: `requirements.txt`

**Step 1: Regenerate the lock file**

Run: `pip-compile --index-url=https://mirrors.aliyun.com/pypi/simple/ --output-file=requirements.txt requirements.in`
Expected: `requirements.txt` updated to include `mem0ai` and its transitive dependencies.

**Step 2: Install dependencies locally if needed**

Run: `pip install -r requirements.txt`
Expected: local environment includes `mem0ai`

**Step 3: Run final regression checks**

Run:
- `pytest tests/test_memory.py tests/test_agent.py -v`
- `pytest tests/test_message_parser.py tests/test_media_processor.py -v`

Expected: PASS

**Step 4: Review logs/config/docs one last time**

Confirm:
- memory settings are documented
- Chinese prompt/tool text requirements are met
- memory IDs are only logged, never injected into model context
- empty retrieval injects no extra `SystemMessage`

**Step 5: Commit**

```bash
git add requirements.txt
git commit -m "build: lock mem0 dependency"
```
