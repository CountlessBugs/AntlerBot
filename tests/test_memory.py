import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from src.agent import memory


class DummyMemory:
    def __init__(self, results):
        self.results = results

    def search(self, query, **kwargs):
        return {"results": self.results}


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


def test_filter_search_results_applies_threshold_max_count_and_seen_ids():
    results = [
        {"id": "a", "memory": "A", "score": 0.9},
        {"id": "b", "memory": "B", "score": 0.8},
        {"id": "c", "memory": "C", "score": 0.7},
    ]
    filtered = memory.filter_search_results(results, threshold=0.8, max_memories=2, blocked_ids={"a"})
    assert [item["id"] for item in filtered] == ["b"]


def test_format_auto_recall_message_returns_none_for_empty_results():
    assert memory.format_auto_recall_message([], "前缀") is None


def test_recall_result_format_uses_plain_effort_label():
    text = memory.format_recall_result(
        [{"memory": "用户喜欢篮球"}, {"memory": "用户养了一只猫"}],
        effort_label="中等",
    )
    assert "已按中等努力程度检索到以下长期记忆：" in text
    assert '"中等"' not in text


def test_recall_result_format_handles_empty_results():
    assert memory.format_recall_result([], effort_label="高") == "未检索到符合条件的长期记忆。"


def test_build_recall_metadata_update_increments_count_and_sets_timestamp():
    current = {"recall_count": 2, "last_recalled_at": "2026-03-01T00:00:00Z", "tag": "x"}
    updated = memory.build_recall_metadata_update(current, recalled_at="2026-03-08T12:00:00Z")
    assert updated["recall_count"] == 3
    assert updated["last_recalled_at"] == "2026-03-08T12:00:00Z"
    assert updated["tag"] == "x"


def test_build_recall_metadata_update_defaults_count_when_missing():
    updated = memory.build_recall_metadata_update({}, recalled_at="2026-03-08T12:00:00Z")
    assert updated["recall_count"] == 1
    assert updated["last_recalled_at"] == "2026-03-08T12:00:00Z"


def test_auto_recall_allows_repeat_results_but_counts_once_per_session():
    class RepeatMemory:
        def search(self, query, **kwargs):
            return {"results": [{"id": "a", "memory": "A", "score": 0.9}]}

    memory.reset_counted_memory_ids()
    history = [HumanMessage("你好")]
    settings = {"memory": {"agent_id": "antlerbot", "auto_recall_query_token_limit": 50, "auto_recall_score_threshold": 0.5, "auto_recall_max_memories": 5, "auto_recall_system_prefix": "前缀"}}

    with patch("src.agent.memory.get_memory_store", return_value=RepeatMemory()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True) as update_mock:
        first = memory.build_auto_recall_system_message(history, settings)
        second = memory.build_auto_recall_system_message(history, settings)

    assert first is not None
    assert second is not None
    assert memory.get_counted_memory_ids() == {"a"}
    assert update_mock.call_count == 1


def test_filter_search_results_excludes_context_locked_ids():
    results = [
        {"id": "a", "memory": "A", "score": 0.9},
        {"id": "b", "memory": "B", "score": 0.8},
    ]
    filtered = memory.filter_search_results(results, threshold=0.0, max_memories=5, blocked_ids={"a"})
    assert [item["id"] for item in filtered] == ["b"]


def test_lock_memory_ids_for_session_blocks_future_auto_recall_results():
    class RepeatMemory:
        def search(self, query, **kwargs):
            return {"results": [
                {"id": "a", "memory": "A", "score": 0.9},
                {"id": "b", "memory": "B", "score": 0.8},
            ]}

    memory.reset_context_locked_memory_ids()
    memory.lock_memory_ids_for_session([{"id": "a"}])
    history = [HumanMessage("你好")]
    settings = {"memory": {"agent_id": "antlerbot", "auto_recall_query_token_limit": 50, "auto_recall_score_threshold": 0.5, "auto_recall_max_memories": 5, "auto_recall_system_prefix": "前缀"}}

    with patch("src.agent.memory.get_memory_store", return_value=RepeatMemory()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        message = memory.build_auto_recall_system_message(history, settings)

    assert message is not None
    assert "- A" not in message.content
    assert "- B" in message.content


class DummyMemoryStore:
    def __init__(self, payload):
        self.payload = payload
        self.updated = None

    def get(self, memory_id):
        return self.payload

    def update(self, memory_id, data):
        self.updated = {"memory_id": memory_id, "data": data}



def test_try_update_memory_recall_metadata_returns_false_when_store_methods_missing():
    class NoUpdateStore:
        pass

    assert memory.try_update_memory_recall_metadata(NoUpdateStore(), "mem-1", "2026-03-08T12:00:00Z") is False



def test_try_update_memory_recall_metadata_returns_false_when_text_is_missing():
    store = DummyMemoryStore({"metadata": {"recall_count": 1}})
    assert memory.try_update_memory_recall_metadata(store, "mem-1", "2026-03-08T12:00:00Z") is False
    assert store.updated is None



def test_try_update_memory_recall_metadata_updates_metadata_with_memory_store():
    store = DummyMemoryStore({"memory": "记忆文本", "metadata": {"recall_count": 1, "tag": "x"}})
    assert memory.try_update_memory_recall_metadata(store, "mem-1", "2026-03-08T12:00:00Z") is True
    assert store.updated["memory_id"] == "mem-1"
    assert store.updated["data"]["memory"] == "记忆文本"
    assert store.updated["data"]["metadata"]["recall_count"] == 2
    assert store.updated["data"]["metadata"]["last_recalled_at"] == "2026-03-08T12:00:00Z"
    assert store.updated["data"]["metadata"]["tag"] == "x"



def test_try_update_memory_recall_metadata_returns_false_when_get_result_is_not_mapping():
    store = DummyMemoryStore(["not-a-dict"])
    assert memory.try_update_memory_recall_metadata(store, "mem-1", "2026-03-08T12:00:00Z") is False
    assert store.updated is None


def test_reset_session_memory_state_clears_counted_and_locked_ids():
    memory.mark_counted_memory_ids([{"id": "a"}])
    memory.lock_memory_ids_for_session([{"id": "b"}])
    memory.reset_session_memory_state()
    assert memory.get_counted_memory_ids() == set()
    assert memory.get_context_locked_memory_ids() == set()


def test_store_summary_async_logs_failure(caplog):
    with patch("src.agent.memory.get_memory_store", side_effect=RuntimeError("boom")), \
         caplog.at_level(logging.WARNING):
        asyncio.run(memory.store_summary_async("总结", {"memory": {"agent_id": "antlerbot"}}))
    assert any("mem0" in r.message.lower() for r in caplog.records)


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
    monkeypatch.delenv("MEM0_LLM_API_KEY", raising=False)
    monkeypatch.delenv("MEM0_LLM_BASE_URL", raising=False)

    with patch.dict(
        "sys.modules",
        {
            "mem0": SimpleNamespace(Memory=FakeMemory),
            "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
        },
    ):
        store = memory.get_memory_store({"memory": {}})

    assert store is not None
    assert captured["config"]["llm"]["provider"] == "openai"
    assert captured["config"]["llm"]["config"]["model"] == "gpt-4o"
    assert captured["config"]["llm"]["config"]["api_key"] == "test-key"


def test_get_memory_store_uses_dedicated_mem0_llm_override(monkeypatch):
    captured = {}

    class FakeMemory:
        def __init__(self, config=None):
            captured["config"] = config

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "main-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://main.example/v1")
    monkeypatch.setenv("MEM0_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MEM0_LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("MEM0_LLM_API_KEY", "mem0-key")
    monkeypatch.setenv("MEM0_LLM_BASE_URL", "https://mem0.example/v1")

    with patch.dict(
        "sys.modules",
        {
            "mem0": SimpleNamespace(Memory=FakeMemory),
            "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
        },
    ):
        memory.get_memory_store({"memory": {}})

    assert captured["config"]["llm"] == {
        "provider": "openai",
        "config": {
            "model": "gpt-4.1-mini",
            "api_key": "mem0-key",
            "base_url": "https://mem0.example/v1",
        },
    }


def test_get_memory_store_uses_default_embedder_when_mem0_embedder_env_is_unset(monkeypatch):
    captured = {}

    class FakeMemory:
        def __init__(self, config=None):
            captured["config"] = config

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "embed-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example/v1")
    monkeypatch.delenv("MEM0_EMBEDDER_PROVIDER", raising=False)
    monkeypatch.delenv("MEM0_EMBEDDER_MODEL", raising=False)
    monkeypatch.delenv("MEM0_EMBEDDER_API_KEY", raising=False)
    monkeypatch.delenv("MEM0_EMBEDDER_BASE_URL", raising=False)

    with patch.dict(
        "sys.modules",
        {
            "mem0": SimpleNamespace(Memory=FakeMemory),
            "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
        },
    ):
        memory.get_memory_store({"memory": {}})

    assert captured["config"]["embedder"] == {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-small",
            "api_key": "embed-key",
            "base_url": "https://openai.example/v1",
        },
    }


def test_get_memory_store_uses_dedicated_mem0_embedder_override(monkeypatch):
    captured = {}

    class FakeMemory:
        def __init__(self, config=None):
            captured["config"] = config

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "main-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://main.example/v1")
    monkeypatch.setenv("MEM0_EMBEDDER_PROVIDER", "ollama")
    monkeypatch.setenv("MEM0_EMBEDDER_MODEL", "bge-m3")
    monkeypatch.setenv("MEM0_EMBEDDER_API_KEY", "embedder-key")
    monkeypatch.setenv("MEM0_EMBEDDER_BASE_URL", "https://embedder.example/v1")

    with patch.dict(
        "sys.modules",
        {
            "mem0": SimpleNamespace(Memory=FakeMemory),
            "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
        },
    ):
        memory.get_memory_store({"memory": {}})

    assert captured["config"]["embedder"] == {
        "provider": "ollama",
        "config": {
            "model": "bge-m3",
            "api_key": "embedder-key",
            "base_url": "https://embedder.example/v1",
        },
    }


def test_get_memory_store_embedder_falls_back_to_openai_connection_env(monkeypatch):
    captured = {}

    class FakeMemory:
        def __init__(self, config=None):
            captured["config"] = config

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "shared-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://shared.example/v1")
    monkeypatch.setenv("MEM0_EMBEDDER_PROVIDER", "openai")
    monkeypatch.setenv("MEM0_EMBEDDER_MODEL", "text-embedding-3-large")
    monkeypatch.delenv("MEM0_EMBEDDER_API_KEY", raising=False)
    monkeypatch.delenv("MEM0_EMBEDDER_BASE_URL", raising=False)

    with patch.dict(
        "sys.modules",
        {
            "mem0": SimpleNamespace(Memory=FakeMemory),
            "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
        },
    ):
        memory.get_memory_store({"memory": {}})

    assert captured["config"]["embedder"] == {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-large",
            "api_key": "shared-key",
            "base_url": "https://shared.example/v1",
        },
    }
