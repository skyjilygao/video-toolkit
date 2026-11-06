"""OpenMontage 视频 AI 生成适配器 — 通过 OpenMontage 工具链生成全新视频.

此适配器利用 OpenMontage 的:
1. shot_prompt_builder 生成专业级 5 层 cinematography prompt
2. video_selector 自动选择最优视频生成 provider (支持 15+ 视频生成后端)
3. video_compose 进行高质量视频拼接 (支持 Remotion/HyperFrames/FFmpeg 三引擎)

使用前提:
    - OpenMontage 项目已安装到本地
    - 配置了至少一个视频生成 provider 的 API Key
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from typing import List, Optional, Tuple

from rich.console import Console

from video_toolkit.generation.base import BaseGenerationAdapter
from video_toolkit.models.analysis import (
    AnalysisBrief,
    RegenerationConfig,
    RegenerationResult,
    SceneGenerationTask,
)
from video_toolkit.utils.ffprobe_utils import get_video_info

console = Console()

# FFmpeg 全局线程优化：避免 Windows 下的线程崩溃
FFMPEG_GLOBAL_ARGS = ["-threads", "1"]


class OpenGenerationAdapter(BaseGenerationAdapter):
    """OpenMontage 视频 AI 生成适配器."""

    name = "openmontage"

    def __init__(
        self,
        video_path: str,
        brief: AnalysisBrief,
        work_dir: Optional[str] = None,
    ):
        super().__init__(video_path=video_path, brief=brief)
        self.work_dir = work_dir or tempfile.mkdtemp(prefix="vt_om_regen_")
        self._openmontage_path: Optional[str] = None
        self._video_selector = None

    # ── 环境验证 ──

    def validate_environment(self) -> Tuple[bool, str]:
        """验证 OpenMontage 环境是否可用."""
        try:
            # 检查 OpenMontage 路径
            from video_toolkit.analysis.openmontage_adapter import (
                _find_openmontage_path,
            )
            self._openmontage_path = _find_openmontage_path()
            if not self._openmontage_path:
                return False, (
                    "未检测到 OpenMontage 安装。请设置 OPENMONTAGE_PATH 环境变量，"
                    "或确保 OpenMontage 位于 video-toolkit 同级目录。"
                )

            # 检查 OpenMontage 核心模块是否可导入
            try:
                from OpenMontage.lib.shot_prompt_builder import build_batch_prompts
                from OpenMontage.tools.video.video_selector import VideoSelector
            except ImportError as e:
                return False, f"OpenMontage 模块导入失败: {e}"

            # 检查是否有可用的视频生成 provider
            selector = VideoSelector()
            if selector.get_status().value != "available":
                return False, (
                    "没有可用的视频生成 provider。请在 OpenMontage 的 .env 文件中配置至少一个 API Key:\n"
                    "  FAL_KEY     — fal.ai (Kling + FLUX, 推荐)\n"
                    "  OPENAI_API_KEY — OpenAI\n"
                    "  RUNWAY_API_KEY — Runway\n"
                    "  或启用本地 GPU 模型"
                )

            # 检查 FFmpeg
            ffmpeg_path = shutil.which("ffmpeg")
            if not ffmpeg_path:
                return False, "未找到 FFmpeg，请安装 FFmpeg 并确保在 PATH 中。"

            # 检查视频合成器是否可用
            try:
                from OpenMontage.tools.video.video_compose import VideoCompose
            except ImportError as e:
                return False, f"视频合成模块导入失败: {e}"

            return True, (
                f"OpenMontage 环境就绪: {self._openmontage_path}\n"
                f"可用 provider: {', '.join(selector.provider_matrix.keys())}\n"
                f"FFmpeg: {ffmpeg_path}"
            )

        except Exception as e:
            return False, f"环境验证失败: {e}"

    # ── 核心再生方法 ──

    def regenerate(self, config: RegenerationConfig) -> RegenerationResult:
        """执行 OpenMontage 视频再生流水线."""
        result = RegenerationResult(
            source_video=self.video_path,
            config=config,
        )

        self._start_time = time.time()

        try:
            # 1. 验证环境
            ok, msg = self.validate_environment()
            if not ok:
                raise RuntimeError(f"环境验证失败: {msg}")
            console.print(f"[green]✓ 环境验证通过[/green]\n[dim]{msg}[/dim]")

            # 2. 筛选场景
            scene_indices = self._filter_scenes(config)
            if not scene_indices:
                raise RuntimeError("没有可生成的场景")

            scenes = [self.brief.scenes[i] for i in scene_indices]
            console.print(f"[dim]将生成 {len(scenes)} 个全新视频片段[/dim]")

            # 3. 初始化 OpenMontage 组件
            from OpenMontage.lib.shot_prompt_builder import build_batch_prompts
            from OpenMontage.tools.video.video_selector import VideoSelector
            from OpenMontage.tools.video.video_compose import VideoCompose

            self._video_selector = VideoSelector()
            prompt_style_context = self._build_style_context()

            # 4. 生成所有场景的 prompt
            om_scenes = self._convert_to_om_scenes(scenes)
            prompt_tasks = build_batch_prompts(om_scenes, prompt_style_context)

            # 5. 生成 AI 视频片段
            tasks = self._generate_all_clips(prompt_tasks, scenes, config)
            result.tasks = tasks

            # 6. 收集成功的片段
            segments = [
                t.output_path for t in tasks
                if t.status == "done" and os.path.isfile(t.output_path)
            ]
            result.generated_segments = segments
            result.failed_scenes = [
                t.scene_index for t in tasks if t.status == "failed"
            ]

            if not segments:
                raise RuntimeError("所有场景的 AI 生成均失败")

            console.print(
                f"[green]成功生成 {len(segments)}/{len(scenes)} 个片段[/green]"
            )

            # 7. 生成 TTS 旁白（可选）
            if config.audio_mode == "tts_narration":
                narration_text = self._build_narration_text(scenes)
                if narration_text:
                    tts_path = self._generate_tts(narration_text, config)
                    result.tts_audio_path = tts_path

            # 8. 拼接最终视频
            self._compose_final_video(segments, config, result)

            # 9. 保存 prompts 到文本文件
            if config.keep_prompts:
                self._save_prompts(tasks, config)

            # 10. 统计
            result.output_path = config.output_path
            result.duration = self._get_duration(config.output_path)
            result.original_duration = self.original_duration
            result.success = True
            result.message = (
                f"OpenMontage 视频再生完成: {len(segments)}/{len(scenes)} 个片段, "
                f"总时长 {result.duration:.1f}s"
            )
            result.total_cost_estimate = self.estimate_cost(config, len(scenes))

        except Exception as e:
            result.success = False
            result.message = f"视频再生失败: {e}"

        # 清理临时文件
        if not config.keep_segments:
            self._cleanup()

        return result

    # ── 辅助方法 ──

    def _build_style_context(self) -> dict:
        """构建 OpenMontage 风格上下文."""
        style = {}
        if self.brief.style_profile:
            style["mood"] = self.brief.style_profile.mood or ""
            style["visual_language"] = {
                "aesthetic": self.brief.style_profile.visual_style or "",
                "color_palette": self.brief.style_profile.color_palette or [],
            }
        # 添加自定义前后缀
        if self.brief.style_prefix:
            style["generation_prefix"] = self.brief.style_prefix
        if self.brief.style_suffix:
            style["generation_suffix"] = self.brief.style_suffix
        return style

    def _convert_to_om_scenes(self, scenes: list) -> list[dict]:
        """将 video-toolkit 的 SceneBrief 转换为 OpenMontage 的场景格式."""
        om_scenes = []
        for scene in scenes:
            shot_language = {
                "shot_size": self._map_shot_size(scene.camera_angle),
                "camera_movement": self._map_camera_movement(scene.camera_movement),
                "lighting_key": self._map_lighting(scene.lighting),
                "depth_of_field": self._map_dof(scene.depth_of_field),
                "color_temperature": self._map_color_temp(scene.color_temperature),
            }
            om_scene = {
                "id": f"scene_{scene.scene_index}",
                "type": "visual",
                "description": scene.description or "",
                "shot_language": shot_language,
                "texture_keywords": scene.texture_keywords or [],
                "hero_moment": scene.hero_moment or False,
                "duration": scene.duration,
            }
            om_scenes.append(om_scene)
        return om_scenes

    @staticmethod
    def _map_shot_size(camera_angle: str) -> str:
        """映射镜头角度到 OpenMontage 的 shot_size."""
        mapping = {
            "close_up": "close_up",
            "medium": "medium",
            "wide": "wide",
            "extreme_wide": "extreme_wide",
            "medium_close": "medium_close",
            "medium_wide": "medium_wide",
            "over_shoulder": "over_shoulder",
            "insert": "insert",
            "establishing": "establishing",
        }
        return mapping.get(camera_angle, "medium")

    @staticmethod
    def _map_camera_movement(movement: str) -> str:
        """映射运镜到 OpenMontage 的 camera_movement."""
        mapping = {
            "static": "static",
            "pan_left": "pan_left",
            "pan_right": "pan_right",
            "tilt_up": "tilt_up",
            "tilt_down": "tilt_down",
            "dolly_in": "dolly_in",
            "dolly_out": "dolly_out",
            "tracking": "tracking_left",
            "crane_up": "crane_up",
            "crane_down": "crane_down",
            "handheld": "handheld",
            "steadicam": "steadicam",
            "orbital": "orbital",
            "zoom_in": "zoom_in",
            "zoom_out": "zoom_out",
        }
        return mapping.get(movement, "static")

    @staticmethod
    def _map_lighting(lighting: str) -> str:
        """映射光照到 OpenMontage 的 lighting_key."""
        mapping = {
            "high_key": "high_key",
            "low_key": "low_key",
            "natural": "natural",
            "golden_hour": "golden_hour",
            "blue_hour": "blue_hour",
            "tungsten": "tungsten_warm",
            "neon": "neon",
            "silhouette": "silhouette",
            "rim_lit": "rim_lit",
            "volumetric": "volumetric",
            "overcast": "overcast_soft",
        }
        return mapping.get(lighting, "natural")

    @staticmethod
    def _map_dof(dof: str) -> str:
        """映射景深到 OpenMontage 的 depth_of_field."""
        mapping = {
            "shallow": "shallow",
            "medium": "medium",
            "deep": "deep",
        }
        return mapping.get(dof, "medium")

    @staticmethod
    def _map_color_temp(temp: str) -> str:
        """映射色温到 OpenMontage 的 color_temperature."""
        mapping = {
            "cool": "cool",
            "neutral": "neutral",
            "warm": "warm",
            "mixed": "mixed",
        }
        return mapping.get(temp, "neutral")

    # ── 片段生成 ──

    def _generate_all_clips(
        self,
        prompt_tasks: list[dict],
        scenes: list,
        config: RegenerationConfig,
    ) -> List[SceneGenerationTask]:
        """为所有场景生成 AI 视频片段."""
        tasks: List[SceneGenerationTask] = []

        for i, (prompt_task, scene) in enumerate(zip(prompt_tasks, scenes)):
            task = SceneGenerationTask(
                scene_index=scene.scene_index,
                prompt=prompt_task["prompt"],
                narration_text=scene.narration_text or scene.description or "",
                duration=min(scene.duration, config.max_clip_duration),
            )
            tasks.append(task)

            console.print(
                f"[bold cyan]生成片段 [{i+1}/{len(prompt_tasks)}][/bold cyan] "
                f"(场景 #{task.scene_index})"
            )
            console.print(f"  [dim]Prompt: {task.prompt[:120]}...[/dim]")

            try:
                self._generate_single_clip(task, config)
            except Exception as e:
                console.print(f"  [red]生成失败: {e}[/red]")
                task.status = "failed"

        return tasks

    def _generate_single_clip(
        self,
        task: SceneGenerationTask,
        config: RegenerationConfig,
    ):
        """生成单个视频片段."""
        task.status = "generating"

        output_path = os.path.join(
            self.work_dir, f"gen_{task.scene_index:04d}.mp4"
        )
        task.output_path = output_path

        # 调用 video_selector 选择最优 provider 生成视频
        inputs = {
            "prompt": task.prompt,
            "operation": "text_to_video",
            "duration": str(int(task.duration)),
            "aspect_ratio": "16:9" if config.output_width > config.output_height else "9:16",
            "output_path": output_path,
        }

        # 添加用户指定的 preferred provider
        if config.preferred_provider and config.preferred_provider != "auto":
            inputs["preferred_provider"] = config.preferred_provider

        result = self._video_selector.execute(inputs)

        if not result.success:
            raise RuntimeError(f"视频生成失败: {result.error}")

        # 下载生成的视频到本地
        video_url = result.data.get("video_url") or result.data.get("output_path")
        if not video_url:
            raise RuntimeError("未返回视频 URL")

        downloaded = self._download_to_local(video_url, output_path)
        if not downloaded:
            raise RuntimeError("视频下载失败")

        # 标准化视频格式
        self._normalize_clip(output_path, config)
        task.status = "done"

    # ── 下载工具 ──

    def _download_to_local(self, url_or_path: str, dest: str) -> bool:
        """下载远程文件到本地，如果已经是本地路径则复制."""
        if not url_or_path:
            return False

        # 已经是本地文件
        if os.path.isfile(url_or_path):
            try:
                shutil.copy2(url_or_path, dest)
                return True
            except Exception:
                return False

        # HTTP URL 下载
        if url_or_path.startswith(("http://", "https://")):
            try:
                import urllib.request
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                urllib.request.urlretrieve(url_or_path, dest)
                return os.path.isfile(dest) and os.path.getsize(dest) > 1000
            except Exception:
                return False

        return False

    # ── 视频标准化 ──

    def _normalize_clip(self, clip_path: str, config: RegenerationConfig):
        """标准化视频格式 (分辨率/帧率/编码)."""
        info = get_video_info(clip_path)
        needs_normalize = (
            info.get("width") != config.output_width
            or info.get("height") != config.output_height
            or abs(info.get("fps", 0) - config.output_fps) > 1
        )

        if not needs_normalize:
            return

        tmp_path = clip_path + ".norm.mp4"
        ffmpeg_path = shutil.which("ffmpeg")

        crf_map = {"high": "18", "medium": "23", "low": "28"}
        crf = crf_map.get(config.quality, "20")

        cmd = [
            ffmpeg_path,
            *FFMPEG_GLOBAL_ARGS,
            "-y",
            "-i", clip_path,
            "-vf", f"scale={config.output_width}:{config.output_height}",
            "-r", str(config.output_fps),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", crf,
            "-pix_fmt", "yuv420p",
            "-an",  # 移除音频，后续统一处理
            "-movflags", "+faststart",
            tmp_path,
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
            shutil.move(tmp_path, clip_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ── TTS 生成 ──

    def _build_narration_text(self, scenes: list) -> str:
        """构建旁白文本."""
        narration_parts = []
        for scene in scenes:
            if scene.narration_text:
                narration_parts.append(scene.narration_text)
            elif scene.description:
                narration_parts.append(scene.description)
        return ". ".join(narration_parts)

    def _generate_tts(self, text: str, config: RegenerationConfig) -> str:
        """生成 TTS 旁白音频 (使用 OpenMontage 的 tts_selector)."""
        try:
            from OpenMontage.tools.audio.tts_selector import TTSSelector

            tts = TTSSelector()
            output_path = os.path.join(self.work_dir, "narration.mp3")

            inputs = {
                "text": text[:4000],  # 限制长度
                "output_path": output_path,
            }
            if config.tts_provider and config.tts_provider != "auto":
                inputs["preferred_provider"] = config.tts_provider
            if config.tts_voice:
                inputs["voice"] = config.tts_voice

            result = tts.execute(inputs)

            if result.success and os.path.isfile(output_path):
                return output_path

        except Exception as e:
            console.print(f"[yellow]TTS 生成失败: {e}[/yellow]")

        return ""

    # ── 视频拼接 ──

    def _compose_final_video(
        self,
        segments: List[str],
        config: RegenerationConfig,
        result: RegenerationResult,
    ):
        """拼接所有 AI 生成片段为最终视频."""
        os.makedirs(os.path.dirname(config.output_path) or ".", exist_ok=True)

        from OpenMontage.tools.video.video_compose import VideoCompose

        composer = VideoCompose()

        # 构建合成配置
        compose_inputs = {
            "clip_paths": segments,
            "output_path": config.output_path,
            "transition": config.transition,
            "transition_duration": config.transition_duration,
            "width": config.output_width,
            "height": config.output_height,
            "fps": config.output_fps,
            "burn_subtitles": config.burn_subtitles,
            "subtitle_font_size": config.subtitle_font_size,
            "subtitle_color": config.subtitle_color,
        }

        comp_result = composer.execute(compose_inputs)

        if not comp_result.success:
            raise RuntimeError(f"视频拼接失败: {comp_result.error}")

        # 混合 TTS 音频
        if (
            config.audio_mode == "tts_narration"
            and result.tts_audio_path
            and os.path.isfile(result.tts_audio_path)
        ):
            self._mix_audio(config.output_path, result.tts_audio_path, config)

    def _mix_audio(
        self,
        video_path: str,
        audio_path: str,
        config: RegenerationConfig,
    ):
        """将 TTS 旁白混入视频."""
        tmp_output = video_path + ".audio.mp4"
        ffmpeg_path = shutil.which("ffmpeg")

        cmd = [
            ffmpeg_path,
            *FFMPEG_GLOBAL_ARGS,
            "-y",
            "-i", video_path,
            "-i", audio_path,
            "-filter_complex",
            f"[0:a]volume=0.8[v0];[1:a]volume=1.0[v1];"
            f"[v0][v1]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            tmp_output,
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
            shutil.move(tmp_output, video_path)
        except Exception:
            if os.path.exists(tmp_output):
                os.remove(tmp_output)

    # ── 辅助 ──

    def _save_prompts(self, tasks: List[SceneGenerationTask], config: RegenerationConfig):
        """保存生成 prompt 到文本文件."""
        prompt_file = os.path.join(
            os.path.dirname(config.output_path) or ".",
            "generation_prompts.txt",
        )
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(f"# OpenMontage Video Regeneration Prompts\n")
            f.write(f"# Source: {self.video_path}\n")
            f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total scenes: {len(tasks)}\n\n")
            for task in tasks:
                f.write(f"--- Scene #{task.scene_index} ---\n")
                f.write(f"Status: {task.status}\n")
                f.write(f"Duration: {task.duration}s\n")
                f.write(f"Prompt: {task.prompt}\n")
                f.write(f"Narration: {task.narration_text}\n\n")

        console.print(f"[dim]Prompts 保存到: {prompt_file}[/dim]")

    @staticmethod
    def _get_duration(path: str) -> float:
        try:
            info = get_video_info(path)
            return info.get("duration", 0.0)
        except Exception:
            return 0.0

    def _cleanup(self):
        """清理工作目录."""
        try:
            if os.path.isdir(self.work_dir):
                shutil.rmtree(self.work_dir, ignore_errors=True)
        except Exception:
            pass

    # ── 成本估算 ──

    def estimate_cost(self, config: RegenerationConfig, scene_count: int) -> float:
        """OpenMontage 成本估算 (基于多 provider 平均)."""
        # OpenMontage 支持多种 provider，平均约 $0.02-0.10/clip，取中间值 $0.05
        return scene_count * 0.05
