import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from src.core.media_processor import check_ffmpeg, download_media, trim_media


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
