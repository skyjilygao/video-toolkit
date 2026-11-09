"""通用OpenAI兼容接口AI生成器，适配所有符合OpenAI API协议的Provider."""

import os
import time
from pathlib import Path

import requests

from video_toolkit.ai.base import (
    BaseAIGenerator,
    GenerationRequest,
    GenerationResult,
    GenerationType,
)


class OpenAICompatibleGenerator(BaseAIGenerator):
    """通用OpenAI兼容接口生成器，支持任意openai-completions协议的Provider."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        default_model_id: str = "",
        supported_types: list[GenerationType] | None = None,
        **kwargs,
    ):
        super().__init__(api_key, **kwargs)
        self.base_url = base_url.rstrip("/")
        self.default_model_id = default_model_id
        self._supported_types = supported_types or []

    @property
    def provider_name(self) -> str:
        return "openai-compatible"

    @property
    def supported_types(self) -> list[GenerationType]:
        return self._supported_types

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """执行生成请求，根据类型调用对应的接口."""
        try:
            if request.generation_type == GenerationType.VIDEO:
                return self._generate_video(request)
            elif request.generation_type == GenerationType.IMAGE:
                return self._generate_image(request)
            elif request.generation_type == GenerationType.AUDIO:
                return self._generate_audio(request)
            else:
                return GenerationResult(
                    success=False,
                    message=f"不支持的生成类型: {request.generation_type.value}",
                )
        except Exception as e:
            return GenerationResult(
                success=False,
                message=f"生成失败: {str(e)}",
            )

    def _generate_video(self, request: GenerationRequest) -> GenerationResult:
        """调用视频生成接口，兼容OpenAI异步任务模式."""
        # 优先使用请求中指定的模型，否则用默认模型
        model_id = request.extra_params.get("model_id", self.default_model_id)
        if not model_id:
            return GenerationResult(
                success=False,
                message="未指定视频生成模型ID",
            )

        # 构建请求参数
        payload = {
            "model": model_id,
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "duration": request.duration,
        }
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt
        if request.seed is not None:
            payload["seed"] = request.seed

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start_time = time.time()
        # 提交生成任务
        resp = requests.post(
            f"{self.base_url}/videos/generations",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # 如果是异步任务，轮询状态
        if data.get("status") == "processing" and data.get("task_id"):
            task_id = data["task_id"]
            while True:
                time.sleep(5)
                status_resp = requests.get(
                    f"{self.base_url}/videos/tasks/{task_id}",
                    headers=headers,
                    timeout=15,
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()
                if status_data.get("status") == "completed":
                    video_url = status_data.get("output_url")
                    break
                if status_data.get("status") in ("failed", "cancelled"):
                    return GenerationResult(
                        success=False,
                        message=f"视频生成任务{status_data.get('status')}: {status_data.get('error', '未知错误')}",
                    )
        elif data.get("output_url"):
            video_url = data["output_url"]
        else:
            return GenerationResult(
                success=False,
                message=f"无效的响应格式: {data}",
            )

        # 下载视频文件
        output_dir = request.extra_params.get("output_dir", os.path.join(os.getcwd(), "ai_outputs"))
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"video_{int(time.time())}.mp4")
        video_resp = requests.get(video_url, timeout=120)
        video_resp.raise_for_status()
        Path(output_path).write_bytes(video_resp.content)

        return GenerationResult(
            success=True,
            output_path=output_path,
            provider=self.provider_name,
            generation_type=GenerationType.VIDEO,
            duration=request.duration,
            metadata={
                "model": model_id,
                "generation_time": round(time.time() - start_time, 2),
            },
        )

    def _generate_image(self, request: GenerationRequest) -> GenerationResult:
        """调用图片生成接口，兼容DALL-E风格API."""
        model_id = request.extra_params.get("model_id", self.default_model_id)
        if not model_id:
            return GenerationResult(
                success=False,
                message="未指定图片生成模型ID",
            )

        payload = {
            "model": model_id,
            "prompt": request.prompt,
            "n": 1,
            "size": f"{request.width}x{request.height}",
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start_time = time.time()
        resp = requests.post(
            f"{self.base_url}/images/generations",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("data"):
            return GenerationResult(
                success=False,
                message=f"无效的响应格式: {data}",
            )

        image_url = data["data"][0]["url"]
        # 下载图片
        output_dir = request.extra_params.get("output_dir", os.path.join(os.getcwd(), "ai_outputs"))
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"image_{int(time.time())}.png")
        img_resp = requests.get(image_url, timeout=60)
        img_resp.raise_for_status()
        Path(output_path).write_bytes(img_resp.content)

        return GenerationResult(
            success=True,
            output_path=output_path,
            provider=self.provider_name,
            generation_type=GenerationType.IMAGE,
            metadata={
                "model": model_id,
                "generation_time": round(time.time() - start_time, 2),
            },
        )

    def _generate_audio(self, request: GenerationRequest) -> GenerationResult:
        """调用语音合成接口，兼容OpenAI TTS风格API."""
        model_id = request.extra_params.get("model_id", self.default_model_id)
        if not model_id:
            return GenerationResult(
                success=False,
                message="未指定语音合成模型ID",
            )

        payload = {
            "model": model_id,
            "input": request.prompt,
            "voice": request.extra_params.get("voice", "alloy"),
            "response_format": "mp3",
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start_time = time.time()
        resp = requests.post(
            f"{self.base_url}/audio/speech",
            headers=headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()

        # 保存音频
        output_dir = request.extra_params.get("output_dir", os.path.join(os.getcwd(), "ai_outputs"))
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"audio_{int(time.time())}.mp3")
        Path(output_path).write_bytes(resp.content)

        return GenerationResult(
            success=True,
            output_path=output_path,
            provider=self.provider_name,
            generation_type=GenerationType.AUDIO,
            duration=len(request.prompt) * 0.1,  # 估算时长
            metadata={
                "model": model_id,
                "voice": payload["voice"],
                "generation_time": round(time.time() - start_time, 2),
            },
        )
