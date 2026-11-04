"""视频拆解器 - 场景切割、片段标记."""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from video_toolkit.models.analysis import (
    SceneInfo,
    SegmentInfo,
    DecompositionResult,
    VideoAnalysisResult,
)
from video_toolkit.core.analyzer import VideoAnalyzer

console = Console()


class VideoDecomposer:
    """视频拆解器."""

    def __init__(self, video_path: str, output_dir: Optional[str] = None):
        self.video_path = os.path.abspath(video_path)
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"视频文件不存在: {self.video_path}")

        if output_dir is None:
            base_name = Path(video_path).stem
            self.output_dir = os.path.join(
                os.path.dirname(video_path), f"{base_name}_decomposed"
            )
        else:
            self.output_dir = output_dir

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "segments"), exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "keyframes"), exist_ok=True)

    def decompose_by_scenes(
        self,
        analysis_result: Optional[VideoAnalysisResult] = None,
        re_encode: bool = False,
    ) -> DecompositionResult:
        """按场景拆解视频."""
        if analysis_result is None:
            with VideoAnalyzer(self.video_path) as analyzer:
                analysis_result = analyzer.full_analysis()

        segments = []
        scenes = analysis_result.scenes

        if not scenes:
            console.print("[yellow]未检测到场景，将整个视频作为单个片段[/yellow]")
            segment = SegmentInfo(
                segment_id=0,
                source_video=self.video_path,
                start_time=0,
                end_time=analysis_result.metadata.duration,
                duration=analysis_result.metadata.duration,
                output_path=os.path.join(
                    self.output_dir, "segments", "segment_0000.mp4"
                ),
                tags=["full_video"],
                description="完整视频",
            )
            self._cut_segment(segment, re_encode)
            segments.append(segment)
        else:
            for i, scene in enumerate(scenes):
                segment = SegmentInfo(
                    segment_id=i,
                    source_video=self.video_path,
                    start_time=scene.start_time,
                    end_time=scene.end_time,
                    duration=scene.duration,
                    output_path=os.path.join(
                        self.output_dir, "segments", f"segment_{i:04d}.mp4"
                    ),
                    scene_info=scene,
                    tags=self._generate_segment_tags(scene),
                    description=self._generate_segment_description(scene),
                )
                self._cut_segment(segment, re_encode)
                segments.append(segment)

        result = DecompositionResult(
            source_video=self.video_path,
            output_dir=self.output_dir,
            segments=segments,
            total_segments=len(segments),
        )

        self._save_index(result, analysis_result)
        return result

    def decompose_by_interval(
        self, interval_seconds: float = 5.0, re_encode: bool = False
    ) -> DecompositionResult:
        """按固定时间间隔拆解视频."""
        import cv2

        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        cap.release()

        segments = []
        seg_id = 0
        start = 0.0

        while start < duration:
            end = min(start + interval_seconds, duration)
            segment = SegmentInfo(
                segment_id=seg_id,
                source_video=self.video_path,
                start_time=start,
                end_time=end,
                duration=end - start,
                output_path=os.path.join(
                    self.output_dir, "segments", f"segment_{seg_id:04d}.mp4"
                ),
                tags=[f"interval_{interval_seconds}s"],
                description=f"时间段: {start:.1f}s - {end:.1f}s",
            )
            self._cut_segment(segment, re_encode)
            segments.append(segment)
            seg_id += 1
            start = end

        result = DecompositionResult(
            source_video=self.video_path,
            output_dir=self.output_dir,
            segments=segments,
            total_segments=len(segments),
        )

        self._save_index(result)
        return result

    def decompose_custom(
        self,
        time_ranges: List[tuple],
        tags_list: Optional[List[List[str]]] = None,
        re_encode: bool = False,
    ) -> DecompositionResult:
        """按自定义时间范围拆解."""
        segments = []

        for i, (start, end) in enumerate(time_ranges):
            tags = tags_list[i] if tags_list and i < len(tags_list) else []
            segment = SegmentInfo(
                segment_id=i,
                source_video=self.video_path,
                start_time=start,
                end_time=end,
                duration=end - start,
                output_path=os.path.join(
                    self.output_dir, "segments", f"segment_{i:04d}.mp4"
                ),
                tags=tags,
                description=f"自定义片段: {start:.1f}s - {end:.1f}s",
            )
            self._cut_segment(segment, re_encode)
            segments.append(segment)

        result = DecompositionResult(
            source_video=self.video_path,
            output_dir=self.output_dir,
            segments=segments,
            total_segments=len(segments),
        )

        self._save_index(result)
        return result

    def _cut_segment(self, segment: SegmentInfo, re_encode: bool = False):
        """切割单个片段."""
        os.makedirs(os.path.dirname(segment.output_path), exist_ok=True)

        if re_encode:
            cmd = [
                "ffmpeg", "-y", "-ss", str(segment.start_time),
                "-i", self.video_path,
                "-t", str(segment.duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k",
                segment.output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-ss", str(segment.start_time),
                "-i", self.video_path,
                "-t", str(segment.duration),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                segment.output_path,
            ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        except subprocess.CalledProcessError as e:
            console.print(
                f"[red]切割片段 {segment.segment_id} 失败: "
                f"{e.stderr.decode()[:200] if e.stderr else str(e)}[/red]"
            )
        except subprocess.TimeoutExpired:
            console.print(f"[yellow]切割片段 {segment.segment_id} 超时[/yellow]")

    def _generate_segment_tags(self, scene: SceneInfo) -> List[str]:
        """为片段生成标签."""
        tags = []

        if scene.is_static:
            tags.append("静态")
        else:
            tags.append("动态")

        if scene.duration < 2:
            tags.append("短片段")
        elif scene.duration < 5:
            tags.append("中等片段")
        else:
            tags.append("长片段")

        if scene.brightness > 180:
            tags.append("明亮")
        elif scene.brightness < 60:
            tags.append("暗沉")

        if scene.motion_level > 0.3:
            tags.append("高运动")

        return tags

    def _generate_segment_description(self, scene: SceneInfo) -> str:
        """生成片段描述."""
        parts = []
        parts.append(f"时间段: {scene.start_time:.1f}s - {scene.end_time:.1f}s")
        parts.append(f"时长: {scene.duration:.1f}s")

        if scene.is_static:
            parts.append("静态场景")
        else:
            parts.append(f"动态场景 (运动强度: {scene.motion_level:.2f})")

        parts.append(f"亮度: {scene.brightness:.0f}")
        return ", ".join(parts)

    def _save_index(
        self,
        result: DecompositionResult,
        analysis_result: Optional[VideoAnalysisResult] = None,
    ):
        """保存拆解索引文件."""
        index = {
            "source_video": result.source_video,
            "output_dir": result.output_dir,
            "total_segments": result.total_segments,
            "created_at": result.created_at,
            "segments": [],
        }

        for seg in result.segments:
            seg_data = {
                "segment_id": seg.segment_id,
                "source_video": seg.source_video,
                "start_time": seg.start_time,
                "end_time": seg.end_time,
                "duration": seg.duration,
                "output_path": seg.output_path,
                "tags": seg.tags,
                "description": seg.description,
            }

            if seg.scene_info:
                seg_data["scene"] = {
                    "motion_level": seg.scene_info.motion_level,
                    "brightness": seg.scene_info.brightness,
                    "is_static": seg.scene_info.is_static,
                }

            index["segments"].append(seg_data)

        if analysis_result:
            index["analysis_summary"] = {
                "resolution": analysis_result.metadata.resolution,
                "fps": analysis_result.metadata.fps,
                "duration": analysis_result.metadata.duration,
                "total_scenes": len(analysis_result.scenes),
                "style_tags": analysis_result.style_tags,
            }

        index_path = os.path.join(self.output_dir, "decomposition_index.json")
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

        console.print(f"[dim]拆解索引已保存: {index_path}[/dim]")
