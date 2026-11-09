"""视频生成适配器抽象基类.

类似于分析适配器的模式，视频生成适配器定义了统一的接口：
每个适配器接收分析结果（RegenerationConfig + Brief），
执行 AI 视频片段生成 + 拼接，返回 RegenerationResult.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from video_toolkit.ai.base import GenerationRequest
from video_toolkit.generation.prompt_engine import PromptEngine
from video_toolkit.models.analysis import (
    AnalysisBrief,
    RegenerationConfig,
    RegenerationResult,
    SceneGenerationTask,
)


@dataclass
class GenerationCandidate:
    """单个大模型调用候选.

    Attributes
    ----------
    provider : 目标 Provider 名称（seedance / fal / openai ...）
    request : 将发送给大模型的完整请求参数
    model_id : 命中的模型 ID（可空，如通用 Provider）
    note : 候选来源标记（preferred / fallback / image_fallback）
    """

    provider: str
    request: GenerationRequest
    model_id: str = ""
    note: str = ""
    available: bool = True  # True=已注册（真实生成可调用）；False=仅 dry-run 展示


@dataclass
class GenerationCallSpec:
    """单个场景的大模型调用计划.

    按优先级排列的候选链：真实生成时依次尝试，dry-run 时完整输出。
    """

    scene_index: int
    candidates: list[GenerationCandidate] = field(default_factory=list)


class BaseGenerationAdapter(ABC):
    """视频 AI 生成适配器基类.

    子类必须实现:

    - ``regenerate`` — 核心生成方法
    - ``validate_environment`` — 验证环境是否满足生成条件
    - ``estimate_cost`` — 估算生成成本

    可选重写:

    - ``build_prompts`` — 从 SceneBrief 列表生成 prompt 和 narration
    """

    def build_generation_plan(self, config: RegenerationConfig) -> list[SceneGenerationTask]:
        """仅为选中场景构建生成任务（prompt + 时长），不调用大模型.

        dry-run 与真实生成共用此方法，保证 prompt 逻辑一致。
        """
        scene_indices = self._filter_scenes(config)
        if not scene_indices:
            return []

        prompt_engine = PromptEngine(
            style_profile=self.brief.style_profile,
            style_prefix=config.style_prefix,
            style_suffix=config.style_suffix,
        )

        tasks: list[SceneGenerationTask] = []
        for i in scene_indices:
            scene = self.brief.scenes[i]
            tasks.append(
                SceneGenerationTask(
                    scene_index=scene.scene_index,
                    prompt=prompt_engine.build_scene_prompt(scene, layer_mode="full"),
                    narration_text=scene.narration_text or scene.description or "",
                    duration=min(scene.duration, config.max_clip_duration),
                )
            )
        return tasks

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
