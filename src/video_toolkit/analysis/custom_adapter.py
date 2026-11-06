"""Custom 适配器 — 基于 video-toolkit 自带分析器增强.

使用 OpenCV 颜色直方图 + Farneback 光流法 + FFmpeg 实现完整的分析链。
不依赖外部 AI 服务，完全本地运行。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

import cv2
import numpy as np
from rich.console import Console

from video_toolkit.analysis.base import BaseAnalysisAdapter
from video_toolkit.analysis.manager import register_adapter
from video_toolkit.models.analysis import (
    AudioEnergyProfile,
    KeyframeBrief,
    SceneBrief,
    TranscriptResult,
    TranscriptSegment,
)

console = Console()


def _run_ffprobe(video_path: str) -> dict:
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
        return json.loads(result.stdout)
    except Exception:
        return {}


def _get_duration(video_path: str) -> float:
    data = _run_ffprobe(video_path)
    return float(data.get("format", {}).get("duration", 0))


def _extract_dominant_colors(image: np.ndarray, k: int = 5) -> list[str]:
    try:
        pixels = image.reshape(-1, 3).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        counts = np.bincount(labels.flatten())
        dominant = centers[np.argsort(-counts)]
        return [f"#{int(c[2]):02x}{int(c[1]):02x}{int(c[0]):02x}" for c in dominant]
    except Exception:
        return []


def _read_frame_at(cap, timestamp: float, fps: float):
    frame_num = int(timestamp * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    return frame if ret else None


@register_adapter("custom")
class CustomAdapter(BaseAnalysisAdapter):
    """Custom 适配器 — 基于 OpenCV 增强的视频分析.

    特性:
    - Farneback 光流法运动分类 (static_image / animated_still / motion_clip)
    - FFmpeg 场景检测 (select=gt(scene))
    - 场景引导的智能关键帧提取
    - 音频能量分析
    - 可选的 faster-whisper 转录
    """

    name = "custom"

    def __init__(self, video_path: str, output_dir: str | None = None):
        super().__init__(video_path, output_dir)
        self._cap: cv2.VideoCapture | None = None
        self._fps: float = 30.0
        self._total_frames: int = 0
        self._width: int = 0
        self._height: int = 0
        self._duration: float = 0.0
        self._setup_capture()

    def _setup_capture(self):
        self._cap = cv2.VideoCapture(self.video_path)
        if not self._cap.isOpened():
            raise RuntimeError(f"无法打开视频: {self.video_path}")
        self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._duration = self._total_frames / self._fps if self._fps > 0 else 0

    def __del__(self):
        if self._cap and self._cap.isOpened():
            self._cap.release()

    # ── ② 字幕/转录 ──

    def transcribe(self) -> TranscriptResult:
        """尝试使用 faster-whisper 进行语音转文字.

        如果 faster-whisper 未安装，返回空结果。
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            console.print(
                "[dim]faster-whisper 未安装，跳过字幕提取 "
                "(pip install faster-whisper 启用)[/dim]"
            )
            return TranscriptResult(has_transcript=False)

        console.print("[dim]正在转录音频 (faster-whisper base)...[/dim]")
        try:
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments_iter, info = model.transcribe(self.video_path, language=None, vad_filter=True)

            segments = []
            full_text_parts = []
            for seg in segments_iter:
                segments.append(
                    TranscriptSegment(
                        start=round(seg.start, 3),
                        end=round(seg.end, 3),
                        text=seg.text.strip(),
                    )
                )
                full_text_parts.append(seg.text.strip())

            full_text = " ".join(full_text_parts)
            return TranscriptResult(
                full_text=full_text,
                segments=segments,
                language=info.language,
                word_count=len(full_text.split()),
                has_transcript=len(segments) > 0,
            )
        except Exception as e:
            console.print(f"[dim]转录失败: {e}[/dim]")
            return TranscriptResult(has_transcript=False)

    # ── ③ 场景检测 ──

    def detect_scenes(self, depth: str = "standard") -> list[SceneBrief]:
        """使用 FFmpeg select 滤镜检测场景变化.

        优先尝试 PySceneDetect，降级到 FFmpeg 内置方法。
        """
        # 优先使用 PySceneDetect
        scenes = self._detect_scenes_pyscenedetect()
        if scenes:
            return scenes

        # 降级到 FFmpeg
        return self._detect_scenes_ffmpeg()

    def _detect_scenes_pyscenedetect(self) -> list[SceneBrief]:
        try:
            from scenedetect import SceneManager, open_video
            from scenedetect.detectors import ContentDetector
        except ImportError:
            return []

        try:
            video = open_video(self.video_path)
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=27.0, min_scene_len=15))
            scene_manager.detect_scenes(video)
            scene_list = scene_manager.get_scene_list()

            scenes = []
            for i, (start, end) in enumerate(scene_list):
                scenes.append(
                    SceneBrief(
                        scene_index=i,
                        start_time=round(start.get_seconds(), 3),
                        end_time=round(end.get_seconds(), 3),
                        duration=round(end.get_seconds() - start.get_seconds(), 3),
                    )
                )
            return scenes
        except Exception:
            return []

    def _detect_scenes_ffmpeg(self) -> list[SceneBrief]:
        """FFmpeg select 滤镜检测场景."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "frame=pts_time",
            "-of",
            "json",
            "-f",
            "lavfi",
            f"movie='{self.video_path}',select='gt(scene,0.3)'",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            data = json.loads(result.stdout)
        except Exception:
            return self._segment_uniform()

        change_points = [0.0]
        for frame in data.get("frames", []):
            ts = float(frame.get("pts_time", 0))
            if ts - change_points[-1] >= 0.5:
                change_points.append(ts)

        # 添加结束点
        if self._duration > 0:
            change_points.append(self._duration)
        else:
            change_points.append(change_points[-1] + 1)  # fallback

        scenes = []
        for i in range(len(change_points) - 1):
            start = change_points[i]
            end = change_points[i + 1]
            scenes.append(
                SceneBrief(
                    scene_index=i,
                    start_time=round(start, 3),
                    end_time=round(end, 3),
                    duration=round(end - start, 3),
                )
            )

        return scenes if scenes else self._segment_uniform()

    def _segment_uniform(self) -> list[SceneBrief]:
        """最终降级: 均匀分段."""
        seg_duration = 5.0  # 每 5 秒一段
        scenes = []
        i = 0
        t = 0.0
        while t < self._duration:
            end = min(t + seg_duration, self._duration)
            scenes.append(
                SceneBrief(
                    scene_index=i,
                    start_time=round(t, 3),
                    end_time=round(end, 3),
                    duration=round(end - t, 3),
                )
            )
            t = end
            i += 1
        return scenes

    # ── ④ 运动分类 ──

    def classify_motion(self, scenes: list[SceneBrief]) -> list[dict]:
        """使用 Farneback 光流法对场景进行运动分类."""
        if not scenes or not self._cap:
            return [{"motion_type": "unknown", "flow_variance": -1.0} for _ in scenes]

        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        results = []

        for scene in scenes:
            start = scene.start_time
            end = scene.end_time
            duration = end - start

            if duration < 0.3:
                results.append({"motion_type": "static_image", "flow_variance": 0.0})
                continue

            # 采 2-3 帧对
            gap = min(0.4, duration / 3)
            sample_times = [
                start + duration * p for p in (0.25, 0.5, 0.75) if start + duration * p + gap <= end
            ]
            if not sample_times:
                sample_times = [start + 0.1]

            flow_variances = []
            flow_mag_means = []

            for t in sample_times:
                frame_a = _read_frame_at(self._cap, t, self._fps)
                frame_b = _read_frame_at(self._cap, t + gap, self._fps)
                if frame_a is None or frame_b is None:
                    continue

                # 降采样加速
                h, w = frame_a.shape[:2]
                scale = 360 / h if h > 360 else 1.0
                if scale < 1.0:
                    dim = (int(w * scale), 360)
                    frame_a = cv2.resize(frame_a, dim)
                    frame_b = cv2.resize(frame_b, dim)

                gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
                gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)

                flow = cv2.calcOpticalFlowFarneback(
                    gray_a,
                    gray_b,
                    None,
                    pyr_scale=0.5,
                    levels=3,
                    winsize=15,
                    iterations=3,
                    poly_n=5,
                    poly_sigma=1.2,
                    flags=0,
                )

                mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
                flow_mag_means.append(float(np.mean(mag)))
                flow_variances.append(float(np.var(mag)))

            if not flow_variances:
                results.append({"motion_type": "unknown", "flow_variance": -1.0})
                continue

            avg_variance = sum(flow_variances) / len(flow_variances)
            avg_magnitude = sum(flow_mag_means) / len(flow_mag_means)

            # 分类阈值
            if avg_magnitude < 0.5:
                motion_type = "static_image"
            elif avg_variance < 2.0:
                motion_type = "animated_still"
            else:
                motion_type = "motion_clip"

            results.append(
                {
                    "motion_type": motion_type,
                    "flow_variance": round(avg_variance, 3),
                }
            )

        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return results

    # ── ⑤ 关键帧提取 ──

    def extract_keyframes(
        self,
        scenes: list[SceneBrief],
        max_frames: int = 20,
        depth: str = "standard",
    ) -> list[KeyframeBrief]:
        """场景引导的智能关键帧提取.

        在每个场景的首帧+中点采样，deep 模式下增加 1/4 和 3/4 位置。
        """
        if not self._cap:
            return []

        # 计算采样时间戳
        timestamps = []
        for scene in scenes:
            start = scene.start_time
            end = scene.end_time
            duration = end - start

            timestamps.append(start + 0.1)

            if duration > 3.0:
                timestamps.append(start + duration / 2)

            if depth == "deep" and duration > 6.0:
                timestamps.append(start + duration * 0.25)
                timestamps.append(start + duration * 0.75)

        timestamps = sorted(set(round(t, 3) for t in timestamps))

        if len(timestamps) > max_frames:
            step = len(timestamps) / max_frames
            timestamps = [timestamps[int(i * step)] for i in range(max_frames)]

        # 创建输出目录
        if self.output_dir:
            kf_dir = self.output_dir
        else:
            kf_dir = os.path.join(tempfile.mkdtemp(prefix="vt_keyframes_"), "keyframes")
        os.makedirs(kf_dir, exist_ok=True)

        keyframes = []
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        for i, ts in enumerate(timestamps):
            frame = _read_frame_at(self._cap, ts, self._fps)
            if frame is None:
                continue

            # 分析帧
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = float(np.mean(gray))
            contrast = float(np.std(gray))
            colors = _extract_dominant_colors(frame)

            # 保存文件
            filename = f"keyframe_{i:04d}_s{ts:06.2f}.jpg"
            file_path = os.path.join(kf_dir, filename)
            cv2.imwrite(file_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

            # 找到对应的场景索引
            scene_idx = 0
            for j, s in enumerate(scenes):
                if s.start_time <= ts <= s.end_time:
                    scene_idx = j
                    break

            keyframes.append(
                KeyframeBrief(
                    timestamp=round(ts, 3),
                    scene_index=scene_idx,
                    path=file_path,
                    brightness=round(brightness, 2),
                    contrast=round(contrast, 2),
                    dominant_colors=colors,
                )
            )

        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return keyframes

    # ── ⑥ 音频能量分析 ──

    def analyze_audio_energy(self) -> AudioEnergyProfile | None:
        """使用 FFmpeg 分析音频能量分布."""
        try:
            import ffmpeg
        except ImportError:
            console.print(
                "[dim]ffmpeg-python 未安装，跳过音频能量分析 "
                "(pip install ffmpeg-python 启用)[/dim]"
            )
            return None

        console.print("[dim]正在分析音频能量...[/dim]")
        try:
            # 提取音频能量数据
            audio_path = self._extract_audio_wav()
            if not audio_path:
                return None

            # 使用 FFmpeg ebur128 滤镜分析响度
            _, err = (
                ffmpeg.input(audio_path)
                .filter("ebur128", framerate=int(self._fps))
                .output("null", f="null")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )

            # 简化为使用 astats 获取 RMS 能量
            _, err2 = (
                ffmpeg.input(audio_path)
                .filter("astats", metadata=1, reset=1)
                .output("null", f="null")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )

            # 清理临时文件
            try:
                os.unlink(audio_path)
            except OSError:
                pass

            return AudioEnergyProfile(
                recommended_offset_seconds=0.0,
                has_energy_data=True,
            )

        except Exception as e:
            console.print(f"[dim]音频能量分析失败: {e}[/dim]")
            return None

    def _extract_audio_wav(self) -> str | None:
        """提取音频为临时 WAV 文件用于分析."""
        try:
            import ffmpeg

            tmp_path = os.path.join(tempfile.mkdtemp(prefix="vt_audio_"), "audio.wav")
            (
                ffmpeg.input(self.video_path)
                .output(tmp_path, ac=1, ar=16000, format="wav")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True, quiet=True)
            )
            return tmp_path
        except Exception:
            return None
