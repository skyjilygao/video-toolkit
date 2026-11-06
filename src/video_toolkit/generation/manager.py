"""视频生成管理器 — 多 Provider 调度.

类似于 AIGeneratorManager 和 AnalysisManager 的模式，
GenerationManager 统一管理多个视频生成适配器。
"""

from __future__ import annotations

from rich.console import Console

from video_toolkit.generation.base import BaseGenerationAdapter

console = Console()


class GenerationManager:
    """视频生成管理器."""

    def __init__(self):
        self._adapters: dict[str, type[BaseGenerationAdapter]] = {}
        self._register_defaults()

    def _register_defaults(self):
        """注册默认适配器."""
        try:
            from video_toolkit.generation.custom_adapter import CustomGenerationAdapter

            self.register("custom", CustomGenerationAdapter)
        except ImportError as e:
            console.print(f"[dim]CustomGenerationAdapter 导入失败: {e}[/dim]")

        try:
            from video_toolkit.generation.openmontage_adapter import OpenGenerationAdapter

            self.register("openmontage", OpenGenerationAdapter)
        except ImportError as e:
            console.print(f"[dim]OpenGenerationAdapter 导入失败: {e}[/dim]")

    def register(self, name: str, adapter_cls: type[BaseGenerationAdapter]):
        """注册适配器."""
        self._adapters[name] = adapter_cls
        console.print(f"[dim]已注册视频生成适配器: {name}[/dim]")

    def get_adapter(
        self,
        name: str,
        video_path: str,
        brief,
    ) -> BaseGenerationAdapter:
        """获取适配器实例."""
        cls = self._adapters.get(name)
        if cls is None:
            available = ", ".join(self._adapters.keys())
            raise ValueError(f"未知的视频生成适配器: '{name}'。可用: {available}")
        return cls(video_path=video_path, brief=brief)

    def list_adapters(self) -> list[str]:
        """列出已注册的适配器."""
        return list(self._adapters.keys())

    def get_default_adapter(self) -> str:
        """获取默认适配器名称."""
        if "custom" in self._adapters:
            return "custom"
        if self._adapters:
            return next(iter(self._adapters.keys()))
        raise RuntimeError("没有可用的视频生成适配器")
