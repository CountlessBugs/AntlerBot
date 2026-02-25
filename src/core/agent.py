import asyncio
import logging
import os
import re
import time
from datetime import datetime
from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing import Annotated, AsyncGenerator, Literal, TypedDict

logger = logging.getLogger(__name__)

PROMPT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "agent", "prompt.txt")
)
PROMPT_EXAMPLE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "agent", "prompt.txt.example")
)

SETTINGS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "agent", "settings.yaml")
)
_SETTINGS_DEFAULTS = {
    "context_limit_tokens": 8000,
    "timeout_summarize_seconds": 1800,
    "timeout_clear_seconds": 3600,
    "reply_max_length": 50,
    "media": {
        "transcription_model": "",
        "transcription_provider": "",
        "timeout": 60,
        "image": {"transcribe": False, "passthrough": False},
        "audio": {"transcribe": False, "passthrough": False, "max_duration": 60, "trim_over_limit": True},
        "video": {"transcribe": False, "passthrough": False, "max_duration": 30, "trim_over_limit": True},
        "document": {"transcribe": False, "passthrough": False},
    },
}


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_PATH):
        return dict(_SETTINGS_DEFAULTS)
    import yaml
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = {**_SETTINGS_DEFAULTS, **data}
    # Deep-merge media config
    default_media = _SETTINGS_DEFAULTS.get("media", {})
    user_media = data.get("media", {})
    merged_media = {**default_media, **user_media}
    for key in ("image", "audio", "video", "document"):
        merged_media[key] = {**default_media.get(key, {}), **user_media.get(key, {})}
    merged["media"] = merged_media
    return merged

_llm = None
_graph = None
_history: list[BaseMessage] = []
_lock = asyncio.Lock()
_tools: list = []
_pending_schema: type | None = None
_current_token_usage: int = 0


def load_prompt() -> str | None:
    if not os.path.exists(PROMPT_PATH):
        os.makedirs(os.path.dirname(PROMPT_PATH), exist_ok=True)
        if not os.path.exists(PROMPT_EXAMPLE_PATH):
            logger.warning("prompt.txt.example not found; creating empty prompt.txt and skipping system prompt.")
            open(PROMPT_PATH, "w").close()
            return None
        import shutil
        shutil.copy(PROMPT_EXAMPLE_PATH, PROMPT_PATH)
        logger.info("Copied prompt.txt.example to prompt.txt.")
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


def _with_tool_logging(t):
    orig = t.ainvoke
    async def logged(input, config=None, **kwargs):
        logger.info("tool: %s", t.name)
        return await orig(input, config, **kwargs)
    object.__setattr__(t, 'ainvoke', logged)
    return t


def register_tools(tools: list) -> None:
    global _tools, _graph
    _tools = [_with_tool_logging(t) for t in tools]
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

    def _safe_for_summary(msgs):
        """Strip trailing incomplete tool call sequences."""
        from langchain_core.messages import AIMessage, ToolMessage
        msgs = list(msgs)
        while msgs and isinstance(msgs[-1], ToolMessage):
            msgs.pop()
        if msgs and isinstance(msgs[-1], AIMessage) and msgs[-1].tool_calls:
            msgs.pop()
        return msgs

    def summarize_node(state: _State) -> dict:
        global _history, _current_token_usage
        msgs = state["messages"]
        last_human = next((i for i in range(len(msgs) - 1, -1, -1) if isinstance(msgs[i], (HumanMessage, SystemMessage))), None)
        if last_human is not None and last_human > 0:
            last_turn = msgs[last_human:]
            to_summarize = _safe_for_summary(msgs[:last_human])
        else:
            # no HumanMessage: summarize everything, keep nothing as last_turn
            to_summarize = _safe_for_summary(msgs)
            last_turn = []
        if not to_summarize:
            return {}
        summary = _llm.invoke([SystemMessage("请总结以下对话，保留关键信息："), *to_summarize])
        if summary.usage_metadata:
            meta = summary.usage_metadata
            _current_token_usage = (
                meta.get("output_tokens", 0)
                + _current_token_usage
                - meta.get("input_tokens", 0)
            )
        t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        wrapped = f"<context-summary summary_time={t}>\n{summary.content}\n</context-summary>"
        _history = [SystemMessage(wrapped)] + list(last_turn)
        return {}

    def summarize_all_node(state: _State) -> dict:
        logger.info("session summarize triggered")
        global _history, _current_token_usage
        from langchain_core.messages import RemoveMessage
        msgs = _safe_for_summary(state["messages"])
        summary = _llm.invoke([SystemMessage("请总结以下对话，保留关键信息："), *msgs])
        if summary.usage_metadata:
            meta = summary.usage_metadata
            _current_token_usage = (
                meta.get("output_tokens", 0)
                + _current_token_usage
                - meta.get("input_tokens", 0)
            )
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
        tokens = (last.usage_metadata or {}).get("input_tokens") or count_tokens_approximately(state["messages"])
        if tokens > load_settings()["context_limit_tokens"]:
            logger.info("auto-summarize | tokens=%d", tokens)
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
) -> AsyncGenerator[str, None]:
    global _pending_schema
    async with _lock:
        _ensure_initialized()
        _pending_schema = schema
        logger.info("agent invoke | reason=%s schema=%s", reason, schema.__name__ if schema else None)
        t0 = time.monotonic()
        if reason == "session_timeout":
            initial = list(_history)
        elif reason == "complex_reschedule":
            initial = list(messages)
        else:
            initial = _history + [HumanMessage(message)]

        def _emit(text: str):
            cleaned = re.sub(r'<[^>]+>', '', text).strip()
            return cleaned if cleaned else None

        buffer = ""
        in_no_split = False

        async for event in _graph.astream_events({"messages": initial, "reason": reason}, version="v2"):
            if event["event"] != "on_chat_model_stream":
                continue
            if event.get("metadata", {}).get("langgraph_node") != "llm":
                continue
            chunk = event["data"]["chunk"].content
            if not chunk:
                continue
            buffer += chunk
            while True:
                if not in_no_split:
                    nl = buffer.find("\n")
                    ns = buffer.find("<no-split>")
                    if nl == -1 and ns == -1:
                        break
                    if ns == -1 or (nl != -1 and nl < ns):
                        seg = _emit(buffer[:nl])
                        if seg:
                            yield seg
                        buffer = buffer[nl + 1:]
                    else:
                        for line in buffer[:ns].split("\n"):
                            seg = _emit(line)
                            if seg:
                                yield seg
                        buffer = buffer[ns + len("<no-split>"):]
                        in_no_split = True
                else:
                    end = buffer.find("</no-split>")
                    if end == -1:
                        break
                    seg = _emit(buffer[:end])
                    if seg:
                        yield seg
                    buffer = buffer[end + len("</no-split>"):]
                    in_no_split = False

        if in_no_split:
            seg = _emit(buffer)
            if seg:
                yield seg
        else:
            for line in buffer.split("\n"):
                seg = _emit(line)
                if seg:
                    yield seg
        logger.info("agent done | reason=%s elapsed=%.2fs", reason, time.monotonic() - t0)
        global _current_token_usage
        if reason in ("user_message", "scheduled_task"):
            last_ai = next((m for m in reversed(_history) if isinstance(m, AIMessage)), None)
            if last_ai:
                _current_token_usage = (last_ai.usage_metadata or {}).get("total_tokens") or count_tokens_approximately(_history)


def has_history() -> bool:
    return bool(_history)


def clear_history() -> None:
    global _history
    _history = []
