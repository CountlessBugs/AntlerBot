import asyncio
import base64
import json
import logging
import os
import shutil
import tempfile

logger = logging.getLogger(__name__)

_ffmpeg_available: bool | None = None


def check_ffmpeg() -> bool:
    global _ffmpeg_available
    if _ffmpeg_available is None:
        _ffmpeg_available = shutil.which("ffmpeg") is not None
        if _ffmpeg_available:
            logger.info("ffmpeg found")
        else:
            logger.warning("ffmpeg not found; audio/video trimming disabled")
    return _ffmpeg_available


async def download_media(seg) -> str | None:
    """Download a media segment to a temp file. Returns the file path or None on failure."""
    try:
        tmp_dir = tempfile.mkdtemp(prefix="antlerbot_media_")
        path = await seg.download(tmp_dir)
        return path
    except Exception:
        logger.warning("Failed to download media: %s", getattr(seg, "file_name", "unknown"), exc_info=True)
        return None


async def _get_duration(path: str) -> float:
    """Get media duration in seconds using ffprobe."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        info = json.loads(stdout)
        return float(info["format"]["duration"])
    except Exception:
        logger.warning("ffprobe failed for %s", path, exc_info=True)
        return 0.0


async def _run_ffmpeg_trim(input_path: str, max_duration: int) -> str | None:
    """Trim media to max_duration seconds. Returns output path or None."""
    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_trimmed{ext}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", input_path,
            "-t", str(max_duration),
            "-c", "copy", output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode == 0:
            return output_path
        logger.warning("ffmpeg trim failed with code %d", proc.returncode)
        return None
    except Exception:
        logger.warning("ffmpeg trim error for %s", input_path, exc_info=True)
        return None


async def trim_media(path: str, max_duration: int) -> str | None:
    """Trim media if over max_duration. Returns path (original or trimmed) or None if skip."""
    if max_duration <= 0:
        return path
    duration = await _get_duration(path)
    if duration <= max_duration:
        return path
    if not check_ffmpeg():
        logger.warning("File %s exceeds %ds but ffmpeg unavailable, skipping", path, max_duration)
        return None
    return await _run_ffmpeg_trim(path, max_duration)


_transcription_llm = None

_TRANSCRIPTION_PROMPTS = {
    "image": "请简要描述这张图片的内容，用一两句话概括。",
    "audio": "请转述这段音频的内容。",
    "video": "请简要描述这段视频的内容，用一两句话概括。",
    "document": "请简要概括这份文档的内容。",
}


def _get_transcription_llm(settings: dict | None = None):
    """Get or create the transcription LLM. Uses main LLM if no override configured."""
    global _transcription_llm
    if _transcription_llm is not None:
        return _transcription_llm

    model = os.environ.get("TRANSCRIPTION_MODEL", "")
    provider = os.environ.get("TRANSCRIPTION_PROVIDER", "")

    if model and provider:
        api_key = os.environ.get("TRANSCRIPTION_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        base_url = os.environ.get("TRANSCRIPTION_BASE_URL", os.environ.get("OPENAI_BASE_URL", ""))
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        from langchain.chat_models import init_chat_model
        _transcription_llm = init_chat_model(model, model_provider=provider, **kwargs)
    else:
        from src.core.agent import _llm, _ensure_initialized
        _ensure_initialized()
        _transcription_llm = _llm

    return _transcription_llm


async def transcribe_media(path: str, media_type: str, settings: dict | None = None) -> str | None:
    """Transcribe a media file using the configured LLM. Returns description text or None."""
    try:
        llm = _get_transcription_llm(settings)
        prompt = _TRANSCRIPTION_PROMPTS.get(media_type, "请描述这个文件的内容。")

        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

        mime_map = {
            "image": "image/png",
            "audio": "audio/mpeg",
            "video": "video/mp4",
            "document": "application/pdf",
        }
        mime = mime_map.get(media_type, "application/octet-stream")

        from langchain_core.messages import HumanMessage
        msg = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
        ])
        response = llm.invoke([msg])
        return response.content
    except Exception:
        logger.warning("Transcription failed for %s (%s)", path, media_type, exc_info=True)
        return None


_MEDIA_TAG = {
    "image": "image",
    "audio": "audio",
    "video": "video",
    "document": "file",
}


def _cleanup_temp(path: str) -> None:
    """Remove a temp file and its parent dir if empty."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
            parent = os.path.dirname(path)
            if parent and not os.listdir(parent):
                os.rmdir(parent)
    except Exception:
        logger.debug("Cleanup failed for %s", path, exc_info=True)


async def process_media_segment(seg, media_type: str, settings: dict) -> str:
    """Full pipeline: download → trim → transcribe → format result."""
    tag = _MEDIA_TAG.get(media_type, media_type)
    type_cfg = settings.get("media", {}).get(media_type, {})
    filename = getattr(seg, "file_name", "") or ""

    if not type_cfg.get("transcribe", False):
        return f"<{tag} />"

    # Download
    path = await download_media(seg)
    if not path:
        return f'<{tag} error="下载失败" />'

    try:
        # Trim (audio/video only)
        if media_type in ("audio", "video"):
            max_dur = type_cfg.get("max_duration", 0)
            if max_dur > 0:
                trimmed = await trim_media(path, max_dur)
                if trimmed is None:
                    if type_cfg.get("trim_over_limit", True):
                        return f'<{tag} error="裁剪失败" />'
                    else:
                        return f"<{tag} />"
                if trimmed != path:
                    _cleanup_temp(path)
                    path = trimmed

        # Transcribe
        desc = await transcribe_media(path, media_type, settings)
        if desc:
            fn_attr = f' filename="{filename}"' if filename else ""
            return f"<{tag}{fn_attr}>{desc}</{tag}>"
        return f'<{tag} error="转述失败" />'
    finally:
        _cleanup_temp(path)
