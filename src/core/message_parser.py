import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field

from ncatbot.core.event.message_segment import (
    Text, At, AtAll, Face, Reply, Image, Record, Video, File,
)

from src.core import contact_cache, media_processor
from src.data.face_map import FACE_MAP

logger = logging.getLogger(__name__)

_EXT_MEDIA_TYPE = {
    "audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".amr", ".m4a", ".opus"},
    "video": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".tiff", ".ico"},
}


@dataclass
class MediaTask:
    placeholder_id: str
    task: asyncio.Task
    media_type: str  # "image" / "audio" / "video" / "document"
    filename: str = ""
    placeholder_tag: str = ""
    passthrough: bool = False


@dataclass
class ParsedMessage:
    text: str
    media_tasks: list[MediaTask] = field(default_factory=list)
    content_blocks: list[dict] = field(default_factory=list)


_MEDIA_TYPE_MAP = {
    Image: "image",
    Record: "audio",
    Video: "video",
    File: "document",
}


def _detect_file_media_type(filename: str) -> str:
    """Detect media type from file extension. Falls back to 'document'."""
    ext = os.path.splitext(filename)[1].lower()
    for media_type, exts in _EXT_MEDIA_TYPE.items():
        if ext in exts:
            return media_type
    return "document"


async def _parse_at(seg) -> str:
    if isinstance(seg, AtAll):
        return "@全体成员"
    user_id = str(seg.qq)
    remark = contact_cache.get_remark(user_id)
    return f"@{remark}" if remark else f"@{user_id}"


def _parse_face(seg) -> str:
    try:
        face_id = int(seg.id)
    except (ValueError, TypeError):
        face_id = None
    name = FACE_MAP.get(face_id) if face_id is not None else None
    return f'<face name="{name}" />' if name else "<face />"


def _parse_reply_segment(seg) -> str:
    """Parse a single segment from a reply message (lightweight, no async)."""
    if isinstance(seg, Text):
        return seg.text
    if isinstance(seg, Face):
        return _parse_face(seg)
    media_type = next(
        (mt for cls, mt in _MEDIA_TYPE_MAP.items() if isinstance(seg, cls)),
        None,
    )
    if media_type:
        tag = media_processor._MEDIA_TAG.get(media_type, media_type)
        filename = seg.get_file_name() if hasattr(seg, "get_file_name") else ""
        fn_attr = f' filename="{filename}"' if filename else ""
        return f"<{tag}{fn_attr} />"
    return ""


async def _parse_reply(seg, settings: dict) -> str:
    max_len = settings.get("reply_max_length", 50)
    try:
        from ncatbot.utils import status
        evt = await status.global_api.get_msg(seg.id)
        segments = getattr(evt, "message", None)
        if segments:
            content = "".join(_parse_reply_segment(s) for s in segments)
        else:
            content = evt.raw_message or ""
        if len(content) > max_len:
            content = content[:max_len] + "..."
        return f"<reply_to>{content}</reply_to>"
    except Exception:
        logger.warning("Failed to fetch reply message %s", seg.id, exc_info=True)
        return "<reply_to>无法获取原消息</reply_to>"


async def parse_message(message_array, settings: dict, source: str = "") -> ParsedMessage:
    parts: list[str] = []
    media_tasks: list[MediaTask] = []
    content_blocks: list[dict] = []
    for seg in message_array:
        if isinstance(seg, Text):
            parts.append(seg.text)
        elif isinstance(seg, (At, AtAll)):
            parts.append(await _parse_at(seg))
        elif isinstance(seg, Face):
            parts.append(_parse_face(seg))
        elif isinstance(seg, Reply):
            parts.append(await _parse_reply(seg, settings))
        else:
            media_type = next(
                (mt for cls, mt in _MEDIA_TYPE_MAP.items() if isinstance(seg, cls)),
                None,
            )
            if media_type:
                filename = seg.get_file_name() if hasattr(seg, "get_file_name") else ""
                if isinstance(seg, File) and filename:
                    media_type = _detect_file_media_type(filename)
                type_cfg = settings.get("media", {}).get(media_type, {})
                tag = media_processor._MEDIA_TAG.get(media_type, media_type)
                fn_attr = f' filename="{filename}"' if filename else ""
                if type_cfg.get("transcribe", False):
                    raw_size = getattr(seg, "file_size", None)
                    file_size = int(raw_size) if raw_size is not None else None
                    max_direct_mb = settings.get("media", {}).get("sync_process_threshold_mb")
                    max_direct = max_direct_mb * 1024 * 1024 if max_direct_mb is not None else None
                    is_small = (
                        max_direct is not None
                        and file_size is not None
                        and file_size <= max_direct
                    )
                    if is_small:
                        try:
                            result = await media_processor.process_media_segment(
                                seg, media_type, settings, source
                            )
                            parts.append(result)
                        except Exception:
                            logger.warning("Failed to process small media segment", exc_info=True)
                            parts.append(f'<{tag} error="处理失败" />')
                    else:
                        pid = uuid.uuid4().hex[:12]
                        placeholder = f'<{tag} status="loading"{fn_attr} />'
                        parts.append(placeholder)
                        task = asyncio.create_task(
                            media_processor.process_media_segment(seg, media_type, settings, source)
                        )
                        media_tasks.append(MediaTask(
                            placeholder_id=pid, task=task, media_type=media_type,
                            filename=filename, placeholder_tag=placeholder,
                        ))
                elif type_cfg.get("passthrough", False):
                    raw_size = getattr(seg, "file_size", None)
                    file_size = int(raw_size) if raw_size is not None else None
                    max_direct_mb = settings.get("media", {}).get("sync_process_threshold_mb")
                    max_direct = max_direct_mb * 1024 * 1024 if max_direct_mb is not None else None
                    is_small = (
                        max_direct is not None
                        and file_size is not None
                        and file_size <= max_direct
                    )
                    if is_small:
                        try:
                            block = await media_processor.passthrough_media_segment(
                                seg, media_type, settings, source
                            )
                            if block:
                                parts.append(f"<{tag}{fn_attr} />")
                                content_blocks.append(block)
                            else:
                                parts.append(f"<{tag}{fn_attr} />")
                        except Exception:
                            logger.warning("Failed to passthrough media segment", exc_info=True)
                            parts.append(f"<{tag}{fn_attr} />")
                    else:
                        pid = uuid.uuid4().hex[:12]
                        placeholder = f'<{tag} status="loading"{fn_attr} />'
                        parts.append(placeholder)
                        task = asyncio.create_task(
                            media_processor.passthrough_media_segment(
                                seg, media_type, settings, source
                            )
                        )
                        media_tasks.append(MediaTask(
                            placeholder_id=pid, task=task, media_type=media_type,
                            filename=filename, placeholder_tag=placeholder,
                            passthrough=True,
                        ))
                else:
                    parts.append(f"<{tag}{fn_attr} />")
            else:
                try:
                    summary = seg.get_summary()
                except Exception:
                    summary = None
                parts.append(summary or f'<unsupported type="{seg.type}" />')
    return ParsedMessage(text="".join(parts), media_tasks=media_tasks, content_blocks=content_blocks)
