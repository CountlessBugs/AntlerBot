import asyncio
import logging
import pytest
import src.core.agent as agent_mod
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage, HumanMessage


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
        result = await agent_mod.invoke("ping")
    assert result == "pong"


@pytest.mark.anyio
async def test_invoke_accumulates_history():
    mock_graph = AsyncMock()
    mock_graph.ainvoke.side_effect = lambda s: {"messages": s["messages"] + [AIMessage("reply")]}
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        await agent_mod.invoke("hello")
    assert len(agent_mod._history) == 2
    assert isinstance(agent_mod._history[0], HumanMessage)
    assert isinstance(agent_mod._history[1], AIMessage)


@pytest.mark.anyio
async def test_invoke_passes_history_on_second_call():
    mock_graph = AsyncMock()
    mock_graph.ainvoke.side_effect = lambda s: {"messages": s["messages"] + [AIMessage("reply")]}
    with patch.object(agent_mod, "_ensure_initialized"), \
         patch.object(agent_mod, "_graph", mock_graph):
        await agent_mod.invoke("msg1")
        await agent_mod.invoke("msg2")
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
        await asyncio.gather(agent_mod.invoke("a"), agent_mod.invoke("b"))
    assert order == ["start", "end", "start", "end"]
