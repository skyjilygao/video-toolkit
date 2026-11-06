"""测试视频分析器."""

import os

import pytest

from video_toolkit.core.analyzer import VideoAnalyzer, _analyze_frame, _extract_dominant_colors

# 跳过标记：需要实际视频文件
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_VIDEO_DIR")
    and not os.path.exists(r"\\192.168.88.121\.n8n-files\video_download\video\2026-11-02\20261102"),
    reason="未设置 TEST_VIDEO_DIR 环境变量或默认目录不存在",
)


class TestUtilityFunctions:
    """测试工具函数."""

    def test_extract_dominent_colors(self):
        import numpy as np

        frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        colors = _extract_dominant_colors(frame, k=3)
        assert len(colors) == 3
        assert all(c.startswith("#") for c in colors)

    def test_analyze_frame(self):
        import numpy as np

        frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        result = _analyze_frame(frame)
        assert "brightness" in result
        assert "contrast" in result
        assert "dominant_colors" in result
        assert 0 <= result["brightness"] <= 255


class TestVideoAnalyzer:
    """测试视频分析器."""

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            VideoAnalyzer("/nonexistent/video.mp4")

    def test_extract_metadata(self, skip_if_no_video):
        analyzer = VideoAnalyzer(skip_if_no_video)
        meta = analyzer.extract_metadata()
        assert meta.file_path == os.path.abspath(skip_if_no_video)
        assert meta.width > 0
        assert meta.height > 0
        assert meta.duration > 0
        analyzer.cap.release()

    def test_detect_scenes(self, skip_if_no_video):
        analyzer = VideoAnalyzer(skip_if_no_video)
        scenes = analyzer.detect_scenes()
        assert isinstance(scenes, list)
        if scenes:
            assert scenes[0].scene_id == 0
            assert scenes[0].start_time >= 0
        analyzer.cap.release()

    def test_full_analysis(self, skip_if_no_video):
        analyzer = VideoAnalyzer(skip_if_no_video)
        result = analyzer.full_analysis(keyframe_count=3)
        assert result.metadata.file_name != ""
        assert isinstance(result.scenes, list)
        assert isinstance(result.style_tags, list)
        assert result.analyzed_at != ""
        analyzer.cap.release()

    def test_context_manager(self, skip_if_no_video):
        with VideoAnalyzer(skip_if_no_video) as analyzer:
            meta = analyzer.extract_metadata()
            assert meta.duration > 0
