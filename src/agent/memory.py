import logging
import os
import re
from datetime import UTC, datetime

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_MEDIA_LOADING_TAG_RE = re.compile(
    r"<(?:image|audio|video|document)\b[^>]*\bstatus=\"loading\"[^>]*/>",
    re.IGNORECASE,
)
_MEDIA_SELF_CLOSING_TAG_RE = re.compile(
    r"<(?:image|audio|video|document)\b[^>]*/>",
    re.IGNORECASE,
)
_XML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_TEMP_AUTO_RECALL_MARKER = "__antlerbot_auto_recall__"
_COUNTED_MEMORY_IDS: set[str] = set()
_CONTEXT_LOCKED_MEMORY_IDS: set[str] = set()
_MEMORY_STORE = None


def normalize_query_text(text: str) -> str:
    normalized = _XML_TAG_RE.sub(" ", text)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def message_has_untextualized_media(text: str) -> bool:
    if _MEDIA_LOADING_TAG_RE.search(text):
        return True

    for match in _MEDIA_SELF_CLOSING_TAG_RE.finditer(text):
        tag = match.group(0)
        if not re.search(r"\b(?:status|alt|text|caption|summary|transcript)=", tag, re.IGNORECASE):
            return True

    return False


def build_auto_recall_query(messages: list[BaseMessage], token_limit: int) -> str | None:
    if not messages:
        return None

    current_text = normalize_query_text(str(messages[-1].content))
    if message_has_untextualized_media(str(messages[-1].content)):
        return None

    if not current_text:
        return None

    parts: list[str] = []
    total_tokens = 0

    for message in reversed(messages):
        raw_text = str(message.content)
        if message_has_untextualized_media(raw_text):
            continue

        normalized = normalize_query_text(raw_text)
        if not normalized:
            continue

        candidate_parts = [normalized] + parts
        candidate_text = " ".join(candidate_parts)
        candidate_tokens = count_tokens_approximately(candidate_text)
        if parts and candidate_tokens > token_limit:
            break

        parts = candidate_parts
        total_tokens = candidate_tokens
        if total_tokens >= token_limit:
            break

    return " ".join(parts) if parts else None


def _get_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def _require_mem0_field(value: str | None, env_name: str) -> str:
    if value:
        return value
    raise RuntimeError(f"{env_name} is required to initialize Mem0.")


def _set_provider_base_url(config: dict, provider: str, base_url: str | None, *, kind: str) -> None:
    if not base_url:
        return

    provider_field_map = {
        "embedder": {
            "openai": "openai_base_url",
            "ollama": "ollama_base_url",
            "huggingface": "huggingface_base_url",
            "lmstudio": "lmstudio_base_url",
        },
        "llm": {
            "openai": "openai_base_url",
            "ollama": "ollama_base_url",
            "anthropic": "anthropic_base_url",
            "deepseek": "deepseek_base_url",
            "lmstudio": "lmstudio_base_url",
        },
    }
    config[provider_field_map.get(kind, {}).get(provider, "base_url")] = base_url


def _resolve_mem0_llm_config() -> dict:
    provider = _require_mem0_field(_get_env("MEM0_LLM_PROVIDER") or _get_env("LLM_PROVIDER"), "LLM_PROVIDER")
    model = _require_mem0_field(_get_env("MEM0_LLM_MODEL") or _get_env("LLM_MODEL"), "LLM_MODEL")
    api_key = _get_env("MEM0_LLM_API_KEY") or _get_env("OPENAI_API_KEY")
    base_url = _get_env("MEM0_LLM_BASE_URL") or _get_env("OPENAI_BASE_URL")

    config = {"model": model}
    if api_key:
        config["api_key"] = api_key
    _set_provider_base_url(config, provider, base_url, kind="llm")
    return {"provider": provider, "config": config}


def _resolve_mem0_embedder_config() -> dict:
    provider = _require_mem0_field(_get_env("MEM0_EMBEDDER_PROVIDER") or "openai", "MEM0_EMBEDDER_PROVIDER")
    model = _require_mem0_field(_get_env("MEM0_EMBEDDER_MODEL") or "text-embedding-3-small", "MEM0_EMBEDDER_MODEL")
    api_key = _get_env("MEM0_EMBEDDER_API_KEY") or _get_env("OPENAI_API_KEY")
    base_url = _get_env("MEM0_EMBEDDER_BASE_URL") or _get_env("OPENAI_BASE_URL")

    config = {"model": model}
    if api_key:
        config["api_key"] = api_key
    _set_provider_base_url(config, provider, base_url, kind="embedder")
    return {"provider": provider, "config": config}


def _resolve_graph_store_config(settings: dict) -> dict | None:
    graph_settings = settings.get("memory", {}).get("graph", {})
    if not graph_settings.get("enabled"):
        return None
    return {
        "provider": graph_settings.get("provider", "neo4j"),
        "config": dict(graph_settings.get("config", {})),
    }


def get_memory_store(settings: dict):
    global _MEMORY_STORE
    if _MEMORY_STORE is None:
        from mem0 import Memory
        from mem0.configs.base import MemoryConfig

        config_kwargs = {
            "llm": _resolve_mem0_llm_config(),
            "embedder": _resolve_mem0_embedder_config(),
        }
        graph_store = _resolve_graph_store_config(settings)
        if graph_store is not None:
            try:
                _MEMORY_STORE = Memory(MemoryConfig(**{**config_kwargs, "graph_store": graph_store}))
            except Exception:
                logger.warning("Mem0 graph store initialization failed; falling back to vector-only mode.", exc_info=True)
                _MEMORY_STORE = Memory(MemoryConfig(**config_kwargs))
        else:
            _MEMORY_STORE = Memory(MemoryConfig(**config_kwargs))
    return _MEMORY_STORE


def filter_search_results(results, threshold: float, max_memories: int, blocked_ids: set[str] | None = None):
    blocked_ids = blocked_ids or set()
    filtered = []
    for item in results:
        item_id = item.get("id")
        if item_id and item_id in blocked_ids:
            continue
        if item.get("score", 0) < threshold:
            continue
        filtered.append(item)
        if len(filtered) >= max_memories:
            break
    return filtered


def format_auto_recall_message(results, prefix: str, relations=None, relation_prefix: str | None = None) -> SystemMessage | None:
    if not results:
        return None

    lines = [prefix, "记忆："]
    for item in results:
        memory_text = str(item.get("memory", "")).strip()
        if memory_text:
            lines.append(f"- {memory_text}")

    relation_lines = _format_relation_lines(relations or [])
    if relation_lines:
        lines.append(relation_prefix or "联想关系：")
        lines.extend(relation_lines)

    if len(lines) == 2:
        return None
    return SystemMessage("\n".join(lines))


def _trim_relations(relations, max_relations: int):
    return list(relations[:max_relations])


def _format_relation_lines(relations) -> list[str]:
    lines = []
    for relation in relations:
        source = str(relation.get("source", "")).strip() if isinstance(relation, dict) else ""
        relationship = str(relation.get("relationship", "")).strip() if isinstance(relation, dict) else ""
        destination = str(relation.get("destination", "")).strip() if isinstance(relation, dict) else ""
        if source and relationship and destination:
            lines.append(f"- {source} -[{relationship}]-> {destination}")
    return lines


def build_recall_metadata_update(current_metadata: dict | None, recalled_at: str) -> dict:
    if not isinstance(current_metadata, dict):
        current_metadata = {}
    metadata = dict(current_metadata)
    current_count = metadata.get("recall_count", 0)
    try:
        current_count = int(current_count)
    except (TypeError, ValueError):
        current_count = 0
    metadata["recall_count"] = current_count + 1
    metadata["last_recalled_at"] = recalled_at
    return metadata


def try_update_memory_recall_metadata(store, memory_id: str, recalled_at: str) -> bool:
    get_method = getattr(store, "get", None)
    update_method = getattr(store, "update", None)
    if not callable(get_method) or not callable(update_method):
        logger.info("mem0 memory store does not support get/update metadata operations")
        return False

    try:
        current = get_method(memory_id=memory_id)
        if not isinstance(current, dict):
            logger.info("mem0 get did not return a mapping for recall metadata update")
            return False

        text = current.get("memory") or current.get("text")
        if not text:
            logger.info("mem0 recall metadata update skipped because original memory text is unavailable")
            return False

        metadata = build_recall_metadata_update(current.get("metadata", {}), recalled_at)
        update_method(memory_id, {"memory": text, "metadata": metadata})
        return True
    except Exception:
        logger.warning("mem0 recall metadata update failed", exc_info=True)
        return False


def lock_memory_ids_for_session(results) -> None:
    for item in results:
        item_id = item.get("id")
        if item_id:
            _CONTEXT_LOCKED_MEMORY_IDS.add(str(item_id))


def reset_context_locked_memory_ids() -> None:
    _CONTEXT_LOCKED_MEMORY_IDS.clear()


def get_context_locked_memory_ids() -> set[str]:
    return set(_CONTEXT_LOCKED_MEMORY_IDS)


def reset_session_memory_state() -> None:
    reset_counted_memory_ids()
    reset_context_locked_memory_ids()


def mark_counted_memory_ids(results) -> None:
    for item in results:
        item_id = item.get("id")
        if item_id:
            _COUNTED_MEMORY_IDS.add(str(item_id))


def reset_counted_memory_ids() -> None:
    _COUNTED_MEMORY_IDS.clear()


def get_counted_memory_ids() -> set[str]:
    return set(_COUNTED_MEMORY_IDS)


def is_temporary_auto_recall_message(message: BaseMessage) -> bool:
    return isinstance(message, SystemMessage) and message.additional_kwargs.get(_TEMP_AUTO_RECALL_MARKER) is True


def ensure_temporary_auto_recall_message(message: SystemMessage | None) -> SystemMessage | None:
    if message is None:
        return None
    if is_temporary_auto_recall_message(message):
        return message
    return SystemMessage(message.content, additional_kwargs={**message.additional_kwargs, _TEMP_AUTO_RECALL_MARKER: True})


def build_temporary_auto_recall_message(results, prefix: str) -> SystemMessage | None:
    message = format_auto_recall_message(results, prefix)
    return ensure_temporary_auto_recall_message(message)


def get_effort_config(settings: dict, effort: str) -> tuple[float, int, str]:
    memory_settings = settings.get("memory", {})
    effort_map = {
        "low": (memory_settings.get("recall_low_score_threshold", 0.85), memory_settings.get("recall_low_max_memories", 3), "低"),
        "medium": (memory_settings.get("recall_medium_score_threshold", 0.70), memory_settings.get("recall_medium_max_memories", 6), "中等"),
        "high": (memory_settings.get("recall_high_score_threshold", 0.55), memory_settings.get("recall_high_max_memories", 10), "高"),
    }
    return effort_map.get(effort, effort_map["medium"])


def format_recall_result(results, effort_label: str, relations=None, relation_prefix: str | None = None) -> str:
    if not results:
        return "未检索到符合条件的长期记忆。"

    lines = [f"已按{effort_label}努力程度检索到以下长期记忆：", "记忆："]
    for item in results:
        memory_text = str(item.get("memory", "")).strip()
        if memory_text:
            lines.append(f"- {memory_text}")

    relation_lines = _format_relation_lines(relations or [])
    if relation_lines:
        lines.append(relation_prefix or "联想关系：")
        lines.extend(relation_lines)

    return "\n".join(lines)


def build_recall_tool(settings: dict):
    @tool("recall_memory", parse_docstring=False)
    def recall_memory(query: str, effort: str = "medium") -> str:
        """按指定努力程度检索与当前问题相关的长期记忆。"""
        store = get_memory_store(settings)
        threshold, max_memories, effort_label = get_effort_config(settings, effort)
        raw_results = store.search(query, agent_id=settings.get("memory", {}).get("agent_id", "antlerbot"))
        results = raw_results.get("results", raw_results) if isinstance(raw_results, dict) else raw_results
        filtered = filter_search_results(
            results,
            threshold=threshold,
            max_memories=max_memories,
            blocked_ids=get_context_locked_memory_ids(),
        )
        recalled_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        for item in filtered:
            item_id = item.get("id")
            if item_id and str(item_id) not in _COUNTED_MEMORY_IDS:
                try_update_memory_recall_metadata(store, str(item_id), recalled_at)
        mark_counted_memory_ids(filtered)
        lock_memory_ids_for_session(filtered)
        return format_recall_result(filtered, effort_label)

    return recall_memory


def build_auto_recall_system_message(history: list[BaseMessage], settings: dict) -> SystemMessage | None:
    memory_settings = settings.get("memory", {})
    query = build_auto_recall_query(history, memory_settings.get("auto_recall_query_token_limit", 400))
    if not query:
        return None

    store = get_memory_store(settings)
    raw_results = store.search(query, agent_id=memory_settings.get("agent_id", "antlerbot"))
    results = raw_results.get("results", raw_results) if isinstance(raw_results, dict) else raw_results
    filtered = filter_search_results(
        results,
        threshold=memory_settings.get("auto_recall_score_threshold", 0.75),
        max_memories=memory_settings.get("auto_recall_max_memories", 5),
        blocked_ids=get_context_locked_memory_ids(),
    )
    if not filtered:
        return None

    recalled_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    for item in filtered:
        item_id = item.get("id")
        if item_id and str(item_id) not in _COUNTED_MEMORY_IDS:
            try_update_memory_recall_metadata(store, str(item_id), recalled_at)
    mark_counted_memory_ids(filtered)
    return build_temporary_auto_recall_message(
        filtered,
        memory_settings.get("auto_recall_system_prefix", "以下是可能与当前对话相关的长期记忆。仅在相关时使用，不要机械复述。"),
    )


async def store_summary_async(summary_text: str, settings: dict) -> None:
    try:
        store = get_memory_store(settings)
        store.add(
            [{"role": "user", "content": summary_text}],
            agent_id=settings.get("memory", {}).get("agent_id", "antlerbot"),
        )
    except Exception:
        logger.warning("mem0 summary store failed", exc_info=True)


def mark_seen_memory_ids(results) -> None:
    """兼容旧测试/旧调用名；语义已变为会话内 recall 计数。"""
    mark_counted_memory_ids(results)


def reset_seen_memory_ids() -> None:
    """兼容旧测试/旧调用名；语义已变为重置会话内 recall 计数。"""
    reset_counted_memory_ids()


def get_seen_memory_ids() -> set[str]:
    """兼容旧测试/旧调用名；语义已变为读取会话内 recall 计数集合。"""
    return get_counted_memory_ids()
