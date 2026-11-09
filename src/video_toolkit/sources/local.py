"""本地文件视频源."""

from __future__ import annotations

import os

from video_toolkit.sources.base import SourceVideo, VideoSource, VideoSourceError


class LocalSource(VideoSource):
    """本地文件视频源 — 直接复用已有文件."""

    name = "local"

    def supports(self, source: str) -> bool:
        """本地路径（含 file:// 前缀）且文件存在时支持."""
        if source.startswith(("http://", "https://")):
            return False
        path = source[7:] if source.startswith("file://") else source
        return os.path.isfile(path)

    def fetch(self, source: str, output_dir: str) -> SourceVideo:
        """返回本地文件的 SourceVideo（不使用 output_dir）."""
        path = source[7:] if source.startswith("file://") else source
        if not os.path.isfile(path):
            raise VideoSourceError(f"本地文件不存在: {path}")
        return SourceVideo(
            local_path=os.path.abspath(path),
            source_type=self.name,
            original_source=source,
            title=os.path.splitext(os.path.basename(path))[0],
        )
