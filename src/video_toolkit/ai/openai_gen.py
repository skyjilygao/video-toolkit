"""OpenAI 生成器 - DALL-E 图片、TTS 语音."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from video_toolkit.ai.base import (
    BaseAIGenerator,
    GenerationRequest,
    GenerationResult,
    GenerationType,
)

if TYPE_CHECKING:
    from openai import OpenAI

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment, misc]


class OpenAIGenerator(BaseAIGenerator):
    """OpenAI 生成器."""

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def supported_types(self) -> list[GenerationType]:
        return [GenerationType.IMAGE, GenerationType.AUDIO]

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self._client: OpenAI | None = None
        if OpenAI is not None:
            self._client = OpenAI(api_key=api_key)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """执行生成."""
        if self._client is None:
            return GenerationResult(
                success=False,
                message="openai 未安装，请运行: pip install openai",
            )

        start_time = time.time()

        try:
            if request.generation_type == GenerationType.IMAGE:
                return self._generate_image(request, start_time)
            elif request.generation_type == GenerationType.AUDIO:
                return self._generate_audio(request, start_time)
            else:
                return GenerationResult(
                    success=False,
                    message=f"openai 不支持 {request.generation_type.value} 类型",
                )
        except Exception as e:
            return GenerationResult(
                success=False,
                message=f"openai 生成失败: {str(e)}",
            )

    def _generate_image(self, request: GenerationRequest, start_time: float) -> GenerationResult:
        """DALL-E 生成图片."""
        client = self._client
        if client is None:
            return GenerationResult(
                success=False,
                message="openai 未安装，请运行: pip install openai",
            )

        size = f"{request.width}x{request.height}"
        response = client.images.generate(
            model="dall-e-3",
            prompt=request.prompt,
            n=1,
            size=size,
        )

        first_image = response.data[0] if response.data else None
        image_url = str(first_image.url or "") if first_image is not None else ""

        return GenerationResult(
            success=bool(image_url),
            output_path=image_url,
            provider=self.provider_name,
            generation_type=GenerationType.IMAGE,
            duration=time.time() - start_time,
            metadata={
                "revised_prompt": (
                    getattr(first_image, "revised_prompt", "") if first_image is not None else ""
                )
            },
        )

    def _generate_audio(self, request: GenerationRequest, start_time: float) -> GenerationResult:
        """TTS 生成语音."""
        client = self._client
        if client is None:
            return GenerationResult(
                success=False,
                message="openai 未安装，请运行: pip install openai",
            )

        import tempfile

        output_path = tempfile.mktemp(suffix=".mp3")

        response = client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=request.prompt,
        )

        response.stream_to_file(output_path)

        return GenerationResult(
            success=True,
            output_path=output_path,
            provider=self.provider_name,
            generation_type=GenerationType.AUDIO,
            duration=time.time() - start_time,
        )
