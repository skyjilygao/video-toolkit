"""自定义视频 AI 生成适配器 — 基于 fal.ai (Kling/FLUX) 生成全新视频.

与 CustomDuplicator 的本质区别:
- CustomDuplicator: 截取原视频片段后重新拼接（画面不变）
- CustomGenerationAdapter: 调用 AI 生成完全新的画面内容

策略:
1. 优先使用 Kling text-to-video 动态生成视频片段
2. Kling 不可用时降级到 FLUX 生成图片 + Ken Burns 动态效果
3. 最后用 FFmpeg 拼接所有 AI 生成片段
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

from rich.console import Console

from video_toolkit.ai.base import GenerationRequest, GenerationType
from video_toolkit.composition.composer import VideoComposer
from video_toolkit.config import config
from video_toolkit.generation.base import BaseGenerationAdapter
from video_toolkit.generation.prompt_engine import PromptEngine
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


class CustomGenerationAdapter(BaseGenerationAdapter):
    """自定义视频 AI 生成适配器.

    基于 fal.ai 的 Kling (视频生成) 和 FLUX (图片生成) 实现。
    """

    name = "custom"

    def __init__(
        self,
        video_path: str,
        brief: AnalysisBrief,
        work_dir: str | None = None,
    ):
        super().__init__(video_path=video_path, brief=brief)
        self.work_dir = work_dir or tempfile.mkdtemp(prefix="vt_regen_")
        self._ai_manager = None

    # ── 环境验证 ──

    def validate_environment(self) -> tuple[bool, str]:
        """验证是否有可用的 AI Provider."""
        if self._ai_manager is None:
            from video_toolkit.ai.manager import AIGeneratorManager

            self._ai_manager = AIGeneratorManager()

        mgr = self._ai_manager
        providers = mgr.list_providers()

        if not providers:
            return False, (
                "没有可用的 AI Provider。请设置以下环境变量之一:\n"
                "  FAL_KEY     — fal.ai (Kling + FLUX, 推荐)\n"
                "  OPENAI_API_KEY — OpenAI (DALL-E + TTS)\n"
                "  ELEVENLABS_API_KEY — ElevenLabs (TTS)"
            )

        # 验证 FFmpeg
        ffmpeg_path = config.get_ffmpeg_path()
        try:
            subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False, (f"未找到 FFmpeg: {ffmpeg_path}\n" "请安装 FFmpeg 并确保在 PATH 中。")

        video_providers = [p for p in providers if p in ("fal", "openai")]
        return True, f"可用 Provider: {', '.join(video_providers)}"

    # ── 核心再生方法 ──

    def regenerate(self, config: RegenerationConfig) -> RegenerationResult:
        """执行完整的视频 AI 再生流水线."""
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

            # 2. 筛选场景
            scene_indices = self._filter_scenes(config)
            if not scene_indices:
                raise RuntimeError("没有可生成的场景")

            scenes = [self.brief.scenes[i] for i in scene_indices]
            console.print(f"[dim]将生成 {len(scenes)} 个全新视频片段[/dim]")

            # 3. 构建 PromptEngine
            prompt_engine = PromptEngine(
                style_profile=self.brief.style_profile,
                style_prefix=config.style_prefix,
                style_suffix=config.style_suffix,
            )

            # 4. 生成 AI 视频片段
            tasks = self._generate_all_clips(scenes, config, prompt_engine)
            result.tasks = tasks

            # 5. 收集成功的片段
            segments = [
                t.output_path for t in tasks if t.status == "done" and os.path.isfile(t.output_path)
            ]
            result.generated_segments = segments
            result.failed_scenes = [t.scene_index for t in tasks if t.status == "failed"]

            if not segments:
                raise RuntimeError("所有场景的 AI 生成均失败")

            console.print(f"[green]成功生成 {len(segments)}/{len(scenes)} 个片段[/green]")

            # 6. 生成 TTS 旁白（可选）
            if config.audio_mode == "tts_narration":
                narration_text = prompt_engine.build_narration_script(scenes, self.brief)
                if narration_text:
                    tts_path = self._generate_tts(narration_text, config)
                    result.tts_audio_path = tts_path

            # 7. 拼接最终视频
            self._compose_final_video(segments, config, result)

            # 8. 保存 prompts 到文本文件
            if config.keep_prompts:
                self._save_prompts(tasks, config)

            # 9. 统计
            result.output_path = config.output_path
            result.duration = self._get_duration(config.output_path)
            result.original_duration = self.original_duration
            result.success = True
            result.message = (
                f"视频再生完成: {len(segments)}/{len(scenes)} 个片段, "
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

    # ── 片段生成 ──

    def _generate_all_clips(
        self,
        scenes: list,
        config: RegenerationConfig,
        prompt_engine: PromptEngine,
    ) -> list[SceneGenerationTask]:
        """为所有场景生成 AI 视频片段."""
        tasks: list[SceneGenerationTask] = []

        for scene in scenes:
            task = SceneGenerationTask(
                scene_index=scene.scene_index,
                prompt=prompt_engine.build_scene_prompt(scene, layer_mode="full"),
                narration_text=scene.narration_text or scene.description or "",
                duration=min(scene.duration, config.max_clip_duration),
            )
            tasks.append(task)

        # 逐个生成
        for i, task in enumerate(tasks):
            console.print(
                f"[bold cyan]生成片段 [{i+1}/{len(tasks)}][/bold cyan] "
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

        output_path = os.path.join(self.work_dir, f"gen_{task.scene_index:04d}.mp4")
        task.output_path = output_path

        generation_mode = config.generation_mode

        if generation_mode == "video_first":
            # 尝试 Kling 视频生成
            success = self._try_generate_video(task, config)
            if not success:
                # 降级到图片 + 动画
                console.print("  [yellow]Kling 不可用，降级到 FLUX 图片+动画[/yellow]")
                success = self._generate_image_animation(task, config)
        elif generation_mode == "image_animation":
            success = self._generate_image_animation(task, config)
        else:
            success = self._try_generate_video(task, config)

        task.status = "done" if success else "failed"

    def _try_generate_video(
        self,
        task: SceneGenerationTask,
        config: RegenerationConfig,
    ) -> bool:
        """尝试生成视频片段，支持通过model_id选择模型."""
        from video_toolkit.ai.manager import AIGeneratorManager
        from video_toolkit.config import config as global_config

        if self._ai_manager is None:
            self._ai_manager = AIGeneratorManager()

        mgr = self._ai_manager

        # 1. 优先使用用户指定的模型ID
        target_model_id = config.preferred_model_id
        if not target_model_id:
            # 使用默认模型
            target_model_id = (
                global_config.get_model_config().get("config", {}).get("defaultVideoModel", "")
            )

        if target_model_id:
            # 查找模型对应的provider
            model_config = global_config.get_model_by_id(target_model_id)
            if model_config:
                provider_name = model_config.get("provider")
                if provider_name and provider_name in mgr.list_providers():
                    console.print(
                        f"  [dim]使用模型 {target_model_id}（Provider: {provider_name}）生成视频[/dim]"
                    )
                    # 构建额外参数，传递模型特定配置
                    extra_params = {
                        "output_dir": self.work_dir,
                    }
                    # 如果是seedance，传递特定参数
                    if provider_name == "seedance":
                        extra_params.update(
                            {
                                "aspect_ratio": config.extra_params.get("aspect_ratio", "16:9"),
                                "resolution": config.extra_params.get("resolution", "720p"),
                                "model_version": model_config.get("version", "2.0"),
                                "variant": model_config.get("variant", "standard"),
                            }
                        )

                    request = GenerationRequest(
                        prompt=task.prompt,
                        generation_type=GenerationType.VIDEO,
                        duration=task.duration,
                        width=config.output_width,
                        height=config.output_height,
                        extra_params=extra_params,
                    )
                    gen_result = mgr.generate(request, provider=provider_name)
                    if gen_result.success:
                        downloaded = self._download_to_local(
                            gen_result.output_path, task.output_path
                        )
                        if downloaded:
                            self._normalize_clip(task.output_path, config)
                            return True
                    # 如果指定模型失败，打印警告并尝试降级
                    console.print(
                        f"  [yellow]模型 {target_model_id} 生成失败，尝试降级到可用模型[/yellow]"
                    )

        # 2. 降级逻辑：遍历所有可用的视频生成provider
        providers = mgr.list_providers()
        # 优先级：seedance > fal > openai
        for provider in ["seedance", "fal", "openai"]:
            if provider in providers:
                console.print(f"  [dim]降级使用 {provider} 生成视频[/dim]")
                extra_params = {
                    "output_dir": self.work_dir,
                }
                if provider == "seedance":
                    extra_params.update(
                        {
                            "aspect_ratio": config.extra_params.get("aspect_ratio", "16:9"),
                            "resolution": config.extra_params.get("resolution", "720p"),
                        }
                    )

                request = GenerationRequest(
                    prompt=task.prompt,
                    generation_type=GenerationType.VIDEO,
                    duration=task.duration,
                    width=config.output_width,
                    height=config.output_height,
                    extra_params=extra_params,
                )
                gen_result = mgr.generate(request, provider=provider)
                if gen_result.success:
                    downloaded = self._download_to_local(gen_result.output_path, task.output_path)
                    if downloaded:
                        self._normalize_clip(task.output_path, config)
                        return True

        return False

    def _generate_image_animation(
        self,
        task: SceneGenerationTask,
        config: RegenerationConfig,
    ) -> bool:
        """降级方案：用 FLUX 生成图片 + Ken Burns 效果."""
        from video_toolkit.ai.manager import AIGeneratorManager

        if self._ai_manager is None:
            self._ai_manager = AIGeneratorManager()

        mgr = self._ai_manager

        # 生成图片
        img_request = GenerationRequest(
            prompt=task.prompt,
            generation_type=GenerationType.IMAGE,
            width=config.output_width,
            height=config.output_height,
        )

        img_result = mgr.generate(img_request, provider="fal")

        if not img_result.success:
            return False

        # 下载图片
        img_path = task.output_path.replace(".mp4", ".png")
        downloaded = self._download_to_local(img_result.output_path, img_path)

        if not downloaded:
            return False

        # 用 FFmpeg 做 Ken Burns 动态效果
        self._ken_burns_to_video(img_path, task.output_path, task.duration, config)

        return os.path.isfile(task.output_path)

    def _ken_burns_to_video(
        self,
        image_path: str,
        output_path: str,
        duration: float,
        config: RegenerationConfig,
    ):
        """将静态图片转换为带 Ken Burns 效果的视频."""
        fps = config.output_fps
        width = config.output_width
        height = config.output_height

        # Ken Burns: 缓慢放大 + 平移
        zoom_filter = (
            f"zoompan=z='1.2':d={int(duration * fps)}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )

        ffmpeg_path = config.get_ffmpeg_path()
        cmd = [
            ffmpeg_path,
            *FFMPEG_GLOBAL_ARGS,
            "-y",
            "-loop",
            "1",
            "-i",
            image_path,
            "-vf",
            zoom_filter,
            "-c:v",
            "libx264",
            "-t",
            str(duration),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
            raise RuntimeError(f"Ken Burns 生成失败: {err[-200:]}") from e

    # ── 下载工具 ──

    def _download_to_local(self, url_or_path: str, dest: str) -> bool:
        """下载远程文件到本地，如果已经是本地路径则复制."""
        if not url_or_path:
            return False

        # 已经是本地文件
        if os.path.isfile(url_or_path):
            try:
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
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
        ffmpeg_path = config.get_ffmpeg_path()

        crf_map = {"high": "18", "medium": "23", "low": "28"}
        crf = crf_map.get(config.quality, "20")

        cmd = [
            ffmpeg_path,
            *FFMPEG_GLOBAL_ARGS,
            "-y",
            "-i",
            clip_path,
            "-vf",
            f"scale={config.output_width}:{config.output_height}",
            "-r",
            str(config.output_fps),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            crf,
            "-pix_fmt",
            "yuv420p",
            "-an",  # 移除音频，后续统一处理
            "-movflags",
            "+faststart",
            tmp_path,
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
            shutil.move(tmp_path, clip_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ── TTS 生成 ──

    def _generate_tts(self, text: str, config: RegenerationConfig) -> str:
        """生成 TTS 旁白音频."""
        from video_toolkit.ai.manager import AIGeneratorManager

        if self._ai_manager is None:
            self._ai_manager = AIGeneratorManager()

        mgr = self._ai_manager
        provider = config.tts_provider

        # 自动选择
        if provider == "auto":
            if "elevenlabs" in mgr.list_providers():
                provider = "elevenlabs"
            elif "openai" in mgr.list_providers():
                provider = "openai"
            else:
                console.print("[yellow]没有可用的 TTS Provider[/yellow]")
                return ""

        # 限制文本长度
        if len(text) > 4000:
            text = text[:4000]

        request = GenerationRequest(
            prompt=text,
            generation_type=GenerationType.AUDIO,
            extra_params={"voice": config.tts_voice},
        )

        result = mgr.generate(request, provider=provider)
        if result.success:
            dest = os.path.join(self.work_dir, "narration.mp3")
            if self._download_to_local(result.output_path, dest):
                return dest

        return ""

    # ── 视频拼接 ──

    def _compose_final_video(
        self,
        segments: list[str],
        config: RegenerationConfig,
        result: RegenerationResult,
    ):
        """拼接所有 AI 生成片段为最终视频."""
        os.makedirs(os.path.dirname(config.output_path) or ".", exist_ok=True)

        from video_toolkit.models.composition import (
            CompositionConfig,
            TransitionType,
        )

        transition_map = {
            "fade": TransitionType.FADE,
            "wipeleft": TransitionType.WIPE_LEFT,
            "wiperight": TransitionType.WIPE_RIGHT,
            "slideleft": TransitionType.SLIDE_LEFT,
            "slideright": TransitionType.SLIDE_RIGHT,
            "dissolve": TransitionType.DISSOLVE,
        }
        transition = transition_map.get(config.transition, TransitionType.FADE)

        comp_config = CompositionConfig(
            output_path=config.output_path,
            transition=transition,
            transition_duration=config.transition_duration,
            output_width=config.output_width,
            output_height=config.output_height,
            burn_subtitles=config.burn_subtitles,
            subtitle_font_size=config.subtitle_font_size,
            subtitle_color=config.subtitle_color,
            audio_mode=config.audio_mode,
        )

        composer = VideoComposer()
        comp_result = composer.compose(segments, comp_config)

        if not comp_result.success:
            raise RuntimeError(f"视频拼接失败: {comp_result.message}")

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
        ffmpeg_path = config.get_ffmpeg_path()

        cmd = [
            ffmpeg_path,
            *FFMPEG_GLOBAL_ARGS,
            "-y",
            "-i",
            video_path,
            "-i",
            audio_path,
            "-filter_complex",
            "[0:a]volume=0.8[v0];[1:a]volume=1.0[v1];"
            "[v0][v1]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            tmp_output,
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
            shutil.move(tmp_output, video_path)
        except Exception:
            if os.path.exists(tmp_output):
                os.remove(tmp_output)

    # ── 辅助 ──

    def _save_prompts(self, tasks: list[SceneGenerationTask], config: RegenerationConfig):
        """保存生成 prompt 到文本文件."""
        prompt_file = os.path.join(
            os.path.dirname(config.output_path) or ".",
            "generation_prompts.txt",
        )
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write("# Video Regeneration Prompts\n")
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
