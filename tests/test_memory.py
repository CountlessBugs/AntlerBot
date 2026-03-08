import asyncio
import logging
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
    filtered = memory.filter_search_results(results, threshold=0.8, max_memories=2, seen_ids={"a"})
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


def test_store_summary_async_logs_failure(caplog):
    with patch("src.agent.memory.get_memory_client", side_effect=RuntimeError("boom")), \
         caplog.at_level(logging.WARNING):
        asyncio.run(memory.store_summary_async("总结", {"memory": {"agent_id": "antlerbot"}}))
    assert any("mem0" in r.message.lower() for r in caplog.records)
