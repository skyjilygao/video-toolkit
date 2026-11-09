"""直链视频源 — 通用 HTTP(S) 文件下载（yt-dlp 失败时的降级）."""

from __future__ import annotations

import os
import shutil
import urllib.request

from video_toolkit.sources.base import SourceVideo, VideoSource, VideoSourceError


class DirectUrlSource(VideoSource):
    """通用 HTTP(S) 直链视频源 — yt-dlp 不支持或失败时的降级方案.

    仅用于下载真正的直链媒体文件；若目标 URL 返回 HTML 页面（例如 YouTube
    的 Shorts 页面），会明确报错而不是把页面存成 ``*.mp4``。
    """

    name = "direct"

    def supports(self, source: str) -> bool:
        """http(s) URL 均支持尝试直接下载."""
        return source.startswith(("http://", "https://"))

    def fetch(self, source: str, output_dir: str, timeout: float = 300.0) -> SourceVideo:
        """通过 HTTP(S) 直接下载视频文件.

        下载前检查 ``Content-Type``：``text/html`` 等页面类型直接报错，避免把
        网页 HTML 当作视频保存（短视频平台页面没有可直接下载的媒体流）。
        """
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.basename(source.split("?")[0].rstrip("/")) or "direct_video"
        if "." not in filename:
            filename += ".mp4"
        dest = os.path.join(output_dir, filename)

        try:
            with urllib.request.urlopen(source, timeout=timeout) as resp:
                self._ensure_video_content_type(source, resp.headers.get("Content-Type", ""))
                with open(dest, "wb") as f:
                    shutil.copyfileobj(resp, f)
        except VideoSourceError:
            if os.path.isfile(dest):
                os.remove(dest)
            raise
        except Exception as e:
            if os.path.isfile(dest):
                os.remove(dest)
            raise VideoSourceError(f"直链下载失败: {e}") from e

        if os.path.getsize(dest) < 1024:
            os.remove(dest)
            raise VideoSourceError(f"下载文件过小，可能不是有效视频: {dest}")

        return SourceVideo(
            local_path=os.path.abspath(dest),
            source_type=self.name,
            original_source=source,
            title=os.path.splitext(filename)[0],
        )

    @staticmethod
    def _ensure_video_content_type(source: str, content_type: str) -> None:
        """校验响应 Content-Type 为可下载的媒体类型（拒绝 HTML 页面）."""
        ctype = content_type.split(";")[0].strip().lower()
        if not ctype:
            return
        allowed_prefixes = ("video/", "audio/")
        allowed_exact = {"application/octet-stream"}
        if ctype.startswith(allowed_prefixes) or ctype in allowed_exact:
            return
        raise VideoSourceError(
            f"直链 Content-Type 为 「{ctype}」，不是可下载的视频文件（可能需要 yt-dlp 解析该页面）: {source}"
        )
