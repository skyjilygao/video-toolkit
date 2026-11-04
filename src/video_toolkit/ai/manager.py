"""AI 生成器管理器 - 多 Provider 调度."""
from typing import Dict, List, Optional

from rich.console import Console

from video_toolkit.ai.base import (
    BaseAIGenerator,
    GenerationRequest,
    GenerationResult,
    GenerationType,
)
from video_toolkit.config import config

console = Console()


class AIGeneratorManager:
    """AI 生成器管理器."""

    def __init__(self):
        self._generators: Dict[str, BaseAIGenerator] = {}
        self._register_defaults()

    def _register_defaults(self):
        """注册默认 Provider."""
        # fal.ai
        if config.fal_key:
            try:
                from video_toolkit.ai.fal_ai import FalAIGenerator

                self.register("fal", FalAIGenerator(config.fal_key))
            except ImportError:
                pass

        # OpenAI
        if config.openai_key:
            try:
                from video_toolkit.ai.openai_gen import OpenAIGenerator

                self.register("openai", OpenAIGenerator(config.openai_key))
            except ImportError:
                pass

        # ElevenLabs
        if config.elevenlabs_key:
            try:
                from video_toolkit.ai.elevenlabs_gen import ElevenLabsGenerator

                self.register("elevenlabs", ElevenLabsGenerator(config.elevenlabs_key))
            except ImportError:
                pass

    def register(self, name: str, generator: BaseAIGenerator):
        """注册生成器."""
        if generator.validate():
            self._generators[name] = generator
            console.print(f"[dim]已注册 AI Provider: {name}[/dim]")

    def generate(
        self,
        request: GenerationRequest,
        provider: Optional[str] = None,
    ) -> GenerationResult:
        """执行生成."""
        if provider:
            gen = self._generators.get(provider)
            if not gen:
                return GenerationResult(
                    success=False,
                    message=f"未找到 Provider: {provider}",
                )
            return gen.generate(request)

        # 自动选择
        for gen_type in [request.generation_type]:
            for name, gen in self._generators.items():
                if gen_type in gen.supported_types:
                    console.print(f"[dim]使用 Provider: {name}[/dim]")
                    return gen.generate(request)

        return GenerationResult(
            success=False,
            message=f"没有可用的 Provider 支持 {request.generation_type.value} 生成",
        )

    def list_providers(self) -> List[str]:
        """列出已注册的 Provider."""
        return list(self._generators.keys())

    def get_provider(self, name: str) -> Optional[BaseAIGenerator]:
        """获取指定 Provider."""
        return self._generators.get(name)
