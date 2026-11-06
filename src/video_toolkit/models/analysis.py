"""分析结果模型."""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Literal
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

    # ── 镜头语言字段（用于 AI 生成 prompt）──
    camera_angle: str = "medium"                # 镜头景别: close_up / medium / wide 等
    camera_movement: str = "static"             # 运镜方式: static / pan_left / dolly_in 等
    lighting: str = "natural"                   # 光照类型: natural / low_key / golden_hour 等
    depth_of_field: str = "medium"              # 景深: shallow / medium / deep
    color_temperature: str = "neutral"          # 色温: cool / neutral / warm / mixed
    texture_keywords: List[str] = Field(default_factory=list)  # 纹理/材质关键词
    hero_moment: bool = False                   # 是否为高光时刻


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


# ─── 视频复制模型（方案 A: CustomDuplicator）───

class DuplicationConfig(BaseModel):
    """视频复制配置 — 基于分析结果重组视频."""

    output_path: str = "duplicated.mp4"
    output_width: int = 1920
    output_height: int = 1080
    output_fps: float = 30.0

    # 场景选择
    scene_selection: str = "all"
    scene_indices: List[int] = Field(default_factory=list)
    scene_count: int = 0

    # 转场
    transition: str = "fade"
    transition_duration: float = 0.5

    # 排序
    reorder_mode: str = "original"

    # 音频
    audio_mode: str = "original"
    music_path: str = ""
    music_volume: float = 0.3

    # 字幕
    burn_subtitles: bool = False
    subtitle_style: str = "default"
    subtitle_font_size: int = 24
    subtitle_color: str = "white"

    # 速度
    speed_factor: float = 1.0

    # 质量
    quality: str = "high"

    # 中间文件保留
    keep_segments: bool = False


class DuplicationResult(BaseModel):
    """视频复制结果."""

    source_video: str = ""
    config: DuplicationConfig = Field(default_factory=DuplicationConfig)
    segments_used: List[int] = Field(default_factory=list)
    segment_paths: List[str] = Field(default_factory=list)
    output_path: str = ""
    duration: float = 0.0
    original_duration: float = 0.0
    compression_ratio: float = 0.0
    success: bool = False
    message: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ─── 视频 AI 再生模型（全新生成）───

class SceneGenerationTask(BaseModel):
    """单个场景的 AI 生成任务."""

    scene_index: int = 0
    prompt: str = ""                        # 给 AI 的视频生成提示词
    narration_text: str = ""                # 场景旁白文本
    duration: float = 5.0                   # 期望生成的视频时长(秒)
    output_path: str = ""                   # 生成后的文件路径
    status: str = "pending"                 # pending / generating / done / failed
    generation_type: str = "video"          # video / image_animation
    retries: int = 0                        # 已重试次数


class RegenerationConfig(BaseModel):
    """视频 AI 再生配置 — 基于分析结果驱动 AI 生成全新视频."""

    output_path: str = "regenerated.mp4"
    output_width: int = 1920
    output_height: int = 1080
    output_fps: float = 24.0

    # 场景选择
    scene_selection: str = "all"            # all / indices / first_n / custom
    scene_indices: List[int] = Field(default_factory=list)
    scene_count: int = 0

    # 生成策略
    generation_mode: str = "video_first"    # video_first / image_animation
    # video_first: 优先 Kling 生成视频片段，失败降级到 FLUX 图片
    # image_animation: 用 FLUX 生成图片后做 Ken Burns 动态效果
    preferred_provider: str = "auto"        # 优先使用的视频生成 provider，auto 表示自动选择
    preferred_model_id: str = ""            # 优先使用的模型ID，为空则使用默认模型

    # 每个场景的最大生成时长（Kling 限制 5-10s）
    max_clip_duration: float = 5.0

    # 转场
    transition: str = "fade"
    transition_duration: float = 0.5

    # 音频
    audio_mode: str = "tts_narration"      # tts_narration / original / mute / background_music
    music_path: str = ""
    music_volume: float = 0.2
    tts_voice: str = "alloy"                # TTS 语音
    tts_provider: str = "auto"              # auto / openai / elevenlabs

    # 字幕
    burn_subtitles: bool = True
    subtitle_style: str = "default"
    subtitle_font_size: int = 28
    subtitle_color: str = "white"

    # 风格
    style_prefix: str = ""                  # 自动从 style_profile 推导
    style_suffix: str = "cinematic, high quality, professional"

    # 质量控制
    quality: str = "high"

    # 重试
    max_retries: int = 2

    # 中间文件保留
    keep_segments: bool = False
    keep_prompts: bool = True               # 保存生成的 prompt 到 txt 文件

    # 扩展参数（传递给底层 Provider 的额外参数，如 aspect_ratio、resolution 等）
    extra_params: Dict[str, Any] = Field(default_factory=dict)


class RegenerationResult(BaseModel):
    """视频 AI 再生结果."""

    source_video: str = ""
    config: RegenerationConfig = Field(default_factory=RegenerationConfig)
    tasks: List[SceneGenerationTask] = Field(default_factory=list)
    generated_segments: List[str] = Field(default_factory=list)   # 成功生成的视频片段
    failed_scenes: List[int] = Field(default_factory=list)       # 生成失败的场景索引
    tts_audio_path: str = ""                # TTS 旁白音频路径
    output_path: str = ""
    duration: float = 0.0
    original_duration: float = 0.0
    success: bool = False
    message: str = ""
    total_cost_estimate: float = 0.0        # 估算成本(USD)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
