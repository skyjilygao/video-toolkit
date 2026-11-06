"""视频 AI 再生模块 — 基于分析结果驱动 AI 生成全新视频内容.

此模块实现了适配器模式，支持多种视频生成后端:

- ``custom``: 基于 fal.ai (Kling/FLUX) 的自定义实现
- ``openmontage``: 通过 OpenMontage 工具链生成（需 OpenMontage 安装）

使用方式::

    from video_toolkit.generation import GenerationManager

    manager = GenerationManager()
    adapter = manager.get_adapter("custom", video_path=..., brief=...)
    result = adapter.regenerate(config)
"""

from video_toolkit.generation.base import BaseGenerationAdapter
from video_toolkit.generation.custom_adapter import CustomGenerationAdapter
from video_toolkit.generation.manager import GenerationManager
from video_toolkit.generation.openmontage_adapter import OpenGenerationAdapter
from video_toolkit.generation.prompt_engine import PromptEngine

__all__ = [
    "BaseGenerationAdapter",
    "CustomGenerationAdapter",
    "OpenGenerationAdapter",
    "GenerationManager",
    "PromptEngine",
]
