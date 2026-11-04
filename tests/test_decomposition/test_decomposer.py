"""测试视频拆解器."""
import os
import pytest
import tempfile
from pathlib import Path

from video_toolkit.decomposition.decomposer import VideoDecomposer
from video_toolkit.core.analyzer import VideoAnalyzer

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_VIDEO_DIR") and not os.path.exists(
        r"\\192.168.88.121\.n8n-files\video_download\video\2026-11-02\20261102"
    ),
    reason="未设置 TEST_VIDEO_DIR 环境变量或默认目录不存在",
)


class TestVideoDecomposer:
    """测试视频拆解器."""

    def test_init_creates_output_dir(self, skip_if_no_video):
        with tempfile.TemporaryDirectory() as tmpdir:
            decomposer = VideoDecomposer(skip_if_no_video, output_dir=tmpdir)
            assert os.path.exists(tmpdir)
            assert os.path.exists(os.path.join(tmpdir, "segments"))

    def test_decompose_by_interval(self, skip_if_no_video):
        with tempfile.TemporaryDirectory() as tmpdir:
            decomposer = VideoDecomposer(skip_if_no_video, output_dir=tmpdir)
            result = decomposer.decompose_by_interval(interval_seconds=2.0)
            assert result.total_segments >= 1
            assert len(result.segments) == result.total_segments

    def test_decompose_by_scenes(self, skip_if_no_video):
        with tempfile.TemporaryDirectory() as tmpdir:
            decomposer = VideoDecomposer(skip_if_no_video, output_dir=tmpdir)
            with VideoAnalyzer(skip_if_no_video) as analyzer:
                analysis = analyzer.full_analysis()
            result = decomposer.decompose_by_scenes(analysis)
            assert result.total_segments >= 1

    def test_index_file_created(self, skip_if_no_video):
        with tempfile.TemporaryDirectory() as tmpdir:
            decomposer = VideoDecomposer(skip_if_no_video, output_dir=tmpdir)
            decomposer.decompose_by_interval(interval_seconds=3.0)
            index_path = os.path.join(tmpdir, "decomposition_index.json")
            assert os.path.exists(index_path)

    def test_custom_decompose(self, skip_if_no_video):
        with tempfile.TemporaryDirectory() as tmpdir:
            decomposer = VideoDecomposer(skip_if_no_video, output_dir=tmpdir)
            with VideoAnalyzer(skip_if_no_video) as analyzer:
                meta = analyzer.extract_metadata()
            duration = meta.duration
            if duration >= 4:
                ranges = [(0, min(2, duration)), (min(2, duration), min(4, duration))]
            else:
                ranges = [(0, duration)]
            result = decomposer.decompose_custom(ranges)
            assert result.total_segments == len(ranges)
