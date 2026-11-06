"""Video Toolkit - 视频拆解与生成工具.

基于 OpenMontage 理念构建的独立视频处理工具。
支持视频分析、场景拆解、重组生成、AI 辅助创作。

Modules:
    models: 数据模型层
    analysis: 可插拔的分析适配器层
    core: 核心视频分析功能
    decomposition: 视频拆解功能
    composition: 视频合成功能
    ai: AI 生成服务接口
    cli: 命令行工具入口
"""

__version__ = "0.1.0"
__author__ = "Video Toolkit"

from video_toolkit.analysis import AnalysisManager, BaseAnalysisAdapter
from video_toolkit.composition.composer import VideoComposer
from video_toolkit.core.analyzer import VideoAnalyzer
from video_toolkit.decomposition.decomposer import VideoDecomposer
from video_toolkit.models.analysis import (
    AnalysisBrief,
    KeyframeInfo,
    SceneInfo,
    VideoAnalysisResult,
)
from video_toolkit.models.composition import CompositionConfig, CompositionResult, TransitionType
from video_toolkit.models.video import AudioInfo, VideoMetadata

__all__ = [
    "__version__",
    # Models
    "VideoMetadata",
    "AudioInfo",
    "VideoAnalysisResult",
    "SceneInfo",
    "KeyframeInfo",
    "AnalysisBrief",
    "CompositionConfig",
    "CompositionResult",
    "TransitionType",
    # Core classes
    "VideoAnalyzer",
    "VideoDecomposer",
    "VideoComposer",
    # Analysis adapters
    "AnalysisManager",
    "BaseAnalysisAdapter",
]
