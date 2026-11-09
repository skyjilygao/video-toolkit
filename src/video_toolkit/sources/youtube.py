"""在线视频源 — 基于 yt-dlp（YouTube 及 1000+ 支持站点）."""

from __future__ import annotations

import os
import time
from typing import Any

from video_toolkit.sources.base import (
    SourceVideo,
    VideoSource,
    VideoSourceError,
    ensure_valid_video_file,
)

# 下载重试（弱网下 DASH 分片易损坏，直到 ffmpeg 合并阶段才暴露；重试可显著提升成功率）
_MAX_DOWNLOAD_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 3.0


class YouTubeSource(VideoSource):
    """yt-dlp 视频源 — 支持 YouTube Shorts/视频及其他 yt-dlp 兼容站点.

    下载完成后会校验合并文件（FFprobe 能解析出时长/画面），
    弱网损坏或合并失败时自动重试。
    """

    name = "youtube"

    def supports(self, source: str) -> bool:
        """http(s) URL 交由 yt-dlp 尝试解析."""
        return source.startswith(("http://", "https://"))

    def fetch(
        self, source: str, output_dir: str, max_retries: int = _MAX_DOWNLOAD_RETRIES
    ) -> SourceVideo:
        """使用 yt-dlp 下载在线视频到本地（下载后校验，失败自动重试）.

        Parameters
        ----------
        source : str
            在线视频 URL（YouTube / yt-dlp 支持站点）.
        output_dir : str
            下载输出目录.
        max_retries : int
            最大尝试次数（弱网分片损坏时自动重试）.

        yt-dlp 为可选依赖，未安装时抛出友好的 VideoSourceError。
        """
        try:
            import yt_dlp
        except ImportError as e:
            raise VideoSourceError(
                "未安装 yt-dlp，无法下载在线视频。请执行: pip install yt-dlp"
            ) from e

        os.makedirs(output_dir, exist_ok=True)
        opts = {
            "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
            "format": "bv*+ba/b",  # 最佳分离流合并，保证音视频齐全
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            # yt-dlp 的真实选项名是 force_overwrites；错误的 "overwrites" 会被静默忽略，
            # 导致重跑时复用上次中断的残留（可能损坏）文件而非重新下载
            "force_overwrites": True,
            "socket_timeout": 60,  # 弱网下减少分片读取超时，降低分片重试导致的损坏
        }

        attempts = max(1, max_retries)
        info: dict = {}
        local_path = ""
        hints = (
            "  常见原因: ① 网络无法访问该站点（需代理/防火墙放行） "
            "② 站点要求登录验证（可配置 cookies） "
            "③ 弱网分片损坏/并发触发限流，可稍后重试"
        )
        for attempt in range(1, attempts + 1):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(source, download=True)
                    if not info:
                        raise VideoSourceError(f"yt-dlp 未返回视频信息: {source}")
                    local_path = self._resolve_downloaded_path(ydl, info)
                ensure_valid_video_file(local_path)  # 校验合并结果，拦截损坏文件
                break
            except Exception as e:  # noqa: BLE001 - 统一按「可重试失败」处理
                if attempt >= attempts:
                    raise VideoSourceError(
                        f"yt-dlp 下载失败（已重试 {attempts} 次）: {e}\n{hints}"
                    ) from e
                time.sleep(_RETRY_BACKOFF_SECONDS)

        return SourceVideo(
            local_path=local_path,
            source_type=self.name,
            original_source=source,
            title=info.get("title") or "",
            duration=info.get("duration"),
            meta={
                "id": info.get("id", ""),
                "uploader": info.get("uploader") or info.get("channel") or "",
                "webpage_url": source,
                "site": info.get("extractor_key") or info.get("ie_key") or "",
            },
        )

    @staticmethod
    def _resolve_downloaded_path(ydl: Any, info: dict) -> str:
        """解析下载后的最终文件路径（合并后扩展名可能变化）."""
        requested = info.get("requested_downloads") or []
        filepath = str(requested[0].get("filepath") if requested else "") or ""
        if filepath and os.path.isfile(filepath):
            return os.path.abspath(filepath)

        filename = str(ydl.prepare_filename(info))
        if os.path.isfile(filename):
            return os.path.abspath(filename)

        # 格式合并后扩展名可能从 .webm/.mkv 变为 .mp4
        base, _ = os.path.splitext(filename)
        for ext in (".mp4", ".mkv", ".webm"):
            candidate = base + ext
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)

        raise VideoSourceError(f"无法定位下载文件: {filename}")
