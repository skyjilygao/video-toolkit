"""命令行工具入口."""
import json
import os
import sys
from pathlib import Path

# Windows UTF-8 修复: 确保 emoji/中文正确输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from video_toolkit import __version__
from video_toolkit.core.analyzer import VideoAnalyzer
from video_toolkit.decomposition.decomposer import VideoDecomposer
from video_toolkit.composition.composer import VideoComposer
from video_toolkit.models.composition import CompositionConfig, TransitionType
from video_toolkit.ai.manager import AIGeneratorManager
from video_toolkit.ai.base import GenerationRequest, GenerationType

console = Console()


def print_banner():
    """打印欢迎横幅."""
    banner = Panel(
        f"[bold cyan]Video Toolkit[/bold cyan] v{__version__}\n"
        "[dim]视频拆解与生成工具[/dim]",
        border_style="cyan",
    )
    console.print(banner)


def _display_brief(brief):
    """显示 AnalysisBrief 结果."""
    # 基本信息
    table = Table(title="视频分析简报", show_header=True)
    table.add_column("属性", style="cyan")
    table.add_column("值", style="green")
    table.add_row("适配器", brief.adapter)
    table.add_row("视频路径", brief.video_path)
    table.add_row("时长", f"{brief.duration_seconds:.1f}s")
    table.add_row("场景数", str(brief.total_scenes))
    table.add_row("关键帧数", str(len(brief.keyframes)))
    table.add_row("分析耗时", f"{brief.duration_analyzed:.1f}s")
    console.print(table)

    # 字幕信息
    if brief.transcript.has_transcript:
        transcript_panel = Panel(
            f"[bold]语言:[/bold] {brief.transcript.language}  "
            f"[bold]字数:[/bold] {brief.transcript.word_count}\n"
            f"{brief.transcript.full_text[:200]}"
            f"{'...' if len(brief.transcript.full_text) > 200 else ''}",
            title="字幕/转录",
            border_style="blue",
        )
        console.print(transcript_panel)

    # 场景列表
    if brief.scenes:
        scene_table = Table(title=f"场景列表 ({len(brief.scenes)} 个)", show_header=True)
        scene_table.add_column("ID", style="cyan", width=4)
        scene_table.add_column("时间段", width=20)
        scene_table.add_column("时长", width=8)
        scene_table.add_column("运动类型", width=14)
        scene_table.add_column("光流方差", width=10)
        for s in brief.scenes:
            motion_label = {
                "static_image": "[STATIC]",
                "animated_still": "[ANIMATED]",
                "motion_clip": "[MOTION]",
                "unknown": "[UNKNOWN]",
            }.get(s.motion_type, s.motion_type)
            scene_table.add_row(
                str(s.scene_index),
                f"{s.start_time:.1f}s - {s.end_time:.1f}s",
                f"{s.duration:.1f}s",
                motion_label,
                f"{s.flow_variance:.2f}" if s.flow_variance >= 0 else "N/A",
            )
        console.print(scene_table)

    # 节奏特征
    if brief.pacing:
        pacing_panel = Panel(
            f"[bold]节奏风格:[/bold] {brief.pacing.pacing_style}  "
            f"[bold]平均场景时长:[/bold] {brief.pacing.avg_scene_duration_seconds:.1f}s  "
            f"[bold]剪辑频率:[/bold] {brief.pacing.cuts_per_minute:.1f} cuts/min",
            title="节奏特征",
            border_style="magenta",
        )
        console.print(pacing_panel)

    # 关键帧
    if brief.keyframes:
        kf_table = Table(title=f"关键帧 ({len(brief.keyframes)} 个)", show_header=True)
        kf_table.add_column("#", style="cyan", width=4)
        kf_table.add_column("时间戳", width=10)
        kf_table.add_column("场景", width=6)
        kf_table.add_column("路径", width=50)
        for i, kf in enumerate(brief.keyframes):
            kf_table.add_row(
                str(i),
                f"{kf.timestamp:.1f}s",
                str(kf.scene_index),
                kf.path,
            )
        console.print(kf_table)


@click.group()
@click.version_option(version=__version__, prog_name="video-toolkit")
def main():
    """Video Toolkit - 视频拆解与生成工具.

    基于 OpenMontage 理念构建，支持视频分析、场景拆解、重组生成、AI 辅助创作。
    """
    pass


@main.command()
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--keyframes", "-k", default=10, help="关键帧数量 (默认 10)")
@click.option("--output", "-o", default=None, help="分析结果输出路径 (JSON)")
@click.option("--report-dir", default=None, help="导出分析报告目录 (包含 summary.md / analysis.json / scenes.json / keyframes/)")
@click.option("--adapter", "-a", type=click.Choice(["auto", "custom", "openmontage"]), default="auto", help="分析适配器")
@click.option("--depth", type=click.Choice(["standard", "deep"]), default="standard", help="分析深度 (standard / deep)")
@click.option("--no-transcript", is_flag=True, help="跳过字幕/转录提取")
@click.option("--no-audio-energy", is_flag=True, help="跳过音频能量分析")
@click.option("--no-keyframes", is_flag=True, help="跳过关键帧提取")
def analyze(video_path, keyframes, output, report_dir, adapter, depth, no_transcript, no_audio_energy, no_keyframes):
    """分析视频 - 提取元数据、场景、关键帧、风格.

    支持通过 --adapter 选择分析后端:
    \b
    - auto: 自动选择 (优先 openmontage，不可用时降级 custom)
    - custom: 纯本地 OpenCV + FFmpeg 实现
    - openmontage: 使用 OpenMontage 分析工具链

    使用 ``--report-dir DIR`` 可同时导出可读报告，便于人工检查结果。
    """
    print_banner()

    try:
        # -- 选择适配器 --
        if adapter == "auto":
            from video_toolkit.analysis import AnalysisManager
            from video_toolkit.analysis.openmontage_adapter import _find_openmontage_path
            if _find_openmontage_path():
                adapter_name = "openmontage"
                console.print("[dim]自动选择适配器: openmontage[/dim]")
            else:
                adapter_name = "custom"
                console.print("[dim]自动选择适配器: custom (OpenMontage 未发现)[/dim]")
        else:
            adapter_name = adapter

        # -- 使用适配器执行分析 --
        from video_toolkit.analysis import AnalysisManager

        # --report-dir: 传给适配器用于导出报告
        adapter_instance = AnalysisManager.get_adapter(
            name=adapter_name, video_path=video_path, output_dir=report_dir,
        )
        brief = adapter_instance.analyze(
            depth=depth,
            max_keyframes=keyframes,
            extract_transcript=not no_transcript,
            extract_audio_energy=not no_audio_energy,
            extract_keyframes=not no_keyframes,
            save_report=bool(report_dir),
        )

        # -- 显示结果 --
        _display_brief(brief)

        # -- 保存结果 --
        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(brief.model_dump(), f, ensure_ascii=False, indent=2, default=str)
            console.print(f"[green]分析结果已保存: {output}[/green]")

        # -- 报告导出提示 --
        if report_dir:
            from video_toolkit.analysis.base import _derive_video_subdir
            subdir = _derive_video_subdir(video_path)
            full_report_path = os.path.join(report_dir, subdir)
            console.print(f"\n[bold green]报告已导出到: {full_report_path}[/bold green]")
            console.print("[dim]包含文件:[/dim]")
            console.print(f"  - {full_report_path}/analysis.json  (完整数据)")
            console.print(f"  - {full_report_path}/summary.md     (可读摘要)")
            console.print(f"  - {full_report_path}/scenes.json    (场景数据)")
            console.print(f"  - {full_report_path}/pacing.json    (节奏特征)")
            console.print(f"  - {full_report_path}/keyframes/     (关键帧图片)")

    except Exception as e:
        console.print(f"[red]分析失败: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


@main.command()
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--mode", "-m", type=click.Choice(["scenes", "interval", "custom"]), default="scenes", help="拆解模式")
@click.option("--interval", "-i", default=5.0, help="间隔秒数 (interval 模式)")
@click.option("--output", "-o", default=None, help="输出目录")
@click.option("--re-encode", is_flag=True, help="使用重编码模式切割")
def decompose(video_path, mode, interval, output, re_encode):
    """拆解视频 - 按场景/间隔/自定义切割."""
    print_banner()

    try:
        decomposer = VideoDecomposer(video_path, output_dir=output)

        if mode == "scenes":
            with VideoAnalyzer(video_path) as analyzer:
                analysis = analyzer.full_analysis()
            result = decomposer.decompose_by_scenes(analysis, re_encode=re_encode)
        elif mode == "interval":
            result = decomposer.decompose_by_interval(interval, re_encode=re_encode)
        else:
            console.print("[yellow]custom 模式需要额外参数，请使用 Python API[/yellow]")
            return

        table = Table(title=f"拆解结果 ({result.total_segments} 个片段)", show_header=True)
        table.add_column("ID", style="cyan", width=4)
        table.add_column("时间段", width=20)
        table.add_column("时长", width=8)
        table.add_column("标签", width=20)
        table.add_column("输出文件", width=30)
        for seg in result.segments:
            table.add_row(
                str(seg.segment_id),
                f"{seg.start_time:.1f}s - {seg.end_time:.1f}s",
                f"{seg.duration:.1f}s",
                ", ".join(seg.tags[:3]),
                os.path.basename(seg.output_path),
            )
        console.print(table)

        console.print(f"[green]拆解完成! 输出目录: {result.output_dir}[/green]")

    except Exception as e:
        console.print(f"[red]拆解失败: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("segments", nargs=-1, required=True)
@click.option("--output", "-o", default="composed.mp4", help="输出文件路径")
@click.option("--transition", "-t", type=click.Choice([t.value for t in TransitionType]), default="fade", help="转场效果")
@click.option("--transition-duration", "-d", default=0.5, help="转场时长秒数")
@click.option("--music", "-m", default=None, help="背景音乐路径")
@click.option("--music-volume", default=0.3, help="背景音乐音量 (0.0-1.0)")
def compose(segments, output, transition, transition_duration, music, music_volume):
    """合成视频 - 拼接片段并添加转场."""
    print_banner()

    try:
        config = CompositionConfig(
            output_path=output,
            transition=TransitionType(transition),
            transition_duration=transition_duration,
            add_music=bool(music),
            music_path=music or "",
            music_volume=music_volume,
        )

        composer = VideoComposer()
        result = composer.compose(list(segments), config)

        if result.success:
            console.print(f"[green]合成完成! 输出: {result.output_path}[/green]")
        else:
            console.print(f"[red]合成失败: {result.message}[/red]")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]合成失败: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("prompt")
@click.option("--type", "gen_type", type=click.Choice(["image", "video", "audio"]), default="image", help="生成类型")
@click.option("--provider", "-p", default=None, help="指定 AI Provider")
@click.option("--output", "-o", default=None, help="输出路径")
@click.option("--width", default=1024, help="图片宽度")
@click.option("--height", default=1024, help="图片高度")
@click.option("--duration", default=5.0, help="视频时长秒数")
def ai(prompt, gen_type, provider, output, width, height, duration):
    """AI 生成 - 调用 AI 服务生成图片/视频/音频."""
    print_banner()

    try:
        manager = AIGeneratorManager()
        providers = manager.list_providers()

        if not providers:
            console.print("[yellow]未配置任何 AI Provider，请在 .env 中设置 API Key[/yellow]")
            console.print("支持的 Provider: fal (FAL_KEY), openai (OPENAI_API_KEY), elevenlabs (ELEVENLABS_API_KEY)")
            return

        console.print(f"可用 Provider: [bold]{', '.join(providers)}[/bold]")

        request = GenerationRequest(
            prompt=prompt,
            generation_type=GenerationType(gen_type),
            width=width,
            height=height,
            duration=duration,
        )

        result = manager.generate(request, provider=provider)

        if result.success:
            console.print(f"[green]生成完成! 耗时: {result.duration:.1f}s[/green]")
            console.print(f"Provider: [bold]{result.provider}[/bold]")
            console.print(f"输出: {result.output_path}")
        else:
            console.print(f"[red]生成失败: {result.message}[/red]")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]AI 生成失败: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("video_path", type=click.Path(exists=True))
def info(video_path):
    """查看视频基本信息."""
    print_banner()

    try:
        with VideoAnalyzer(video_path) as analyzer:
            meta = analyzer.extract_metadata()

        table = Table(title="视频信息", show_header=True)
        table.add_column("属性", style="cyan")
        table.add_column("值", style="green")
        table.add_row("文件路径", meta.file_path)
        table.add_row("文件大小", f"{meta.file_size / 1024 / 1024:.1f} MB")
        table.add_row("格式", meta.format)
        table.add_row("分辨率", meta.resolution)
        table.add_row("宽高比", meta.aspect_ratio)
        table.add_row("帧率", f"{meta.fps:.2f} fps")
        table.add_row("总帧数", str(meta.total_frames))
        table.add_row("时长", f"{meta.duration:.2f}s")
        table.add_row("视频编码", meta.video_codec)
        table.add_row("视频码率", f"{meta.video_bitrate / 1000:.0f} kbps" if meta.video_bitrate else "N/A")
        table.add_row("音频", "有" if meta.audio.has_audio else "无")
        if meta.audio.has_audio:
            table.add_row("音频编码", meta.audio.codec)
            table.add_row("采样率", f"{meta.audio.sample_rate} Hz")
            table.add_row("声道数", str(meta.audio.channels))
            table.add_row("平均音量", f"{meta.audio.avg_volume:.1f} dB")
        console.print(table)

    except Exception as e:
        console.print(f"[red]获取信息失败: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("video_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--output", "-o", default=None, help="输出目录")
@click.option("--mode", "-m", type=click.Choice(["scenes", "interval"]), default="scenes", help="拆解模式")
def batch_decompose(video_dir, output, mode):
    """批量拆解目录中的所有视频."""
    print_banner()

    video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}
    video_files = [
        f for f in Path(video_dir).iterdir()
        if f.suffix.lower() in video_extensions
    ]

    if not video_files:
        console.print(f"[yellow]目录中未找到视频文件: {video_dir}[/yellow]")
        return

    console.print(f"找到 [bold]{len(video_files)}[/bold] 个视频文件")

    for i, vf in enumerate(video_files, 1):
        console.print(f"\n[bold cyan][{i}/{len(video_files)}] 处理: {vf.name}[/bold cyan]")
        try:
            decomposer = VideoDecomposer(str(vf), output_dir=output)
            if mode == "scenes":
                with VideoAnalyzer(str(vf)) as analyzer:
                    analysis = analyzer.full_analysis()
                result = decomposer.decompose_by_scenes(analysis)
            else:
                result = decomposer.decompose_by_interval()
            console.print(f"  [green]拆解完成: {result.total_segments} 个片段[/green]")
        except Exception as e:
            console.print(f"  [red]拆解失败: {e}[/red]")


@main.command()
@click.option("--video-dir", "-d", default=None, help="测试视频目录")
def test(video_dir):
    """运行端到端测试."""
    print_banner()

    test_dir = video_dir or os.environ.get(
        "TEST_VIDEO_DIR",
        r"\\192.168.88.121\.n8n-files\video_download\video\2026-11-02\20261102",
    )

    if not os.path.exists(test_dir):
        console.print(f"[red]测试目录不存在: {test_dir}[/red]")
        sys.exit(1)

    video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    video_files = [
        f for f in Path(test_dir).rglob("*")
        if f.suffix.lower() in video_extensions
    ][:3]

    if not video_files:
        console.print(f"[red]未找到测试视频: {test_dir}[/red]")
        sys.exit(1)

    console.print(f"使用测试视频: [bold]{video_files[0].name}[/bold]")

    test_video = str(video_files[0])
    output_dir = os.path.join(os.path.dirname(test_video), "test_output")
    os.makedirs(output_dir, exist_ok=True)

    # 阶段 1: 元数据
    console.print("\n[bold cyan]阶段 1: 提取元数据[/bold cyan]")
    try:
        with VideoAnalyzer(test_video) as analyzer:
            meta = analyzer.extract_metadata()
        console.print(f"  [green]PASS[/green] - {meta.resolution}, {meta.duration:.1f}s")
    except Exception as e:
        console.print(f"  [red]FAIL[/red] - {e}")
        sys.exit(1)

    # 阶段 2: 场景检测
    console.print("\n[bold cyan]阶段 2: 场景检测[/bold cyan]")
    try:
        with VideoAnalyzer(test_video) as analyzer:
            scenes = analyzer.detect_scenes()
        console.print(f"  [green]PASS[/green] - {len(scenes)} 个场景")
    except Exception as e:
        console.print(f"  [red]FAIL[/red] - {e}")
        sys.exit(1)

    # 阶段 3: 拆解
    console.print("\n[bold cyan]阶段 3: 视频拆解[/bold cyan]")
    try:
        decomposer = VideoDecomposer(test_video, output_dir=output_dir)
        with VideoAnalyzer(test_video) as analyzer:
            analysis = analyzer.full_analysis()
        result = decomposer.decompose_by_scenes(analysis)
        console.print(f"  [green]PASS[/green] - {result.total_segments} 个片段")
    except Exception as e:
        console.print(f"  [red]FAIL[/red] - {e}")
        sys.exit(1)

    # 阶段 4: 合成
    console.print("\n[bold cyan]阶段 4: 视频合成[/bold cyan]")
    try:
        segment_paths = [s.output_path for s in result.segments if os.path.exists(s.output_path)]
        if len(segment_paths) >= 2:
            config = CompositionConfig(
                output_path=os.path.join(output_dir, "composed.mp4"),
                transition=TransitionType.FADE,
                transition_duration=0.3,
            )
            composer = VideoComposer()
            comp_result = composer.compose(segment_paths[:5], config)
            if comp_result.success:
                console.print(f"  [green]PASS[/green] - {comp_result.output_path}")
            else:
                console.print(f"  [red]FAIL[/red] - {comp_result.message}")
        else:
            console.print(f"  [yellow]SKIP[/green] - 片段不足")
    except Exception as e:
        console.print(f"  [red]FAIL[/red] - {e}")

    console.print("\n[bold green]测试完成![/bold green]")


if __name__ == "__main__":
    main()
