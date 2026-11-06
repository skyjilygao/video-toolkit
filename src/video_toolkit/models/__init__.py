"""数据模型层."""

from video_toolkit.models.analysis import (
    DecompositionResult,
    KeyframeInfo,
    SceneInfo,
    SegmentInfo,
    VideoAnalysisResult,
)
from video_toolkit.models.composition import (
    CompositionConfig,
    CompositionResult,
    TransitionType,
)
from video_toolkit.models.video import AudioInfo, VideoFormat, VideoMetadata

VideoAnalysisResult.model_rebuild()

__all__ = [
    "VideoMetadata",
    "AudioInfo",
    "VideoFormat",
    "VideoAnalysisResult",
    "SceneInfo",
    "KeyframeInfo",
    "SegmentInfo",
    "DecompositionResult",
    "CompositionConfig",
    "CompositionResult",
    "TransitionType",
]
