"""视频源抽象基类 — 本地文件 / 在线 URL 的统一获取接口."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from video_toolkit.utils.ffprobe_utils import get_video_info


class VideoSourceError(Exception):
    """视频源获取失败时抛出的统一异常."""


@dataclass
class SourceVideo:
    """解析后的本地视频文件信息."""

    local_path: str
    source_type: str  # local / youtube / direct
    original_source: str  # 用户输入（本地路径或 URL）
    title: str = ""
    duration: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def filename(self) -> str:
        """文件名（含扩展名）."""
        return os.path.basename(self.local_path)


class VideoSource(ABC):
    """视频源抽象基类.

    新增视频源时实现此接口并注册到 ``sources.__init__._SOURCES`` 即可，
    例如：B 站、抖音、或直接替换为其他下载库。
    """

    name: str = "base"

    @abstractmethod
    def supports(self, source: str) -> bool:
        """判断该来源是否支持给定的输入."""

    @abstractmethod
    def fetch(self, source: str, output_dir: str) -> SourceVideo:
        """获取视频到本地，返回 :class:`SourceVideo`."""


def ensure_valid_video_file(local_path: str) -> None:
    """校验文件确为可读视频（FFprobe 能解析出时长与画面）.

    用于拦截「URL 被当作直链下载」后保存下来的 HTML/JSON 等非视频文件：
    例如 YouTube Shorts 页面被 DirectUrlSource 下载会得到 ``*.mp4`` 后缀的
    网页内容，若不拦截会在分析阶段静默产出空结果。

    Parameters
    ----------
    local_path : str
        待校验的本地文件路径.

    Raises
    ------
    VideoSourceError
        文件不存在、FFprobe 无法解析、时长为 0 或缺少视频流时抛出。
    """
    if not os.path.isfile(local_path):
        raise VideoSourceError(f"文件不存在: {local_path}")
    info = get_video_info(local_path)
    if info.get("duration", 0.0) <= 0.0 or info.get("width", 0) <= 0:
        raise VideoSourceError(
            f"文件不是有效的视频（FFprobe 无法解析出时长/画面）: {local_path}"
        )
