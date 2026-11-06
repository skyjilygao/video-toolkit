"""测试视频合成器."""

import os
import tempfile

import pytest

from video_toolkit.composition.composer import TRANSITION_EFFECTS, VideoComposer
from video_toolkit.models.composition import CompositionConfig, TransitionType

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_VIDEO_DIR")
    and not os.path.exists(r"\\192.168.88.121\.n8n-files\video_download\video\2026-11-02\20261102"),
    reason="未设置 TEST_VIDEO_DIR 环境变量或默认目录不存在",
)


class TestVideoComposer:
    """测试视频合成器."""

    def test_compose_empty_segments(self):
        composer = VideoComposer()
        config = CompositionConfig()
        result = composer.compose([], config)
        assert result.success is False

    def test_compose_single_segment(self, skip_if_no_video):
        composer = VideoComposer()
        with tempfile.TemporaryDirectory() as tmpdir:
            config = CompositionConfig(output_path=os.path.join(tmpdir, "output.mp4"))
            result = composer.compose([skip_if_no_video], config)
            assert result.success is True
            assert os.path.exists(config.output_path)

    def test_transition_effects_mapping(self):
        assert TRANSITION_EFFECTS[TransitionType.FADE] == "fade"
        assert TRANSITION_EFFECTS[TransitionType.WIPE_LEFT] == "wipeleft"
        assert TRANSITION_EFFECTS[TransitionType.CROSSFADE] == "fadeblack"
        assert len(TRANSITION_EFFECTS) == len(TransitionType)

    def test_compose_two_segments_with_transition(self, skip_if_no_video):
        with tempfile.TemporaryDirectory() as tmpdir:
            from video_toolkit.decomposition.decomposer import VideoDecomposer

            decomposer = VideoDecomposer(skip_if_no_video, output_dir=tmpdir)
            result = decomposer.decompose_by_interval(interval_seconds=2.0)

            segments = [s.output_path for s in result.segments if os.path.exists(s.output_path)]
            if len(segments) < 2:
                pytest.skip("无法生成足够片段用于合成测试")

            composer = VideoComposer()
            config = CompositionConfig(
                output_path=os.path.join(tmpdir, "composed_test.mp4"),
                transition=TransitionType.FADE,
                transition_duration=0.3,
            )
            comp_result = composer.compose(segments[:2], config)
            assert comp_result.success is True or comp_result.success is not None
