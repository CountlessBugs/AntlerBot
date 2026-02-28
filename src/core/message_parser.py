import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from ncatbot.core.event.message_segment import (
    Text, At, AtAll, Face, Reply, Image, Record, Video, File,
)

from src.core import contact_cache, media_processor
from src.data.face_map import FACE_MAP

logger = logging.getLogger(__name__)


@dataclass
class MediaTask:
    placeholder_id: str
    task: asyncio.Task
    media_type: str  # "image" / "audio" / "video" / "document"
    filename: str = ""
    placeholder_tag: str = ""


@dataclass
class ParsedMessage:
    text: str
    media_tasks: list[MediaTask] = field(default_factory=list)

    def resolve(self, results: dict[str, str] | None = None) -> str:
        """Replace downloading placeholders with resolved media content."""
        if not results:
            return self.text
        out = self.text
        for mt in self.media_tasks:
            if mt.placeholder_id in results:
                out = out.replace(mt.placeholder_tag, results[mt.placeholder_id])
        return out


_MEDIA_TYPE_MAP = {
    Image: "image",
    Record: "audio",
    Video: "video",
    File: "document",
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


async def parse_message(message_array, settings: dict) -> ParsedMessage:
    parts: list[str] = []
    media_tasks: list[MediaTask] = []
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
                type_cfg = settings.get("media", {}).get(media_type, {})
                tag = media_processor._MEDIA_TAG.get(media_type, media_type)
                if type_cfg.get("transcribe", False):
                    pid = uuid.uuid4().hex[:12]
                    filename = getattr(seg, "file_name", "") or ""
                    fn_attr = f' filename="{filename}"' if filename else ""
                    placeholder = f'<{tag} status="downloading"{fn_attr} />'
                    parts.append(placeholder)
                    task = asyncio.create_task(
                        media_processor.process_media_segment(seg, media_type, settings)
                    )
                    media_tasks.append(MediaTask(
                        placeholder_id=pid, task=task, media_type=media_type,
                        filename=filename, placeholder_tag=placeholder,
                    ))
                else:
                    parts.append(f"<{tag} />")
            else:
                try:
                    summary = seg.get_summary()
                except Exception:
                    summary = None
                parts.append(summary or f'<unsupported type="{seg.type}" />')
    return ParsedMessage(text="".join(parts), media_tasks=media_tasks)
