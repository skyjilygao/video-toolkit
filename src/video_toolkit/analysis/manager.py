"""适配器注册与管理."""

from __future__ import annotations

from video_toolkit.analysis.base import BaseAnalysisAdapter

# 适配器注册表: name -> class
_REGISTRY: dict[str, type[BaseAnalysisAdapter]] = {}


def register_adapter(name: str):
    """装饰器：注册适配器类."""

    def decorator(cls: type[BaseAnalysisAdapter]):
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return decorator


class AnalysisManager:
    """适配器管理器 — 提供统一的适配器发现与实例化接口."""

    @staticmethod
    def get_adapter(
        name: str, video_path: str, output_dir: str | None = None
    ) -> BaseAnalysisAdapter:
        """获取指定名称的适配器实例.

        Parameters
        ----------
        name : str
            适配器名称 (``custom``, ``openmontage`` 等)
        video_path : str
            待分析的视频路径
        output_dir : str, optional
            输出目录路径
        """
        if name not in _REGISTRY:
            available = ", ".join(AnalysisManager.available_adapters())
            raise ValueError(f"未知适配器 '{name}'。可用适配器: [{available}]")
        return _REGISTRY[name](video_path=video_path, output_dir=output_dir)

    @staticmethod
    def available_adapters() -> list[str]:
        """列出所有可用的适配器名称."""
        return sorted(_REGISTRY.keys())

    @staticmethod
    def has_adapter(name: str) -> bool:
        """检查适配器是否可用."""
        return name in _REGISTRY
