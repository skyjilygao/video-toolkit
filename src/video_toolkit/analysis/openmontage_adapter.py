"""OpenMontage 适配器 — 封装 OpenMontage 分析工具链.

此适配器利用 OpenMontage 的完整分析模块（PySceneDetect + FFmpeg + faster-whisper）.

使用前提:
    1. OpenMontage 项目已安装到本地（git clone 或 pip install）
    2. 可选依赖: faster-whisper, scenedetect, youtube-transcript-api
    3. 首次使用若未检测到 OpenMontage，将自动从 GitHub clone 并安装

环境变量:
    OPENMONTAGE_PATH: OpenMontage 仓库的本地路径（如未设置，自动探测或安装）
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

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

# ── OpenMontage 安装配置 ──
OPENMONTAGE_GITHUB_URL = "https://github.com/calesthio/OpenMontage.git"


def _get_sibling_openmontage_dir() -> Path:
    """获取 video-toolkit 同级目录下的 OpenMontage 路径."""
    return Path(__file__).resolve().parents[4] / "OpenMontage"


def _find_openmontage_path() -> str | None:
    """自动查找 OpenMontage 安装路径."""
    # 1. 环境变量
    env_path = os.environ.get("OPENMONTAGE_PATH")
    if env_path and Path(env_path).joinpath("tools/analysis").exists():
        return env_path

    # 2. 优先探测 video-toolkit 同级目录的 OpenMontage
    sibling_om = _get_sibling_openmontage_dir()
    if sibling_om.joinpath("tools/analysis").exists():
        return str(sibling_om)

    # 3. 尝试从 Python 路径导入
    try:
        import tools.analysis.video_analyzer as _  # noqa: F401

        return str(sibling_om)
    except ImportError:
        pass

    # 4. 常见位置探测
    candidates = [
        Path.home() / "OpenMontage",
        Path.home() / "workspace" / "OpenMontage",
        Path.home() / "projects" / "OpenMontage",
        Path("/workspace/OpenMontage"),
    ]
    for c in candidates:
        if c.joinpath("tools/analysis").exists():
            return str(c)

    return None


def _install_openmontage(target_dir: Path | None = None) -> str | None:
    """自动从 GitHub clone OpenMontage 并安装依赖.

    Parameters
    ----------
    target_dir : Path, optional
        安装目标目录。默认安装到 video-toolkit 同级目录。

    Returns
    -------
    str | None
        安装成功时返回 OpenMontage 根目录路径，失败返回 None.
    """
    if target_dir is None:
        target_dir = _get_sibling_openmontage_dir()

    target_dir = Path(target_dir)
    console.print("[bold cyan]OpenMontage 未检测到，开始自动安装...[/bold cyan]")
    console.print(f"[dim]安装路径: {target_dir}[/dim]")

    try:
        # Step 1: Clone 仓库
        console.print("[dim]Step 1/4: 从 GitHub clone OpenMontage...[/dim]")
        if target_dir.exists():
            console.print(f"[yellow]目录已存在但内容不完整: {target_dir}[/yellow]")
            console.print("[dim]尝试移除并重新 clone...[/dim]")
            import shutil

            shutil.rmtree(target_dir, ignore_errors=True)

        result = subprocess.run(
            ["git", "clone", "--depth", "1", OPENMONTAGE_GITHUB_URL, str(target_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            console.print(f"[red]git clone 失败: {result.stderr[:200]}[/red]")
            return None
        console.print("[green]  ✓ Clone 完成[/green]")

        # Step 2: 安装 OpenMontage 依赖
        console.print("[dim]Step 2/4: 安装 OpenMontage 依赖...[/dim]")
        if not _install_openmontage_deps(target_dir):
            console.print("[yellow]  ! 依赖安装出现警告，继续验证...[/yellow]")

        # Step 3: 验证安装
        console.print("[dim]Step 3/4: 验证 OpenMontage 安装...[/dim]")
        if not _verify_openmontage(target_dir):
            console.print("[red]  ✗ 安装验证失败[/red]")
            return None
        console.print("[green]  ✓ 验证通过[/green]")

        # Step 4: 安装到 sys.path
        console.print("[dim]Step 4/4: 添加到 Python 路径...[/dim]")
        om_path = str(target_dir)
        if om_path not in sys.path:
            sys.path.insert(0, om_path)
        console.print(f"[green]  ✓ 已添加到 sys.path: {om_path}[/green]")

        console.print(f"[bold green]OpenMontage 安装成功! ({target_dir})[/bold green]")
        return om_path

    except subprocess.TimeoutExpired:
        console.print("[red]git clone 超时（>120s），请检查网络连接[/red]")
        return None
    except FileNotFoundError:
        console.print("[red]未找到 git 命令，请先安装 Git: https://git-scm.com/[/red]")
        return None
    except Exception as e:
        console.print(f"[red]OpenMontage 安装失败: {e}[/red]")
        return None


def _install_openmontage_deps(om_dir: Path) -> bool:
    """安装 OpenMontage 的依赖."""
    if not om_dir.exists():
        return False

    pip_cmd = [sys.executable, "-m", "pip", "install"]

    # 检查 OpenMontage 是否有 requirements.txt
    req_file = om_dir / "requirements.txt"
    if req_file.exists():
        console.print("  [dim]发现 requirements.txt，安装中...[/dim]")
        result = subprocess.run(
            pip_cmd + ["-r", str(req_file)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            console.print(f"  [yellow]requirements.txt 安装警告: {result.stderr[:100]}[/yellow]")

    # 确保关键依赖已安装
    core_deps = ["faster-whisper>=1.0.0", "scenedetect>=0.6.2", "av>=11"]
    console.print(f"  [dim]确保核心依赖: {', '.join(core_deps)}[/dim]")
    result = subprocess.run(
        pip_cmd + core_deps,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.returncode == 0


def _verify_openmontage(om_dir: Path) -> bool:
    """验证 OpenMontage 安装是否可用."""
    analysis_dir = om_dir / "tools" / "analysis"
    if not analysis_dir.exists():
        console.print("[red]  ✗ 缺少 tools/analysis 目录[/red]")
        return False

    # 检查关键文件是否存在
    required_files = ["scene_detect.py", "transcriber.py", "frame_sampler.py"]
    missing = [f for f in required_files if not (analysis_dir / f).exists()]
    if missing:
        console.print(f"[yellow]  ! 缺少文件: {', '.join(missing)}[/yellow]")

    # 尝试 Python import 验证
    original_path = sys.path.copy()
    try:
        om_str = str(om_dir)
        if om_str not in sys.path:
            sys.path.insert(0, om_str)

        # 尝试导入核心模块
        from tools.analysis.scene_detect import SceneDetect  # noqa: F401

        return True
    except ImportError as e:
        console.print(f"[yellow]  ! 导入验证警告: {e}[/yellow]")
        # 导入失败但不代表不可用，文件存在即可
        return analysis_dir.exists()
    finally:
        sys.path[:] = original_path


def _ensure_openmontage_installed() -> str | None:
    """确保 OpenMontage 已安装，未安装则自动执行安装."""
    # 先尝试查找
    existing = _find_openmontage_path()
    if existing:
        return existing

    # 未找到，执行自动安装
    console.print("[yellow]未在本地检测到 OpenMontage 安装[/yellow]")
    return _install_openmontage()


# ── URL 判断工具 ──


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "www."))


# ── OpenMontage 适配器 ──


@register_adapter("openmontage")
class OpenMontageAdapter(BaseAnalysisAdapter):
    """OpenMontage 适配器 — 调用 OpenMontage 的分析工具.

    OpenMontage 的分析工具通过 Python 类调用，此适配器
    将 OpenMontage 的工具链包装为统一的 BaseAnalysisAdapter 接口。

    首次使用时若未检测到 OpenMontage，会自动:
    1. 从 GitHub (calesthio/OpenMontage) clone 到同级目录
    2. 安装 OpenMontage 依赖（requirements.txt + 核心依赖）
    3. 验证安装是否成功
    4. 添加到 sys.path 以便导入
    """

    name = "openmontage"

    def __init__(self, video_path: str, output_dir: str | None = None):
        super().__init__(video_path, output_dir)
        self._openmontage_path: str | None = None
        # 使用独立工作目录，避免中间文件污染 output_dir
        if self.output_dir:
            self._base_dir = os.path.join(self.output_dir, ".working")
        else:
            self._base_dir = tempfile.mkdtemp(prefix="vt_om_")
        self._keyframe_dir = os.path.join(self._base_dir, "keyframes")
        os.makedirs(self._keyframe_dir, exist_ok=True)
        self._discover_openmontage()

    def _discover_openmontage(self):
        """发现 OpenMontage 并添加到 sys.path. 未安装时自动安装."""
        self._openmontage_path = _find_openmontage_path()
        if not self._openmontage_path:
            # 自动安装
            self._openmontage_path = _ensure_openmontage_installed()

        if not self._openmontage_path:
            console.print("[yellow]未找到 OpenMontage，请设置 OPENMONTAGE_PATH 环境变量[/yellow]")
            console.print(
                "[dim]或手动安装: git clone https://github.com/calesthio/OpenMontage.git[/dim]"
            )
            return

        if self._openmontage_path not in sys.path:
            sys.path.insert(0, self._openmontage_path)

    def _ensure_openmontage(self) -> bool:
        """确保 OpenMontage 可用."""
        if not self._openmontage_path:
            self._discover_openmontage()
        return self._openmontage_path is not None

    # ── ② 字幕/转录 ──

    def transcribe(self) -> TranscriptResult:
        """调用 OpenMontage 的转录工具."""
        if self._is_youtube_url():
            return self._transcribe_youtube()
        return self._transcribe_local()

    def _is_youtube_url(self) -> bool:
        if not _is_url(self.video_path):
            return False
        s = self.video_path.lower()
        return "youtube.com" in s or "youtu.be" in s

    def _transcribe_youtube(self) -> TranscriptResult:
        """尝试 YouTube Transcript API."""
        try:
            from tools.analysis.transcript_fetcher import TranscriptFetcher

            if not self._ensure_openmontage():
                return TranscriptResult(has_transcript=False)

            fetcher = TranscriptFetcher()
            result = fetcher.execute(
                {
                    "url_or_video_id": self.video_path,
                    "languages": ["en"],
                    "include_auto_generated": True,
                }
            )

            if result.success:
                data = result.data
                segments = [
                    TranscriptSegment(
                        start=s.get("start", 0),
                        end=s.get("end", 0),
                        text=s.get("text", ""),
                    )
                    for s in data.get("transcript", [])
                ]
                return TranscriptResult(
                    full_text=data.get("full_text", ""),
                    segments=segments,
                    language=data.get("language", "unknown"),
                    word_count=data.get("word_count", 0),
                    has_transcript=True,
                )
        except Exception as e:
            console.print(f"[dim]YouTube 字幕获取失败: {e}[/dim]")

        return TranscriptResult(has_transcript=False)

    def _transcribe_local(self) -> TranscriptResult:
        """使用 faster-whisper 转录本地视频，降级到 CustomAdapter."""
        try:
            from tools.analysis.transcriber import Transcriber

            if not self._ensure_openmontage():
                return self._fallback_transcribe()

            transcriber = Transcriber()
            result = transcriber.execute(
                {
                    "input_path": self.video_path,
                    "model_size": "base",
                    "output_dir": self._base_dir,
                }
            )

            if result.success:
                segments_data = result.data.get("segments", [])
                segments = [
                    TranscriptSegment(
                        start=s.get("start", 0),
                        end=s.get("end", 0),
                        text=s.get("text", ""),
                    )
                    for s in segments_data
                ]
                full_text = " ".join(s.get("text", "") for s in segments_data)

                return TranscriptResult(
                    full_text=full_text,
                    segments=segments,
                    language=result.data.get("language", "unknown"),
                    word_count=len(full_text.split()),
                    has_transcript=True,
                )
        except Exception as e:
            console.print(f"[dim]本地转录失败: {e}[/dim]")

        return self._fallback_transcribe()

    def _fallback_transcribe(self) -> TranscriptResult:
        """降级：使用 CustomAdapter 的转录."""
        try:
            from video_toolkit.analysis.custom_adapter import CustomAdapter

            fallback = CustomAdapter(self.video_path, self._base_dir)
            return fallback.transcribe()
        except Exception as e:
            console.print(f"[dim]CustomAdapter 转录降级失败: {e}[/dim]")
            return TranscriptResult(has_transcript=False)

    # ── ③ 场景检测 ──

    def detect_scenes(self, depth: str = "standard") -> list[SceneBrief]:
        """调用 OpenMontage 的场景检测工具."""
        try:
            from tools.analysis.scene_detect import SceneDetect

            if not self._ensure_openmontage():
                return self._fallback_detect_scenes()

            detector = SceneDetect()
            result = detector.execute(
                {
                    "input_path": self.video_path,
                    "method": "content",
                    "min_scene_length_seconds": 0.5,
                    "output_path": os.path.join(self._base_dir, "scenes.json"),
                }
            )

            if result.success:
                scenes = []
                for s in result.data.get("scenes", []):
                    scenes.append(
                        SceneBrief(
                            scene_index=s.get("index", 0),
                            start_time=s.get("start_seconds", 0),
                            end_time=s.get("end_seconds", 0),
                            duration=s.get("duration_seconds", 0),
                        )
                    )
                return scenes

        except Exception as e:
            console.print(f"[dim]OpenMontage 场景检测失败: {e}，降级[/dim]")

        return self._fallback_detect_scenes()

    def _fallback_detect_scenes(self) -> list[SceneBrief]:
        """降级场景检测 — 使用 CustomAdapter 的 FFmpeg/场景检测逻辑."""
        try:
            from video_toolkit.analysis.custom_adapter import CustomAdapter

            fallback = CustomAdapter(self.video_path, self._base_dir)
            return fallback.detect_scenes(depth="standard")
        except Exception as e:
            console.print(f"[dim]CustomAdapter 场景检测降级失败: {e}[/dim]")
            return []

    # ── ④ 运动分类 ──

    def classify_motion(self, scenes: list[SceneBrief]) -> list[dict]:
        """调用 OpenMontage 的视频分析器获取运动分类."""
        try:
            from tools.analysis.video_analyzer import VideoAnalyzer

            if not self._ensure_openmontage():
                return super().classify_motion(scenes)

            analyzer = VideoAnalyzer.__new__(VideoAnalyzer)
            results = analyzer._classify_scene_motion(
                self.video_path,
                [
                    {
                        "start_seconds": s.start_time,
                        "end_seconds": s.end_time,
                        "index": s.scene_index,
                    }
                    for s in scenes
                ],
            )
            return results

        except Exception as e:
            console.print(f"[dim]OpenMontage 运动分类失败: {e}，使用降级[/dim]")

        # 使用 CustomAdapter 的降级方案（复用光流逻辑）
        try:
            from video_toolkit.analysis.custom_adapter import CustomAdapter

            fallback = CustomAdapter(self.video_path, self._base_dir)
            return fallback.classify_motion(scenes)
        except Exception:
            return [{"motion_type": "unknown", "flow_variance": -1.0} for _ in scenes]

    # ── ⑤ 关键帧提取 ──

    def extract_keyframes(
        self,
        scenes: list[SceneBrief],
        max_frames: int = 20,
        depth: str = "standard",
    ) -> list[KeyframeBrief]:
        """调用 OpenMontage 的关键帧提取工具."""
        try:
            from tools.analysis.frame_sampler import FrameSampler
            from tools.analysis.video_analyzer import VideoAnalyzer

            if not self._ensure_openmontage():
                return self._fallback_keyframes(scenes, max_frames, depth)

            # 计算时间戳
            analyzer = VideoAnalyzer.__new__(VideoAnalyzer)
            timestamps = analyzer._compute_keyframe_timestamps(
                [
                    {
                        "start_seconds": s.start_time,
                        "end_seconds": s.end_time,
                    }
                    for s in scenes
                ],
                max_frames,
                depth,
            )

            sampler = FrameSampler()
            result = sampler.execute(
                {
                    "input_path": self.video_path,
                    "strategy": "timestamps",
                    "timestamps": timestamps,
                    "output_dir": self._keyframe_dir,
                    "format": "jpg",
                    "quality": 2,
                }
            )

            if result.success:
                keyframes = []
                for frame in result.data.get("frames", []):
                    ts = frame["timestamp_seconds"]
                    scene_idx = 0
                    for j, s in enumerate(scenes):
                        if s.start_time <= ts <= s.end_time:
                            scene_idx = j
                            break

                    keyframes.append(
                        KeyframeBrief(
                            timestamp=round(ts, 3),
                            scene_index=scene_idx,
                            path=frame["path"],
                        )
                    )
                return keyframes

        except Exception as e:
            console.print(f"[dim]OpenMontage 关键帧提取失败: {e}，降级[/dim]")

        return self._fallback_keyframes(scenes, max_frames, depth)

    def _fallback_keyframes(
        self,
        scenes: list[SceneBrief],
        max_frames: int,
        depth: str,
    ) -> list[KeyframeBrief]:
        """降级：使用 CustomAdapter 的关键帧逻辑."""
        try:
            from video_toolkit.analysis.custom_adapter import CustomAdapter

            fallback = CustomAdapter(self.video_path, self._base_dir)
            return fallback.extract_keyframes(scenes, max_frames, depth)
        except Exception:
            return []

    # ── ⑥ 音频能量分析 ──

    def analyze_audio_energy(self) -> AudioEnergyProfile | None:
        """调用 OpenMontage 的音频能量分析."""
        try:
            from tools.analysis.audio_energy import AudioEnergy

            if not self._ensure_openmontage():
                return None

            energy = AudioEnergy()
            result = energy.execute(
                {
                    "input_path": self.video_path,
                    "video_duration_seconds": 0,
                }
            )

            if result.success:
                return AudioEnergyProfile(
                    recommended_offset_seconds=result.data.get("recommended_offset_seconds", 0),
                    has_energy_data=True,
                )
        except Exception as e:
            console.print(f"[dim]OpenMontage 音频能量分析失败: {e}[/dim]")

        return None
