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
        """注册默认 Provider，从模型配置文件中读取配置，支持任意OpenAI兼容接口自动适配"""
        # 加载模型配置
        model_config = config.get_model_config()
        providers = model_config.get("config", {}).get("providers", {})
        
        for provider_name, provider_conf in providers.items():
            # 获取API Key
            api_key = config.get_api_key_for_provider(provider_name)
            if not api_key:
                continue  # 跳过没有配置API Key的Provider
            
            # 检查是否有支持的生成类型，没有则跳过
            has_supported_model = False
            for model in provider_conf.get("models", []):
                if any(op in model.get("supports", []) for op in ["text_to_video", "text_to_image", "text_to_speech"]):
                    has_supported_model = True
                    break
            if not has_supported_model:
                continue  # 跳过没有可用生成模型的Provider
                
            try:
                # 优先匹配专用Provider实现
                if provider_name == "seedance":
                    from video_toolkit.ai.seedance_gen import SeedanceAIGenerator
                    # 获取Seedance默认模型配置
                    default_model = next(iter(provider_conf.get("models", [])), {})
                    self.register(
                        provider_name,
                        SeedanceAIGenerator(
                            api_key=api_key,
                            api_url=provider_conf.get("baseURL", "https://queue.fal.run"),
                            model_version=default_model.get("version", "2.0"),
                            variant=default_model.get("variant", "standard"),
                        ),
                    )
                    continue
                
                # 通用OpenAI兼容接口适配（新增Provider只要符合openai-completions协议就会自动适配）
                if provider_conf.get("api") == "openai-completions":
                    from video_toolkit.ai.openai_compatible_gen import OpenAICompatibleGenerator
                    # 获取默认支持的模型ID
                    default_model_id = next(
                        (m["id"] for m in provider_conf.get("models", []) 
                         if any(op in m.get("supports", []) for op in ["text_to_video", "text_to_image", "text_to_speech"])),
                        ""
                    )
                    self.register(
                        provider_name,
                        OpenAICompatibleGenerator(
                            api_key=api_key,
                            base_url=provider_conf.get("baseURL", ""),
                            default_model_id=default_model_id,
                            supported_types=self._get_supported_types(provider_conf),
                        ),
                    )
                    continue
                
                # 未知类型的provider跳过
                console.print(f"[dim]不支持的Provider类型: {provider_name} (api: {provider_conf.get('api')})[/dim]")
                
            except ImportError as e:
                console.print(f"[dim]Provider {provider_name} 导入失败: {e}[/dim]")
            except Exception as e:
                console.print(f"[dim]注册Provider {provider_name} 失败: {e}[/dim]")
    
    def _get_supported_types(self, provider_conf: dict) -> list:
        """获取Provider支持的生成类型"""
        supported_types = set()
        for model in provider_conf.get("models", []):
            for op in model.get("supports", []):
                if op == "text_to_video":
                    supported_types.add(GenerationType.VIDEO)
                elif op == "text_to_image":
                    supported_types.add(GenerationType.IMAGE)
                elif op == "text_to_speech":
                    supported_types.add(GenerationType.AUDIO)
        return list(supported_types)

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
