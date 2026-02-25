import asyncio
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
