import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from ncatbot.core.event.message_segment import (
    Text, At, AtAll, Face, Reply, Image, Record, Video, File,
)

from src.core import contact_cache
from src.data.face_map import FACE_MAP

logger = logging.getLogger(__name__)

MEDIA_PREFIX = "media:"


@dataclass
class MediaTask:
    placeholder_id: str
    task: asyncio.Task
    media_type: str  # "image" / "audio" / "video" / "document"


@dataclass
class ParsedMessage:
    text: str
    media_tasks: list[MediaTask] = field(default_factory=list)

    def resolve(self, results: dict[str, str] | None = None) -> str:
        if not results:
            return self.text
        out = self.text
        for pid, replacement in results.items():
            out = out.replace(f"{{{{{MEDIA_PREFIX}{pid}}}}}", replacement)
        return out


_MEDIA_PLACEHOLDERS = {
    Image: "<image />",
    Record: "<audio />",
    Video: "<video />",
    File: "<file />",
}


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


async def _parse_reply(seg, settings: dict) -> str:
    max_len = settings.get("reply_max_length", 50)
    try:
        from ncatbot.utils import status
        evt = await status.global_api.get_msg(seg.id)
        content = evt.raw_message or ""
        if len(content) > max_len:
            content = content[:max_len] + "..."
        return f"<reply_to>{content}</reply_to>"
    except Exception:
        logger.warning("Failed to fetch reply message %s", seg.id, exc_info=True)
        return "<reply_to>无法获取原消息</reply_to>"


async def parse_message(message_array, settings: dict) -> str:
    parts: list[str] = []
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
            placeholder = next(
                (ph for cls, ph in _MEDIA_PLACEHOLDERS.items() if isinstance(seg, cls)),
                None,
            )
            if placeholder:
                parts.append(placeholder)
            else:
                try:
                    summary = seg.get_summary()
                except Exception:
                    summary = None
                parts.append(summary or f'<unsupported type="{seg.type}" />')
    return "".join(parts)
