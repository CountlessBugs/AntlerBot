import asyncio
import logging
import os
from datetime import datetime
from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing import Annotated, Literal, TypedDict

logger = logging.getLogger(__name__)

PROMPT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "agent", "prompt.txt")
)
DEFAULT_PROMPT = "你是一个QQ机器人"

SETTINGS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "agent", "settings.yaml")
)
_SETTINGS_DEFAULTS = {
    "context_limit_tokens": 8000,
    "timeout_summarize_seconds": 1800,
    "timeout_clear_seconds": 3600,
}


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_PATH):
        return dict(_SETTINGS_DEFAULTS)
    import yaml
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {**_SETTINGS_DEFAULTS, **data}

_llm = None
_graph = None
_history: list[BaseMessage] = []
_lock = asyncio.Lock()
_tools: list = []
_pending_schema: type | None = None


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
    reason: Literal["user_message", "scheduled_task", "complex_reschedule", "session_timeout"]


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

    def llm_node(state: _State) -> dict:
        msgs = state["messages"]
        if system_prompt:
            msgs = [SystemMessage(system_prompt)] + msgs
        if not isinstance(msgs[-1], ToolMessage):
            msgs = msgs + [SystemMessage(f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")]
        response = llm_with_tools.invoke(msgs)
        return {"messages": [response]}

    def finalize_node(state: _State) -> dict:
        global _history
        _history = list(state["messages"])
        return {}

    def summarize_node(state: _State) -> dict:
        global _history
        msgs = state["messages"]
        last_turn = msgs[-2:] if len(msgs) >= 2 else msgs
        to_summarize = msgs[:-2] if len(msgs) >= 2 else []
        summary = _llm.invoke([SystemMessage("请总结以下对话，保留关键信息："), *to_summarize])
        t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        wrapped = f"<context-summary summary_time={t}>\n{summary.content}\n</context-summary>"
        _history = [SystemMessage(wrapped)] + list(last_turn)
        return {}

    def summarize_all_node(state: _State) -> dict:
        global _history
        from langchain_core.messages import RemoveMessage
        msgs = state["messages"]
        summary = _llm.invoke([SystemMessage("请总结以下对话，保留关键信息："), *msgs])
        t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        summary_msg = SystemMessage(f"<context-summary summary_time={t}>\n{summary.content}\n</context-summary>")
        _history = [summary_msg]
        return {"messages": [RemoveMessage(id=m.id) for m in msgs] + [summary_msg]}

    def utility_node(state: _State) -> dict:
        schema = _pending_schema
        llm = _llm.with_structured_output(schema) if schema else _llm
        response = llm.invoke(state["messages"])
        content = response.model_dump_json() if hasattr(response, "model_dump_json") else response.content
        return {"messages": [AIMessage(content)]}

    def route_by_reason(state: _State) -> str:
        return state["reason"]

    def route_after_llm(state: _State) -> str:
        last = state["messages"][-1]
        if last.tool_calls:
            return "tools"
        tokens = (last.usage_metadata or {}).get("input_tokens", 0)
        if tokens > load_settings()["context_limit_tokens"]:
            return "summarize"
        return "finalize"

    builder = StateGraph(_State)
    builder.add_node("llm", llm_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("summarize", summarize_node)
    builder.add_node("summarize_all", summarize_all_node)
    builder.add_node("utility", utility_node)
    if _tools:
        builder.add_node("tools", ToolNode(_tools))
        builder.add_edge("tools", "llm")

    builder.add_conditional_edges(START, route_by_reason, {
        "user_message": "llm",
        "scheduled_task": "llm",
        "complex_reschedule": "utility",
        "session_timeout": "summarize_all",
    })
    builder.add_conditional_edges("llm", route_after_llm, {
        "tools": "tools" if _tools else END,
        "summarize": "summarize",
        "finalize": "finalize",
    })
    builder.add_edge("summarize", END)
    builder.add_edge("summarize_all", END)
    builder.add_edge("finalize", END)
    builder.add_edge("utility", END)

    _graph = builder.compile()


async def _invoke(
    reason: Literal["user_message", "scheduled_task", "complex_reschedule", "session_timeout"],
    message: str = "",
    *,
    messages: list[BaseMessage] | None = None,
    schema: type | None = None,
) -> str:
    global _pending_schema
    async with _lock:
        _ensure_initialized()
        _pending_schema = schema
        if reason == "session_timeout":
            initial = list(_history)
        elif reason == "complex_reschedule":
            initial = list(messages)
        else:
            initial = _history + [HumanMessage(message)]
        result = await _graph.ainvoke({"messages": initial, "reason": reason})
        return result["messages"][-1].content


def clear_history() -> None:
    global _history
    _history = []
