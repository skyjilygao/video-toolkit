"""Dry-Run 全流程测试 — 不调用大模型、不执行 FFmpeg 拼接.

完整流程:
1. 获取视频源（本地路径 / 在线 URL，经 ``sources`` 模块解析，支持 yt-dlp）
2. 视频分析（场景 / 关键帧 / 音频能量 / 节奏，导出报告）
3. 场景拆解（FFmpeg 切割原画面，验证拆解链路）
4. 生成计划（PromptEngine 构建 prompt + ``build_generation_calls`` 构建大模型调用候选参数）

说明:
- 全新视频只能由 text-to-video 大模型生成，未配置时不发送真实请求；
- FFmpeg 拼接的是「AI 生成的全新片段」，无大模型调用则无拼接对象，故 Dry-Run 到
  生成参数为止；
- 所有中间结果写入 ``output_dir``，其中 ``generation/llm_calls.json`` 为全部
  大模型调用参数（含每个场景的 prompt）。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime

from rich.console import Console

from video_toolkit.analysis import AnalysisManager
from video_toolkit.analysis.base import _derive_video_subdir
from video_toolkit.decomposition.decomposer import DecompositionResult, VideoDecomposer
from video_toolkit.generation.base import GenerationCallSpec
from video_toolkit.generation.custom_adapter import CustomGenerationAdapter
from video_toolkit.generation.prompt_engine import PromptEngine
from video_toolkit.models.analysis import (
    AnalysisBrief,
    RegenerationConfig,
    SceneBrief,
    SceneGenerationTask,
    SceneInfo,
    VideoAnalysisResult,
)
from video_toolkit.models.video import AudioInfo, VideoMetadata
from video_toolkit.sources import SourceVideo, resolve_video_source
from video_toolkit.utils.ffprobe_utils import get_video_info

console = Console()


@dataclass
class DryRunReport:
    """Dry-Run 全流程结果报告."""

    source_input: str
    video_path: str
    output_dir: str
    source: SourceVideo
    analysis_adapter: str
    brief: AnalysisBrief
    decomposition: DecompositionResult | None
    tasks: list[SceneGenerationTask]
    llm_calls: list[dict]
    written_files: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    elapsed_seconds: float = 0.0

    @property
    def total_candidates(self) -> int:
        """大模型调用候选总数."""
        return sum(len(call.get("candidates", [])) for call in self.llm_calls)


def run_dry_run(
    source: str,
    output_dir: str,
    *,
    adapter: str = "auto",
    depth: str = "standard",
    max_keyframes: int = 10,
    scene_selection: str = "all",
    scene_count: int = 0,
    scene_indices: list[int] | None = None,
    max_clip_duration: float = 5.0,
    style_prefix: str = "",
    style_suffix: str | None = None,
    preferred_provider: str = "auto",
    preferred_model_id: str = "",
    generation_mode: str = "video_first",
    extract_transcript: bool = False,
    extra_params: dict | None = None,
) -> DryRunReport:
    """执行 Dry-Run 全流程（不调用大模型、不拼接）.

    Parameters
    ----------
    source : str
        本地视频路径或在线视频 URL（YouTube / yt-dlp 支持站点 / http 直链）.
    output_dir : str
        结果输出目录，全部中间产物写入此处.
    adapter : str
        分析适配器: auto / custom / openmontage.
    scene_selection / scene_count / scene_indices : 场景筛选参数
    max_clip_duration : 每个片段的最大生成时长（大模型限制）.
    style_prefix / style_suffix : PromptEngine 风格前后缀.
    preferred_provider / preferred_model_id : 首选大模型（dry-run 中仅影响候选顺序展示）.
    generation_mode : video_first / image_animation.
    extract_transcript : 是否提取字幕转录（需要可选依赖，本地转录较慢）.
    extra_params : 透传给底层 Provider 的额外参数（如 aspect_ratio / resolution）.

    Returns
    -------
    DryRunReport
        含 brief / decomposition / tasks / llm_calls 与全部落盘文件列表.
    """
    started_at = datetime.now().isoformat(timespec="seconds")
    t0 = time.time()
    os.makedirs(output_dir, exist_ok=True)
    written: list[str] = []

    # ── Stage 1: 获取视频源 ──
    console.rule("[bold]Stage 1/4 · 获取视频源[/bold]")
    downloads_dir = os.path.join(output_dir, "downloaded")
    source_video = resolve_video_source(source, downloads_dir)
    video_path = source_video.local_path
    console.print(f"[green]✔ 视频就绪[/green]: {video_path}（来源: {source_video.source_type}）")
    if source_video.source_type != "local":
        _write_json(
            os.path.join(downloads_dir, "source_meta.json"),
            {
                "source_input": source,
                "source_type": source_video.source_type,
                "original_source": source_video.original_source,
                "title": source_video.title,
                "duration_hint": source_video.duration,
                "local_path": source_video.local_path,
                "meta": source_video.meta,
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
            },
            written,
        )

    # ── Stage 2: 视频分析 ──
    console.rule("[bold]Stage 2/4 · 视频分析[/bold]")
    analysis_dir = os.path.join(output_dir, "analysis")
    adapter_name = _resolve_analysis_adapter(adapter)
    analysis_adapter = AnalysisManager.get_adapter(
        name=adapter_name, video_path=video_path, output_dir=analysis_dir
    )
    brief = analysis_adapter.analyze(
        depth=depth,
        max_keyframes=max_keyframes,
        extract_transcript=extract_transcript,
        extract_audio_energy=True,
        extract_keyframes=True,
        save_report=True,
    )
    report_subdir = os.path.join(analysis_dir, _derive_video_subdir(video_path))
    console.print(
        f"[green]✔ 分析完成[/green]: {brief.total_scenes} 场景 / {len(brief.keyframes)} 关键帧 "
        f"（耗时 {brief.duration_analyzed:.1f}s）"
    )
    console.print(f"[dim]分析报告: {report_subdir}[/dim]")
    if brief.total_scenes == 0:
        console.print(
            "[bold yellow]⚠ 警告: 未识别到任何场景 — 请检查视频文件是否有效、"
            "分析器是否正常工作，后续拆解与生成参数可能为空[/bold yellow]"
        )

    # ── Stage 3: 场景拆解（切割原画面，验证 FFmpeg 拆解链路） ──
    console.rule("[bold]Stage 3/4 · 场景拆解（FFmpeg 切割原画面）[/bold]")
    decomp_dir = os.path.join(output_dir, "decomposition")
    analysis_result = _to_video_analysis_result(video_path, brief)
    decomposition = VideoDecomposer(video_path, output_dir=decomp_dir).decompose_by_scenes(
        analysis_result, re_encode=False
    )
    console.print(f"[green]✔ 拆解完成[/green]: {decomposition.total_segments} 个片段（原画面）")

    # ── Stage 4: 生成计划与大模型调用参数（Dry-Run，不调用） ──
    console.rule("[bold]Stage 4/4 · 大模型调用参数（Dry-Run，不调用）[/bold]")
    gen_dir = os.path.join(output_dir, "generation")
    os.makedirs(gen_dir, exist_ok=True)

    config = RegenerationConfig(
        output_path=os.path.join(gen_dir, "regenerated.mp4"),  # dry-run 不产出，仅记录
        scene_selection=scene_selection,
        scene_count=scene_count,
        scene_indices=list(scene_indices or []),
        max_clip_duration=max_clip_duration,
        style_prefix=style_prefix,
        style_suffix=(
            style_suffix if style_suffix is not None else "cinematic, high quality, professional"
        ),
        preferred_provider=preferred_provider,
        preferred_model_id=preferred_model_id,
        generation_mode=generation_mode,
        extra_params=dict(extra_params or {}),
    )

    gen_adapter = CustomGenerationAdapter(
        video_path=video_path,
        brief=brief,
        work_dir=os.path.join(gen_dir, "work"),
    )
    tasks = gen_adapter.build_generation_plan(config)
    scene_map = {s.scene_index: s for s in brief.scenes}

    # TTS 旁白脚本（dry-run 不调用 TTS，仅输出文本）
    task_scene_indices = {t.scene_index for t in tasks}
    selected_scenes = [s for s in brief.scenes if s.scene_index in task_scene_indices]
    prompt_engine = PromptEngine(
        style_profile=brief.style_profile,
        style_prefix=config.style_prefix,
        style_suffix=config.style_suffix,
    )
    narration_script = (
        prompt_engine.build_narration_script(selected_scenes, brief) if selected_scenes else ""
    )

    llm_calls: list[dict] = []
    for task in tasks:
        spec = gen_adapter.build_generation_calls(task, config, include_unregistered=True)
        llm_calls.append(
            _build_call_dict(task, spec, config, scene_map.get(task.scene_index), gen_dir)
        )
    console.print(f"[green]✔ 生成计划完成[/green]: {len(tasks)} 个场景片段 prompt")

    # ── 落盘: 大模型调用参数 ──
    llm_doc = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "dry-run",
        "note": "本文件仅包含将调用大模型的全部参数（含 prompt），Dry-Run 不发送真实请求、不拼接",
        "source": {
            "input": source,
            "type": source_video.source_type,
            "title": source_video.title,
            "original_source": source_video.original_source,
        },
        "video": {"path": video_path, "duration_seconds": brief.duration_seconds},
        "analysis": {
            "adapter": adapter_name,
            "total_scenes": brief.total_scenes,
            "keyframes": len(brief.keyframes),
            "report_dir": report_subdir,
        },
        "decomposition": {
            "segments": decomposition.total_segments,
            "output_dir": decomp_dir,
        },
        "config": config.model_dump(),
        "narration_script": narration_script,
        "summary": {
            "tasks_planned": len(tasks),
            "calls_total": sum(len(c["candidates"]) for c in llm_calls),
            "calls_by_provider": _count_by_provider(llm_calls),
        },
        "calls": llm_calls,
    }
    _write_json(os.path.join(gen_dir, "llm_calls.json"), llm_doc, written)
    _write_text(os.path.join(gen_dir, "llm_calls.md"), _render_calls_md(llm_doc), written)
    _write_text(os.path.join(gen_dir, "prompts.txt"), _render_prompts_txt(tasks, brief), written)

    elapsed = round(time.time() - t0, 2)
    report = DryRunReport(
        source_input=source,
        video_path=video_path,
        output_dir=output_dir,
        source=source_video,
        analysis_adapter=adapter_name,
        brief=brief,
        decomposition=decomposition,
        tasks=tasks,
        llm_calls=llm_calls,
        written_files=written,
        started_at=started_at,
        finished_at=datetime.now().isoformat(timespec="seconds"),
        elapsed_seconds=elapsed,
    )

    _write_text(os.path.join(output_dir, "README.md"), _render_report_md(report), written)
    report.written_files = written

    console.rule("[bold green]Dry-Run 完成[/bold green]")
    console.print(
        f"[green]全部结果已写入[/green]: {output_dir}\n"
        f"[dim]大模型调用参数: {os.path.join(gen_dir, 'llm_calls.json')}（{len(tasks)} 场景 / "
        f"{report.total_candidates} 个调用候选，耗时 {elapsed}s）[/dim]"
    )
    return report


# ── 辅助函数 ──


def _resolve_analysis_adapter(name: str) -> str:
    """解析 auto 分析适配器为具体名称."""
    if name != "auto":
        return name
    from video_toolkit.analysis.openmontage_adapter import _find_openmontage_path

    if _find_openmontage_path():
        console.print("[dim]自动选择分析适配器: openmontage[/dim]")
        return "openmontage"
    console.print("[dim]自动选择分析适配器: custom (OpenMontage 未发现)[/dim]")
    return "custom"


def _to_video_analysis_result(video_path: str, brief: AnalysisBrief) -> VideoAnalysisResult:
    """将 AnalysisBrief 转换为 decomposer 需要的 VideoAnalysisResult."""
    metadata = brief.metadata or _build_metadata(video_path)
    scenes = [
        SceneInfo(
            scene_id=s.scene_index,
            start_time=s.start_time,
            end_time=s.end_time,
            duration=s.duration,
        )
        for s in brief.scenes
    ]
    return VideoAnalysisResult(metadata=metadata, scenes=scenes)


def _build_metadata(video_path: str) -> VideoMetadata:
    """通过 FFprobe 构建视频元数据."""
    info = get_video_info(video_path)
    return VideoMetadata(
        file_path=video_path,
        file_name=os.path.basename(video_path),
        format=os.path.splitext(video_path)[1].lstrip(".").lower(),
        duration=info.get("duration", 0.0),
        width=info.get("width", 0),
        height=info.get("height", 0),
        fps=info.get("fps", 0.0),
        total_frames=info.get("total_frames", 0),
        audio=AudioInfo(has_audio=info.get("has_audio", False)),
    )


def _build_call_dict(
    task: SceneGenerationTask,
    spec: GenerationCallSpec,
    config: RegenerationConfig,
    scene: SceneBrief | None,
    gen_dir: str,
) -> dict:
    """构建单个场景的大模型调用参数字典."""
    candidates = []
    for c in spec.candidates:
        req = c.request
        candidates.append(
            {
                "provider": c.provider,
                "model_id": c.model_id,
                "note": c.note,
                "available": c.available,
                "generation_type": req.generation_type.value,
                "prompt": req.prompt,
                "width": req.width,
                "height": req.height,
                "aspect_ratio": config.extra_params.get("aspect_ratio", "16:9"),
                "duration": req.duration,
                "negative_prompt": req.negative_prompt,
                "seed": req.seed,
                "extra_params": req.extra_params,
            }
        )
    return {
        "scene_index": task.scene_index,
        "scene_start_time": scene.start_time if scene else None,
        "scene_end_time": scene.end_time if scene else None,
        "scene_duration": scene.duration if scene else None,
        "clip_duration_target": task.duration,
        "narration_text": task.narration_text,
        "output_path_planned": os.path.join(gen_dir, "work", f"gen_{task.scene_index:04d}.mp4"),
        "candidates": candidates,
    }


def _count_by_provider(llm_calls: list[dict]) -> dict[str, int]:
    """统计各 provider 的候选调用数."""
    counts: dict[str, int] = {}
    for call in llm_calls:
        for cand in call.get("candidates", []):
            counts[cand["provider"]] = counts.get(cand["provider"], 0) + 1
    return counts


def _write_json(path: str, data: dict, written: list[str]) -> None:
    """写入 JSON 文件（utf-8 / ensure_ascii=False / indent=2）."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    written.append(path)


def _write_text(path: str, content: str, written: list[str]) -> None:
    """写入文本文件（utf-8）."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    written.append(path)


def _render_calls_md(doc: dict) -> str:
    """渲染大模型调用参数的可读 Markdown."""
    lines = [
        "# 大模型调用参数（Dry-Run）",
        "",
        "> 候选按优先级排列；真实运行时依次尝试，成功即停。",
        "> 本文件不产生真实大模型调用，仅展示全部参数（含 prompt）。",
        "",
        f"- 生成时间: {doc['generated_at']}",
        f"- 输入源: {doc['source']['input']}（{doc['source']['type']}）",
        f"- 计划片段数: {doc['summary']['tasks_planned']}",
        f"- 调用候选总数: {doc['summary']['calls_total']}",
        f"- Provider 分布: {json.dumps(doc['summary']['calls_by_provider'], ensure_ascii=False)}",
        "",
        "---",
        "",
    ]
    for call in doc["calls"]:
        start = call["scene_start_time"]
        end = call["scene_end_time"]
        lines += [
            f"## 场景 #{call['scene_index']}"
            + (f" — {start:.2f}s ~ {end:.2f}s（{end - start:.2f}s）" if start is not None else ""),
            "",
            "**Prompt（给大模型的提示词）**",
            "",
            "```",
            call["candidates"][0]["prompt"] if call["candidates"] else "",
            "```",
            "",
            f"期望片段时长: {call['clip_duration_target']:.2f}s　|　"
            f"旁白: {call['narration_text'] or '（无）'}",
            "",
        ]
        for i, cand in enumerate(call["candidates"], start=1):
            note_label = {
                "preferred": "首选",
                "fallback": "降级候选",
                "image_fallback": "图片动画兜底（仅展示）",
            }.get(cand["note"], cand["note"])
            avail_note = "（未注册：无 API Key，仅展示）" if not cand.get("available", True) else ""
            lines += [
                f"### 候选 {i}（{note_label}）{avail_note}: Provider `{cand['provider']}`"
                + (f" | 模型 `{cand['model_id']}`" if cand["model_id"] else ""),
                "",
                f"- 生成类型: `{cand['generation_type']}`",
                f"- 分辨率: {cand['width']} x {cand['height']}（宽高比 {cand['aspect_ratio']}）",
                f"- 时长: {cand['duration']}s",
            ]
            if cand.get("negative_prompt"):
                lines.append(f"- 反向提示: {cand['negative_prompt']}")
            if cand.get("seed") is not None:
                lines.append(f"- 随机种子: {cand['seed']}")
            if cand.get("extra_params"):
                lines += [
                    "- 额外参数:",
                    "",
                    "```json",
                    json.dumps(cand["extra_params"], ensure_ascii=False, indent=2),
                    "```",
                ]
            lines += ["", "```", cand["prompt"], "```", ""]
        lines += ["---", ""]
    return "\n".join(lines)


def _render_prompts_txt(tasks: list[SceneGenerationTask], brief: AnalysisBrief) -> str:
    """渲染场景 prompt 纯文本（便于快速浏览）."""
    scene_map = {s.scene_index: s for s in brief.scenes}
    lines = [
        "=" * 70,
        "Video Toolkit · Dry-Run 场景 Prompts（全部候选均以首个 prompt 为准）",
        f"场景总数: {len(tasks)}",
        "=" * 70,
        "",
    ]
    for task in tasks:
        scene = scene_map.get(task.scene_index)
        lines += [
            f"场景 #{task.scene_index}"
            + (
                f"（{scene.start_time:.2f}s ~ {scene.end_time:.2f}s, 时长 {scene.duration:.2f}s）"
                if scene
                else ""
            ),
            f"目标生成时长: {task.duration:.2f}s",
            "-" * 70,
            "Prompt:",
            task.prompt,
            "",
            "Narration:",
            task.narration_text or "（无）",
            "",
            "=" * 70,
            "",
        ]
    return "\n".join(lines)


def _render_report_md(report: DryRunReport) -> str:
    """渲染顶层流程报告."""
    brief = report.brief
    lines = [
        "# Dry-Run 全流程报告",
        "",
        "- 模式: **Dry-Run**（不调用大模型、不执行 FFmpeg 拼接）",
        f"- 输入源: {report.source_input}（{report.source.source_type}）",
        f"- 本地视频: `{report.video_path}`",
        f"- 分析适配器: {report.analysis_adapter}",
        f"- 视频时长: {brief.duration_seconds:.1f}s",
        f"- 场景数: {brief.total_scenes}　关键帧: {len(brief.keyframes)}",
        f"- 计划生成片段: {len(report.tasks)}",
        f"- 大模型调用候选: {report.total_candidates} 个（全部参数见 generation/llm_calls.json）",
        f"- 执行耗时: {report.elapsed_seconds:.1f}s（{report.started_at} ~ {report.finished_at}）",
        "",
        "## 输出文件",
        "",
        "| 文件 | 说明 |",
        "| --- | --- |",
        "| `downloaded/` | 在线视频下载目录（本地源时仅记录元信息） |",
        "| `analysis/<video>/analysis.json` | 完整分析数据 |",
        "| `analysis/<video>/summary.md` | 可读分析摘要 |",
        "| `analysis/<video>/scenes.json` | 场景数据 |",
        "| `analysis/<video>/keyframes/` | 关键帧图片 |",
        "| `decomposition/decomposition_index.json` | 拆解索引 |",
        "| `decomposition/segments/` | 切割出的原画面片段（拆解验证，非新生成） |",
        "| `generation/llm_calls.json` | **全部大模型调用参数（含 prompt）** |",
        "| `generation/llm_calls.md` | 可读版调用参数 |",
        "| `generation/prompts.txt` | 场景 prompt 列表 |",
        "",
        "## 说明",
        "",
        "- 全新视频需调用 text-to-video 大模型生成；未配置 provider 时 Dry-Run 仅输出参数。",
        "- FFmpeg 拼接的对象是「AI 生成的全新片段」，无大模型调用则无拼接对象。",
        "- 复用: `video-toolkit dryrun <source|url> -o <output_dir>`。",
        "",
    ]
    return "\n".join(lines)
