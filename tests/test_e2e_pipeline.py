"""端到端全流程测试 — 从合成视频输入到 AI 再生视频输出.

测试策略:
1. 使用 FFmpeg 合成测试视频（无需外部文件）
2. Mock AI 生成器（不发起真实 API 请求）
3. 覆盖完整链路：分析 → 拆解 → AI生成 → 拼接

运行方式:
    cd video-toolkit
    python -m pytest tests/test_e2e_pipeline.py -v --tb=short

    # 或者使用一键脚本:
    python run_e2e_test.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

import pytest

# 使用绝对导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tests.fixtures.mock_ai_generator import (
    MockImageGenerator,
    MockSeedanceGenerator,
)
from tests.fixtures.mock_video import (
    generate_test_video,
    get_temp_dir,
)

# ── Fixtures ──


@pytest.fixture(scope="module")
def test_env():
    """创建模块级测试环境."""
    tmp_dir = get_temp_dir(prefix="vt_e2e_module_")

    # 1. 创建合成测试视频
    video_path = os.path.join(tmp_dir, "input_video.mp4")
    generate_test_video(
        video_path,
        duration=12.0,
        width=640,
        height=360,
        fps=24,
        with_audio=True,
        scene_changes=[3.0, 6.0, 9.0],  # 4个场景
    )

    # 2. 创建输出目录
    output_dir = os.path.join(tmp_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    env = {
        "tmp_dir": tmp_dir,
        "video_path": video_path,
        "output_dir": output_dir,
        "analysis_json": os.path.join(output_dir, "analysis.json"),
        "regenerated_video": os.path.join(output_dir, "regenerated.mp4"),
    }

    yield env

    # 清理
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def ai_manager_with_mock():
    """创建带有 Mock AI 生成器的 AIGeneratorManager."""
    from video_toolkit.ai.manager import AIGeneratorManager

    manager = AIGeneratorManager()
    # 清除默认注册的 provider
    manager._generators = {}

    # 注册 Mock 生成器
    mock_dir = tempfile.mkdtemp(prefix="vt_mock_ai_global_")
    manager.register("seedance", MockSeedanceGenerator(output_dir=mock_dir))
    manager.register("mock_video", MockImageGenerator(output_dir=mock_dir))

    return manager


@pytest.fixture
def analysis_brief(test_env):
    """生成 AnalysisBrief（使用 custom 适配器真实分析）."""
    from video_toolkit.analysis.custom_adapter import CustomAdapter

    adapter = CustomAdapter(test_env["video_path"])
    brief = adapter.analyze(
        depth="standard",
        max_keyframes=10,
        extract_transcript=False,  # 跳过 Whisper 转录加速测试
        extract_audio_energy=False,  # 跳过音频能量分析加速测试
        extract_keyframes=True,
    )
    return brief


# ── 阶段 1: 测试视频生成 ──


class TestStage1VideoGeneration:
    """验证测试视频正确生成."""

    def test_video_file_exists(self, test_env):
        """测试视频文件是否存在."""
        assert os.path.isfile(test_env["video_path"])

    def test_video_is_valid_mp4(self, test_env):
        """验证是有效的 MP4 文件."""
        from video_toolkit.utils.ffprobe_utils import get_video_info

        info = get_video_info(test_env["video_path"])
        assert info["width"] == 640
        assert info["height"] == 360
        assert info["duration"] > 10  # 约 12 秒
        assert info["fps"] > 0
        print(f"  Video info: {info}")

    def test_video_has_audio(self, test_env):
        """验证有音频轨道."""
        from video_toolkit.utils.ffprobe_utils import get_video_info

        info = get_video_info(test_env["video_path"])
        assert info["has_audio"] is True

    def test_video_reasonable_size(self, test_env):
        """文件大小合理（非空）."""
        size = os.path.getsize(test_env["video_path"])
        assert size > 10000, f"文件太小: {size} bytes"


# ── 阶段 2: 视频分析 ──


class TestStage2VideoAnalysis:
    """验证分析模块正确工作."""

    def test_analysis_produces_brief(self, analysis_brief):
        """分析能产出 AnalysisBrief."""
        assert analysis_brief is not None
        assert analysis_brief.video_path != ""

    def test_analysis_detects_scenes(self, analysis_brief):
        """检测到场景."""
        assert (
            len(analysis_brief.scenes) >= 3
        ), f"期望至少3个场景，实际: {len(analysis_brief.scenes)}"
        print(f"  Detected {len(analysis_brief.scenes)} scenes")

    def test_scenes_have_valid_time_ranges(self, analysis_brief):
        """场景时间范围有效."""
        for scene in analysis_brief.scenes:
            assert scene.start_time < scene.end_time
            assert scene.duration > 0
            assert scene.scene_index >= 0

    def test_scenes_have_camera_language_fields(self, analysis_brief):
        """场景包含镜头语言字段."""
        for scene in analysis_brief.scenes:
            # 这些字段应该有默认值或推导值
            assert scene.camera_angle in ("close_up", "medium", "wide")
            assert scene.camera_movement in (
                "static",
                "pan_left",
                "dolly_in",
                "pan_right",
                "tilt_up",
                "tilt_down",
            )

    def test_analysis_keyframes_extracted(self, analysis_brief):
        """关键帧提取."""
        assert len(analysis_brief.keyframes) > 0
        for kf in analysis_brief.keyframes:
            assert os.path.isfile(kf.path), f"关键帧文件不存在: {kf.path}"

    def test_analysis_json_serializable(self, analysis_brief, test_env):
        """分析结果可序列化为 JSON."""
        data = analysis_brief.model_dump()
        json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        assert len(json_str) > 100

        # 保存到文件供后续步骤使用
        with open(test_env["analysis_json"], "w", encoding="utf-8") as f:
            f.write(json_str)

        assert os.path.isfile(test_env["analysis_json"])

    def test_analysis_json_roundtrip(self, test_env):
        """JSON 反序列化验证."""
        from video_toolkit.models.analysis import AnalysisBrief

        with open(test_env["analysis_json"], encoding="utf-8") as f:
            data = json.load(f)

        brief = AnalysisBrief.model_validate(data)
        assert brief.total_scenes == len(brief.scenes)


# ── 阶段 3: 视频拆解 ──


class TestStage3VideoDecomposition:
    """验证拆解模块正确工作."""

    def test_decomposition_creates_segments(self, analysis_brief, test_env):
        """拆解产生片段文件."""
        from video_toolkit.decomposition.decomposer import VideoDecomposer
        from video_toolkit.models.analysis import SceneInfo, VideoAnalysisResult

        # 构建 VideoAnalysisResult（兼容 decomposer 的接口）
        video_analysis = VideoAnalysisResult(
            scenes=[
                SceneInfo(
                    scene_id=s.scene_index,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    duration=s.duration,
                    start_frame=int(s.start_time * 24),
                    end_frame=int(s.end_time * 24),
                    brightness=128.0,
                    motion_level=0.5,
                    is_static=(s.motion_type == "static_image"),
                    dominant_colors=[],
                )
                for s in analysis_brief.scenes
            ],
        )
        # 设置 metadata
        from video_toolkit.models.video import VideoMetadata

        video_analysis.metadata = VideoMetadata(
            file_path=test_env["video_path"],
            duration=analysis_brief.duration_seconds,
            width=640,
            height=360,
            fps=24.0,
            total_frames=int(analysis_brief.duration_seconds * 24),
        )

        decomposer = VideoDecomposer(
            test_env["video_path"],
            output_dir=os.path.join(test_env["output_dir"], "decomposed"),
        )
        result = decomposer.decompose_by_scenes(video_analysis)

        assert result.total_segments > 0
        # 验证第一个和最后一个片段存在
        assert os.path.isfile(result.segments[0].output_path)

        # 保存结果供后续使用
        test_env["decomposition_result"] = result
        print(f"  Decomposed into {result.total_segments} segments")

    def test_decomposition_index_saved(self, test_env):
        """拆解索引文件保存."""
        decomp_dir = os.path.join(test_env["output_dir"], "decomposed")
        index_path = os.path.join(decomp_dir, "decomposition_index.json")
        assert os.path.isfile(index_path)

        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        assert index["total_segments"] > 0
        assert len(index["segments"]) > 0


# ── 阶段 4: AI Mock 生成 ──


class TestStage4MockAIGeneration:
    """验证 Mock AI 生成器正确工作."""

    def test_mock_seedance_video_generation(self):
        """Mock Seedance 能生成视频文件."""
        from video_toolkit.ai.base import GenerationRequest, GenerationType

        mock = MockSeedanceGenerator(api_key="test_key")
        request = GenerationRequest(
            prompt="A beautiful mountain landscape",
            generation_type=GenerationType.VIDEO,
            duration=3.0,
            width=640,
            height=360,
        )

        result = mock.generate(request)
        assert result.success is True, f"生成失败: {result.message}"
        assert os.path.isfile(result.output_path)
        assert result.output_path.endswith(".mp4")

        # 验证生成的文件是有效视频
        from video_toolkit.utils.ffprobe_utils import get_video_info

        info = get_video_info(result.output_path)
        assert info["width"] == 640
        assert info["height"] == 360
        print(f"  Mock video: {result.output_path} ({info})")

    def test_mock_image_generation(self):
        """Mock 图片生成."""
        from video_toolkit.ai.base import GenerationRequest, GenerationType

        mock = MockImageGenerator(api_key="test_key")
        request = GenerationRequest(
            prompt="A sunset over the ocean",
            generation_type=GenerationType.IMAGE,
            width=512,
            height=512,
        )

        result = mock.generate(request)
        assert result.success is True
        assert os.path.isfile(result.output_path)
        assert result.output_path.endswith(".png")

    def test_mock_provider_registration(self, ai_manager_with_mock):
        """Mock Provider 注册正确."""
        providers = ai_manager_with_mock.list_providers()
        assert "seedance" in providers
        assert "mock_video" in providers

    def test_mock_manager_auto_select(self, ai_manager_with_mock):
        """自动选择 Provider."""
        from video_toolkit.ai.base import GenerationRequest, GenerationType

        request = GenerationRequest(
            prompt="Test auto select",
            generation_type=GenerationType.VIDEO,
            width=640,
            height=360,
        )

        result = ai_manager_with_mock.generate(request)
        assert result.success is True


# ── 阶段 5: 完整再生流水线 ──


class TestStage5FullRegenerationPipeline:
    """端到端再生流水线测试."""

    def test_regeneration_with_mock_ai(self, test_env, analysis_brief, ai_manager_with_mock):
        """使用 Mock AI 执行完整的视频再生."""
        from video_toolkit.generation.custom_adapter import CustomGenerationAdapter
        from video_toolkit.models.analysis import RegenerationConfig

        # 1. 构建配置
        config = RegenerationConfig(
            output_path=test_env["regenerated_video"],
            output_width=640,
            output_height=360,
            output_fps=24.0,
            generation_mode="video_first",
            preferred_provider="seedance",
            max_clip_duration=3.0,
            scene_selection="first_n",
            scene_count=3,  # 只生成前3个场景加速测试
            audio_mode="mute",  # 跳过 TTS 加速测试
            transition="fade",
            transition_duration=0.3,
            quality="low",  # 低质量加快速度
            burn_subtitles=False,
            max_retries=1,
            keep_segments=True,  # 保留中间文件供检查
            keep_prompts=True,
        )

        # 2. 创建生成适配器
        adapter = CustomGenerationAdapter(
            video_path=test_env["video_path"],
            brief=analysis_brief,
            work_dir=os.path.join(test_env["output_dir"], "regen_work"),
        )

        # 3. 注入 Mock AI Manager
        adapter._ai_manager = ai_manager_with_mock

        # 4. 执行再生
        result = adapter.regenerate(config)

        # 5. 验证结果
        print(f"  Regeneration result: success={result.success}, message={result.message}")
        if not result.success:
            print(f"  Failed scenes: {result.failed_scenes}")
            print(f"  Tasks: {[(t.scene_index, t.status, t.prompt[:80]) for t in result.tasks]}")

        assert result.success is True, f"再生失败: {result.message}"
        assert os.path.isfile(test_env["regenerated_video"]), "输出视频文件不存在"

    def test_output_video_is_valid(self, test_env):
        """输出视频是有效 MP4."""
        from video_toolkit.utils.ffprobe_utils import get_video_info

        info = get_video_info(test_env["regenerated_video"])
        assert info["width"] == 640
        assert info["height"] == 360
        assert info["duration"] > 0
        assert info["fps"] > 0
        print(f"  Output video: {info}")

    def test_output_video_has_multiple_scenes(self, test_env):
        """输出视频包含多个场景（时长 = 3个场景 x ~3秒 ≈ 9秒）."""
        from video_toolkit.utils.ffprobe_utils import get_video_info

        info = get_video_info(test_env["regenerated_video"])
        # 3个场景，每个约3秒 + 转场重叠
        assert info["duration"] >= 5.0, f"视频太短 ({info['duration']:.1f}s)，可能只生成了1个场景"

    def test_prompts_saved(self, test_env):
        """Prompts 文本文件保存."""
        prompts_file = os.path.join(test_env["output_dir"], "generation_prompts.txt")
        assert os.path.isfile(prompts_file), "prompts 文件未生成"

        with open(prompts_file, encoding="utf-8") as f:
            content = f.read()
        assert "Scene" in content
        assert "Mock" in content or "mock" in content.lower() or len(content) > 50


# ── 阶段 6: 模型配置驱动测试 ──


class TestStage6ConfigDriven:
    """验证配置驱动的 Provider 注册."""

    def test_model_config_loading(self):
        """模型配置文件加载."""
        from video_toolkit.config import config

        model_config = config.get_model_config()
        assert model_config is not None
        assert "config" in model_config

    def test_video_models_query(self):
        """视频模型查询."""
        from video_toolkit.config import config

        models = config.get_video_models()
        assert isinstance(models, list)
        # 至少有空列表或配置的模型
        print(f"  Video models: {len(models)}")

    def test_image_models_query(self):
        """图片模型查询."""
        from video_toolkit.config import config

        models = config.get_image_models()
        assert isinstance(models, list)

    def test_model_by_id_lookup(self):
        """模型 ID 反向查找."""
        from video_toolkit.config import config

        # 测试从 model_providers.yml 中的模型
        model_config = config.get_model_config()
        providers = model_config.get("config", {}).get("providers", {})

        for _, provider_conf in providers.items():
            for model in provider_conf.get("models", []):
                model_id = model["id"]
                found = config.get_model_by_id(model_id)
                # 即使没有 API key，配置也应可被查询
                if any(
                    op in model.get("supports", [])
                    for op in ["text_to_video", "text_to_image", "text_to_speech"]
                ):
                    assert found is not None, f"模型 {model_id} 应该能被查到"


# ── 阶段 7: 错误处理和边界条件 ──


class TestStage7EdgeCases:
    """边界条件和错误处理."""

    def test_empty_scenes_handling(self):
        """空场景列表处理."""
        from video_toolkit.generation.custom_adapter import CustomGenerationAdapter
        from video_toolkit.models.analysis import AnalysisBrief, RegenerationConfig

        # 创建一个空场景的 brief
        brief = AnalysisBrief(
            video_path="/fake.mp4",
            duration_seconds=10.0,
            total_scenes=0,
            scenes=[],
        )

        adapter = CustomGenerationAdapter("/fake.mp4", brief)
        config = RegenerationConfig(
            output_path="/tmp/test_output.mp4",
            scene_selection="all",
        )

        # 筛选场景应该返回空列表
        indices = adapter._filter_scenes(config)
        assert indices == []

    def test_single_scene_regeneration(self, test_env, ai_manager_with_mock):
        """单场景再生."""
        from video_toolkit.generation.custom_adapter import CustomGenerationAdapter
        from video_toolkit.models.analysis import (
            AnalysisBrief,
            RegenerationConfig,
            SceneBrief,
        )

        # 创建只有1个场景的 brief
        brief = AnalysisBrief(
            video_path=test_env["video_path"],
            duration_seconds=5.0,
            total_scenes=1,
            scenes=[
                SceneBrief(
                    scene_index=0,
                    start_time=0.0,
                    end_time=5.0,
                    duration=5.0,
                    motion_type="static_image",
                    description="A simple test scene",
                    narration_text="Test narration",
                ),
            ],
        )

        work_dir = os.path.join(test_env["output_dir"], "regen_single")
        adapter = CustomGenerationAdapter(test_env["video_path"], brief, work_dir)
        adapter._ai_manager = ai_manager_with_mock

        config = RegenerationConfig(
            output_path=os.path.join(test_env["output_dir"], "single_scene.mp4"),
            output_width=640,
            output_height=360,
            output_fps=24.0,
            scene_selection="all",
            audio_mode="mute",
            quality="low",
            keep_segments=False,
            keep_prompts=True,
        )

        result = adapter.regenerate(config)
        assert result.success is True, f"单场景再生失败: {result.message}"
        assert os.path.isfile(os.path.join(test_env["output_dir"], "single_scene.mp4"))

    def test_dry_run_mode(self, test_env, analysis_brief):
        """Dry-run 模式不实际生成."""
        from video_toolkit.generation.custom_adapter import CustomGenerationAdapter
        from video_toolkit.models.analysis import RegenerationConfig

        adapter = CustomGenerationAdapter(
            test_env["video_path"],
            analysis_brief,
            work_dir=os.path.join(test_env["output_dir"], "dry_run_work"),
        )

        config = RegenerationConfig(
            output_path=os.path.join(test_env["output_dir"], "dry_run_output.mp4"),
            scene_selection="first_n",
            scene_count=2,
            audio_mode="mute",
        )

        # dry-run 模式下 _filter_scenes 应该正常工作
        indices = adapter._filter_scenes(config)
        assert len(indices) == 2

        # estimate_cost 应该返回合理值
        cost = adapter.estimate_cost(config, 2)
        assert cost > 0

    def test_compose_empty_segments(self):
        """空片段列表合成."""
        from video_toolkit.composition.composer import VideoComposer
        from video_toolkit.models.composition import CompositionConfig

        composer = VideoComposer()
        config = CompositionConfig(output_path="/tmp/empty_compose.mp4")

        result = composer.compose([], config)
        assert result.success is False
        assert "至少" in result.message or "1" in result.message


# ── 便捷的全流程运行入口 ──


def test_full_pipeline_summary(test_env, analysis_brief):
    """打印全流程测试摘要.\n\n    此测试总是通过，用于汇总之前所有阶段的测试结果.\n"""
    print("\n" + "=" * 70)
    print("  端到端全流程测试摘要")
    print("=" * 70)
    print(f"  输入视频: {test_env['video_path']}")
    print(f"  视频大小: {os.path.getsize(test_env['video_path']) / 1024:.1f} KB")
    print(f"  分析场景数: {len(analysis_brief.scenes)}")
    print(f"  分析关键帧数: {len(analysis_brief.keyframes)}")
    print(f"  分析 JSON: {test_env['analysis_json']}")
    print(f"  再生输出: {test_env['regenerated_video']}")

    if os.path.isfile(test_env["regenerated_video"]):
        from video_toolkit.utils.ffprobe_utils import get_video_info

        info = get_video_info(test_env["regenerated_video"])
        print(f"  输出视频时长: {info['duration']:.1f}s")
        print(f"  输出视频分辨率: {info['width']}x{info['height']}")
    else:
        print("  输出视频: 未生成（之前的阶段可能失败）")

    print("=" * 70)
    assert True  # 这个测试总是通过
