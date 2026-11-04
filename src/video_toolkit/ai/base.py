"""AI 生成器基类."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class GenerationType(str, Enum):
    """生成类型."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"


@dataclass
class GenerationRequest:
    """生成请求."""

    prompt: str
    generation_type: GenerationType = GenerationType.IMAGE
    width: int = 1024
    height: int = 1024
    duration: float = 5.0
    negative_prompt: str = ""
    seed: Optional[int] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    """生成结果."""

    success: bool = False
    output_path: str = ""
    provider: str = ""
    generation_type: GenerationType = GenerationType.IMAGE
    duration: float = 0.0
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseAIGenerator(ABC):
    """AI 生成器基类."""

    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key
        self.extra_config = kwargs

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider 名称."""
        ...

    @property
    @abstractmethod
    def supported_types(self) -> List[GenerationType]:
        """支持的生成类型."""
        ...

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """执行生成."""
        ...

    def validate(self) -> bool:
        """验证配置."""
        return bool(self.api_key)
