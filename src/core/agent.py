import asyncio
import logging
import os
from datetime import datetime
from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing import Annotated, TypedDict

logger = logging.getLogger(__name__)

PROMPT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "agent", "prompt.txt")
)
DEFAULT_PROMPT = "你是一个QQ机器人"

_llm = None
_graph = None
_history: list[BaseMessage] = []
_lock = asyncio.Lock()
_tools: list = []


def load_prompt() -> str | None:
    if not os.path.exists(PROMPT_PATH):
        logger.warning("Prompt file not found at %s, creating with default.", PROMPT_PATH)
        os.makedirs(os.path.dirname(PROMPT_PATH), exist_ok=True)
        with open(PROMPT_PATH, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PROMPT)
        return DEFAULT_PROMPT
    with open(PROMPT_PATH, encoding="utf-8") as f:
        content = f.read()
    if not content:
        logger.warning("Prompt file at %s is empty.", PROMPT_PATH)
        return None
    return content


class _State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


_PROVIDER_PACKAGES = {
    "openai": "langchain-openai",
    "anthropic": "langchain-anthropic",
    "google": "langchain-google-genai",
    "google-genai": "langchain-google-genai",
    "ollama": "langchain-ollama",
    "groq": "langchain-groq",
    "mistralai": "langchain-mistralai",
    "cohere": "langchain-cohere",
    "fireworks": "langchain-fireworks",
    "together": "langchain-together",
    "huggingface": "langchain-huggingface",
}


def register_tools(tools: list) -> None:
    global _tools, _graph
    _tools = tools
    _graph = None


def _ensure_initialized():
    global _llm, _graph
    if _graph is not None:
        return
    system_prompt = load_prompt()
    for var in ("LLM_PROVIDER", "LLM_MODEL"):
        if not os.environ.get(var):
            raise RuntimeError(f"{var} is not set. Copy .env.example to .env and configure it.")
    provider = os.environ["LLM_PROVIDER"]
    try:
        _llm = init_chat_model(os.environ["LLM_MODEL"], model_provider=provider)
    except ImportError:
        pkg = _PROVIDER_PACKAGES.get(provider, f"langchain-{provider}")
        raise ImportError(
            f"Provider '{provider}' requires '{pkg}'. "
            f"Install it with:\n  pip install {pkg}"
        ) from None

    llm_with_tools = _llm.bind_tools(_tools) if _tools else _llm

    def llm_node(state: _State) -> _State:
        msgs = state["messages"]
        if system_prompt:
            msgs = [SystemMessage(system_prompt)] + msgs
        response = llm_with_tools.invoke(msgs)
        return {"messages": [response]}

    builder = StateGraph(_State)
    builder.add_node("llm", llm_node)
    builder.add_edge(START, "llm")

    if _tools:
        builder.add_node("tools", ToolNode(_tools))
        builder.add_conditional_edges(
            "llm",
            lambda state: "tools" if state["messages"][-1].tool_calls else END,
        )
        builder.add_edge("tools", "llm")
    else:
        builder.add_edge("llm", END)

    _graph = builder.compile()


async def invoke(human_message: str) -> str:
    global _history
    async with _lock:
        _ensure_initialized()
        _history = _history + [HumanMessage(human_message)]
        result = await _graph.ainvoke({"messages": _history})
        _history = result["messages"]
        _history = _history + [SystemMessage(f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")]
        return _history[-2].content


async def invoke_bare(messages: list[BaseMessage], schema=None):
    async with _lock:
        _ensure_initialized()
        llm = _llm.with_structured_output(schema) if schema else _llm
        response = await llm.ainvoke(messages)
        return response if schema else response.content
