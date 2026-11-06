"""视频生成适配器抽象基类.

类似于分析适配器的模式，视频生成适配器定义了统一的接口：
每个适配器接收分析结果（RegenerationConfig + Brief），
执行 AI 视频片段生成 + 拼接，返回 RegenerationResult.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from video_toolkit.models.analysis import (
    AnalysisBrief,
    RegenerationConfig,
    RegenerationResult,
)


class BaseGenerationAdapter(ABC):
    """视频 AI 生成适配器基类.

    子类必须实现:

    - ``regenerate`` — 核心生成方法
    - ``validate_environment`` — 验证环境是否满足生成条件
    - ``estimate_cost`` — 估算生成成本

    可选重写:

    - ``build_prompts`` — 从 SceneBrief 列表生成 prompt 和 narration
    """

    name: str = "base"

    def __init__(
        self,
        video_path: str,
        brief: AnalysisBrief,
    ):
        self.video_path = video_path
        self.brief = brief
        self._start_time = 0.0

    # ── 核心 API ──

    @abstractmethod
    def regenerate(self, config: RegenerationConfig) -> RegenerationResult:
        """执行完整的视频再生流水线.

        包括: 选择场景 → 生成片段 → TTS → 拼接 → 输出.
        """

    @abstractmethod
    def validate_environment(self) -> tuple[bool, str]:
        """验证当前环境是否满足生成条件.

        Returns
        -------
        tuple[bool, str]
            (是否可用, 不可用时原因说明)
        """

    def estimate_cost(self, config: RegenerationConfig, scene_count: int) -> float:
        """估算生成成本（USD）.

        默认实现：每个视频片段约 $0.05（Kling via fal.ai）.
        子类可重写以反映实际成本.
        """
        # Kling v3 ~$0.05 per 5s clip, FLUX ~$0.04 per image
        if config.generation_mode == "image_animation":
            return scene_count * 0.04
        return scene_count * 0.05

    # ── 工具方法（子类可复用）──

    def _filter_scenes(self, config: RegenerationConfig) -> list[int]:
        """根据 config.scene_selection 筛选场景索引."""
        scenes = self.brief.scenes or []
        if not scenes:
            return []

        mode = config.scene_selection
        total = len(scenes)

        if mode == "all":
            return list(range(total))
        elif mode == "first_n" and config.scene_count > 0:
            return list(range(min(config.scene_count, total)))
        elif mode == "indices":
            return [i for i in config.scene_indices if 0 <= i < total]
        elif mode == "custom" and config.scene_indices:
            return [i for i in config.scene_indices if 0 <= i < total]

        return list(range(total))

    @property
    def original_duration(self) -> float:
        """原视频时长."""
        return self.brief.duration_seconds or 0.0
