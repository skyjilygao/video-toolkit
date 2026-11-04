"""分析结果模型."""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

from video_toolkit.models.video import VideoMetadata


# ─── 原有模型（保持向后兼容）───

class SceneInfo(BaseModel):
    """场景信息."""

    scene_id: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    start_frame: int = 0
    end_frame: int = 0
    dominant_colors: List[str] = Field(default_factory=list)
    brightness: float = 0.0
    motion_level: float = 0.0
    is_static: bool = False


class KeyframeInfo(BaseModel):
    """关键帧信息."""

    frame_id: int = 0
    timestamp: float = 0.0
    file_path: str = ""
    width: int = 0
    height: int = 0
    brightness: float = 0.0
    contrast: float = 0.0
    dominant_colors: List[str] = Field(default_factory=list)


class VideoAnalysisResult(BaseModel):
    """视频分析结果（基础版，向后兼容）."""

    metadata: "VideoMetadata" = Field(default=None)
    scenes: List[SceneInfo] = Field(default_factory=list)
    keyframes: List[KeyframeInfo] = Field(default_factory=list)
    avg_brightness: float = 0.0
    avg_motion: float = 0.0
    color_palette: List[str] = Field(default_factory=list)
    style_tags: List[str] = Field(default_factory=list)
    analyzed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SegmentInfo(BaseModel):
    """视频片段信息（拆解后的片段）."""

    segment_id: int = 0
    source_video: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    output_path: str = ""
    scene_info: Optional[SceneInfo] = None
    tags: List[str] = Field(default_factory=list)
    description: str = ""


class DecompositionResult(BaseModel):
    """拆解结果."""

    source_video: str = ""
    output_dir: str = ""
    segments: List[SegmentInfo] = Field(default_factory=list)
    total_segments: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ─── 适配器扩展模型（用于 AnalysisBrief）───

class TranscriptSegment(BaseModel):
    """字幕片段."""

    start: float = 0.0
    end: float = 0.0
    text: str = ""


class TranscriptResult(BaseModel):
    """字幕/转录结果."""

    full_text: str = ""
    segments: List[TranscriptSegment] = Field(default_factory=list)
    language: str = "unknown"
    word_count: int = 0
    has_transcript: bool = False


class MotionClassification(BaseModel):
    """场景运动类型分类."""

    scene_id: int = 0
    motion_type: Literal["static_image", "animated_still", "motion_clip", "unknown"] = "unknown"
    flow_variance: float = -1.0


class AudioEnergyPoint(BaseModel):
    """音频能量采样点."""

    timestamp: float = 0.0
    energy: float = 0.0


class AudioEnergyProfile(BaseModel):
    """音频能量分析结果."""

    recommended_offset_seconds: float = 0.0
    has_energy_data: bool = False
    energy_points: List[AudioEnergyPoint] = Field(default_factory=list)
    avg_energy: float = 0.0
    peak_energy: float = 0.0
    peak_timestamp: float = 0.0


class PacingProfile(BaseModel):
    """视频节奏特征."""

    avg_scene_duration_seconds: float = 0.0
    shortest_scene_seconds: float = 0.0
    longest_scene_seconds: float = 0.0
    cuts_per_minute: float = 0.0
    pacing_style: Literal[
        "slow_contemplative", "steady_educational", "dynamic_social", "rapid_fire", "variable"
    ] = "variable"


class KeyframeBrief(BaseModel):
    """场景引导的关键帧（OpenMontage 风格）."""

    timestamp: float = 0.0
    scene_index: int = 0
    path: str = ""
    description: str = ""
    brightness: float = 0.0
    contrast: float = 0.0
    dominant_colors: List[str] = Field(default_factory=list)


class SceneBrief(BaseModel):
    """增强的场景信息."""

    scene_index: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    motion_type: Literal["static_image", "animated_still", "motion_clip", "unknown"] = "unknown"
    flow_variance: float = -1.0
    energy_level: Literal["low", "medium", "high"] = "medium"
    description: str = ""
    narration_text: str = ""
    visual_type: str = "other"


class StyleProfile(BaseModel):
    """风格特征画像."""

    audio_energy_profile: Optional[AudioEnergyProfile] = None
    narration_style: Optional[dict] = None
    color_palette: dict = Field(default_factory=lambda: {
        "primary_colors": [], "accent_colors": [], "overall_mood": "",
    })
    typography_observed: str = ""
    transition_types: List[str] = Field(default_factory=list)
    music_style: str = ""
    subtitle_style: str = ""
    production_quality: str = "prosumer"
    closest_playbook: str = ""
    playbook_delta: str = ""


class AnalysisBrief(BaseModel):
    """统一的视频分析简报 — 适配器的核心输出.

    对标 OpenMontage 的 VideoAnalysisBrief schema，
    但做了简化以适配更通用的场景。
    """

    version: str = "1.0"
    video_path: str = ""
    duration_seconds: float = 0.0
    total_scenes: int = 0

    # ② 字幕/转录
    transcript: TranscriptResult = Field(default_factory=TranscriptResult)

    # ③ 场景检测 + ④ 运动分类
    scenes: List[SceneBrief] = Field(default_factory=list)

    # ⑤ 关键帧
    keyframes: List[KeyframeBrief] = Field(default_factory=list)

    # ⑥ 音频能量
    audio_energy: Optional[AudioEnergyProfile] = None

    # 节奏特征
    pacing: Optional[PacingProfile] = None

    # 综合风格画像
    style_profile: StyleProfile = Field(default_factory=StyleProfile)

    # 元数据
    metadata: Optional["VideoMetadata"] = None

    # 适配信息
    adapter: str = "unknown"
    analyzed_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    duration_analyzed: float = 0.0
