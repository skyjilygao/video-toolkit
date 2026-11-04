"""数据模型层."""
from video_toolkit.models.video import VideoMetadata, AudioInfo, VideoFormat
from video_toolkit.models.analysis import (
    VideoAnalysisResult,
    SceneInfo,
    KeyframeInfo,
    SegmentInfo,
    DecompositionResult,
)
from video_toolkit.models.composition import (
    CompositionConfig,
    CompositionResult,
    TransitionType,
)

# Solve forward reference for VideoAnalysisResult.metadata
from video_toolkit.models.video import VideoMetadata as _VM
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
