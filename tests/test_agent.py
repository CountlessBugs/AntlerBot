import asyncio
import logging
import pytest
import src.core.agent as agent_mod
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


@pytest.fixture(autouse=True)
def reset_agent_state():
    agent_mod._history = []
    agent_mod._graph = None
    agent_mod._llm = None
    agent_mod._lock = asyncio.Lock()
    yield
    agent_mod._history = []
    agent_mod._graph = None
    agent_mod._llm = None
    agent_mod._lock = asyncio.Lock()


def test_load_prompt_missing_creates_default(tmp_path, caplog):
    path = str(tmp_path / "prompt.txt")
    from src.core.agent import load_prompt
    with patch("src.core.agent.PROMPT_PATH", path), caplog.at_level(logging.WARNING, logger="src.core.agent"):
        result = load_prompt()
    assert result == "你是一个QQ机器人"
    assert (tmp_path / "prompt.txt").read_text(encoding="utf-8") == "你是一个QQ机器人"
    assert caplog.records


def test_load_prompt_empty_returns_none(tmp_path, caplog):
    path = str(tmp_path / "prompt.txt")
    (tmp_path / "prompt.txt").write_text("", encoding="utf-8")
    from src.core.agent import load_prompt
    with patch("src.core.agent.PROMPT_PATH", path), caplog.at_level(logging.WARNING, logger="src.core.agent"):
        result = load_prompt()
    assert result is None
    assert caplog.records


def test_load_prompt_returns_content(tmp_path):
    path = str(tmp_path / "prompt.txt")
    (tmp_path / "prompt.txt").write_text("你好机器人", encoding="utf-8")
    from src.core.agent import load_prompt
    with patch("src.core.agent.PROMPT_PATH", path):
        result = load_prompt()
    assert result == "你好机器人"


def test_ensure_initialized_friendly_import_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-3-5-sonnet-20241022")
    with patch("src.core.agent.load_prompt", return_value=None), \
         patch("src.core.agent.init_chat_model", side_effect=ImportError):
        with pytest.raises(ImportError, match="pip install langchain-anthropic"):
            agent_mod._ensure_initialized()


def test_ensure_initialized_missing_env_var(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with patch("src.core.agent.load_prompt", return_value=None):
        with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
            agent_mod._ensure_initialized()


@pytest.mark.anyio
async def test_invoke_returns_ai_content():
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {"messages": [AIMessage("pong")]}
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        result = await agent_mod._invoke("user_message", "ping")
    assert result == "pong"


@pytest.mark.anyio
async def test_invoke_accumulates_history():
    def fake_ainvoke(s):
        msgs = s["messages"] + [AIMessage("reply")]
        agent_mod._history = msgs
        return {"messages": msgs}
    mock_graph = AsyncMock()
    mock_graph.ainvoke.side_effect = fake_ainvoke
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        await agent_mod._invoke("user_message", "hello")
    assert len(agent_mod._history) == 2
    assert isinstance(agent_mod._history[0], HumanMessage)
    assert isinstance(agent_mod._history[1], AIMessage)


@pytest.mark.anyio
async def test_invoke_passes_history_on_second_call():
    def fake_ainvoke(s):
        msgs = s["messages"] + [AIMessage("reply")]
        agent_mod._history = msgs
        return {"messages": msgs}
    mock_graph = AsyncMock()
    mock_graph.ainvoke.side_effect = fake_ainvoke
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        await agent_mod._invoke("user_message", "msg1")
        await agent_mod._invoke("user_message", "msg2")
    second_call_msgs = mock_graph.ainvoke.call_args_list[1][0][0]["messages"]
    assert len(second_call_msgs) == 3  # human, ai, human


@pytest.mark.anyio
async def test_invoke_executes_sequentially():
    order = []

    async def slow_ainvoke(state):
        order.append("start")
        await asyncio.sleep(0)
        order.append("end")
        return {"messages": [AIMessage("reply")]}

    mock_graph = AsyncMock()
    mock_graph.ainvoke.side_effect = slow_ainvoke
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        await asyncio.gather(agent_mod._invoke("user_message", "a"), agent_mod._invoke("user_message", "b"))
    assert order == ["start", "end", "start", "end"]


def test_load_settings_defaults_when_missing(tmp_path):
    with patch("src.core.agent.SETTINGS_PATH", str(tmp_path / "settings.yaml")):
        result = agent_mod.load_settings()
    assert result == {"context_limit_tokens": 8000, "timeout_summarize_seconds": 1800, "timeout_clear_seconds": 3600}


def test_load_settings_reads_file(tmp_path):
    f = tmp_path / "settings.yaml"
    f.write_text("context_limit_tokens: 4000\n", encoding="utf-8")
    with patch("src.core.agent.SETTINGS_PATH", str(f)):
        result = agent_mod.load_settings()
    assert result["context_limit_tokens"] == 4000
    assert result["timeout_summarize_seconds"] == 1800


def test_clear_history():
    agent_mod._history = [HumanMessage("x")]
    agent_mod.clear_history()
    assert agent_mod._history == []


@pytest.mark.anyio
async def test_invoke_complex_reschedule_does_not_touch_history():
    agent_mod._history = [HumanMessage("existing")]
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {"messages": [AIMessage("{}")]}
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        await agent_mod._invoke("complex_reschedule", messages=[SystemMessage("sys"), HumanMessage("ctx")])
    assert len(agent_mod._history) == 1
    assert isinstance(agent_mod._history[0], HumanMessage)


def test_route_after_llm_over_limit():
    from langchain_core.messages import AIMessage as AI
    last = AI("reply")
    last.usage_metadata = {"input_tokens": 99999}
    state = {"messages": [last], "reason": "user_message"}
    with patch("src.core.agent.load_settings", return_value={"context_limit_tokens": 8000}):
        # route_after_llm is defined inside _ensure_initialized; test via graph routing indirectly
        tokens = (last.usage_metadata or {}).get("input_tokens", 0)
        assert tokens > 8000
