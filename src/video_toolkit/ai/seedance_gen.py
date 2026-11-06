"""Seedance AI 视频生成器."""
import os
import time
from pathlib import Path
from typing import List, Optional

from video_toolkit.ai.base import (
    BaseAIGenerator,
    GenerationRequest,
    GenerationResult,
    GenerationType,
)


class SeedanceAIGenerator(BaseAIGenerator):
    """Seedance 视频生成器，对接字节跳动Seedance 2.0/2.5 API."""

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://queue.fal.run",
        model_version: str = "2.0",
        variant: str = "standard",
        **kwargs,
    ):
        super().__init__(api_key, **kwargs)
        self.api_url = api_url
        self.model_version = model_version
        self.variant = variant

    @property
    def provider_name(self) -> str:
        return "seedance"

    @property
    def supported_types(self) -> List[GenerationType]:
        return [GenerationType.VIDEO]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """执行Seedance视频生成."""
        try:
            import requests
        except ImportError:
            return GenerationResult(
                success=False,
                message="需要安装requests库: pip install requests",
            )

        # 构建模型路径
        operation = "text-to-video"
        if self.model_version == "2.5" and self.variant == "fast":
            return GenerationResult(
                success=False,
                message="Seedance 2.5不支持fast模式，请使用standard模式",
            )
        
        if self.model_version == "2.5":
            model_path = f"bytedance/seedance-2.5/{operation}"
        elif self.variant == "fast":
            model_path = f"bytedance/seedance-2.0/fast/{operation}"
        else:
            model_path = f"bytedance/seedance-2.0/{operation}"

        # 构建请求参数
        payload = {
            "prompt": request.prompt,
            "duration": str(int(request.duration)),
            "aspect_ratio": request.extra_params.get("aspect_ratio", "16:9"),
            "resolution": request.extra_params.get("resolution", "720p"),
            "generate_audio": request.extra_params.get("generate_audio", True),
        }
        if request.seed is not None:
            payload["seed"] = request.seed

        headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }

        start_time = time.time()
        try:
            # 提交生成任务
            submit_resp = requests.post(
                f"{self.api_url}/{model_path}",
                headers=headers,
                json=payload,
                timeout=30,
            )
            submit_resp.raise_for_status()
            queue_data = submit_resp.json()
            status_url = queue_data["status_url"]
            response_url = queue_data["response_url"]

            # 轮询任务状态
            while True:
                time.sleep(5)
                status_resp = requests.get(status_url, headers=headers, timeout=15)
                status_resp.raise_for_status()
                status = status_resp.json().get("status", "UNKNOWN")
                if status == "COMPLETED":
                    break
                if status in ("FAILED", "CANCELLED"):
                    return GenerationResult(
                        success=False,
                        message=f"Seedance生成任务{status.lower()}",
                    )

            # 获取结果
            result_resp = requests.get(response_url, headers=headers, timeout=30)
            result_resp.raise_for_status()
            data = result_resp.json()

            video_url = data["video"]["url"]
            video_resp = requests.get(video_url, timeout=120)
            video_resp.raise_for_status()

            # 保存视频
            output_dir = request.extra_params.get("output_dir", os.path.join(os.getcwd(), "seedance_outputs"))
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"seedance_{int(time.time())}.mp4")
            Path(output_path).write_bytes(video_resp.content)

            return GenerationResult(
                success=True,
                output_path=output_path,
                provider=self.provider_name,
                generation_type=GenerationType.VIDEO,
                duration=float(payload["duration"]),
                metadata={
                    "model": model_path,
                    "seedance_version": self.model_version,
                    "variant": self.variant,
                    "seed": data.get("seed"),
                    "aspect_ratio": payload["aspect_ratio"],
                    "resolution": payload["resolution"],
                    "generation_time": round(time.time() - start_time, 2),
                },
            )

        except Exception as e:
            return GenerationResult(
                success=False,
                message=f"Seedance生成失败: {str(e)}",
            )
