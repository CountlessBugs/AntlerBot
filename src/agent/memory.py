import logging
import re

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately

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


def mark_seen_memory_ids(results) -> None:
    for item in results:
        item_id = item.get("id")
        if item_id:
            _SEEN_MEMORY_IDS.add(str(item_id))


def reset_seen_memory_ids() -> None:
    _SEEN_MEMORY_IDS.clear()


def get_seen_memory_ids() -> set[str]:
    return set(_SEEN_MEMORY_IDS)
