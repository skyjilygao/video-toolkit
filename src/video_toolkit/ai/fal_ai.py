"""fal.ai 生成器 - FLUX 图片、Kling/Seedance/Hailuo 视频."""

import time

from video_toolkit.ai.base import (
    BaseAIGenerator,
    GenerationRequest,
    GenerationResult,
    GenerationType,
)

try:
    import fal_client
except ImportError:
    fal_client = None


class FalAIGenerator(BaseAIGenerator):
    """fal.ai 生成器."""

    @property
    def provider_name(self) -> str:
        return "fal"

    @property
    def supported_types(self) -> list[GenerationType]:
        return [GenerationType.IMAGE, GenerationType.VIDEO]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """执行生成."""
        if fal_client is None:
            return GenerationResult(
                success=False,
                message="fal_client 未安装，请运行: pip install fal-client",
            )

        start_time = time.time()

        try:
            if request.generation_type == GenerationType.IMAGE:
                return self._generate_image(request, start_time)
            elif request.generation_type == GenerationType.VIDEO:
                return self._generate_video(request, start_time)
            else:
                return GenerationResult(
                    success=False,
                    message=f"fal 不支持 {request.generation_type.value} 类型",
                )
        except Exception as e:
            return GenerationResult(
                success=False,
                message=f"fal 生成失败: {str(e)}",
            )

    def _generate_image(self, request: GenerationRequest, start_time: float) -> GenerationResult:
        """生成图片."""
        handler = fal_client.submit(
            "fal-ai/flux/dev",
            arguments={
                "prompt": request.prompt,
                "image_size": {"width": request.width, "height": request.height},
                "num_images": 1,
            },
        )

        result = handler.get()

        urls = result.get("images", [])
        output_path = ""
        if urls:
            output_path = urls[0].get("url", "")

        return GenerationResult(
            success=bool(output_path),
            output_path=output_path,
            provider=self.provider_name,
            generation_type=GenerationType.IMAGE,
            duration=time.time() - start_time,
            metadata={"raw_result": result},
        )

    def _generate_video(self, request: GenerationRequest, start_time: float) -> GenerationResult:
        """生成视频."""
        handler = fal_client.submit(
            "fal-ai/kling-video/v1/standard/text-to-video",
            arguments={
                "prompt": request.prompt,
                "duration": str(int(request.duration)),
            },
        )

        result = handler.get()
        video = result.get("video", {})
        output_path = video.get("url", "") if isinstance(video, dict) else ""

        return GenerationResult(
            success=bool(output_path),
            output_path=output_path,
            provider=self.provider_name,
            generation_type=GenerationType.VIDEO,
            duration=time.time() - start_time,
            metadata={"raw_result": result},
        )
