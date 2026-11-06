"""测试视频模型."""

from video_toolkit.models.analysis import (
    DecompositionResult,
    SceneInfo,
    SegmentInfo,
    VideoAnalysisResult,
)
from video_toolkit.models.composition import CompositionConfig, CompositionResult, TransitionType
from video_toolkit.models.video import AudioInfo, VideoFormat, VideoMetadata


class TestVideoMetadata:
    """测试视频元数据模型."""

    def test_create_minimal(self):
        meta = VideoMetadata()
        assert meta.width == 0
        assert meta.height == 0
        assert meta.audio.has_audio is False

    def test_create_full(self):
        meta = VideoMetadata(
            file_path="/test/video.mp4",
            file_name="video.mp4",
            width=1920,
            height=1080,
            fps=30.0,
            duration=10.0,
            total_frames=300,
        )
        assert meta.resolution == "1920x1080"
        assert meta.file_name == "video.mp4"

    def test_aspect_ratio(self):
        meta = VideoMetadata(width=1920, height=1080)
        assert meta.aspect_ratio == "16:9"

        meta2 = VideoMetadata(width=1080, height=1920)
        assert meta2.aspect_ratio == "9:16"

        meta3 = VideoMetadata(width=1280, height=720)
        assert meta3.aspect_ratio == "16:9"

    def test_with_audio(self):
        meta = VideoMetadata(
            audio=AudioInfo(
                has_audio=True,
                sample_rate=44100,
                channels=2,
                codec="aac",
                avg_volume=-20.0,
            )
        )
        assert meta.audio.has_audio is True
        assert meta.audio.channels == 2

    def test_format_enum(self):
        assert VideoFormat.MP4 == "mp4"
        assert VideoFormat.AVI == "avi"


class TestSceneInfo:
    """测试场景模型."""

    def test_create(self):
        scene = SceneInfo(
            scene_id=0,
            start_time=0.0,
            end_time=5.0,
            duration=5.0,
            is_static=False,
        )
        assert scene.scene_id == 0
        assert scene.duration == 5.0


class TestCompositionModels:
    """测试合成模型."""

    def test_transition_type(self):
        assert TransitionType.FADE == "fade"
        assert TransitionType.WIPE_LEFT == "wipeleft"

    def test_composition_config(self):
        config = CompositionConfig(
            output_path="output.mp4",
            transition=TransitionType.FADE,
            transition_duration=0.5,
        )
        assert config.output_width == 1920
        assert config.transition == TransitionType.FADE

    def test_composition_result(self):
        result = CompositionResult(success=True, output_path="test.mp4")
        assert result.success is True


class TestDecompositionResult:
    """测试拆解结果模型."""

    def test_create(self):
        result = DecompositionResult(
            source_video="test.mp4",
            output_dir="/tmp/output",
        )
        assert result.total_segments == 0

    def test_with_segments(self):
        segments = [
            SegmentInfo(segment_id=0, start_time=0, end_time=5, duration=5),
            SegmentInfo(segment_id=1, start_time=5, end_time=10, duration=5),
        ]
        result = DecompositionResult(
            source_video="test.mp4",
            output_dir="/tmp/decomposed",
            segments=segments,
            total_segments=2,
        )
        assert result.total_segments == 2
        assert len(result.segments) == 2


class TestVideoAnalysisResult:
    """测试视频分析结果模型."""

    def test_create(self):

        result = VideoAnalysisResult()
        assert result.scenes == []
        assert result.keyframes == []
        assert result.style_tags == []
