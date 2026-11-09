"""合成配置与结果模型."""

from enum import StrEnum

from pydantic import BaseModel, Field


class TransitionType(StrEnum):
    """转场类型."""

    FADE = "fade"
    WIPE_LEFT = "wipeleft"
    WIPE_RIGHT = "wiperight"
    WIPE_UP = "wipeup"
    WIPE_DOWN = "wipedown"
    SLIDE_LEFT = "slideleft"
    SLIDE_RIGHT = "slideright"
    SLIDE_UP = "slideup"
    SLIDE_DOWN = "slidedown"
    DISSOLVE = "dissolve"
    ZOOM_IN = "zoomin"
    ZOOM_OUT = "zoomout"
    CROSSFADE = "crossfade"


class CompositionConfig(BaseModel):
    """合成配置."""

    output_path: str = "output.mp4"
    output_width: int = 1920
    output_height: int = 1080
    output_fps: float = 30.0
    transition: TransitionType = TransitionType.FADE
    transition_duration: float = 0.5
    add_music: bool = False
    music_path: str = ""
    music_volume: float = 0.3
    segment_order: str = "original"
    burn_subtitles: bool = False
    subtitle_font_size: int = 24
    subtitle_color: str = "white"
    audio_mode: str = "original"  # "original" | "mute" | "tts_narration"


class CompositionResult(BaseModel):
    """合成结果."""

    config: CompositionConfig = Field(default_factory=CompositionConfig)
    segments_used: list[str] = Field(default_factory=list)
    output_path: str = ""
    duration: float = 0.0
    success: bool = False
    message: str = ""
