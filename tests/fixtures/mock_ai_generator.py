"""Mock AI 生成器 — 不发起真实 API 请求，返回本地合成的视频/图片.

用法:
    1. 在 AIGeneratorManager 注册 Mock Generator
    2. 调用 generate() 时返回本地预设的视频文件
    3. 完全绕过网络请求，适合 CI/CD 和本地快速验证

设计思路:
    - MockVideoGenerator.generate() 根据请求参数生成不同颜色的视频
    - MockImageGenerator.generate() 返回本地图像文件
    - MockAudioGenerator.generate() 返回本地音频文件
    - MockSeedanceGenerator 模拟 Seedance provider 的行为
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import List

from video_toolkit.ai.base import (
    BaseAIGenerator,
    GenerationRequest,
    GenerationResult,
    GenerationType,
)
from tests.fixtures.mock_video import (
    generate_solid_color_video,
    generate_test_image,
)


# ── Mock 视频生成器 ──

class MockVideoGenerator(BaseAIGenerator):
    """Mock 视频生成器 — 返回本地合成的短视频."""

    def __init__(
        self,
        api_key: str = "mock_key",
        output_dir: str = "",
        fixed_color: str = "teal",
    ):
        super().__init__(api_key=api_key)
        self._output_dir = output_dir or tempfile.mkdtemp(prefix="vt_mock_ai_")
        self._fixed_color = fixed_color
        self._call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock_video"

    @property
    def supported_types(self) -> List[GenerationType]:
        return [GenerationType.VIDEO]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """生成 Mock 视频 — 根据 prompt 哈希颜色."""
        self._call_count += 1

        # 根据 prompt 关键词选择颜色
        color_map = {
            "mountain": "forestgreen",
            "sunset": "orangered",
            "ocean": "dodgerblue",
            "city": "slategray",
            "person": "gold",
            "running": "crimson",
            "data": "mediumpurple",
            "landscape": "limegreen",
            "portrait": "deeppink",
        }

        color = self._fixed_color
        prompt_lower = request.prompt.lower()
        for keyword, c in color_map.items():
            if keyword in prompt_lower:
                color = c
                break

        # 生成本地视频
        output_path = os.path.join(
            self._output_dir,
            f"mock_video_{self._call_count:04d}.mp4",
        )

        try:
            generate_solid_color_video(
                output_path=output_path,
                duration=min(request.duration, 3.0),
                width=request.width,
                height=request.height,
                fps=24,
                color=color,
                label=f"Mock #{self._call_count}",
            )

            return GenerationResult(
                success=True,
                output_path=output_path,
                provider=self.provider_name,
                generation_type=GenerationType.VIDEO,
                duration=min(request.duration, 3.0),
                metadata={"mock": True, "color": color, "prompt": request.prompt[:100]},
            )
        except Exception as e:
            return GenerationResult(
                success=False,
                message=f"Mock 视频生成失败: {e}",
                provider=self.provider_name,
            )


# ── Mock 图片生成器 ──

class MockImageGenerator(BaseAIGenerator):
    """Mock 图片生成器 — 返回本地图像文件."""

    def __init__(
        self,
        api_key: str = "mock_key",
        output_dir: str = "",
    ):
        super().__init__(api_key=api_key)
        self._output_dir = output_dir or tempfile.mkdtemp(prefix="vt_mock_img_")
        self._call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock_image"

    @property
    def supported_types(self) -> List[GenerationType]:
        return [GenerationType.IMAGE]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """生成 Mock 图片."""
        self._call_count += 1

        output_path = os.path.join(
            self._output_dir,
            f"mock_img_{self._call_count:04d}.png",
        )

        try:
            generate_test_image(
                output_path=output_path,
                width=request.width,
                height=request.height,
                color="steelblue",
                label=f"Mock #{self._call_count}",
            )

            return GenerationResult(
                success=True,
                output_path=output_path,
                provider=self.provider_name,
                generation_type=GenerationType.IMAGE,
                metadata={"mock": True},
            )
        except Exception as e:
            return GenerationResult(
                success=False,
                message=f"Mock 图片生成失败: {e}",
                provider=self.provider_name,
            )


# ── Mock 音频生成器 ──

class MockAudioGenerator(BaseAIGenerator):
    """Mock 音频生成器 — 返回本地合成的音频文件."""

    def __init__(
        self,
        api_key: str = "mock_key",
        output_dir: str = "",
    ):
        super().__init__(api_key=api_key)
        self._output_dir = output_dir or tempfile.mkdtemp(prefix="vt_mock_audio_")
        self._call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock_audio"

    @property
    def supported_types(self) -> List[GenerationType]:
        return [GenerationType.AUDIO]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """生成 Mock 音频."""
        self._call_count += 1

        output_path = os.path.join(
            self._output_dir,
            f"mock_audio_{self._call_count:04d}.mp3",
        )

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # 生成正弦波音频
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavvi",
                    "-i", "sine=frequency=440:duration=2:sample_rate=44100",
                    "-b:a", "128k",
                    output_path,
                ],
                capture_output=True,
                timeout=15,
                check=True,
            )

            return GenerationResult(
                success=True,
                output_path=output_path,
                provider=self.provider_name,
                generation_type=GenerationType.AUDIO,
                duration=2.0,
                metadata={"mock": True},
            )
        except Exception as e:
            return GenerationResult(
                success=False,
                message=f"Mock 音频生成失败: {e}",
                provider=self.provider_name,
            )


# ── Seedance 专用 Mock ──

class MockSeedanceGenerator(BaseAIGenerator):
    """Mock Seedance 生成器 — 模拟 Seedance 2.0/2.5 provider 行为."""

    def __init__(
        self,
        api_key: str = "mock_seedance_key",
        output_dir: str = "",
        model_version: str = "2.0",
        variant: str = "standard",
    ):
        super().__init__(api_key=api_key)
        self._output_dir = output_dir or tempfile.mkdtemp(prefix="vt_mock_seedance_")
        self._model_version = model_version
        self._variant = variant
        self._call_count = 0

    @property
    def provider_name(self) -> str:
        return "seedance"

    @property
    def supported_types(self) -> List[GenerationType]:
        return [GenerationType.VIDEO, GenerationType.IMAGE]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """生成 Mock Seedance 视频."""
        self._call_count += 1

        if request.generation_type == GenerationType.VIDEO:
            output_path = os.path.join(
                self._output_dir,
                f"mock_seedance_{self._call_count:04d}.mp4",
            )

            try:
                generate_solid_color_video(
                    output_path=output_path,
                    duration=min(request.duration, 3.0),
                    width=request.width,
                    height=request.height,
                    fps=24,
                    color="darkviolet",
                    label=f"Seedance {self._model_version} #{self._call_count}",
                )

                return GenerationResult(
                    success=True,
                    output_path=output_path,
                    provider=self.provider_name,
                    generation_type=GenerationType.VIDEO,
                    duration=min(request.duration, 3.0),
                    metadata={
                        "mock": True,
                        "seedance": True,
                        "model_version": self._model_version,
                        "variant": self._variant,
                    },
                )
            except Exception as e:
                return GenerationResult(
                    success=False,
                    message=f"Mock Seedance 视频生成失败: {e}",
                    provider=self.provider_name,
                )

        elif request.generation_type == GenerationType.IMAGE:
            output_path = os.path.join(
                self._output_dir,
                f"mock_seedance_img_{self._call_count:04d}.png",
            )

            try:
                generate_test_image(
                    output_path=output_path,
                    width=request.width,
                    height=request.height,
                    color="indigo",
                    label=f"Seedance #{self._call_count}",
                )

                return GenerationResult(
                    success=True,
                    output_path=output_path,
                    provider=self.provider_name,
                    generation_type=GenerationType.IMAGE,
                    metadata={"mock": True, "seedance": True},
                )
            except Exception as e:
                return GenerationResult(
                    success=False,
                    message=str(e),
                    provider=self.provider_name,
                )

        return GenerationResult(
            success=False,
            message=f"不支持 {request.generation_type}",
            provider=self.provider_name,
        )
