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
