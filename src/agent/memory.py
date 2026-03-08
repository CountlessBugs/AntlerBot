import logging
import re

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
_SEEN_MEMORY_IDS: set[str] = set()
_MEMORY_CLIENT = None


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


def get_memory_client(settings: dict):
    global _MEMORY_CLIENT
    if _MEMORY_CLIENT is None:
        from mem0 import Memory

        _MEMORY_CLIENT = Memory()
    return _MEMORY_CLIENT


def filter_search_results(results, threshold: float, max_memories: int, seen_ids: set[str]):
    filtered = []
    for item in results:
        item_id = item.get("id")
        if item_id and item_id in seen_ids:
            continue
        if item.get("score", 0) < threshold:
            continue
        filtered.append(item)
        if len(filtered) >= max_memories:
            break
    return filtered


def format_auto_recall_message(results, prefix: str) -> SystemMessage | None:
    if not results:
        return None

    lines = [prefix]
    for item in results:
        memory_text = str(item.get("memory", "")).strip()
        if memory_text:
            lines.append(f"- {memory_text}")
    if len(lines) == 1:
        return None
    return SystemMessage("\n".join(lines))


def get_effort_config(settings: dict, effort: str) -> tuple[float, int, str]:
    memory_settings = settings.get("memory", {})
    effort_map = {
        "low": (memory_settings.get("recall_low_score_threshold", 0.85), memory_settings.get("recall_low_max_memories", 3), "低"),
        "medium": (memory_settings.get("recall_medium_score_threshold", 0.70), memory_settings.get("recall_medium_max_memories", 6), "中等"),
        "high": (memory_settings.get("recall_high_score_threshold", 0.55), memory_settings.get("recall_high_max_memories", 10), "高"),
    }
    return effort_map.get(effort, effort_map["medium"])


def format_recall_result(results, effort_label: str) -> str:
    if not results:
        return "未检索到符合条件的长期记忆。"

    lines = [f"已按{effort_label}努力程度检索到以下长期记忆："]
    for item in results:
        memory_text = str(item.get("memory", "")).strip()
        if memory_text:
            lines.append(f"- {memory_text}")
    return "\n".join(lines)


def build_recall_tool(settings: dict):
    @tool("recall_memory", parse_docstring=False)
    def recall_memory(query: str, effort: str = "medium") -> str:
        """按指定努力程度检索与当前问题相关的长期记忆。"""
        client = get_memory_client(settings)
        threshold, max_memories, effort_label = get_effort_config(settings, effort)
        raw_results = client.search(query, agent_id=settings.get("memory", {}).get("agent_id", "antlerbot"))
        results = raw_results.get("results", raw_results) if isinstance(raw_results, dict) else raw_results
        filtered = filter_search_results(results, threshold=threshold, max_memories=max_memories, seen_ids=set())
        return format_recall_result(filtered, effort_label)

    return recall_memory


def build_auto_recall_system_message(history: list[BaseMessage], settings: dict) -> SystemMessage | None:
    memory_settings = settings.get("memory", {})
    query = build_auto_recall_query(history, memory_settings.get("auto_recall_query_token_limit", 400))
    if not query:
        return None

    client = get_memory_client(settings)
    raw_results = client.search(query, agent_id=memory_settings.get("agent_id", "antlerbot"))
    results = raw_results.get("results", raw_results) if isinstance(raw_results, dict) else raw_results
    filtered = filter_search_results(
        results,
        threshold=memory_settings.get("auto_recall_score_threshold", 0.75),
        max_memories=memory_settings.get("auto_recall_max_memories", 5),
        seen_ids=get_seen_memory_ids(),
    )
    mark_seen_memory_ids(filtered)
    return format_auto_recall_message(filtered, memory_settings.get("auto_recall_system_prefix", "以下是可能与当前对话相关的长期记忆。仅在相关时使用，不要机械复述。"))


async def store_summary_async(summary_text: str, settings: dict) -> None:
    try:
        client = get_memory_client(settings)
        client.add(
            [{"role": "user", "content": summary_text}],
            agent_id=settings.get("memory", {}).get("agent_id", "antlerbot"),
        )
    except Exception:
        logger.warning("mem0 summary store failed", exc_info=True)


def mark_seen_memory_ids(results) -> None:
    for item in results:
        item_id = item.get("id")
        if item_id:
            _SEEN_MEMORY_IDS.add(str(item_id))


def reset_seen_memory_ids() -> None:
    _SEEN_MEMORY_IDS.clear()


def get_seen_memory_ids() -> set[str]:
    return set(_SEEN_MEMORY_IDS)
