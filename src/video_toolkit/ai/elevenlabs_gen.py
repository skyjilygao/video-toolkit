"""ElevenLabs 生成器 - 高质量 TTS."""

import time

import requests

from video_toolkit.ai.base import (
    BaseAIGenerator,
    GenerationRequest,
    GenerationResult,
    GenerationType,
)


class ElevenLabsGenerator(BaseAIGenerator):
    """ElevenLabs 生成器."""

    BASE_URL = "https://api.elevenlabs.io/v1"

    @property
    def provider_name(self) -> str:
        return "elevenlabs"

    @property
    def supported_types(self) -> list[GenerationType]:
        return [GenerationType.AUDIO]

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """执行生成."""
        if request.generation_type != GenerationType.AUDIO:
            return GenerationResult(
                success=False,
                message="ElevenLabs 仅支持音频生成",
            )

        import tempfile

        start_time = time.time()
        output_path = tempfile.mktemp(suffix=".mp3")
        voice_id = request.extra_params.get("voice_id", "21m00Tcm4TlvDq8ikWAM")

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        data = {
            "text": request.prompt,
            "model_id": "eleven_monolingual_v1",
        }

        try:
            resp = requests.post(
                f"{self.BASE_URL}/text-to-speech/{voice_id}",
                json=data,
                headers=headers,
                timeout=120,
            )

            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return GenerationResult(
                    success=True,
                    output_path=output_path,
                    provider=self.provider_name,
                    generation_type=GenerationType.AUDIO,
                    duration=time.time() - start_time,
                )
            else:
                return GenerationResult(
                    success=False,
                    message=f"ElevenLabs 请求失败: {resp.status_code} {resp.text[:200]}",
                )
        except Exception as e:
            return GenerationResult(
                success=False,
                message=f"ElevenLabs 生成失败: {str(e)}",
            )
