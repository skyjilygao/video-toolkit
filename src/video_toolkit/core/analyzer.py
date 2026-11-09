"""视频分析器 - 元数据提取、场景分割、关键帧提取、音频分析."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from rich.console import Console

from video_toolkit.models.analysis import KeyframeInfo, SceneInfo, VideoAnalysisResult
from video_toolkit.models.video import AudioInfo, VideoMetadata

console = Console()


def _run_ffprobe(video_path: str) -> dict:
    """运行 ffprobe 获取视频信息."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return cast(dict[Any, Any], json.loads(result.stdout))
    except subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError:
        return {}


def _extract_dominant_colors(image: np.ndarray, k: int = 5) -> list[str]:
    """提取主色调."""
    try:
        pixels = image.reshape(-1, 3).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        # OpenCV API 允许 bestLabels=None（输出型参数），但上游 stub 未提供 None 重载
        _, labels, centers = cv2.kmeans(  # type: ignore[call-overload]
            pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS
        )
        counts = np.bincount(labels.flatten())
        dominant = centers[np.argsort(-counts)]
        return [f"#{int(c[2]):02x}{int(c[1]):02x}{int(c[0]):02x}" for c in dominant]
    except Exception:
        return []


def _analyze_frame(frame: np.ndarray) -> dict:
    """分析单帧图像特征."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    return {
        "brightness": brightness,
        "contrast": contrast,
        "dominant_colors": _extract_dominant_colors(frame),
    }


class VideoAnalyzer:
    """视频分析器."""

    def __init__(self, video_path: str):
        self.video_path = os.path.abspath(video_path)
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"视频文件不存在: {self.video_path}")

        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开视频: {self.video_path}")

        self._total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._fps = self.cap.get(cv2.CAP_PROP_FPS)
        self._width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._duration = self._total_frames / self._fps if self._fps > 0 else 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cap.release()

    def extract_metadata(self) -> VideoMetadata:
        """提取视频元数据."""
        ffprobe_data = _run_ffprobe(self.video_path)
        file_stat = os.stat(self.video_path)

        video_stream = None
        audio_stream = None
        for stream in ffprobe_data.get("streams", []):
            if stream.get("codec_type") == "video" and not video_stream:
                video_stream = stream
            elif stream.get("codec_type") == "audio" and not audio_stream:
                audio_stream = stream

        metadata = VideoMetadata(
            file_path=self.video_path,
            file_name=os.path.basename(self.video_path),
            file_size=file_stat.st_size,
            format=Path(self.video_path).suffix.lstrip("."),
            duration=self._duration,
            width=self._width,
            height=self._height,
            fps=self._fps,
            total_frames=self._total_frames,
        )

        if video_stream:
            metadata.video_codec = video_stream.get("codec_name", "")
            metadata.video_bitrate = int(video_stream.get("bit_rate", 0))

        if audio_stream:
            metadata.audio = AudioInfo(
                has_audio=True,
                sample_rate=int(audio_stream.get("sample_rate", 0)),
                channels=int(audio_stream.get("channels", 0)),
                duration=float(audio_stream.get("duration", 0)),
                codec=audio_stream.get("codec_name", ""),
                bitrate=int(audio_stream.get("bit_rate", 0)),
            )

        if metadata.audio.has_audio:
            self._analyze_audio_volume(metadata)

        return metadata

    def _analyze_audio_volume(self, metadata: VideoMetadata):
        """分析音频音量."""
        try:
            import ffmpeg

            _, err = (
                ffmpeg.input(self.video_path)
                .filter("volumedetect")
                .output("null", f="null")
                .run(capture_stdout=True, capture_stderr=True)
            )
            output = err.decode("utf-8")
            for line in output.split("\n"):
                if "mean_volume:" in line:
                    metadata.audio.avg_volume = float(
                        line.split("mean_volume:")[1].split("dB")[0].strip()
                    )
                if "max_volume:" in line:
                    metadata.audio.peak_volume = float(
                        line.split("max_volume:")[1].split("dB")[0].strip()
                    )
        except Exception:
            pass

    def detect_scenes(
        self, threshold: float = 30.0, min_scene_duration: float = 1.0
    ) -> list[SceneInfo]:
        """检测场景分割."""
        scenes = []
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        prev_hist = None
        frame_idx = 0
        scene_id = 0
        scene_start_frame = 0
        brightness_accum = 0.0
        motion_scores = []

        console.print(f"[dim]正在分析场景 (共 {self._total_frames} 帧)...[/dim]")

        while True:
            ret, frame = self.cap.read()
            if not ret:
                break

            hist = cv2.calcHist([frame], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            hist = cv2.normalize(hist, hist).flatten()

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness_accum += float(np.mean(gray))

            if prev_hist is not None:
                diff = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                motion_scores.append(1.0 - diff)

                if diff < (1.0 - threshold / 100.0):
                    scene_end_frame = frame_idx - 1
                    scene_duration = (scene_end_frame - scene_start_frame) / self._fps

                    if scene_duration >= min_scene_duration:
                        scene = SceneInfo(
                            scene_id=scene_id,
                            start_time=scene_start_frame / self._fps,
                            end_time=scene_end_frame / self._fps,
                            duration=scene_duration,
                            start_frame=scene_start_frame,
                            end_frame=scene_end_frame,
                            brightness=brightness_accum / (scene_end_frame - scene_start_frame + 1),
                            motion_level=float(np.mean(motion_scores)) if motion_scores else 0.0,
                            is_static=(
                                float(np.mean(motion_scores)) < 0.02 if motion_scores else True
                            ),
                        )
                        scenes.append(scene)

                        scene_id += 1
                        scene_start_frame = frame_idx
                        brightness_accum = 0.0
                        motion_scores = []

            prev_hist = hist
            frame_idx += 1

        if scene_start_frame < self._total_frames:
            scene_duration = (self._total_frames - 1 - scene_start_frame) / self._fps
            if scene_duration >= min_scene_duration:
                scene = SceneInfo(
                    scene_id=scene_id,
                    start_time=scene_start_frame / self._fps,
                    end_time=(self._total_frames - 1) / self._fps,
                    duration=scene_duration,
                    start_frame=scene_start_frame,
                    end_frame=self._total_frames - 1,
                    brightness=brightness_accum / max(self._total_frames - scene_start_frame, 1),
                    motion_level=float(np.mean(motion_scores)) if motion_scores else 0.0,
                    is_static=float(np.mean(motion_scores)) < 0.02 if motion_scores else True,
                )
                scenes.append(scene)

        return scenes

    def extract_keyframes(
        self, count: int = 10, output_dir: str | None = None
    ) -> list[KeyframeInfo]:
        """提取关键帧."""
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="vt_keyframes_")

        os.makedirs(output_dir, exist_ok=True)
        keyframes = []

        if self._total_frames <= count:
            frame_indices = list(range(self._total_frames))
        else:
            frame_indices = [int(i * self._total_frames / count) for i in range(count)]

        for i, idx in enumerate(frame_indices):
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = self.cap.read()
            if not ret:
                continue

            timestamp = idx / self._fps
            analysis = _analyze_frame(frame)

            file_path = os.path.join(output_dir, f"keyframe_{i:04d}.jpg")
            cv2.imwrite(file_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

            kf = KeyframeInfo(
                frame_id=idx,
                timestamp=timestamp,
                file_path=file_path,
                width=self._width,
                height=self._height,
                brightness=analysis["brightness"],
                contrast=analysis["contrast"],
                dominant_colors=analysis["dominant_colors"],
            )
            keyframes.append(kf)

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return keyframes

    def detect_style(self, scenes: list[SceneInfo]) -> list[str]:
        """检测视频风格标签."""
        tags: list[str] = []

        if not scenes:
            return tags

        avg_scene_duration = np.mean([s.duration for s in scenes])
        if avg_scene_duration < 2.0:
            tags.append("快节奏")
        elif avg_scene_duration < 5.0:
            tags.append("中等节奏")
        else:
            tags.append("慢节奏")

        if len(scenes) > 20:
            tags.append("场景丰富")
        elif len(scenes) > 10:
            tags.append("场景适中")
        else:
            tags.append("场景简洁")

        avg_motion = np.mean([s.motion_level for s in scenes])
        if avg_motion > 0.3:
            tags.append("高动态")
        elif avg_motion > 0.1:
            tags.append("中动态")
        else:
            tags.append("低动态")

        avg_brightness = np.mean([s.brightness for s in scenes])
        if avg_brightness > 180:
            tags.append("明亮")
        elif avg_brightness > 100:
            tags.append("适中亮度")
        else:
            tags.append("暗沉")

        static_ratio = sum(1 for s in scenes if s.is_static) / len(scenes)
        if static_ratio > 0.5:
            tags.append("静态为主")

        return tags

    def full_analysis(
        self,
        scene_threshold: float = 30.0,
        min_scene_duration: float = 1.0,
        keyframe_count: int = 10,
        keyframe_dir: str | None = None,
    ) -> VideoAnalysisResult:
        """完整分析视频."""
        console.print("[bold blue]开始视频分析...[/bold blue]")

        console.print("[dim]1/4 提取元数据...[/dim]")
        metadata = self.extract_metadata()
        console.print(
            f"  分辨率: {metadata.resolution}, 帧率: {metadata.fps:.1f}, "
            f"时长: {metadata.duration:.1f}s"
        )

        console.print("[dim]2/4 场景检测...[/dim]")
        scenes = self.detect_scenes(
            threshold=scene_threshold, min_scene_duration=min_scene_duration
        )
        console.print(f"  检测到 [bold]{len(scenes)}[/bold] 个场景")

        console.print("[dim]3/4 关键帧提取...[/dim]")
        keyframes = self.extract_keyframes(count=keyframe_count, output_dir=keyframe_dir)
        console.print(f"  提取了 [bold]{len(keyframes)}[/bold] 个关键帧")

        console.print("[dim]4/4 风格检测...[/dim]")
        style_tags = self.detect_style(scenes)
        console.print(f"  风格: [bold]{', '.join(style_tags)}[/bold]")

        all_colors = []
        for kf in keyframes:
            all_colors.extend(kf.dominant_colors[:3])

        return VideoAnalysisResult(
            metadata=metadata,
            scenes=scenes,
            keyframes=keyframes,
            avg_brightness=float(np.mean([s.brightness for s in scenes])) if scenes else 0.0,
            avg_motion=float(np.mean([s.motion_level for s in scenes])) if scenes else 0.0,
            color_palette=all_colors[:10],
            style_tags=style_tags,
        )
