"""视频元数据模型."""

from enum import StrEnum

from pydantic import BaseModel, Field


class VideoFormat(StrEnum):
    """视频格式枚举."""

    MP4 = "mp4"
    AVI = "avi"
    MOV = "mov"
    MKV = "mkv"
    WEBM = "webm"


class AudioInfo(BaseModel):
    """音频信息."""

    has_audio: bool = False
    sample_rate: int = 0
    channels: int = 0
    duration: float = 0.0
    codec: str = ""
    bitrate: int = 0
    avg_volume: float = 0.0
    peak_volume: float = 0.0
    tempo: float = 0.0
    is_silence: bool = False


class VideoMetadata(BaseModel):
    """视频元数据."""

    file_path: str = ""
    file_name: str = ""
    file_size: int = 0
    format: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    total_frames: int = 0
    video_codec: str = ""
    video_bitrate: int = 0
    audio: AudioInfo = Field(default_factory=AudioInfo)

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def aspect_ratio(self) -> str:
        from math import gcd

        if self.width == 0 or self.height == 0:
            return "unknown"
        g = gcd(self.width, self.height)
        return f"{self.width // g}:{self.height // g}"
