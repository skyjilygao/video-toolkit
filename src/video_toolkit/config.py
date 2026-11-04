"""全局配置管理."""
import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    """全局配置."""

    # 默认测试视频目录
    DEFAULT_TEST_VIDEO_DIR: str = r"\\192.168.88.121\.n8n-files\video_download\video\2026-11-02\20261102"

    def __init__(self):
        self._fal_key: Optional[str] = None
        self._openai_key: Optional[str] = None
        self._elevenlabs_key: Optional[str] = None

    @property
    def fal_key(self) -> Optional[str]:
        if self._fal_key is None:
            self._fal_key = os.environ.get("FAL_KEY", "")
        return self._fal_key or None

    @property
    def openai_key(self) -> Optional[str]:
        if self._openai_key is None:
            self._openai_key = os.environ.get("OPENAI_API_KEY", "")
        return self._openai_key or None

    @property
    def elevenlabs_key(self) -> Optional[str]:
        if self._elevenlabs_key is None:
            self._elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY", "")
        return self._elevenlabs_key or None

    @property
    def test_video_dir(self) -> str:
        return os.environ.get("TEST_VIDEO_DIR", self.DEFAULT_TEST_VIDEO_DIR)

    def get_ffmpeg_path(self) -> str:
        return os.environ.get("FFMPEG_PATH", "ffmpeg")

    def get_ffprobe_path(self) -> str:
        return os.environ.get("FFPROBE_PATH", "ffprobe")


# 全局单例
config = Config()
