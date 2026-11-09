"""视频合成器 - 片段拼接与转场效果."""

import os
import subprocess
import tempfile

from rich.console import Console

from video_toolkit.models.composition import (
    CompositionConfig,
    CompositionResult,
    TransitionType,
)

console = Console()

# 支持的转场效果映射
TRANSITION_EFFECTS = {
    TransitionType.FADE: "fade",
    TransitionType.WIPE_LEFT: "wipeleft",
    TransitionType.WIPE_RIGHT: "wiperight",
    TransitionType.WIPE_UP: "wipeup",
    TransitionType.WIPE_DOWN: "wipedown",
    TransitionType.SLIDE_LEFT: "slideleft",
    TransitionType.SLIDE_RIGHT: "slideright",
    TransitionType.SLIDE_UP: "slideup",
    TransitionType.SLIDE_DOWN: "slidedown",
    TransitionType.DISSOLVE: "dissolve",
    TransitionType.ZOOM_IN: "zoomin",
    TransitionType.ZOOM_OUT: "zoomout",
    TransitionType.CROSSFADE: "fadeblack",
}


class VideoComposer:
    """视频合成器."""

    def compose(
        self,
        segment_paths: list[str],
        config: CompositionConfig | None = None,
    ) -> CompositionResult:
        """合成视频片段."""
        if config is None:
            config = CompositionConfig()

        if len(segment_paths) < 1:
            return CompositionResult(config=config, success=False, message="至少需要1个片段")

        os.makedirs(os.path.dirname(config.output_path) or ".", exist_ok=True)

        if len(segment_paths) == 1:
            return self._compose_single(segment_paths[0], config)
        elif config.transition == TransitionType.FADE and config.transition_duration <= 0:
            return self._compose_concat(segment_paths, config)
        else:
            return self._compose_with_transitions(segment_paths, config)

    def _compose_single(self, segment_path: str, config: CompositionConfig) -> CompositionResult:
        """单个片段直接复制."""
        import shutil

        try:
            shutil.copy2(segment_path, config.output_path)
            return CompositionResult(
                config=config,
                segments_used=[segment_path],
                output_path=config.output_path,
                success=True,
                message="单片段已直接输出",
            )
        except Exception as e:
            return CompositionResult(
                config=config,
                success=False,
                message=f"复制失败: {e}",
            )

    def _compose_concat(
        self, segment_paths: list[str], config: CompositionConfig
    ) -> CompositionResult:
        """使用 concat 模式合成（无转场）."""
        list_file = os.path.join(
            tempfile.mkdtemp(prefix="vt_compose_"),
            "file_list.txt",
        )

        with open(list_file, "w", encoding="utf-8") as f:
            for path in segment_paths:
                # Windows 路径需要转义
                escaped_path = path.replace("\\", "/").replace(":", "\\:")
                f.write(f"file '{escaped_path}'\n")

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file,
            "-c",
            "copy",
            config.output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            success = result.returncode == 0
            return CompositionResult(
                config=config,
                segments_used=segment_paths,
                output_path=config.output_path,
                success=success,
                message="concat 拼接完成" if success else f"失败: {result.stderr.decode()[-200:]}",
            )
        except subprocess.TimeoutExpired:
            return CompositionResult(config=config, success=False, message="拼接超时")
        finally:
            if os.path.exists(list_file):
                os.remove(list_file)

    def _has_audio_stream(self, video_path: str) -> bool:
        """检查视频文件是否包含音频流."""
        try:
            import json

            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "a",
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return False
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            return len(streams) > 0
        except Exception:
            return False

    def _compose_with_transitions(
        self,
        segment_paths: list[str],
        config: CompositionConfig,
    ) -> CompositionResult:
        """使用 xfade 滤镜合成（带转场）."""
        effect = TRANSITION_EFFECTS.get(config.transition, "fade")
        offset = config.transition_duration

        # 检测所有片段是否都有音频
        all_have_audio = config.audio_mode != "mute" and all(
            self._has_audio_stream(p) for p in segment_paths
        )

        # 构建视频 xfade 链式滤镜
        video_parts = []
        prev_v = "[0:v]"
        accumulated_offset = 0.0

        # 构建音频 acrossfade 链式滤镜（仅当有音频时）
        audio_parts = []
        prev_a = "[0:a]" if all_have_audio else None

        for i in range(1, len(segment_paths)):
            out_v = f"[v{i}]"
            seg_duration = self._get_video_duration(segment_paths[i - 1])
            accumulated_offset += seg_duration - offset

            video_parts.append(
                f"{prev_v}[{i}:v]xfade=transition={effect}:"
                f"duration={offset}:offset={accumulated_offset:.4f}{out_v}"
            )
            if all_have_audio:
                out_a = f"[a{i}]"
                audio_parts.append(f"{prev_a}[{i}:a]acrossfade=d={offset}:c1=tri:c2=tri{out_a}")
                prev_a = out_a
            prev_v = out_v

        # 合并视频和音频滤镜
        all_parts = video_parts + audio_parts
        filter_complex = ";".join(all_parts)

        # 构建命令
        cmd = ["ffmpeg", "-y"]
        for path in segment_paths:
            cmd.extend(["-i", path])

        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", prev_v])
        if all_have_audio and prev_a is not None:
            cmd.extend(["-map", prev_a])
        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "18"])
        if all_have_audio:
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            cmd.extend(["-an"])
        cmd.extend([config.output_path])

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            success = result.returncode == 0

            if success and config.add_music and os.path.exists(config.music_path):
                self._add_background_music(config)

            return CompositionResult(
                config=config,
                segments_used=segment_paths,
                output_path=config.output_path,
                success=success,
                message="转场合成完成" if success else f"失败: {result.stderr.decode()[-300:]}",
            )
        except subprocess.TimeoutExpired:
            return CompositionResult(config=config, success=False, message="转场合成超时")

    def _add_background_music(self, config: CompositionConfig):
        """添加背景音频."""
        temp_output = config.output_path + ".tmp.mp4"

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            config.output_path,
            "-i",
            config.music_path,
            "-filter_complex",
            f"[1:a]volume={config.music_volume}[bgm];"
            f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            temp_output,
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=120)
            os.replace(temp_output, config.output_path)
        except Exception:
            if os.path.exists(temp_output):
                os.remove(temp_output)

    @staticmethod
    def _get_video_duration(video_path: str) -> float:
        """获取视频时长."""
        try:
            import json

            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
        except Exception:
            return 0.0
