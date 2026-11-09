"""视频源模块 — 统一解析本地路径与在线视频 URL.

支持的视频源（按注册顺序尝试）:
- ``local``   : 本地视频文件路径
- ``youtube``: YouTube / yt-dlp 支持的 1000+ 站点（需要 yt-dlp 可选依赖）
- ``direct`` : 通用 HTTP(S) 直链下载（yt-dlp 失败时的降级）

用法:
    from video_toolkit.sources import resolve_video_source

    video = resolve_video_source("https://youtube.com/shorts/xxx", output_dir="./downloads")

切换/扩展视频源:
    1. 在 sources/ 下新建 ``VideoSource`` 子类
    2. 调用 :func:`register_source` 注册，或修改 ``_SOURCES`` 顺序
"""

from __future__ import annotations

import os

from video_toolkit.sources.base import (
    SourceVideo,
    VideoSource,
    VideoSourceError,
    ensure_valid_video_file,
)
from video_toolkit.sources.direct import DirectUrlSource
from video_toolkit.sources.local import LocalSource
from video_toolkit.sources.youtube import YouTubeSource

# 注册顺序即尝试顺序: 本地文件 → yt-dlp 站点 → 通用直链
_SOURCES: list[VideoSource] = [
    LocalSource(),
    YouTubeSource(),
    DirectUrlSource(),
]


def register_source(source: VideoSource) -> None:
    """注册新的视频源（追加到尝试链末尾）."""
    _SOURCES.append(source)


def list_sources() -> list[str]:
    """列出已注册的视频源名称."""
    return [s.name for s in _SOURCES]


def resolve_video_source(source: str, output_dir: str | None = None) -> SourceVideo:
    """将本地路径或 URL 解析为本地视频文件.

    Parameters
    ----------
    source : str
        本地文件路径或 http(s) URL（YouTube Shorts / 普通视频 / 直链）.
    output_dir : str | None
        在线视频下载目录；本地路径忽略该参数。默认 ``./downloads``.

    Returns
    -------
    SourceVideo
        本地视频文件信息（含来源类型、标题等）.

    Raises
    ------
    VideoSourceError
        所有已注册来源均无法获取时抛出，附带各来源的失败原因.
    """
    errors: list[str] = []
    for src in _SOURCES:
        try:
            if not src.supports(source):
                continue
            target_dir = output_dir or os.path.join(os.getcwd(), "downloads")
            video = src.fetch(source, target_dir)
            ensure_valid_video_file(video.local_path)
            return video
        except Exception as e:  # noqa: BLE001 - 汇总所有来源的错误统一抛出
            errors.append(f"{src.name}: {e}")

    raise VideoSourceError(
        f"无法获取视频源: {source}\n  已尝试: "
        + ("; ".join(errors) if errors else "无匹配的视频源")
    )


__all__ = [
    "DirectUrlSource",
    "LocalSource",
    "SourceVideo",
    "VideoSource",
    "VideoSourceError",
    "YouTubeSource",
    "ensure_valid_video_file",
    "list_sources",
    "register_source",
    "resolve_video_source",
]
