"""视频源模块单元测试 — 本地/直链/在线源解析与通用校验.

测试策略（不依赖网络）:
1. 使用 FFmpeg 合成最小测试视频作为有效输入；
2. 直接校验 Content-Type 护栏与 ffprobe 视频校验逻辑；
3. 通过 ``resolve_video_source`` 验证本地路径解析与错误汇总。

运行方式:
    cd video-toolkit
    python -m pytest tests/test_sources/ -v --tb=short
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from tests.fixtures.mock_video import generate_test_video
from video_toolkit.sources import (
    DirectUrlSource,
    LocalSource,
    VideoSourceError,
    YouTubeSource,
    ensure_valid_video_file,
    resolve_video_source,
)

# ── Fixtures ──


@pytest.fixture(scope="module")
def tiny_video_path():
    """合成最小测试视频（2s / 320x240）."""
    tmp_dir = tempfile.mkdtemp(prefix="vt_sources_video_")
    path = os.path.join(tmp_dir, "tiny.mp4")
    generate_test_video(
        path,
        duration=2.0,
        width=320,
        height=240,
        fps=12,
        with_audio=False,
    )
    yield path
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def fake_html_as_mp4(tmp_path_factory):
    """构造 HTML 内容但扩展名为 .mp4 的伪视频文件."""
    tmp_dir = tmp_path_factory.mktemp("vt_sources_fake_")
    path = os.path.join(tmp_dir, "page.mp4")
    with open(path, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html><body>not a video</body></html>")
    yield path


# ── Content-Type 护栏 ──


class TestDirectUrlContentGuard:
    """DirectUrlSource 必须拒绝把 HTML 等页面内容存成视频文件."""

    def test_reject_text_html(self):
        with pytest.raises(VideoSourceError):
            DirectUrlSource._ensure_video_content_type(
                "https://youtube.com/shorts/xxx", "text/html; charset=utf-8"
            )

    def test_reject_application_json(self):
        with pytest.raises(VideoSourceError):
            DirectUrlSource._ensure_video_content_type(
                "https://example.com/api", "application/json"
            )

    def test_allow_video_mp4(self):
        DirectUrlSource._ensure_video_content_type(
            "https://example.com/a.mp4", "video/mp4; codecs=avc1.42E01E"
        )

    def test_allow_audio_and_octet_stream(self):
        DirectUrlSource._ensure_video_content_type("https://example.com/a.webm", "audio/webm")
        DirectUrlSource._ensure_video_content_type(
            "https://example.com/a.bin", "application/octet-stream"
        )

    def test_allow_empty_content_type(self):
        # 无 Content-Type 时不拦截，由 resolve 阶段的 ffprobe 校验兜底
        DirectUrlSource._ensure_video_content_type("https://example.com/a", "")


# ── supports 判断 ──


class TestSourceSupports:
    """各来源的 supports 判定."""

    def test_local_supports_existing_path(self, tiny_video_path):
        assert LocalSource().supports(tiny_video_path) is True

    def test_local_rejects_url_and_missing(self):
        src = LocalSource()
        assert src.supports("https://example.com/a.mp4") is False
        assert src.supports("./definitely_not_exist_12345.mp4") is False

    def test_youtube_supports_http_url(self):
        assert YouTubeSource().supports("https://youtube.com/shorts/xxx") is True
        assert YouTubeSource().supports("./local.mp4") is False

    def test_direct_supports_http_url(self):
        assert DirectUrlSource().supports("https://cdn.example.com/a.mp4") is True
        assert DirectUrlSource().supports("./local.mp4") is False


# ── FFprobe 视频校验 ──


class TestEnsureValidVideoFile:
    """ensure_valid_video_file 拒绝伪视频文件."""

    def test_valid_video_passes(self, tiny_video_path):
        ensure_valid_video_file(tiny_video_path)  # 不抛异常即通过

    def test_html_as_mp4_rejected(self, fake_html_as_mp4):
        with pytest.raises(VideoSourceError, match="不是有效的视频"):
            ensure_valid_video_file(fake_html_as_mp4)

    def test_missing_file_rejected(self):
        with pytest.raises(VideoSourceError, match="不存在"):
            ensure_valid_video_file("./definitely_not_exist_12345.mp4")


# ── resolve_video_source ──


class TestResolveVideoSource:
    """统一解析入口的行为."""

    def test_resolve_local_video(self, tiny_video_path):
        video = resolve_video_source(tiny_video_path)
        assert video.source_type == "local"
        assert os.path.isfile(video.local_path)
        assert video.title == "tiny"

    def test_resolve_fake_video_raises(self, fake_html_as_mp4):
        # 本地路径存在但内容不是视频 → 校验拦截并汇总错误
        with pytest.raises(VideoSourceError):
            resolve_video_source(fake_html_as_mp4)

    def test_resolve_missing_path_raises(self):
        with pytest.raises(VideoSourceError):
            resolve_video_source("./definitely_not_exist_12345.mp4")


# ── YouTubeSource 下载参数 ──


class TestYouTubeSourceOpts:
    """YouTubeSource 的 yt-dlp 参数（覆盖/重试）验证.

    历史 bug: ``overwrites: True`` 并非 yt-dlp 的有效选项名（静默忽略），
    重跑时会复用上次的残留文件；真实选项名为 ``force_overwrites``。
    """

    def test_opts_use_force_overwrites(self, monkeypatch, tmp_path):
        captured: dict = {}

        class _FakeYDL:
            def __init__(self, opts):
                captured.update(opts)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def extract_info(self, url, download=True):
                return {
                    "id": "test123",
                    "title": "Test",
                    "duration": 10,
                    "uploader": "Tester",
                    "requested_downloads": [],
                }

            def prepare_filename(self, info):
                return str(tmp_path / "none.mp4")

        fake_module = types.SimpleNamespace(YoutubeDL=_FakeYDL)
        monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)

        # 下载后无法定位到有效文件 → 抛出 VideoSourceError（选项已被捕获）
        with pytest.raises(VideoSourceError):
            YouTubeSource().fetch("https://youtube.com/shorts/xxx", str(tmp_path), max_retries=1)

        assert captured.get("force_overwrites") is True
        assert "overwrites" not in captured
        assert captured.get("max_retries") is None  # 确认 opts 未被其他键污染
