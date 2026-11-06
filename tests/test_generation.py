"""视频 AI 再生模块单元测试.

测试内容：
1. 数据模型验证
2. PromptEngine 5层提示词生成
3. GenerationManager 适配器注册
4. CustomGenerationAdapter 接口验证

运行方式：
    cd video-toolkit
    python -m pytest tests/test_generation.py -v
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── Fixtures ──

def make_mock_brief(tmp_path):
    """创建用于测试的 mock AnalysisBrief."""
    from video_toolkit.models.analysis import (
        AnalysisBrief,
        SceneBrief,
        StyleProfile,
        PacingProfile,
        TranscriptResult,
    )

    scenes = [
        SceneBrief(
            scene_index=0,
            start_time=0.0,
            end_time=5.0,
            duration=5.0,
            motion_type="static_image",
            visual_type="landscape",
            energy_level="low",
            description="A serene mountain landscape at dawn",
            narration_text="清晨的山谷宁静而美丽",
            transcript_text="清晨的山谷宁静而美丽",
        ),
        SceneBrief(
            scene_index=1,
            start_time=5.0,
            end_time=12.0,
            duration=7.0,
            motion_type="motion_clip",
            visual_type="portrait",
            energy_level="high",
            description="A person running through a busy city street",
            narration_text="繁忙都市中奔跑的身影",
        ),
        SceneBrief(
            scene_index=2,
            start_time=12.0,
            end_time=15.0,
            duration=3.0,
            motion_type="animated_still",
            visual_type="other",
            energy_level="medium",
            description="An animated infographic showing data trends",
            narration_text="数据趋势图表动画",
        ),
    ]

    video_path = os.path.join(tmp_path, "test.mp4") if isinstance(tmp_path, str) else str(tmp_path / "test.mp4")
    return AnalysisBrief(
        video_path=video_path,
        duration_seconds=15.0,
        total_scenes=3,
        scenes=scenes,
        keyframes=[],
        transcript=TranscriptResult(
            full_text="清晨的山谷宁静而美丽 繁忙都市中奔跑的身影 数据趋势图表动画",
            language="zh",
            word_count=30,
            has_transcript=True,
        ),
        pacing=PacingProfile(
            pacing_style="variable",
            avg_scene_duration_seconds=5.0,
            cuts_per_minute=12,
        ),
        style_profile=StyleProfile(
            brightness_level="medium",
            contrast_level="medium",
            saturation_level="medium",
            dominant_colors=["#87CEEB", "#228B22"],
            color_palette={
                "primary_colors": [{"hex": "#87CEEB"}, {"hex": "#228B22"}],
                "overall_mood": "serene",
            },
        ),
    )


def make_mock_analysis_json(brief, tmp_path):
    """保存为 JSON 文件供测试使用."""
    json_path = tmp_path / "analysis.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(brief.model_dump(), f, ensure_ascii=False, indent=2, default=str)
    return str(json_path)


# ── 测试 1: PromptEngine ──

class TestPromptEngine:
    def test_build_scene_prompt_full(self):
        """测试完整5层提示词生成."""
        from video_toolkit.generation.prompt_engine import PromptEngine
        from video_toolkit.models.analysis import SceneBrief, StyleProfile

        engine = PromptEngine(
            style_profile=StyleProfile(
                color_palette={"overall_mood": "dramatic"}
            ),
            style_prefix="epic cinematic",
            style_suffix="high quality, 8K",
        )

        scene = SceneBrief(
            scene_index=0,
            description="A castle on a hill at sunset",
            motion_type="static_image",
            visual_type="landscape",
            energy_level="low",
        )

        prompt = engine.build_scene_prompt(scene, layer_mode="full")
        assert isinstance(prompt, str)
        assert len(prompt) > 20
        # 应该包含主体描述
        assert "castle" in prompt or "hill" in prompt or "sunset" in prompt
        # 应该包含风格后缀
        assert "high quality" in prompt.lower() or "8k" in prompt.lower()
        print(f"  Full prompt: {prompt}")

    def test_build_scene_prompt_minimal(self):
        """测试最小模式提示词."""
        from video_toolkit.generation.prompt_engine import PromptEngine
        from video_toolkit.models.analysis import SceneBrief

        engine = PromptEngine(style_suffix="high quality")
        scene = SceneBrief(
            scene_index=0,
            description="Simple test description",
        )

        prompt = engine.build_scene_prompt(scene, layer_mode="minimal")
        assert "Simple test description" in prompt
        assert "high quality" in prompt

    def test_build_all_prompts(self):
        """测试批量生成提示词."""
        from video_toolkit.generation.prompt_engine import PromptEngine
        from video_toolkit.models.analysis import SceneBrief

        engine = PromptEngine()
        scenes = [
            SceneBrief(scene_index=0, description="Scene one", narration_text="Narration one"),
            SceneBrief(scene_index=1, description="Scene two", narration_text="Narration two"),
        ]

        results = engine.build_all_prompts(scenes)
        assert len(results) == 2
        assert results[0]["scene_index"] == 0
        assert "Scene one" in results[0]["prompt"]
        assert results[1]["narration_text"] == "Narration two"

    def test_narration_script(self):
        """测试旁白脚本生成."""
        from video_toolkit.generation.prompt_engine import PromptEngine
        from video_toolkit.models.analysis import (
            AnalysisBrief,
            SceneBrief,
            TranscriptResult,
        )

        brief = AnalysisBrief(
            transcript=TranscriptResult(
                full_text="This is the full transcript",
                has_transcript=True,
            ),
        )
        engine = PromptEngine()
        script = engine.build_narration_script([], brief)
        assert script == "This is the full transcript"

    def test_moderate_prompt_content(self):
        """验证提示词包含 5 层元素."""
        from video_toolkit.generation.prompt_engine import PromptEngine
        from video_toolkit.models.analysis import SceneBrief

        engine = PromptEngine(
            style_prefix="cinematic",
            style_suffix="professional",
        )

        scene = SceneBrief(
            scene_index=0,
            description="A bird flying over the ocean",
            motion_type="motion_clip",
            visual_type="landscape",
            energy_level="high",
        )

        prompt = engine.build_scene_prompt(scene, layer_mode="full")
        # 检查基础结构
        assert "bird" in prompt.lower() or "ocean" in prompt.lower()
        assert "cinematic" in prompt or "professional" in prompt


# ── 测试 2: 数据模型 ──

class TestModels:
    def test_regeneration_config_defaults(self):
        from video_toolkit.models.analysis import RegenerationConfig

        cfg = RegenerationConfig()
        assert cfg.generation_mode == "video_first"
        assert cfg.output_width == 1920
        assert cfg.scene_selection == "all"

    def test_scene_generation_task(self):
        from video_toolkit.models.analysis import SceneGenerationTask

        task = SceneGenerationTask(
            scene_index=0,
            prompt="test prompt",
            narration_text="test narration",
            duration=5.0,
        )
        assert task.status == "pending"
        assert task.generation_type == "video"

    def test_scene_task_full_state(self):
        from video_toolkit.models.analysis import SceneGenerationTask

        task = SceneGenerationTask(
            scene_index=1,
            prompt="A sunny beach",
            output_path="/tmp/gen_0001.mp4",
            status="done",
        )
        assert task.status == "done"
        assert "sunny" in task.prompt.lower()


# ── 测试 3: GenerationManager ──

class TestGenerationManager:
    def test_list_adapters(self):
        from video_toolkit.generation.manager import GenerationManager

        mgr = GenerationManager()
        adapters = mgr.list_adapters()
        assert "custom" in adapters
        # openmontage 可能未安装

    def test_get_adapter(self):
        from video_toolkit.generation.manager import GenerationManager
        from video_toolkit.generation.custom_adapter import CustomGenerationAdapter

        mgr = GenerationManager()
        tmp = tempfile.mkdtemp()
        brief = make_mock_brief(tmp)
        adapter = mgr.get_adapter("custom", "/fake/path.mp4", brief)
        assert adapter.name == "custom"
        assert isinstance(adapter, CustomGenerationAdapter)

    def test_unknown_adapter_raises(self):
        from video_toolkit.generation.manager import GenerationManager

        mgr = GenerationManager()
        tmp = tempfile.mkdtemp()
        brief = make_mock_brief(tmp)
        with pytest.raises(ValueError, match="未知的视频生成适配器"):
            mgr.get_adapter("nonexistent", "/fake", brief)


# ── 测试 4: CustomGenerationAdapter ──

class TestCustomGenerationAdapter:
    def test_init(self):
        from video_toolkit.generation.custom_adapter import CustomGenerationAdapter

        tmp = tempfile.mkdtemp()
        brief = make_mock_brief(tmp)
        adapter = CustomGenerationAdapter("/fake/video.mp4", brief)
        assert adapter.name == "custom"
        assert adapter.video_path == "/fake/video.mp4"

    def test_filter_scenes_all(self):
        from video_toolkit.generation.custom_adapter import CustomGenerationAdapter
        from video_toolkit.models.analysis import RegenerationConfig

        tmp = tempfile.mkdtemp()
        brief = make_mock_brief(tmp)
        adapter = CustomGenerationAdapter("/fake/video.mp4", brief)

        config = RegenerationConfig(scene_selection="all")
        indices = adapter._filter_scenes(config)
        assert indices == [0, 1, 2]

    def test_filter_scenes_first_n(self):
        from video_toolkit.generation.custom_adapter import CustomGenerationAdapter
        from video_toolkit.models.analysis import RegenerationConfig

        tmp = tempfile.mkdtemp()
        brief = make_mock_brief(tmp)
        adapter = CustomGenerationAdapter("/fake/video.mp4", brief)

        config = RegenerationConfig(scene_selection="first_n", scene_count=2)
        indices = adapter._filter_scenes(config)
        assert indices == [0, 1]

    def test_filter_scenes_indices(self):
        from video_toolkit.generation.custom_adapter import CustomGenerationAdapter
        from video_toolkit.models.analysis import RegenerationConfig

        tmp = tempfile.mkdtemp()
        brief = make_mock_brief(tmp)
        adapter = CustomGenerationAdapter("/fake/video.mp4", brief)

        config = RegenerationConfig(
            scene_selection="indices",
            scene_indices=[0, 2],
        )
        indices = adapter._filter_scenes(config)
        assert indices == [0, 2]

    def test_estimate_cost(self):
        from video_toolkit.generation.custom_adapter import CustomGenerationAdapter
        from video_toolkit.models.analysis import RegenerationConfig

        tmp = tempfile.mkdtemp()
        brief = make_mock_brief(tmp)
        adapter = CustomGenerationAdapter("/fake/video.mp4", brief)

        config = RegenerationConfig()
        cost = adapter.estimate_cost(config, 5)
        assert cost > 0


# ── 测试 5: CLI 辅助函数 ──

class TestCLIHelpers:
    def test_derive_style_prefix(self):
        """测试风格前缀推导."""
        from video_toolkit.cli import _derive_style_prefix
        from video_toolkit.models.analysis import (
            AnalysisBrief,
            StyleProfile,
            PacingProfile,
        )

        brief = AnalysisBrief(
            style_profile=StyleProfile(
                color_palette={"overall_mood": "dramatic"}
            ),
            pacing=PacingProfile(pacing_style="dynamic_social"),
        )
        prefix = _derive_style_prefix(brief)
        assert "dramatic" in prefix
        assert "high energy" in prefix

    def test_derive_style_prefix_empty(self):
        from video_toolkit.cli import _derive_style_prefix
        from video_toolkit.models.analysis import AnalysisBrief

        prefix = _derive_style_prefix(AnalysisBrief())
        assert prefix == ""


# ── 入口点 ──

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
