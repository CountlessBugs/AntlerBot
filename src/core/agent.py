import logging
import os
from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

logger = logging.getLogger(__name__)

PROMPT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "agent", "prompt.txt")
)
DEFAULT_PROMPT = "你是一个QQ机器人"

_llm = None
_graph = None
_history: list[BaseMessage] = []


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
    messages: list[BaseMessage]


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

    def llm_node(state: _State) -> _State:
        msgs = state["messages"]
        if system_prompt:
            msgs = [SystemMessage(system_prompt)] + msgs
        response = _llm.invoke(msgs)
        return {"messages": state["messages"] + [response]}

    builder = StateGraph(_State)
    builder.add_node("llm", llm_node)
    builder.add_edge(START, "llm")
    builder.add_edge("llm", END)
    _graph = builder.compile()


async def invoke(human_message: str) -> str:
    global _history
    _ensure_initialized()
    _history = _history + [HumanMessage(human_message)]
    result = await _graph.ainvoke({"messages": _history})
    response = result["messages"][-1].content
    _history = _history + [AIMessage(response)]
    return response
