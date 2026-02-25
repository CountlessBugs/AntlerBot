import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from src.core.media_processor import check_ffmpeg, download_media


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
