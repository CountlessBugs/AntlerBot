import asyncio
import logging
import os
import sys
from pathlib import Path
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


def test_trim_relations_respects_context_max_relations():
    relations = [
        {"source": "A", "relationship": "关联", "destination": "B"},
        {"source": "B", "relationship": "目标", "destination": "C"},
    ]

    trimmed = memory._trim_relations(relations, 1)

    assert trimmed == [{"source": "A", "relationship": "关联", "destination": "B"}]


def test_format_recall_result_omits_relation_section_when_relations_are_empty():
    text = memory.format_recall_result(
        [{"memory": "用户正在做 AntlerBot 长期记忆系统"}],
        effort_label="中等",
        relations=[],
    )

    assert "记忆：" in text
    assert "联想关系：" not in text


def test_format_recall_result_includes_memory_and_relation_sections_in_chinese():
    results = [{"memory": "用户正在做 AntlerBot 长期记忆系统"}]
    relations = [
        {"source": "AntlerBot", "relationship": "关联", "destination": "长期记忆系统"},
        {"source": "长期记忆系统", "relationship": "目标", "destination": "更像真实的人"},
    ]

    text = memory.format_recall_result(results, effort_label="中等", relations=relations)

    assert "记忆：" in text
    assert "联想关系：" in text
    assert "- 用户正在做 AntlerBot 长期记忆系统" in text
    assert "- AntlerBot -[关联]-> 长期记忆系统" in text
    assert "- 长期记忆系统 -[目标]-> 更像真实的人" in text


def test_format_recall_result_drops_malformed_relations_without_dropping_memory_section():
    text = memory.format_recall_result(
        [{"memory": "用户正在做 AntlerBot 长期记忆系统"}],
        effort_label="中等",
        relations=[{"source": "AntlerBot", "relationship": "关联"}],
    )

    assert "记忆：" in text
    assert "- 用户正在做 AntlerBot 长期记忆系统" in text
    assert "联想关系：" not in text


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


def test_build_auto_recall_system_message_includes_relations_when_graph_auto_recall_enabled():
    class FakeStore:
        def search(self, query, **kwargs):
            return {
                "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.9}],
                "relations": [{"source": "bot", "relationship": "目标", "destination": "真实的人类式记忆"}],
            }

    memory.reset_counted_memory_ids()
    memory.reset_context_locked_memory_ids()
    history = [HumanMessage("你好")]
    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "auto_recall_query_token_limit": 50,
            "auto_recall_score_threshold": 0.5,
            "auto_recall_max_memories": 5,
            "auto_recall_system_prefix": "前缀",
            "graph": {"enabled": True, "auto_recall_enabled": True, "context_max_relations": 8},
        }
    }

    with patch("src.agent.memory.get_memory_store", return_value=FakeStore()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        message = memory.build_auto_recall_system_message(history, settings)

    assert message is not None
    assert "记忆：" in message.content
    assert "联想关系：" in message.content


def test_build_auto_recall_system_message_omits_relations_when_graph_auto_recall_disabled():
    class FakeStore:
        def search(self, query, **kwargs):
            return {
                "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.9}],
                "relations": [{"source": "bot", "relationship": "目标", "destination": "真实的人类式记忆"}],
            }

    memory.reset_counted_memory_ids()
    memory.reset_context_locked_memory_ids()
    history = [HumanMessage("你好")]
    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "auto_recall_query_token_limit": 50,
            "auto_recall_score_threshold": 0.5,
            "auto_recall_max_memories": 5,
            "auto_recall_system_prefix": "前缀",
            "graph": {"enabled": True, "auto_recall_enabled": False, "context_max_relations": 8},
        }
    }

    with patch("src.agent.memory.get_memory_store", return_value=FakeStore()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        message = memory.build_auto_recall_system_message(history, settings)

    assert message is not None
    assert "记忆：" in message.content
    assert "联想关系：" not in message.content


def test_build_auto_recall_system_message_uses_graph_context_prefix_when_provided():
    class FakeStore:
        def search(self, query, **kwargs):
            return {
                "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.9}],
                "relations": [{"source": "bot", "relationship": "目标", "destination": "真实的人类式记忆"}],
            }

    memory.reset_counted_memory_ids()
    memory.reset_context_locked_memory_ids()
    history = [HumanMessage("你好")]
    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "auto_recall_query_token_limit": 50,
            "auto_recall_score_threshold": 0.5,
            "auto_recall_max_memories": 5,
            "auto_recall_system_prefix": "前缀",
            "graph": {
                "enabled": True,
                "auto_recall_enabled": True,
                "context_max_relations": 8,
                "context_prefix": "以下是图联想提示：",
            },
        }
    }

    with patch("src.agent.memory.get_memory_store", return_value=FakeStore()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        message = memory.build_auto_recall_system_message(history, settings)

    assert message is not None
    assert "以下是图联想提示：" in message.content
    assert "联想关系：" not in message.content


def test_build_auto_recall_system_message_keeps_memory_section_when_relations_are_malformed():
    class FakeStore:
        def search(self, query, **kwargs):
            return {
                "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.9}],
                "relations": [{"source": "bot", "relationship": "目标"}],
            }

    memory.reset_counted_memory_ids()
    memory.reset_context_locked_memory_ids()
    history = [HumanMessage("你好")]
    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "auto_recall_query_token_limit": 50,
            "auto_recall_score_threshold": 0.5,
            "auto_recall_max_memories": 5,
            "auto_recall_system_prefix": "前缀",
            "graph": {"enabled": True, "auto_recall_enabled": True, "context_max_relations": 8},
        }
    }

    with patch("src.agent.memory.get_memory_store", return_value=FakeStore()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        message = memory.build_auto_recall_system_message(history, settings)

    assert message is not None
    assert "记忆：" in message.content
    assert "联想关系：" not in message.content


def test_build_auto_recall_system_message_returns_none_when_filtered_memories_are_empty_even_if_relations_exist():
    class FakeStore:
        def search(self, query, **kwargs):
            return {
                "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.1}],
                "relations": [{"source": "bot", "relationship": "目标", "destination": "真实的人类式记忆"}],
            }

    memory.reset_counted_memory_ids()
    memory.reset_context_locked_memory_ids()
    history = [HumanMessage("你好")]
    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "auto_recall_query_token_limit": 50,
            "auto_recall_score_threshold": 0.5,
            "auto_recall_max_memories": 5,
            "auto_recall_system_prefix": "前缀",
            "graph": {"enabled": True, "auto_recall_enabled": True, "context_max_relations": 8},
        }
    }

    with patch("src.agent.memory.get_memory_store", return_value=FakeStore()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        message = memory.build_auto_recall_system_message(history, settings)

    assert message is None


def test_filter_search_results_excludes_context_locked_ids():
    results = [
        {"id": "a", "memory": "A", "score": 0.9},
        {"id": "b", "memory": "B", "score": 0.8},
    ]
    filtered = memory.filter_search_results(results, threshold=0.0, max_memories=5, blocked_ids={"a"})
    assert [item["id"] for item in filtered] == ["b"]


def test_resolve_vector_store_config_resolves_default_qdrant_path_to_stable_absolute_path():
    settings = {"memory": {"vector_store": {"provider": "qdrant", "config": {}}}}

    config = memory._resolve_vector_store_config(settings)

    assert config["provider"] == "qdrant"
    assert config["config"]["collection_name"] == "mem0"
    assert config["config"]["on_disk"] is True
    assert Path(config["config"]["path"]).is_absolute()
    assert Path(config["config"]["path"]).as_posix().endswith("data/mem0/qdrant")


def test_resolve_vector_store_config_preserves_absolute_qdrant_path():
    absolute_path = str(Path("D:/custom/qdrant") if os.name == "nt" else Path("/custom/qdrant"))
    settings = {
        "memory": {
            "vector_store": {
                "provider": "qdrant",
                "config": {"path": absolute_path, "collection_name": "custom", "on_disk": False},
            }
        }
    }

    config = memory._resolve_vector_store_config(settings)

    assert config["config"]["path"] == absolute_path
    assert config["config"]["collection_name"] == "custom"
    assert config["config"]["on_disk"] is False


def test_get_memory_store_includes_vector_store_when_graph_disabled(monkeypatch):
    memory._MEMORY_STORE = None
    captured = {}

    class FakeMemoryConfig:
        def __init__(self, **kwargs):
            captured["config_kwargs"] = kwargs
            self.kwargs = kwargs

    class FakeMemory:
        def __init__(self, config):
            self.config = config
            self.vector_store = None

    settings = {
        "memory": {
            "graph": {"enabled": False},
            "vector_store": {
                "provider": "qdrant",
                "config": {"collection_name": "mem0", "path": "data/mem0/qdrant", "on_disk": True},
            },
        }
    }

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")

    with patch("mem0.Memory", FakeMemory), \
         patch("mem0.configs.base.MemoryConfig", FakeMemoryConfig):
        store = memory.get_memory_store(settings)

    assert store is not None
    assert captured["config_kwargs"]["vector_store"]["provider"] == "qdrant"
    assert Path(captured["config_kwargs"]["vector_store"]["config"]["path"]).is_absolute()
    assert Path(captured["config_kwargs"]["vector_store"]["config"]["path"]).as_posix().endswith("data/mem0/qdrant")


def test_get_memory_store_includes_graph_store_and_vector_store_when_graph_enabled(monkeypatch):
    memory._MEMORY_STORE = None
    captured = {}

    class FakeMemoryConfig:
        def __init__(self, **kwargs):
            captured["config_kwargs"] = kwargs
            self.kwargs = kwargs

    class FakeMemory:
        def __init__(self, config):
            self.config = config
            self.vector_store = None

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
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {"collection_name": "mem0", "path": "data/mem0/qdrant", "on_disk": True},
            },
        }
    }

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")

    monkeypatch.setattr(memory, "_verify_graph_connectivity", lambda provider, config: None)

    with patch("importlib.import_module", return_value=SimpleNamespace()), \
         patch.dict(
             sys.modules,
             {
                 "mem0": SimpleNamespace(Memory=FakeMemory),
                 "mem0.configs.base": SimpleNamespace(MemoryConfig=FakeMemoryConfig),
             },
         ):
        store = memory.get_memory_store(settings)

    assert store is not None
    assert "graph_store" in captured["config_kwargs"]
    assert "vector_store" in captured["config_kwargs"]
    assert captured["config_kwargs"]["graph_store"]["provider"] == "neo4j"
    assert captured["config_kwargs"]["vector_store"]["provider"] == "qdrant"


def test_get_memory_store_falls_back_to_same_vector_store_when_graph_init_fails(monkeypatch, caplog):
    memory._MEMORY_STORE = None
    attempts = []

    class FakeMemoryConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeMemory:
        def __init__(self, config):
            attempts.append(config.kwargs)
            if "graph_store" in config.kwargs:
                raise RuntimeError("graph init failed")
            self.config = config
            self.vector_store = None

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
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {"collection_name": "mem0", "path": "data/mem0/qdrant", "on_disk": True},
            },
        }
    }

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")

    monkeypatch.setattr(memory, "_verify_graph_connectivity", lambda provider, config: None)

    with patch("importlib.import_module", return_value=SimpleNamespace()), \
         patch.dict(
             sys.modules,
             {
                 "mem0": SimpleNamespace(Memory=FakeMemory),
                 "mem0.configs.base": SimpleNamespace(MemoryConfig=FakeMemoryConfig),
             },
         ), \
         caplog.at_level(logging.WARNING):
        store = memory.get_memory_store(settings)

    assert store is not None
    assert len(attempts) == 2
    assert "graph_store" in attempts[0]
    assert "vector_store" in attempts[0]
    assert "graph_store" not in attempts[1]
    assert attempts[1]["vector_store"] == attempts[0]["vector_store"]
    assert "/tmp/qdrant" not in str(attempts[1]["vector_store"])


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


class OSSUpdateOnlyMemoryStore:
    def __init__(self):
        self.updated = None

    def get(self, memory_id=None, **kwargs):
        return {
            "id": memory_id or "mem-1",
            "memory": "记忆文本",
            "agent_id": "antlerbot",
            "metadata": {"recall_count": 1, "tag": "x"},
        }

    def update(self, memory_id, text=None, metadata=None):
        if not isinstance(text, str):
            raise TypeError("OSS mem0 update expects text string")
        self.updated = {
            "memory_id": memory_id,
            "text": text,
            "metadata": metadata,
        }
        return {"message": "ok"}


class OSSDummyMemoryStore:
    def __init__(self):
        self.updated = None

    def get(self, memory_id=None, **kwargs):
        return {
            "id": memory_id or "mem-1",
            "memory": "记忆文本",
            "agent_id": "antlerbot",
            "metadata": {"recall_count": 1, "tag": "x"},
        }

    def update(self, memory_id, data):
        if not isinstance(data, str):
            raise TypeError("OSS mem0 update expects string data")
        self.updated = {"memory_id": memory_id, "data": data}
        return {"message": "ok"}

    def _update_memory(self, memory_id, data, existing_embeddings, metadata=None):
        self.updated = {
            "memory_id": memory_id,
            "data": data,
            "existing_embeddings": existing_embeddings,
            "metadata": metadata,
        }
        return memory_id



def test_try_update_memory_recall_metadata_supports_oss_mem0_update_contract():
    store = OSSDummyMemoryStore()

    assert memory.try_update_memory_recall_metadata(store, "mem-1", "2026-03-08T12:00:00Z") is True
    assert store.updated["memory_id"] == "mem-1"
    assert store.updated["data"] == "记忆文本"
    assert store.updated["existing_embeddings"] == {}
    assert store.updated["metadata"]["recall_count"] == 2
    assert store.updated["metadata"]["last_recalled_at"] == "2026-03-08T12:00:00Z"
    assert store.updated["metadata"]["tag"] == "x"



def test_try_update_memory_recall_metadata_supports_oss_public_update_contract_when_internal_method_is_absent():
    store = OSSUpdateOnlyMemoryStore()

    assert memory.try_update_memory_recall_metadata(store, "mem-1", "2026-03-08T12:00:00Z") is True
    assert store.updated["memory_id"] == "mem-1"
    assert store.updated["text"] == "记忆文本"
    assert store.updated["metadata"]["recall_count"] == 2
    assert store.updated["metadata"]["last_recalled_at"] == "2026-03-08T12:00:00Z"
    assert store.updated["metadata"]["tag"] == "x"



def test_try_update_memory_recall_metadata_returns_false_when_get_result_is_not_mapping():
    store = DummyMemoryStore(["not-a-dict"])
    assert memory.try_update_memory_recall_metadata(store, "mem-1", "2026-03-08T12:00:00Z") is False
    assert store.updated is None


class DummyQdrantClient:
    def __init__(self):
        self.payload_calls = []

    def set_payload(self, collection_name, payload, points):
        self.payload_calls.append(
            {"collection_name": collection_name, "payload": payload, "points": points}
        )


class DummyQdrantVectorStore:
    def __init__(self):
        self.client = DummyQdrantClient()
        self.collection_name = "memories"
        self.update_calls = []

    def update(self, vector_id, vector=None, payload=None):
        if vector is None:
            raise TypeError("PointStruct requires a non-null vector")
        self.update_calls.append({"vector_id": vector_id, "vector": vector, "payload": payload})



def test_patch_vector_store_update_handles_payload_only_updates_for_qdrant():
    vector_store = DummyQdrantVectorStore()

    memory._patch_vector_store_update_for_payload_only(vector_store)
    vector_store.update("mem-1", vector=None, payload={"agent_id": "antlerbot"})

    assert vector_store.client.payload_calls == [
        {
            "collection_name": "memories",
            "payload": {"agent_id": "antlerbot"},
            "points": ["mem-1"],
        }
    ]



def test_get_memory_store_patches_qdrant_payload_only_updates(monkeypatch):
    class FakeVectorStore(DummyQdrantVectorStore):
        pass

    class FakeMemory:
        def __init__(self, config=None):
            self.vector_store = FakeVectorStore()

    class FakeMemoryConfig(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(__import__("sys").modules, "mem0", SimpleNamespace(Memory=FakeMemory))
    monkeypatch.setitem(__import__("sys").modules, "mem0.configs.base", SimpleNamespace(MemoryConfig=FakeMemoryConfig))

    store = memory.get_memory_store({"memory": {"graph": {"enabled": False}}})
    store.vector_store.update("mem-1", vector=None, payload={"agent_id": "antlerbot"})

    assert store.vector_store.client.payload_calls == [
        {
            "collection_name": "memories",
            "payload": {"agent_id": "antlerbot"},
            "points": ["mem-1"],
        }
    ]



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


def test_store_summary_async_uses_summary_only_with_graph_enabled():
    class FakeStore:
        def __init__(self):
            self.calls = []

        def add(self, messages, agent_id=None, user_id=None):
            self.calls.append({"messages": messages, "agent_id": agent_id, "user_id": user_id})

    store = FakeStore()
    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "graph": {"enabled": True, "provider": "neo4j", "config": {"url": "bolt://localhost:7687"}},
        }
    }

    with patch("src.agent.memory.get_memory_store", return_value=store):
        asyncio.run(memory.store_summary_async("总结文本", settings))

    assert store.calls == [
        {
            "messages": [{"role": "user", "content": "总结文本"}],
            "agent_id": "antlerbot",
            "user_id": "antlerbot",
        }
    ]


def test_manual_recall_includes_relations_when_graph_manual_recall_enabled():
    class FakeStore:
        def search(self, query, **kwargs):
            return {
                "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.9}],
                "relations": [{"source": "bot", "relationship": "目标", "destination": "真实的人类式记忆"}],
            }

    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "graph": {"enabled": True, "manual_recall_enabled": True, "context_max_relations": 8},
            "recall_medium_score_threshold": 0.7,
            "recall_medium_max_memories": 6,
        }
    }

    memory.reset_counted_memory_ids()
    memory.reset_context_locked_memory_ids()
    with patch("src.agent.memory.get_memory_store", return_value=FakeStore()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        result = memory.build_recall_tool(settings).func("用户目标", "medium")

    assert "记忆：" in result
    assert "联想关系：" in result
    assert "- bot -[目标]-> 真实的人类式记忆" in result


def test_manual_recall_remains_memory_only_when_graph_is_disabled():
    class FakeStore:
        def search(self, query, **kwargs):
            return {
                "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.9}],
                "relations": [{"source": "bot", "relationship": "目标", "destination": "真实的人类式记忆"}],
            }

    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "graph": {"enabled": False, "manual_recall_enabled": True, "context_max_relations": 8},
            "recall_medium_score_threshold": 0.7,
            "recall_medium_max_memories": 6,
        }
    }

    memory.reset_counted_memory_ids()
    memory.reset_context_locked_memory_ids()
    with patch("src.agent.memory.get_memory_store", return_value=FakeStore()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        result = memory.build_recall_tool(settings).func("用户目标", "medium")

    assert "记忆：" in result
    assert "联想关系：" not in result


def test_manual_recall_keeps_memory_section_when_relations_are_malformed():
    class FakeStore:
        def search(self, query, **kwargs):
            return {
                "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.9}],
                "relations": [{"source": "bot", "relationship": "目标"}],
            }

    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "graph": {"enabled": True, "manual_recall_enabled": True, "context_max_relations": 8},
            "recall_medium_score_threshold": 0.7,
            "recall_medium_max_memories": 6,
        }
    }

    memory.reset_counted_memory_ids()
    memory.reset_context_locked_memory_ids()
    with patch("src.agent.memory.get_memory_store", return_value=FakeStore()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        result = memory.build_recall_tool(settings).func("用户目标", "medium")

    assert "记忆：" in result
    assert "联想关系：" not in result


def test_manual_recall_enforces_context_max_relations():
    class FakeStore:
        def search(self, query, **kwargs):
            return {
                "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.9}],
                "relations": [
                    {"source": "bot", "relationship": "目标", "destination": "真实的人类式记忆"},
                    {"source": "长期记忆", "relationship": "支持", "destination": "更自然回复"},
                ],
            }

    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "graph": {"enabled": True, "manual_recall_enabled": True, "context_max_relations": 1},
            "recall_medium_score_threshold": 0.7,
            "recall_medium_max_memories": 6,
        }
    }

    memory.reset_counted_memory_ids()
    memory.reset_context_locked_memory_ids()
    with patch("src.agent.memory.get_memory_store", return_value=FakeStore()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        result = memory.build_recall_tool(settings).func("用户目标", "medium")

    assert result.count("-[") == 1


def test_manual_recall_uses_graph_context_prefix_when_provided():
    class FakeStore:
        def search(self, query, **kwargs):
            return {
                "results": [{"id": "1", "memory": "用户想让 bot 更像真实的人", "score": 0.9}],
                "relations": [{"source": "bot", "relationship": "目标", "destination": "真实的人类式记忆"}],
            }

    settings = {
        "memory": {
            "agent_id": "antlerbot",
            "graph": {
                "enabled": True,
                "manual_recall_enabled": True,
                "context_max_relations": 8,
                "context_prefix": "以下是图联想提示：",
            },
            "recall_medium_score_threshold": 0.7,
            "recall_medium_max_memories": 6,
        }
    }

    memory.reset_counted_memory_ids()
    memory.reset_context_locked_memory_ids()
    with patch("src.agent.memory.get_memory_store", return_value=FakeStore()), \
         patch("src.agent.memory.try_update_memory_recall_metadata", return_value=True):
        result = memory.build_recall_tool(settings).func("用户目标", "medium")

    assert "以下是图联想提示：" in result
    assert "联想关系：" not in result


def test_get_memory_store_rejects_graph_max_hops_other_than_one(monkeypatch):
    monkeypatch.setattr(memory, "_MEMORY_STORE", None)

    settings = {
        "memory": {
            "graph": {
                "enabled": True,
                "provider": "neo4j",
                "config": {"url": "bolt://localhost:7687"},
                "max_hops": 2,
            }
        }
    }

    try:
        memory._resolve_graph_store_config(settings)
    except RuntimeError as exc:
        assert "max_hops" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for unsupported max_hops")



def test_resolve_graph_store_config_normalizes_numeric_graph_credentials_to_strings():
    settings = {
        "memory": {
            "graph": {
                "enabled": True,
                "provider": "neo4j",
                "config": {
                    "url": "bolt://localhost:7687",
                    "username": "Antler",
                    "password": 347,
                    "database": "neo4j",
                },
            }
        }
    }

    with patch.object(memory.importlib, "import_module"), patch.object(
        memory, "_verify_graph_connectivity"
    ):
        graph_store = memory._resolve_graph_store_config(settings)

    assert graph_store == {
        "provider": "neo4j",
        "config": {
            "url": "bolt://localhost:7687",
            "username": "Antler",
            "password": "347",
            "database": "neo4j",
        },
    }



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
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("OPENAI_API_KEY", "main-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://main.example/v1")
    monkeypatch.setenv("MEM0_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("MEM0_LLM_MODEL", "deepseek-chat")
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
        "provider": "deepseek",
        "config": {
            "model": "deepseek-chat",
            "api_key": "mem0-key",
            "deepseek_base_url": "https://mem0.example/v1",
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
            "openai_base_url": "https://openai.example/v1",
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
            "ollama_base_url": "https://embedder.example/v1",
        },
    }


def test_get_memory_store_includes_graph_store_when_enabled(monkeypatch):
    captured = {}

    class FakeMemory:
        def __init__(self, config=None):
            captured["config"] = config

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

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

    monkeypatch.setattr(memory, "_verify_graph_connectivity", lambda provider, config: None)

    with patch("importlib.import_module", return_value=SimpleNamespace()), \
         patch.dict(
             sys.modules,
             {
                 "mem0": SimpleNamespace(Memory=FakeMemory),
                 "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
             },
         ):
        memory.get_memory_store(settings)

    assert captured["config"]["graph_store"] == {
        "provider": "neo4j",
        "config": {
            "url": "bolt://localhost:7687",
            "username": "neo4j",
            "password": "secret",
            "database": "neo4j",
        },
    }


def test_get_memory_store_falls_back_when_graph_init_fails(monkeypatch, caplog):
    init_configs = []

    class FakeMemory:
        def __init__(self, config=None):
            init_configs.append(config)
            if config.get("graph_store") is not None:
                raise RuntimeError("graph init failed")

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

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

    monkeypatch.setattr(memory, "_verify_graph_connectivity", lambda provider, config: None)

    with patch("importlib.import_module", return_value=SimpleNamespace()), \
         patch.dict(
             sys.modules,
             {
                 "mem0": SimpleNamespace(Memory=FakeMemory),
                 "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
             },
         ), caplog.at_level(logging.WARNING):
        store = memory.get_memory_store(settings)

    assert store is not None
    assert len(init_configs) == 2
    assert any("graph" in record.message.lower() for record in caplog.records)
    assert "graph_store" not in init_configs[1]



def test_get_memory_store_uses_persistent_vector_store_path_when_graph_dependency_is_missing(monkeypatch, caplog):
    init_configs = []

    class FakeMemory:
        def __init__(self, config=None):
            init_configs.append(config)

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = {
        "memory": {
            "agent_id": "test-agent",
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

    def fake_import_module(name, package=None):
        if name == "mem0.memory.graph_memory":
            raise ModuleNotFoundError("No module named 'langchain_neo4j'")
        return __import__(name, fromlist=["*"])

    with patch("importlib.import_module", side_effect=fake_import_module), \
         patch.dict(
             sys.modules,
             {
                 "mem0": SimpleNamespace(Memory=FakeMemory),
                 "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
             },
         ), \
         caplog.at_level(logging.WARNING):
        store = memory.get_memory_store(settings)

    assert store is not None
    assert len(init_configs) == 1
    assert init_configs[0]["vector_store"]["provider"] == "qdrant"
    assert init_configs[0]["vector_store"]["config"]["path"] != "/tmp/qdrant"
    assert Path(init_configs[0]["vector_store"]["config"]["path"]).is_absolute()
    assert Path(init_configs[0]["vector_store"]["config"]["path"]).as_posix().endswith("data/mem0/qdrant")



def test_get_memory_store_falls_back_when_graph_config_is_invalid_before_mem0_init(monkeypatch, caplog):
    init_configs = []

    class FakeMemory:
        def __init__(self, config=None):
            init_configs.append(config)

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = {
        "memory": {
            "graph": {
                "enabled": True,
                "provider": "neo4j",
                "config": {"db": ":memory:"},
            }
        }
    }

    with patch.dict(
        "sys.modules",
        {
            "mem0": SimpleNamespace(Memory=FakeMemory),
            "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
        },
    ), caplog.at_level(logging.WARNING):
        store = memory.get_memory_store(settings)

    assert store is not None
    assert len(init_configs) == 1
    assert "graph_store" not in init_configs[0]
    assert any("graph" in record.message.lower() for record in caplog.records)



def test_get_memory_store_skips_graph_init_when_graph_dependency_is_missing(monkeypatch, caplog):
    init_configs = []

    class FakeMemory:
        def __init__(self, config=None):
            init_configs.append(config)
            self.vector_store = None

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

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

    def fake_import_module(name, package=None):
        if name == "mem0.memory.graph_memory":
            raise ImportError("rank_bm25 is not installed")
        return __import__(name, fromlist=["*"])

    with patch("importlib.import_module", side_effect=fake_import_module), \
         patch.dict(
             sys.modules,
             {
                 "mem0": SimpleNamespace(Memory=FakeMemory),
                 "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
             },
         ), \
         caplog.at_level(logging.WARNING):
        store = memory.get_memory_store(settings)

    assert store is not None
    assert len(init_configs) == 1
    assert "graph_store" not in init_configs[0]
    assert any("graph" in record.message.lower() for record in caplog.records)



def test_get_memory_store_skips_graph_init_when_graph_module_dependency_is_missing(monkeypatch, caplog):
    init_configs = []

    class FakeMemory:
        def __init__(self, config=None):
            init_configs.append(config)
            self.vector_store = None

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

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

    def fake_import_module(name, package=None):
        if name == "mem0.memory.graph_memory":
            raise ImportError("rank_bm25 is not installed")
        return __import__(name, fromlist=["*"])

    with patch("importlib.import_module", side_effect=fake_import_module), \
         patch.dict(
             sys.modules,
             {
                 "mem0": SimpleNamespace(Memory=FakeMemory),
                 "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
             },
         ), \
         caplog.at_level(logging.WARNING):
        store = memory.get_memory_store(settings)

    assert store is not None
    assert len(init_configs) == 1
    assert "graph_store" not in init_configs[0]
    assert any("graph" in record.message.lower() for record in caplog.records)



def test_patch_mem0_neo4jgraph_signature_compat_maps_fourth_positional_arg_to_database(monkeypatch):
    captured = {}

    class FakeNeo4jGraph:
        def __init__(
            self,
            url=None,
            username=None,
            password=None,
            token=None,
            database=None,
            refresh_schema=True,
            driver_config=None,
            **kwargs,
        ):
            captured["url"] = url
            captured["username"] = username
            captured["password"] = password
            captured["token"] = token
            captured["database"] = database
            captured["refresh_schema"] = refresh_schema
            captured["driver_config"] = driver_config
            captured["kwargs"] = kwargs

    fake_module = SimpleNamespace(Neo4jGraph=FakeNeo4jGraph)
    monkeypatch.setitem(sys.modules, "mem0.memory.graph_memory", fake_module)

    memory._patch_mem0_neo4jgraph_signature_compat()

    fake_module.Neo4jGraph(
        "bolt://localhost:7687",
        "neo4j",
        "secret",
        "neo4j",
        refresh_schema=False,
        driver_config={"notifications_min_severity": "OFF"},
    )

    assert captured == {
        "url": "bolt://localhost:7687",
        "username": "neo4j",
        "password": "secret",
        "token": None,
        "database": "neo4j",
        "refresh_schema": False,
        "driver_config": {"notifications_min_severity": "OFF"},
        "kwargs": {},
    }



def test_verify_graph_connectivity_does_not_touch_undefined_store_on_success(monkeypatch):
    captured = {}

    class FakeDriver:
        def verify_connectivity(self):
            captured["verified"] = True

        def close(self):
            captured["closed"] = True

    class FakeGraphDatabase:
        @staticmethod
        def driver(url, auth=None):
            captured["url"] = url
            captured["auth"] = auth
            return FakeDriver()

    monkeypatch.setitem(sys.modules, "neo4j", SimpleNamespace(GraphDatabase=FakeGraphDatabase))

    memory._verify_graph_connectivity(
        "neo4j",
        {
            "url": "bolt://localhost:7687",
            "username": "neo4j",
            "password": "secret",
        },
    )

    assert captured == {
        "url": "bolt://localhost:7687",
        "auth": ("neo4j", "secret"),
        "verified": True,
        "closed": True,
    }



def test_get_memory_store_skips_graph_init_when_neo4j_connectivity_check_fails(monkeypatch, caplog):
    init_configs = []

    class FakeMemory:
        def __init__(self, config=None):
            init_configs.append(config)
            self.vector_store = None

    monkeypatch.setattr(memory, "_MEMORY_STORE", None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

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

    class FakeDriver:
        def verify_connectivity(self):
            raise RuntimeError("connect refused")

        def close(self):
            return None

    with patch("importlib.import_module", return_value=SimpleNamespace()), \
         patch.dict(
             sys.modules,
             {
                 "neo4j": SimpleNamespace(GraphDatabase=SimpleNamespace(driver=lambda *args, **kwargs: FakeDriver())),
                 "mem0": SimpleNamespace(Memory=FakeMemory),
                 "mem0.configs.base": SimpleNamespace(MemoryConfig=lambda **kwargs: kwargs),
             },
         ), \
         caplog.at_level(logging.WARNING):
        store = memory.get_memory_store(settings)

    assert store is not None
    assert len(init_configs) == 1
    assert "graph_store" not in init_configs[0]
    assert any("graph" in record.message.lower() for record in caplog.records)



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



def test_build_auto_recall_system_message_passes_user_id_for_graph_search(monkeypatch):
    captured = {}

    class FakeStore:
        def search(self, query, **kwargs):
            captured["query"] = query
            captured["kwargs"] = kwargs
            return {
                "results": [{"id": "m1", "memory": "用户喜欢篮球", "score": 0.95}],
                "relations": [],
            }

    monkeypatch.setattr(memory, "get_memory_store", lambda settings: FakeStore())
    monkeypatch.setattr(memory, "try_update_memory_recall_metadata", lambda store, memory_id, recalled_at: None)
    monkeypatch.setattr(memory, "get_context_locked_memory_ids", lambda: set())
    monkeypatch.setattr(memory, "mark_counted_memory_ids", lambda results: None)

    message = memory.build_auto_recall_system_message(
        [HumanMessage("我最近喜欢打篮球")],
        {
            "memory": {
                "agent_id": "test-agent",
                "graph": {"enabled": True, "auto_recall_enabled": True},
            }
        },
    )

    assert message is not None
    assert captured["kwargs"]["agent_id"] == "test-agent"
    assert captured["kwargs"]["user_id"] == "test-agent"



def test_store_summary_async_passes_user_id_for_graph_add(monkeypatch):
    captured = {}

    class FakeStore:
        def add(self, messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs

    monkeypatch.setattr(memory, "get_memory_store", lambda settings: FakeStore())

    asyncio.run(
        memory.store_summary_async(
            "测试摘要",
            {"memory": {"agent_id": "test-agent", "graph": {"enabled": True}}},
        )
    )

    assert captured["messages"] == [{"role": "user", "content": "测试摘要"}]
    assert captured["kwargs"]["agent_id"] == "test-agent"
    assert captured["kwargs"]["user_id"] == "test-agent"
