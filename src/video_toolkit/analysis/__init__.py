"""分析适配器层 — 可插拔的视频分析后端.

使用方式::

    from video_toolkit.analysis import AnalysisManager

    adapter = AnalysisManager.get_adapter("openmontage")
    brief = adapter.analyze("path/to/video.mp4")

可用适配器:
- ``openmontage``: 使用 OpenMontage 工具链 (PySceneDetect + FFmpeg + faster-whisper)
- ``custom``: 使用 video-toolkit 自带的分析器 (OpenCV 颜色直方图 + 光流)
"""

from video_toolkit.analysis.base import BaseAnalysisAdapter
from video_toolkit.analysis.manager import AnalysisManager
from video_toolkit.analysis.exporter import AnalysisExporter

# 自动导入所有已安装的适配器以完成注册
from video_toolkit.analysis import custom_adapter  # noqa: F401
from video_toolkit.analysis import openmontage_adapter  # noqa: F401

__all__ = ["BaseAnalysisAdapter", "AnalysisManager", "AnalysisExporter"]
