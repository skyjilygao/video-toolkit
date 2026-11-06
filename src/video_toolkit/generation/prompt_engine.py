"""Prompt 引擎 — 将 SceneBrief 转换为 AI 视频生成提示词.

借鉴 OpenMontage 的 5 层 cinematography 框架:
  Layer 1: Camera (镜头/景深)
  Layer 2: Movement (机位/运动)
  Layer 3: Subject (主体描述)
  Layer 4: Lighting (光线/色温)
  Layer 5: Style (风格修饰)

参考: OpenMontage/lib/shot_prompt_builder.py
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from video_toolkit.models.analysis import (
    AnalysisBrief,
    SceneBrief,
    StyleProfile,
)


# ── 运动类型到镜头语言的映射 ──

_MOTION_TO_SHOT_SIZE: Dict[str, str] = {
    "static_image": "locked-off static camera, wide establishing shot",
    "animated_still": "slow pan across the scene, medium shot",
    "motion_clip": "dynamic tracking shot, medium-wide framing",
    "unknown": "smooth camera movement, medium shot",
}

_MOTION_TO_MOVEMENT: Dict[str, str] = {
    "static_image": "locked-off static camera",
    "animated_still": "gentle tilt and pan across details",
    "motion_clip": "smooth tracking following the action",
    "unknown": "subtle camera drift",
}


# ── 能量级别到光线/色调的映射 ──

_ENERGY_TO_LIGHTING: Dict[str, str] = {
    "low": "soft diffused lighting, muted tones, calm atmosphere",
    "medium": "balanced natural lighting, neutral color temperature",
    "high": "dramatic high-contrast lighting, vibrant saturated colors",
}

_ENERGY_TO_TEMPERATURE: Dict[str, str] = {
    "low": "cool blue-toned color palette",
    "medium": "neutral balanced colors",
    "high": "warm amber-toned color palette with energy",
}


# ── 视觉类型到主体描述的修饰 ──

_VISUAL_TYPE_MODIFIERS: Dict[str, str] = {
    "landscape": "expansive scenic vista, natural environment",
    "portrait": "human subject centered, shallow depth of field",
    "screen_recording": "digital interface, clean UI elements",
    "product": "product centered on neutral background, studio lighting",
    "text_heavy": "typography-focused composition, minimal background",
    "other": "cinematic composition",
}


class PromptEngine:
    """从 SceneBrief 生成 AI 视频生成提示词.

    采用 5 层 cinematography 框架，确保生成的视频具有
    专业级的视觉语言一致性。
    """

    def __init__(
        self,
        style_profile: Optional[StyleProfile] = None,
        style_prefix: str = "",
        style_suffix: str = "cinematic, high quality, professional",
    ):
        self.style_profile = style_profile
        self.style_prefix = style_prefix
        self.style_suffix = style_suffix

    def build_scene_prompt(
        self,
        scene: SceneBrief,
        layer_mode: str = "full",  # full / subject_only / minimal
    ) -> str:
        """为单个场景生成完整的 AI 提示词.

        Parameters
        ----------
        scene : SceneBrief
            场景分析结果
        layer_mode : str
            full — 完整 5 层
            subject_only — 仅主体描述 + 风格
            minimal — 仅描述 + 后缀

        Returns
        -------
        str
            自然语言提示词，可直接传给 Kling/FLUX
        """
        if layer_mode == "minimal":
            return self._build_minimal(scene)
        elif layer_mode == "subject_only":
            return self._build_subject_only(scene)

        return self._build_full_layers(scene)

    def _build_full_layers(self, scene: SceneBrief) -> str:
        """完整 5 层提示词."""
        layers: List[str] = []

        # Layer 1: Camera — 基于运动类型推导
        camera_desc = self._derive_camera(scene)
        if camera_desc:
            layers.append(camera_desc)

        # Layer 2: Movement — 基于运动类型
        movement_desc = self._derive_movement(scene)
        if movement_desc:
            layers.append(movement_desc)

        # Layer 3: Subject — 场景描述 + 视觉类型修饰
        subject_desc = self._derive_subject(scene)
        if subject_desc:
            layers.append(subject_desc)

        # Layer 4: Lighting — 基于能量级别
        lighting_desc = self._derive_lighting(scene)
        if lighting_desc:
            layers.append(lighting_desc)

        # Layer 5: Style — 风格修饰
        style_desc = self._derive_style()
        if style_desc:
            layers.append(style_desc)

        return ". ".join(filter(None, layers))

    def _build_subject_only(self, scene: SceneBrief) -> str:
        """仅主体 + 风格（适合简单场景）."""
        parts = []
        subject = self._derive_subject(scene)
        if subject:
            parts.append(subject)
        style = self._derive_style()
        if style:
            parts.append(style)
        return ". ".join(filter(None, parts))

    def _build_minimal(self, scene: SceneBrief) -> str:
        """最简模式：描述 + 后缀."""
        parts = []
        desc = scene.description or scene.narration_text or ""
        if desc:
            parts.append(desc)
        if self.style_suffix:
            parts.append(self.style_suffix)
        return ". ".join(filter(None, parts))

    # ── 各层推导方法 ──

    def _derive_camera(self, scene: SceneBrief) -> str:
        """Layer 1: 镜头/景深."""
        motion = scene.motion_type or "unknown"
        shot = _MOTION_TO_SHOT_SIZE.get(motion, "medium shot")
        # 静态场景用浅景深，运动场景用深景深
        if motion == "static_image":
            return f"{shot}, shallow depth of field with bokeh"
        return f"{shot}, medium depth of field"

    def _derive_movement(self, scene: SceneBrief) -> str:
        """Layer 2: 机位运动."""
        motion = scene.motion_type or "unknown"
        return _MOTION_TO_MOVEMENT.get(motion, "subtle camera drift")

    def _derive_subject(self, scene: SceneBrief) -> str:
        """Layer 3: 主体描述."""
        parts = []

        # 优先使用 description，否则用 narration_text
        desc = scene.description or scene.narration_text or ""
        if desc:
            parts.append(desc)

        # 视觉类型修饰
        visual_type = scene.visual_type or "other"
        modifier = _VISUAL_TYPE_MODIFIERS.get(visual_type, "")
        if modifier and desc:
            parts.append(modifier)

        return ", ".join(filter(None, parts))

    def _derive_lighting(self, scene: SceneBrief) -> str:
        """Layer 4: 光线/色温."""
        energy = scene.energy_level or "medium"
        lighting = _ENERGY_TO_LIGHTING.get(energy, "")
        temp = _ENERGY_TO_TEMPERATURE.get(energy, "")
        return ", ".join(filter(None, [lighting, temp]))

    def _derive_style(self) -> str:
        """Layer 5: 风格修饰."""
        parts = []

        # 从 style_profile 提取风格信息
        if self.style_profile:
            mood = self.style_profile.color_palette.get("overall_mood", "")
            if mood:
                parts.append(f"{mood} mood")

        # 用户自定义前缀
        if self.style_prefix:
            parts.append(self.style_prefix)

        # 通用后缀
        if self.style_suffix:
            parts.append(self.style_suffix)

        return ", ".join(filter(None, parts))

    # ── 批量生成 ──

    def build_all_prompts(
        self,
        scenes: List[SceneBrief],
        layer_mode: str = "full",
    ) -> List[Dict[str, Any]]:
        """为所有场景批量生成提示词.

        Returns
        -------
        List[Dict]
            [{scene_index, prompt, narration_text, duration}, ...]
        """
        results = []
        for scene in scenes:
            prompt = self.build_scene_prompt(scene, layer_mode=layer_mode)
            narration = scene.narration_text or scene.description or ""
            results.append({
                "scene_index": scene.scene_index,
                "prompt": prompt,
                "narration_text": narration,
                "duration": scene.duration or 5.0,
            })
        return results

    # ── 旁白生成 ──

    def build_narration_script(
        self,
        scenes: List[SceneBrief],
        brief: AnalysisBrief,
    ) -> str:
        """生成完整的旁白脚本.

        优先使用字幕转录，否则使用场景描述拼接.
        """
        # 如果有转录，直接用
        if brief.transcript and brief.transcript.has_transcript:
            return brief.transcript.full_text

        # 否则用场景描述拼接
        parts = []
        for scene in scenes:
            text = scene.narration_text or scene.description or ""
            if text:
                parts.append(text.strip())

        return " ".join(parts)
