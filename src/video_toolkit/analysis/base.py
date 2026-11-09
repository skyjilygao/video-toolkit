"""分析适配器抽象基类."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path

from video_toolkit.models.analysis import (
    AnalysisBrief,
    AudioEnergyProfile,
    KeyframeBrief,
    PacingProfile,
    SceneBrief,
    TranscriptResult,
)


def _derive_video_subdir(video_path: str) -> str:
    """从视频路径推导安全的子目录名."""
    import os
    import re

    stem = os.path.splitext(os.path.basename(video_path))[0]
    safe = re.sub(r"[^\w\u4e00-\u9fff\-.]", "_", stem)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "untitled"


class BaseAnalysisAdapter(ABC):
    """视频分析适配器抽象基类.

    子类必须实现以下方法来提供分析数据:

    - ``transcribe`` — 字幕/语音转文字
    - ``detect_scenes`` — 场景检测
    - ``classify_motion`` — 运动分类 (可选，默认 unknown)
    - ``extract_keyframes`` — 关键帧提取
    - ``analyze_audio_energy`` — 音频能量分析 (可选)
    - ``compute_pacing`` — 节奏分析 (可选)

    适配器只负责"分析过程"（步骤 ②~⑥），
    元数据（步骤 ①）和复制指导（步骤 ⑦）由调用方自行处理。
    """

    name: str = "base"

    def __init__(self, video_path: str, output_dir: str | None = None):
        self.video_path = str(Path(video_path).resolve())
        self.output_dir = output_dir
        self._start_time = 0.0

    # ── 高层入口 ──

    def analyze(
        self,
        depth: str = "standard",
        max_keyframes: int = 20,
        extract_transcript: bool = True,
        extract_audio_energy: bool = True,
        extract_keyframes: bool = True,
        save_report: bool = False,
    ) -> AnalysisBrief:
        """执行完整分析流程并返回 AnalysisBrief.

        Parameters
        ----------
        depth : str
            分析深度: ``standard`` 或 ``deep``.
        max_keyframes : int
            最大关键帧数量.
        extract_transcript : bool
            是否提取字幕/转录.
        extract_audio_energy : bool
            是否分析音频能量.
        extract_keyframes : bool
            是否提取关键帧.
        save_report : bool
            是否自动导出分析报告. 默认 ``False``.
            若启用，将在 ``self.output_dir`` 下生成报告目录
            (包含 analysis.json, summary.md, scenes.json,
            transcript.txt 等文件).
        """
        self._start_time = time.time()

        brief = AnalysisBrief(
            version="1.0",
            video_path=self.video_path,
            adapter=self.name,
        )

        # ② 字幕/转录
        if extract_transcript:
            brief.transcript = self.transcribe()

        # ③ 场景检测
        brief.scenes = self.detect_scenes(depth=depth)
        brief.total_scenes = len(brief.scenes)

        # ④ 运动分类（如果子类未重写，使用启发式方法）
        motion_results = self.classify_motion(brief.scenes)
        if motion_results:
            for scene, motion in zip(brief.scenes, motion_results, strict=False):
                scene.motion_type = motion.get("motion_type", "unknown")
                scene.flow_variance = motion.get("flow_variance", -1.0)

        # ⑤ 关键帧提取
        if extract_keyframes:
            brief.keyframes = self.extract_keyframes(
                scenes=brief.scenes,
                max_frames=max_keyframes,
                depth=depth,
            )

        # ⑥ 音频能量分析
        if extract_audio_energy:
            brief.audio_energy = self.analyze_audio_energy()

        # 节奏分析（基于场景数据自动计算）
        if brief.scenes:
            brief.pacing = self.compute_pacing(brief.scenes)

        # 计算时长
        if brief.scenes:
            last_scene = brief.scenes[-1]
            brief.duration_seconds = last_scene.end_time

        brief.duration_analyzed = round(time.time() - self._start_time, 2)

        # 导出报告 — 自动按视频文件名创建子目录
        if save_report and self.output_dir:
            from video_toolkit.analysis.exporter import AnalysisExporter

            subdir = _derive_video_subdir(self.video_path)
            exporter = AnalysisExporter(brief, self.output_dir, subdir=subdir)
            exporter.save_all()

        return brief

    # ── 子类必须实现的抽象方法 ──

    @abstractmethod
    def transcribe(self) -> TranscriptResult:
        """提取字幕/语音转文字."""

    @abstractmethod
    def detect_scenes(self, depth: str = "standard") -> list[SceneBrief]:
        """检测场景边界."""

    @abstractmethod
    def extract_keyframes(
        self,
        scenes: list[SceneBrief],
        max_frames: int = 20,
        depth: str = "standard",
    ) -> list[KeyframeBrief]:
        """提取关键帧."""

    # ── 有默认实现的可选方法 ──

    def classify_motion(self, scenes: list[SceneBrief]) -> list[dict]:
        """运动分类 — 默认使用启发式规则."""
        return [{"motion_type": "unknown", "flow_variance": -1.0} for _ in scenes]

    def analyze_audio_energy(self) -> AudioEnergyProfile | None:
        """音频能量分析 — 默认不实现."""
        return None

    def compute_pacing(self, scenes: list[SceneBrief]) -> PacingProfile:
        """基于场景时长自动计算节奏特征."""
        if not scenes:
            return PacingProfile()

        durations = [s.duration for s in scenes]
        avg = sum(durations) / len(durations)
        total_duration = sum(durations)

        if avg > 10:
            style = "slow_contemplative"
        elif avg > 5:
            style = "steady_educational"
        elif avg > 2:
            style = "dynamic_social"
        else:
            style = "rapid_fire"

        return PacingProfile(
            avg_scene_duration_seconds=round(avg, 2),
            shortest_scene_seconds=round(min(durations), 2),
            longest_scene_seconds=round(max(durations), 2),
            cuts_per_minute=(
                round(len(durations) / (total_duration / 60), 2) if total_duration > 0 else 0
            ),
            pacing_style=style,  # type: ignore
        )
