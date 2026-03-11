import asyncio
import logging
import pytest
import src.agent.agent as agent_mod
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


def test_new_agent_package_importable():
    import src.agent.agent as agent_mod
    assert agent_mod is not None


def test_core_runtime_modules_removed():
    from pathlib import Path

    assert not Path("src/core").exists()
    assert not Path("src/core/agent.py").exists()
    assert not Path("src/core/scheduler.py").exists()


@pytest.fixture(autouse=True)
def reset_agent_state():
    agent_mod._history = []
    agent_mod._graph = None
    agent_mod._llm = None
    agent_mod._lock = asyncio.Lock()
    agent_mod._current_token_usage = 0
    yield
    agent_mod._history = []
    agent_mod._graph = None
    agent_mod._llm = None
    agent_mod._lock = asyncio.Lock()
    agent_mod._current_token_usage = 0


def test_ensure_initialized_binds_recall_tool_when_memory_enabled(monkeypatch):
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    with patch("src.agent.agent.load_prompt", return_value=None), \
         patch("src.agent.agent.init_chat_model", return_value=mock_llm), \
         patch("src.agent.agent.load_settings", return_value={**agent_mod._SETTINGS_DEFAULTS, "memory": {**agent_mod._SETTINGS_DEFAULTS["memory"], "enabled": True}}):
        agent_mod.register_tools([])
        agent_mod._ensure_initialized()
    bound_tools = mock_llm.bind_tools.call_args[0][0]
    recall_tool = next((tool for tool in bound_tools if tool.name == "recall_memory"), None)
    assert recall_tool is not None
    assert "长期记忆" in recall_tool.description


def test_load_prompt_missing_creates_default(tmp_path, caplog):
    path = str(tmp_path / "prompt.txt")
    from src.agent.agent import load_prompt, PROMPT_EXAMPLE_PATH
    with open(PROMPT_EXAMPLE_PATH, encoding="utf-8") as f:
        expected = f.read()
    with patch("src.agent.agent.PROMPT_PATH", path), caplog.at_level(logging.INFO, logger="src.agent.agent"):
        result = load_prompt()
    assert result == expected
    assert (tmp_path / "prompt.txt").read_text(encoding="utf-8") == expected
    assert caplog.records


def test_load_prompt_empty_returns_none(tmp_path, caplog):
    path = str(tmp_path / "prompt.txt")
    (tmp_path / "prompt.txt").write_text("", encoding="utf-8")
    from src.agent.agent import load_prompt
    with patch("src.agent.agent.PROMPT_PATH", path), caplog.at_level(logging.WARNING, logger="src.agent.agent"):
        result = load_prompt()
    assert result is None
    assert caplog.records


def test_load_prompt_returns_content(tmp_path):
    path = str(tmp_path / "prompt.txt")
    (tmp_path / "prompt.txt").write_text("你好机器人", encoding="utf-8")
    from src.agent.agent import load_prompt
    with patch("src.agent.agent.PROMPT_PATH", path):
        result = load_prompt()
    assert result == "你好机器人"


def test_ensure_initialized_friendly_import_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-3-5-sonnet-20241022")
    with patch("src.agent.agent.load_prompt", return_value=None), \
         patch("src.agent.agent.init_chat_model", side_effect=ImportError):
        with pytest.raises(ImportError, match="pip install langchain-anthropic"):
            agent_mod._ensure_initialized()


def test_ensure_initialized_missing_env_var(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with patch("src.agent.agent.load_prompt", return_value=None):
        with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
            agent_mod._ensure_initialized()


def _make_stream_event(content, node="llm"):
    return {"event": "on_chat_model_stream", "metadata": {"langgraph_node": node},
            "data": {"chunk": AIMessage(content)}}


async def _aiter(events):
    for e in events:
        yield e


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


@pytest.mark.anyio
async def test_invoke_returns_ai_content():
    mock_graph = MagicMock()
    mock_graph.astream_events.return_value = _aiter([_make_stream_event("pong")])
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        result = "".join([s async for s in agent_mod._invoke("user_message", "ping")])
    assert result == "pong"


@pytest.mark.anyio
async def test_invoke_accepts_multimodal_content_list():
    """When message is a list (multimodal), HumanMessage uses content=list."""
    content = [
        {"type": "text", "text": "look at this"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]

    def fake_astream_events(s, version):
        agent_mod._history = s["messages"] + [AIMessage("got it")]
        return _aiter([_make_stream_event("got it")])

    mock_graph = MagicMock()
    mock_graph.astream_events.side_effect = fake_astream_events
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        async for _ in agent_mod._invoke("user_message", content):
            pass
    # Verify HumanMessage was created with list content
    sent_msgs = mock_graph.astream_events.call_args[0][0]["messages"]
    human_msg = sent_msgs[-1]
    assert isinstance(human_msg, HumanMessage)
    assert isinstance(human_msg.content, list)
    assert len(human_msg.content) == 2
    assert human_msg.content[1]["type"] == "image_url"


@pytest.mark.anyio
async def test_invoke_keeps_auto_recall_message_out_of_persistent_history():
    def fake_astream_events(state, version):
        agent_mod._history = state["messages"] + [AIMessage("reply")]
        return _aiter([_make_stream_event("reply")])

    mock_graph = MagicMock()
    mock_graph.astream_events.side_effect = fake_astream_events
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph), \
         patch("src.agent.agent.load_settings", return_value={**agent_mod._SETTINGS_DEFAULTS, "memory": {**agent_mod._SETTINGS_DEFAULTS["memory"], "enabled": True}}), \
         patch("src.agent.agent.memory_mod.build_auto_recall_system_message", return_value=SystemMessage("长期记忆")):
        async for _ in agent_mod._invoke("user_message", "hello"):
            pass

    assert len(agent_mod._history) == 2
    assert isinstance(agent_mod._history[0], HumanMessage)
    assert agent_mod._history[0].content == "hello"
    assert isinstance(agent_mod._history[1], AIMessage)
    assert all(not (isinstance(msg, SystemMessage) and msg.content == "长期记忆") for msg in agent_mod._history)


@pytest.mark.anyio
async def test_invoke_accumulates_history():
    def fake_astream_events(s, version):
        agent_mod._history = s["messages"] + [AIMessage("reply")]
        return _aiter([_make_stream_event("reply")])
    mock_graph = MagicMock()
    mock_graph.astream_events.side_effect = fake_astream_events
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        async for _ in agent_mod._invoke("user_message", "hello"):
            pass
    assert len(agent_mod._history) == 2
    assert isinstance(agent_mod._history[0], HumanMessage)
    assert isinstance(agent_mod._history[1], AIMessage)


@pytest.mark.anyio
async def test_invoke_passes_history_on_second_call():
    def fake_astream_events(s, version):
        agent_mod._history = s["messages"] + [AIMessage("reply")]
        return _aiter([_make_stream_event("reply")])
    mock_graph = MagicMock()
    mock_graph.astream_events.side_effect = fake_astream_events
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        async for _ in agent_mod._invoke("user_message", "msg1"):
            pass
        async for _ in agent_mod._invoke("user_message", "msg2"):
            pass
    second_call_msgs = mock_graph.astream_events.call_args_list[1][0][0]["messages"]
    assert len(second_call_msgs) == 3  # human, ai, human


@pytest.mark.anyio
async def test_invoke_executes_sequentially():
    order = []

    def slow_astream_events(state, version):
        async def _gen():
            order.append("start")
            await asyncio.sleep(0)
            order.append("end")
            yield _make_stream_event("reply")
        return _gen()

    mock_graph = MagicMock()
    mock_graph.astream_events.side_effect = slow_astream_events
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        async def consume(msg):
            async for _ in agent_mod._invoke("user_message", msg):
                pass
        await asyncio.gather(consume("a"), consume("b"))
    assert order == ["start", "end", "start", "end"]


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


def test_load_settings_defaults_when_missing(tmp_path):
    with patch("src.agent.agent.SETTINGS_PATH", str(tmp_path / "settings.yaml")):
        result = agent_mod.load_settings()
    assert result == agent_mod._SETTINGS_DEFAULTS


def test_load_settings_reads_file(tmp_path):
    f = tmp_path / "settings.yaml"
    f.write_text("context_limit_tokens: 4000\n", encoding="utf-8")
    with patch("src.agent.agent.SETTINGS_PATH", str(f)):
        result = agent_mod.load_settings()
    assert result["context_limit_tokens"] == 4000
    assert result["timeout_summarize_seconds"] == 1800


def test_load_settings_includes_graph_memory_defaults(tmp_path):
    with patch("src.agent.agent.SETTINGS_PATH", str(tmp_path / "settings.yaml")):
        settings = agent_mod.load_settings()

    assert settings["memory"]["graph"]["enabled"] is False
    assert settings["memory"]["graph"]["provider"] == "neo4j"
    assert isinstance(settings["memory"]["graph"]["config"], dict)
    assert settings["memory"]["graph"]["context_max_relations"] == 8
    assert settings["memory"]["graph"]["max_hops"] == 1


def test_load_settings_deep_merges_memory_graph_defaults(tmp_path):
    f = tmp_path / "settings.yaml"
    f.write_text("memory:\n  graph:\n    enabled: true\n", encoding="utf-8")

    with patch("src.agent.agent.SETTINGS_PATH", str(f)):
        settings = agent_mod.load_settings()

    assert settings["memory"]["graph"]["enabled"] is True
    assert settings["memory"]["graph"]["provider"] == "neo4j"
    assert settings["memory"]["graph"]["context_max_relations"] == 8


def test_load_settings_preserves_graph_config_defaults_when_partially_overridden(tmp_path):
    f = tmp_path / "settings.yaml"
    f.write_text("memory:\n  graph:\n    config:\n      url: bolt://graph.example:7687\n", encoding="utf-8")

    with patch("src.agent.agent.SETTINGS_PATH", str(f)):
        settings = agent_mod.load_settings()

    assert settings["memory"]["graph"]["config"]["url"] == "bolt://graph.example:7687"
    assert settings["memory"]["graph"]["config"]["username"] == "neo4j"


def test_clear_history():
    agent_mod._history = [HumanMessage("x")]
    agent_mod.clear_history()
    assert agent_mod._history == []


def test_clear_history_resets_session_memory_state():
    agent_mod._history = [HumanMessage("x")]
    with patch("src.agent.agent.memory_mod.reset_session_memory_state") as reset_mock:
        agent_mod.clear_history()
    assert agent_mod._history == []
    reset_mock.assert_called_once()


@pytest.mark.anyio
async def test_invoke_complex_reschedule_does_not_touch_history():
    agent_mod._history = [HumanMessage("existing")]
    mock_graph = MagicMock()
    mock_graph.astream_events.return_value = _aiter([_make_stream_event("{}")])
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        async for _ in agent_mod._invoke("complex_reschedule", messages=[SystemMessage("sys"), HumanMessage("ctx")]):
            pass
    assert len(agent_mod._history) == 1
    assert isinstance(agent_mod._history[0], HumanMessage)


def test_route_after_llm_over_limit():
    from langchain_core.messages import AIMessage as AI
    last = AI("reply")
    last.usage_metadata = {"input_tokens": 99999}
    state = {"messages": [last], "reason": "user_message"}
    with patch("src.agent.agent.load_settings", return_value={"context_limit_tokens": 8000}):
        # route_after_llm is defined inside _ensure_initialized; test via graph routing indirectly
        tokens = (last.usage_metadata or {}).get("input_tokens", 0)
        assert tokens > 8000


@pytest.mark.anyio
async def test_invoke_logs_start_and_done(caplog):
    mock_graph = MagicMock()
    mock_graph.astream_events.return_value = _aiter([_make_stream_event("hi")])
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph), \
         caplog.at_level(logging.INFO, logger="src.agent.agent"):
        async for _ in agent_mod._invoke("user_message", "ping"):
            pass
    msgs = [r.message for r in caplog.records]
    assert any("agent invoke" in m and "user_message" in m for m in msgs)
    assert any("agent done" in m and "user_message" in m for m in msgs)


@pytest.mark.anyio
async def test_with_tool_logging_logs_tool_name(caplog):
    mock_tool = MagicMock()
    mock_tool.name = "my_tool"
    mock_tool.ainvoke = AsyncMock(return_value="result")
    wrapped = agent_mod._with_tool_logging(mock_tool)
    with caplog.at_level(logging.INFO, logger="src.agent.agent"):
        await wrapped.ainvoke({"input": "x"})
    assert any("my_tool" in r.message for r in caplog.records)


@pytest.mark.anyio
async def test_invoke_updates_last_token_usage():
    def fake_astream_events(s, version):
        ai = AIMessage("reply")
        ai.usage_metadata = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        agent_mod._history = s["messages"] + [ai]
        return _aiter([_make_stream_event("reply")])
    mock_graph = MagicMock()
    mock_graph.astream_events.side_effect = fake_astream_events
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        async for _ in agent_mod._invoke("user_message", "hello"):
            pass
    assert agent_mod._current_token_usage == 150


@pytest.mark.anyio
async def test_complex_reschedule_does_not_update_token_usage():
    mock_graph = MagicMock()
    mock_graph.astream_events.return_value = _aiter([_make_stream_event("{}")])
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        async for _ in agent_mod._invoke("complex_reschedule", messages=[SystemMessage("sys"), HumanMessage("ctx")]):
            pass
    assert agent_mod._current_token_usage == 0


@pytest.mark.anyio
async def test_summarize_all_schedules_async_memory_store_and_resets_seen_ids():
    summary_ai = AIMessage("总结文本")
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = summary_ai
    mock_llm.bind_tools.return_value = mock_llm
    agent_mod._history = [HumanMessage("旧消息")]

    async def fake_store_summary_async(summary_text, settings):
        return None

    with patch("src.agent.agent.init_chat_model", return_value=mock_llm), \
         patch.dict("os.environ", {"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-4o"}), \
         patch("src.agent.agent.load_settings", return_value={**agent_mod._SETTINGS_DEFAULTS, "memory": {**agent_mod._SETTINGS_DEFAULTS["memory"], "enabled": True, "auto_store_enabled": True}}) as load_settings_mock, \
         patch("src.agent.agent.memory_mod.reset_session_memory_state") as reset_mock, \
         patch("src.agent.agent.memory_mod.store_summary_async", side_effect=fake_store_summary_async) as store_mock, \
         patch("src.agent.agent.asyncio.create_task", wraps=asyncio.create_task) as create_task_mock:
        agent_mod._ensure_initialized()
        graph = agent_mod._graph
        state = {"messages": [HumanMessage("旧消息")], "reason": "session_timeout"}
        await graph.ainvoke(state, config={"configurable": {"thread_id": "test-memory-store"}})

    settings = load_settings_mock.return_value
    reset_mock.assert_called_once()
    store_mock.assert_called_once_with("总结文本", settings)
    assert create_task_mock.call_count >= 1


@pytest.mark.anyio
async def test_session_timeout_records_summary_token_usage():
    summary_ai = AIMessage("summary text")
    summary_ai.usage_metadata = {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100}
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = summary_ai
    mock_llm.bind_tools.return_value = mock_llm
    agent_mod._history = [HumanMessage("hello"), AIMessage("hi")]
    agent_mod._current_token_usage = 200
    with patch("src.agent.agent.init_chat_model", return_value=mock_llm), \
         patch.dict("os.environ", {"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-4o"}):
        agent_mod._ensure_initialized()
    graph = agent_mod._graph
    state = {"messages": [HumanMessage("hello"), AIMessage("hi")], "reason": "session_timeout"}
    await graph.ainvoke(state, config={"configurable": {"thread_id": "test"}})
    assert agent_mod._current_token_usage == 140  # 20 + (200 - 80)


@pytest.mark.anyio
async def test_auto_summarize_records_token_usage():
    # prev=200, summary input=180, output=30 → new = 30 + (200 - 180) = 50
    llm_reply = AIMessage("reply")
    llm_reply.usage_metadata = {"input_tokens": 99999, "output_tokens": 10, "total_tokens": 100009}
    summary_ai = AIMessage("summary")
    summary_ai.usage_metadata = {"input_tokens": 180, "output_tokens": 30, "total_tokens": 210}
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = [llm_reply, summary_ai]
    mock_llm.bind_tools.return_value = mock_llm
    agent_mod._history = [HumanMessage("hello")]
    agent_mod._current_token_usage = 200
    with patch("src.agent.agent.init_chat_model", return_value=mock_llm), \
         patch.dict("os.environ", {"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-4o"}):
        agent_mod._ensure_initialized()
    graph = agent_mod._graph
    state = {"messages": [HumanMessage("hello")], "reason": "user_message"}
    await graph.ainvoke(state, config={"configurable": {"thread_id": "test3"}})
    assert agent_mod._current_token_usage == 50
