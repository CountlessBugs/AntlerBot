import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from src.core.media_processor import (
    check_ffmpeg, download_media, trim_media, transcribe_media,
    process_media_segment, passthrough_media_segment,
)


@pytest.fixture(autouse=True)
def reset_ffmpeg_cache():
    import src.core.media_processor as mp
    mp._ffmpeg_available = None
    yield
    mp._ffmpeg_available = None


def test_check_ffmpeg_available():
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        assert check_ffmpeg() is True


def test_check_ffmpeg_unavailable():
    with patch("shutil.which", return_value=None):
        assert check_ffmpeg() is False


def test_check_ffmpeg_caches_result():
    with patch("shutil.which", return_value="/usr/bin/ffmpeg") as mock_which:
        check_ffmpeg()
        check_ffmpeg()
        mock_which.assert_called_once()


@pytest.mark.anyio
async def test_download_media_from_url():
    seg = MagicMock()
    seg.url = "https://example.com/pic.jpg"
    seg.file_name = "pic.jpg"
    seg.download = AsyncMock(return_value="/tmp/pic.jpg")
    result = await download_media(seg)
    seg.download.assert_awaited_once()
    assert result is not None


# --- Trim ---

@pytest.mark.anyio
async def test_trim_media_under_limit():
    """File under max_duration is returned as-is."""
    with patch("src.core.media_processor._get_duration", return_value=30.0):
        result = await trim_media("/tmp/voice.amr", max_duration=60)
        assert result == "/tmp/voice.amr"


@pytest.mark.anyio
async def test_trim_media_over_limit_trims():
    """File over max_duration gets trimmed via ffmpeg."""
    with patch("src.core.media_processor._get_duration", return_value=120.0), \
         patch("src.core.media_processor.check_ffmpeg", return_value=True), \
         patch("src.core.media_processor._run_ffmpeg_trim", new_callable=AsyncMock, return_value="/tmp/trimmed.amr"):
        result = await trim_media("/tmp/voice.amr", max_duration=60)
        assert result == "/tmp/trimmed.amr"


@pytest.mark.anyio
async def test_trim_media_over_limit_no_ffmpeg():
    """File over limit with no ffmpeg returns None."""
    with patch("src.core.media_processor._get_duration", return_value=120.0), \
         patch("src.core.media_processor.check_ffmpeg", return_value=False):
        result = await trim_media("/tmp/voice.amr", max_duration=60)
        assert result is None


@pytest.mark.anyio
async def test_trim_media_zero_max_duration():
    """max_duration=0 means unlimited, no trim."""
    with patch("src.core.media_processor._get_duration", return_value=9999.0):
        result = await trim_media("/tmp/voice.amr", max_duration=0)
        assert result == "/tmp/voice.amr"


# --- Transcribe ---

@pytest.mark.anyio
async def test_transcribe_image():
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="一只橘猫趴在沙发上"))
    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    mock_file.read.return_value = b"fake image bytes"
    with patch("src.core.media_processor._get_transcription_llm", return_value=mock_llm), \
         patch("builtins.open", return_value=mock_file):
        result = await transcribe_media("/tmp/cat.jpg", "image")
        assert result == "一只橘猫趴在沙发上"


@pytest.mark.anyio
async def test_transcribe_audio():
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="用户说了你好"))
    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    mock_file.read.return_value = b"fake audio bytes"
    with patch("src.core.media_processor._get_transcription_llm", return_value=mock_llm), \
         patch("builtins.open", return_value=mock_file):
        result = await transcribe_media("/tmp/voice.amr", "audio")
        assert result == "用户说了你好"


@pytest.mark.anyio
async def test_transcribe_failure():
    with patch("src.core.media_processor._get_transcription_llm", side_effect=Exception("no model")):
        result = await transcribe_media("/tmp/cat.jpg", "image")
        assert result is None


# --- Process media segment ---

@pytest.mark.anyio
async def test_process_image_transcribe():
    seg = MagicMock()
    seg.url = "https://example.com/cat.jpg"
    seg.file_name = "cat.jpg"
    seg.get_file_name.return_value = "cat.jpg"
    seg.download = AsyncMock(return_value="/tmp/cat.jpg")
    settings = {"media": {"image": {"transcribe": True}}}
    with patch("src.core.media_processor.transcribe_media", new_callable=AsyncMock, return_value="一只猫"), \
         patch("src.core.media_processor._cleanup_temp"):
        result = await process_media_segment(seg, "image", settings)
        assert result == '<image filename="cat.jpg">一只猫</image>'


@pytest.mark.anyio
async def test_process_image_disabled():
    seg = MagicMock()
    seg.file_name = "cat.jpg"
    seg.get_file_name.return_value = "cat.jpg"
    settings = {"media": {"image": {"transcribe": False}}}
    result = await process_media_segment(seg, "image", settings)
    assert result == '<image filename="cat.jpg" />'


@pytest.mark.anyio
async def test_process_audio_transcribe_with_trim():
    seg = MagicMock()
    seg.file_name = "voice.amr"
    seg.get_file_name.return_value = "voice.amr"
    seg.download = AsyncMock(return_value="/tmp/voice.amr")
    settings = {"media": {"audio": {"transcribe": True, "max_duration": 60, "trim_over_limit": True}}}
    with patch("src.core.media_processor.trim_media", new_callable=AsyncMock, return_value="/tmp/voice.amr"), \
         patch("src.core.media_processor.transcribe_media", new_callable=AsyncMock, return_value="你好"), \
         patch("src.core.media_processor._cleanup_temp"):
        result = await process_media_segment(seg, "audio", settings)
        assert result == '<audio filename="voice.amr">你好</audio>'


@pytest.mark.anyio
async def test_process_download_failure():
    seg = MagicMock()
    seg.file_name = "pic.jpg"
    seg.get_file_name.return_value = "pic.jpg"
    seg.download = AsyncMock(side_effect=Exception("network error"))
    settings = {"media": {"image": {"transcribe": True}}}
    result = await process_media_segment(seg, "image", settings)
    assert result == '<image filename="pic.jpg" error="download_failed" />'


@pytest.mark.anyio
async def test_process_transcription_failure():
    seg = MagicMock()
    seg.file_name = "pic.jpg"
    seg.get_file_name.return_value = "pic.jpg"
    seg.download = AsyncMock(return_value="/tmp/pic.jpg")
    settings = {"media": {"image": {"transcribe": True}}}
    with patch("src.core.media_processor.transcribe_media", new_callable=AsyncMock, return_value=None), \
         patch("src.core.media_processor._cleanup_temp"):
        result = await process_media_segment(seg, "image", settings)
        assert result == '<image filename="pic.jpg" error="transcription_failed" />'


# --- Passthrough ---

@pytest.mark.anyio
async def test_passthrough_image():
    seg = MagicMock()
    seg.url = "https://example.com/cat.jpg"
    seg.get_file_name.return_value = "cat.jpg"
    seg.download = AsyncMock(return_value="/tmp/cat.jpg")
    settings = {"media": {"image": {"passthrough": True}}}
    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    mock_file.read.return_value = b"fake image bytes"
    with patch("builtins.open", return_value=mock_file), \
         patch("src.core.media_processor._cleanup_temp"):
        result = await passthrough_media_segment(seg, "image", settings)
        assert result is not None
        assert result["type"] == "image_url"
        assert result["image_url"]["url"].startswith("data:image/")


@pytest.mark.anyio
async def test_passthrough_disabled():
    seg = MagicMock()
    seg.get_file_name.return_value = "cat.jpg"
    settings = {"media": {"image": {"passthrough": False}}}
    result = await passthrough_media_segment(seg, "image", settings)
    assert result is None


@pytest.mark.anyio
async def test_passthrough_download_failure():
    seg = MagicMock()
    seg.get_file_name.return_value = "cat.jpg"
    seg.download = AsyncMock(side_effect=Exception("network error"))
    settings = {"media": {"image": {"passthrough": True}}}
    result = await passthrough_media_segment(seg, "image", settings)
    assert result is None


@pytest.mark.anyio
async def test_passthrough_audio_with_trim():
    seg = MagicMock()
    seg.url = "https://example.com/voice.amr"
    seg.get_file_name.return_value = "voice.amr"
    seg.download = AsyncMock(return_value="/tmp/voice.amr")
    settings = {"media": {"audio": {"passthrough": True, "max_duration": 60}}}
    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    mock_file.read.return_value = b"fake audio bytes"
    with patch("builtins.open", return_value=mock_file), \
         patch("src.core.media_processor.trim_media", new_callable=AsyncMock, return_value="/tmp/voice.amr"), \
         patch("src.core.media_processor._cleanup_temp"):
        result = await passthrough_media_segment(seg, "audio", settings)
        assert result is not None
        assert result["image_url"]["url"].startswith("data:audio/")
