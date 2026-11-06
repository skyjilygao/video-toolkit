"""测试 AI 管理器."""

from video_toolkit.ai.base import (
    BaseAIGenerator,
    GenerationRequest,
    GenerationResult,
    GenerationType,
)
from video_toolkit.ai.manager import AIGeneratorManager


class TestAIGeneratorManager:
    """测试 AI 生成器管理器."""

    def test_create_manager(self):
        manager = AIGeneratorManager()
        assert manager is not None

    def test_list_providers_empty_by_default(self):
        manager = AIGeneratorManager()
        # 没有 API key 时应该为空或极少
        providers = manager.list_providers()
        assert isinstance(providers, list)

    def test_generate_without_provider(self):
        manager = AIGeneratorManager()
        request = GenerationRequest(
            prompt="test",
            generation_type=GenerationType.IMAGE,
        )
        result = manager.generate(request)
        assert result.success is False
        assert "Provider" in result.message or "provider" in result.message.lower()

    def test_generate_with_invalid_provider(self):
        manager = AIGeneratorManager()
        request = GenerationRequest(
            prompt="test",
            generation_type=GenerationType.IMAGE,
        )
        result = manager.generate(request, provider="nonexistent")
        assert result.success is False
        assert "nonexistent" in result.message

    def test_register_custom_generator(self):
        class DummyGenerator(BaseAIGenerator):
            @property
            def provider_name(self):
                return "dummy"

            @property
            def supported_types(self):
                return [GenerationType.IMAGE]

            def generate(self, request):
                return GenerationResult(
                    success=True,
                    output_path="/tmp/dummy.png",
                    provider=self.provider_name,
                    generation_type=GenerationType.IMAGE,
                )

        manager = AIGeneratorManager()
        # 清除已有
        manager._generators = {}
        manager.register("dummy", DummyGenerator("fake_key"))
        assert "dummy" in manager.list_providers()

        result = manager.generate(
            GenerationRequest(prompt="test", generation_type=GenerationType.IMAGE),
            provider="dummy",
        )
        assert result.success is True
        assert result.provider == "dummy"

    def test_auto_select_provider(self):
        class DummyGenerator(BaseAIGenerator):
            @property
            def provider_name(self):
                return "dummy_auto"

            @property
            def supported_types(self):
                return [GenerationType.IMAGE, GenerationType.VIDEO]

            def generate(self, request):
                return GenerationResult(
                    success=True,
                    output_path="/tmp/dummy.png",
                    provider=self.provider_name,
                    generation_type=request.generation_type,
                )

        manager = AIGeneratorManager()
        manager._generators = {}
        manager.register("dummy", DummyGenerator("fake_key"))

        result = manager.generate(
            GenerationRequest(prompt="test", generation_type=GenerationType.IMAGE),
        )
        assert result.success is True


class TestGenerationModels:
    """测试生成相关数据模型."""

    def test_generation_request(self):
        req = GenerationRequest(prompt="a sunset", generation_type=GenerationType.IMAGE)
        assert req.prompt == "a sunset"
        assert req.width == 1024
        assert req.height == 1024

    def test_generation_result(self):
        result = GenerationResult(success=True, output_path="/tmp/test.png")
        assert result.success is True
        assert result.provider == ""

    def test_generation_type(self):
        assert GenerationType.IMAGE == "image"
        assert GenerationType.VIDEO == "video"
        assert GenerationType.AUDIO == "audio"
