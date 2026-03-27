import importlib
import logging
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import MethodType

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


def _parse_neo4j_auth(value: str | None) -> tuple[str | None, str | None]:
    if not value or "/" not in value:
        return None, None
    username, password = value.split("/", 1)
    return (username or None), (password or None)


def _apply_graph_env_overrides(config: dict) -> dict:
    neo4j_auth_username, neo4j_auth_password = _parse_neo4j_auth(_get_env("NEO4J_AUTH"))
    return {
        **config,
        "url": _get_env("MEM0_GRAPH_NEO4J_URL") or config.get("url"),
        "username": neo4j_auth_username or config.get("username"),
        "password": neo4j_auth_password or config.get("password"),
    }


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



def _resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[2]



def _resolve_vector_store_config(settings: dict) -> dict:
    vector_store_settings = settings.get("memory", {}).get("vector_store", {})
    provider = vector_store_settings.get("provider", "qdrant")
    config = {
        **{
            "collection_name": "mem0",
            "path": "data/mem0/qdrant",
            "on_disk": True,
        },
        **dict(vector_store_settings.get("config", {})),
    }
    if provider == "qdrant" and config.get("path"):
        vector_path = Path(str(config["path"]))
        if not vector_path.is_absolute():
            config["path"] = str((_resolve_project_root() / vector_path).resolve())
    return {"provider": provider, "config": config}



def _patch_mem0_neo4jgraph_signature_compat() -> None:
    graph_memory_module = sys.modules.get("mem0.memory.graph_memory")
    if graph_memory_module is None:
        return

    neo4j_graph_class = getattr(graph_memory_module, "Neo4jGraph", None)
    if neo4j_graph_class is None or getattr(neo4j_graph_class, "_antlerbot_signature_compat_patch", False):
        return

    original_init = getattr(neo4j_graph_class, "__init__", None)
    if not callable(original_init):
        return

    def patched_init(self, url=None, username=None, password=None, *args, **kwargs):
        if args and "database" not in kwargs and "token" not in kwargs:
            database, *remaining_args = args
            return original_init(
                self,
                url=url,
                username=username,
                password=password,
                token=None,
                database=database,
                *remaining_args,
                **kwargs,
            )
        return original_init(self, url=url, username=username, password=password, *args, **kwargs)

    neo4j_graph_class.__init__ = patched_init
    neo4j_graph_class._antlerbot_signature_compat_patch = True



def _resolve_graph_store_config(settings: dict) -> dict | None:
    graph_settings = settings.get("memory", {}).get("graph", {})
    if not graph_settings.get("enabled"):
        return None

    max_hops = graph_settings.get("max_hops", 1)
    if max_hops != 1:
        raise RuntimeError("memory.graph.max_hops currently only supports value 1.")

    provider = graph_settings.get("provider", "neo4j")
    config = {
        key: str(value) if value is not None and not isinstance(value, str) else value
        for key, value in dict(graph_settings.get("config", {})).items()
    }
    if provider == "neo4j":
        config = _apply_graph_env_overrides(config)

    required_fields_by_provider = {
        "neo4j": ("url", "username", "password"),
        "memgraph": ("url", "username", "password"),
    }
    provider_graph_modules = {
        "neo4j": "mem0.memory.graph_memory",
        "memgraph": "mem0.memory.graph_memory",
    }
    missing_fields = [field for field in required_fields_by_provider.get(provider, ()) if not config.get(field)]
    if missing_fields:
        raise RuntimeError(
            f"memory.graph.config missing required fields for {provider}: {', '.join(missing_fields)}"
        )

    graph_module = provider_graph_modules.get(provider)
    if graph_module is not None:
        try:
            importlib.import_module(graph_module)
            _patch_mem0_neo4jgraph_signature_compat()
            _verify_graph_connectivity(provider, config)
        except Exception as exc:
            raise RuntimeError(
                f"memory.graph provider '{provider}' is unavailable or unreachable"
            ) from exc

    return {
        "provider": provider,
        "config": config,
    }





def _verify_graph_connectivity(provider: str, config: dict) -> None:
    if provider not in {"neo4j", "memgraph"}:
        return
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        config.get("url"),
        auth=(config.get("username"), config.get("password")),
    )
    try:
        driver.verify_connectivity()
    finally:
        driver.close()


def _patch_vector_store_update_for_payload_only(vector_store) -> None:
    if getattr(vector_store, "_antlerbot_payload_only_patch", False):
        return

    client = getattr(vector_store, "client", None)
    collection_name = getattr(vector_store, "collection_name", None)
    original_update = getattr(vector_store, "update", None)
    set_payload = getattr(client, "set_payload", None)
    if not callable(original_update) or not callable(set_payload) or not collection_name:
        return

    def patched_update(self, vector_id, vector=None, payload=None):
        if vector is None and payload is not None:
            set_payload(collection_name=collection_name, payload=payload, points=[vector_id])
            return None
        return original_update(vector_id=vector_id, vector=vector, payload=payload)

    vector_store.update = MethodType(patched_update, vector_store)
    vector_store._antlerbot_payload_only_patch = True


def get_memory_store(settings: dict):
    global _MEMORY_STORE
    if _MEMORY_STORE is None:
        from mem0 import Memory
        from mem0.configs.base import MemoryConfig

        config_kwargs = {
            "llm": _resolve_mem0_llm_config(),
            "embedder": _resolve_mem0_embedder_config(),
            "vector_store": _resolve_vector_store_config(settings),
        }
        try:
            graph_store = _resolve_graph_store_config(settings)
        except Exception:
            logger.warning("Mem0 graph store configuration is invalid; falling back to vector-only mode.", exc_info=True)
            graph_store = None
        if graph_store is not None:
            try:
                _MEMORY_STORE = Memory(MemoryConfig(**{**config_kwargs, "graph_store": graph_store}))
            except Exception:
                failed_store = _MEMORY_STORE
                if failed_store is not None:
                    _close_memory_store_vector_store(failed_store)
                _MEMORY_STORE = None
                logger.warning("Mem0 graph store initialization failed; falling back to vector-only mode.", exc_info=True)
                _MEMORY_STORE = Memory(MemoryConfig(**config_kwargs))
        else:
            _MEMORY_STORE = Memory(MemoryConfig(**config_kwargs))
        vector_store = getattr(_MEMORY_STORE, "vector_store", None)
        if vector_store is not None:
            _patch_vector_store_update_for_payload_only(vector_store)
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


def build_memory_creation_metadata(created_at: str) -> dict:
    return {
        "created_at": created_at,
        "last_updated_at": created_at,
        "update_count": 0,
    }


def build_memory_creation_metadata_update(current_metadata: dict | None, created_at: str) -> dict:
    if not isinstance(current_metadata, dict):
        current_metadata = {}
    metadata = dict(current_metadata)
    metadata.update(build_memory_creation_metadata(created_at))
    return metadata


def build_memory_content_update_metadata(current_metadata: dict | None, updated_at: str, *, created_at: str | None = None) -> dict:
    if not isinstance(current_metadata, dict):
        current_metadata = {}
    metadata = dict(current_metadata)
    created_at = created_at or metadata.get("created_at") or updated_at
    current_count = metadata.get("update_count", 0)
    try:
        current_count = int(current_count)
    except (TypeError, ValueError):
        current_count = 0
    metadata["created_at"] = created_at
    metadata["last_updated_at"] = updated_at
    metadata["update_count"] = current_count + 1
    return metadata


def _resolve_original_created_at(store, memory_id: str, current_metadata: dict | None) -> str | None:
    if isinstance(current_metadata, dict):
        created_at = current_metadata.get("created_at")
        if created_at:
            current_created_at = str(created_at)
        else:
            current_created_at = None
    else:
        current_created_at = None

    history_method = getattr(store, "history", None)
    if not callable(history_method):
        return current_created_at

    try:
        history_entries = history_method(memory_id=memory_id)
    except TypeError:
        try:
            history_entries = history_method(memory_id)
        except Exception:
            return current_created_at
    except Exception:
        return current_created_at

    if not isinstance(history_entries, list):
        return current_created_at

    created_candidates = []
    for entry in history_entries:
        if not isinstance(entry, dict):
            continue
        metadata = entry.get("metadata")
        if not isinstance(metadata, dict):
            continue
        created_at = metadata.get("created_at")
        if created_at:
            created_candidates.append(str(created_at))

    if not created_candidates:
        return current_created_at
    return min(created_candidates)


def try_update_memory_creation_metadata(store, memory_id: str, created_at: str) -> bool:
    get_method = getattr(store, "get", None)
    update_method = getattr(store, "update", None)
    internal_update_method = getattr(store, "_update_memory", None)
    if not callable(get_method) or (not callable(update_method) and not callable(internal_update_method)):
        logger.info("mem0 memory store does not support get/update metadata operations")
        return False

    try:
        current = get_method(memory_id=memory_id)
        if not isinstance(current, dict):
            logger.info("mem0 get did not return a mapping for creation metadata update")
            return False

        text = current.get("memory") or current.get("text")
        if not text:
            logger.info("mem0 creation metadata update skipped because original memory text is unavailable")
            return False

        metadata = build_memory_creation_metadata_update(current.get("metadata", {}), created_at)

        if callable(internal_update_method):
            internal_update_method(memory_id, text, {}, metadata=metadata)
        else:
            try:
                update_method(memory_id, text, metadata=metadata)
            except TypeError:
                update_method(memory_id, {"memory": text, "metadata": metadata})
        return True
    except Exception:
        logger.warning("mem0 creation metadata update failed", exc_info=True)
        return False


def try_update_memory_content_metadata(store, memory_id: str, updated_at: str) -> bool:
    get_method = getattr(store, "get", None)
    update_method = getattr(store, "update", None)
    internal_update_method = getattr(store, "_update_memory", None)
    if not callable(get_method) or (not callable(update_method) and not callable(internal_update_method)):
        logger.info("mem0 memory store does not support get/update metadata operations")
        return False

    try:
        current = get_method(memory_id=memory_id)
        if not isinstance(current, dict):
            logger.info("mem0 get did not return a mapping for content metadata update")
            return False

        text = current.get("memory") or current.get("text")
        if not text:
            logger.info("mem0 content metadata update skipped because original memory text is unavailable")
            return False

        original_created_at = _resolve_original_created_at(store, memory_id, current.get("metadata", {}))
        metadata = build_memory_content_update_metadata(
            current.get("metadata", {}),
            updated_at,
            created_at=original_created_at,
        )

        if callable(internal_update_method):
            internal_update_method(memory_id, text, {}, metadata=metadata)
        else:
            try:
                update_method(memory_id, text, metadata=metadata)
            except TypeError:
                update_method(memory_id, {"memory": text, "metadata": metadata})
        return True
    except Exception:
        logger.warning("mem0 content metadata update failed", exc_info=True)
        return False


def try_update_memory_recall_metadata(store, memory_id: str, recalled_at: str) -> bool:
    get_method = getattr(store, "get", None)
    update_method = getattr(store, "update", None)
    internal_update_method = getattr(store, "_update_memory", None)
    if not callable(get_method) or (not callable(update_method) and not callable(internal_update_method)):
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

        if callable(internal_update_method):
            internal_update_method(memory_id, text, {}, metadata=metadata)
        else:
            try:
                update_method(memory_id, text, metadata=metadata)
            except TypeError:
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


def build_temporary_auto_recall_message(results, prefix: str, relations=None, relation_prefix: str | None = None) -> SystemMessage | None:
    message = format_auto_recall_message(results, prefix, relations=relations, relation_prefix=relation_prefix)
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


def _build_mem0_scope_kwargs(settings: dict) -> dict:
    memory_settings = settings.get("memory", {})
    agent_id = memory_settings.get("agent_id", "antlerbot")
    scope = {"agent_id": agent_id}
    if memory_settings.get("graph", {}).get("enabled"):
        scope["user_id"] = agent_id
    return scope



def build_recall_tool(settings: dict):
    @tool("recall_memory", parse_docstring=False)
    def recall_memory(query: str, effort: str = "medium") -> str:
        """按指定努力程度检索与当前问题相关的长期记忆。"""
        store = get_memory_store(settings)
        threshold, max_memories, effort_label = get_effort_config(settings, effort)
        memory_settings = settings.get("memory", {})
        graph_settings = memory_settings.get("graph", {})
        raw_results = store.search(query, **_build_mem0_scope_kwargs(settings))
        results = raw_results.get("results", raw_results) if isinstance(raw_results, dict) else raw_results
        filtered = filter_search_results(
            results,
            threshold=threshold,
            max_memories=max_memories,
            blocked_ids=get_context_locked_memory_ids(),
        )
        relations = []
        if isinstance(raw_results, dict) and graph_settings.get("enabled") and graph_settings.get("manual_recall_enabled"):
            relations = _trim_relations(raw_results.get("relations", []), graph_settings.get("context_max_relations", 8))
        relation_prefix = graph_settings.get("context_prefix") if graph_settings.get("enabled") else None
        recalled_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        for item in filtered:
            item_id = item.get("id")
            if item_id and str(item_id) not in _COUNTED_MEMORY_IDS:
                try_update_memory_recall_metadata(store, str(item_id), recalled_at)
        mark_counted_memory_ids(filtered)
        lock_memory_ids_for_session(filtered)
        return format_recall_result(filtered, effort_label, relations=relations, relation_prefix=relation_prefix)

    return recall_memory


def build_auto_recall_system_message(history: list[BaseMessage], settings: dict) -> SystemMessage | None:
    memory_settings = settings.get("memory", {})
    graph_settings = memory_settings.get("graph", {})
    query = build_auto_recall_query(history, memory_settings.get("auto_recall_query_token_limit", 400))
    if not query:
        return None

    store = get_memory_store(settings)
    raw_results = store.search(query, **_build_mem0_scope_kwargs(settings))
    results = raw_results.get("results", raw_results) if isinstance(raw_results, dict) else raw_results
    filtered = filter_search_results(
        results,
        threshold=memory_settings.get("auto_recall_score_threshold", 0.75),
        max_memories=memory_settings.get("auto_recall_max_memories", 5),
        blocked_ids=get_context_locked_memory_ids(),
    )
    if not filtered:
        return None

    relations = []
    if isinstance(raw_results, dict) and graph_settings.get("enabled") and graph_settings.get("auto_recall_enabled"):
        relations = _trim_relations(raw_results.get("relations", []), graph_settings.get("context_max_relations", 8))

    relation_prefix = graph_settings.get("context_prefix") if graph_settings.get("enabled") else None
    recalled_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    for item in filtered:
        item_id = item.get("id")
        if item_id and str(item_id) not in _COUNTED_MEMORY_IDS:
            try_update_memory_recall_metadata(store, str(item_id), recalled_at)
    mark_counted_memory_ids(filtered)
    return build_temporary_auto_recall_message(
        filtered,
        memory_settings.get("auto_recall_system_prefix", "以下是可能与当前对话相关的长期记忆。仅在相关时使用，不要机械复述。"),
        relations=relations,
        relation_prefix=relation_prefix,
    )


async def store_summary_async(summary_text: str, settings: dict) -> None:
    try:
        store = get_memory_store(settings)
        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        result = store.add(
            [{"role": "user", "content": summary_text}],
            **_build_mem0_scope_kwargs(settings),
        )
        operations = result.get("results", []) if isinstance(result, dict) else []
        for item in operations:
            if not isinstance(item, dict):
                continue
            memory_id = item.get("id")
            if not memory_id:
                continue
            event = item.get("event")
            if event == "ADD":
                try_update_memory_creation_metadata(store, str(memory_id), created_at)
            elif event == "UPDATE":
                try_update_memory_content_metadata(store, str(memory_id), created_at)
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
