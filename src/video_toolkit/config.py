"""全局配置管理."""

import os
from pathlib import Path
from typing import Any, cast

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# 默认模型配置文件路径
DEFAULT_MODEL_CONFIG_PATH = Path.home() / ".video-toolkit" / "models.config.yml"


class Config:
    """全局配置."""

    # 默认测试视频目录
    DEFAULT_TEST_VIDEO_DIR: str = (
        r"\\192.168.88.121\.n8n-files\video_download\video\2026-11-02\20261102"
    )

    def __init__(self):
        self._fal_key: str | None = None
        self._openai_key: str | None = None
        self._elevenlabs_key: str | None = None
        self._seedance_key: str | None = None
        self._seedance_api_url: str | None = None
        self._seedance_model_version: str | None = None
        self._seedance_variant: str | None = None
        self._model_config: dict[str, Any] | None = None

    # ── 模型配置加载 ──
    def load_model_config(self, config_path: str | None = None) -> dict[str, Any]:
        """加载模型配置文件.

        Args:
            config_path: 配置文件路径，默认使用~/.video-toolkit/models.config.yml

        Returns:
            模型配置字典
        """
        if self._model_config is not None:
            return self._model_config

        path = Path(config_path) if config_path else DEFAULT_MODEL_CONFIG_PATH

        if not path.exists():
            # 如果文件不存在，创建默认配置
            self._create_default_model_config(path)

        try:
            with open(path, encoding="utf-8") as f:
                self._model_config = yaml.safe_load(f) or {}
            return self._model_config
        except Exception as e:
            print(f"[警告] 加载模型配置文件失败: {e}")
            return {}

    def _create_default_model_config(self, path: Path) -> None:
        """创建默认模型配置文件."""
        default_content = """config:
  defaultVideoModel: seedance-2.0-standard
  defaultImageModel: fal-flux-1.1-pro
  defaultAudioModel: openai-tts-1

  providers:
    seedance:
      displayName: Seedance（字节跳动视频生成）
      apiKeyEnv: SEEDANCE_API_KEY
      api: openai-completions
      baseURL: https://queue.fal.run
      models:
        - id: seedance-2.0-standard
          name: Seedance 2.0 标准版
          version: "2.0"
          variant: standard
          description: 高质量视频生成，适合大多数场景
          supports:
            - text_to_video
            - image_to_video
        - id: seedance-2.0-fast
          name: Seedance 2.0 快速版
          version: "2.0"
          variant: fast
          description: 低延迟快速生成，成本更低
          supports:
            - text_to_video
            - image_to_video
        - id: seedance-2.5-standard
          name: Seedance 2.5 标准版（最新）
          version: "2.5"
          variant: standard
          description: 最新版本，画质更好，支持参考图生成
          supports:
            - text_to_video
            - image_to_video
            - reference_to_video

    fal:
      displayName: fal.ai（Kling/FLUX）
      apiKeyEnv: FAL_KEY
      api: openai-completions
      baseURL: https://api.fal.ai/v1
      models:
        - id: fal-kling-2.0
          name: Kling 2.0
          description: fal.ai提供的Kling视频生成
          supports:
            - text_to_video
            - image_to_video
        - id: fal-flux-1.1-pro
          name: FLUX 1.1 Pro
          description: 高质量图片生成，用于降级到Ken Burns动画
          supports:
            - image_to_image
            - text_to_image

    openai:
      displayName: OpenAI（DALL-E + TTS）
      apiKeyEnv: OPENAI_API_KEY
      api: openai-completions
      baseURL: https://api.openai.com/v1
      models:
        - id: dall-e-3
          name: DALL-E 3
          description: 高质量图片生成
          supports:
            - text_to_image
        - id: tts-1
          name: TTS-1
          description: 标准语音合成
          supports:
            - text_to_speech
        - id: tts-1-hd
          name: TTS-1 HD
          description: 高清语音合成，音质更好
          supports:
            - text_to_speech

    elevenlabs:
      displayName: ElevenLabs（语音合成）
      apiKeyEnv: ELEVENLABS_API_KEY
      api: openai-completions
      baseURL: https://api.elevenlabs.io/v1
      models:
        - id: eleven_multilingual_v2
          name: Eleven Multilingual V2
          description: 多语言高质量语音合成
          supports:
            - text_to_speech
"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(default_content)
            print(f"[信息] 已创建默认模型配置文件: {path}")
        except Exception as e:
            print(f"[警告] 创建默认模型配置文件失败: {e}")

    def get_model_config(self) -> dict[str, Any]:
        """获取模型配置，如果未加载则自动加载."""
        if self._model_config is None:
            return self.load_model_config()
        return self._model_config

    def get_video_models(self) -> list[dict[str, Any]]:
        """获取所有可用的视频生成模型."""
        config = self.get_model_config()
        models = []
        for provider_name, provider in config.get("config", {}).get("providers", {}).items():
            for model in provider.get("models", []):
                if "text_to_video" in model.get("supports", []):
                    models.append(
                        {
                            "id": model["id"],
                            "name": model["name"],
                            "provider": provider_name,
                            "providerDisplayName": provider["displayName"],
                            **model,
                        }
                    )
        return models

    def get_image_models(self) -> list[dict[str, Any]]:
        """获取所有可用的图片生成模型."""
        config = self.get_model_config()
        models = []
        for provider_name, provider in config.get("config", {}).get("providers", {}).items():
            for model in provider.get("models", []):
                if "text_to_image" in model.get("supports", []):
                    models.append(
                        {
                            "id": model["id"],
                            "name": model["name"],
                            "provider": provider_name,
                            "providerDisplayName": provider["displayName"],
                            **model,
                        }
                    )
        return models

    def get_audio_models(self) -> list[dict[str, Any]]:
        """获取所有可用的音频生成模型."""
        config = self.get_model_config()
        models = []
        for provider_name, provider in config.get("config", {}).get("providers", {}).items():
            for model in provider.get("models", []):
                if "text_to_speech" in model.get("supports", []):
                    models.append(
                        {
                            "id": model["id"],
                            "name": model["name"],
                            "provider": provider_name,
                            "providerDisplayName": provider["displayName"],
                            **model,
                        }
                    )
        return models

    def get_model_by_id(self, model_id: str) -> dict[str, Any] | None:
        """根据模型ID获取模型配置."""
        # 查找所有类型的模型
        all_models = self.get_video_models() + self.get_image_models() + self.get_audio_models()
        for model in all_models:
            if model["id"] == model_id:
                return model
        return None

    def get_provider_config(self, provider_name: str) -> dict[str, Any] | None:
        """获取Provider配置."""
        model_config = self.get_model_config()
        provider = model_config.get("config", {}).get("providers", {}).get(provider_name)
        return cast(dict[str, Any], provider) if provider is not None else None

    def get_api_key_for_provider(self, provider_name: str) -> str | None:
        """获取指定Provider的API Key（从环境变量读取）."""
        provider = self.get_provider_config(provider_name)
        if not provider:
            return None
        api_key_env = provider.get("apiKeyEnv")
        if not api_key_env:
            return None
        return os.environ.get(api_key_env, "") or None

    @property
    def fal_key(self) -> str | None:
        if self._fal_key is None:
            self._fal_key = os.environ.get("FAL_KEY", "")
        return self._fal_key or None

    @property
    def openai_key(self) -> str | None:
        if self._openai_key is None:
            self._openai_key = os.environ.get("OPENAI_API_KEY", "")
        return self._openai_key or None

    @property
    def elevenlabs_key(self) -> str | None:
        if self._elevenlabs_key is None:
            self._elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY", "")
        return self._elevenlabs_key or None

    @property
    def seedance_key(self) -> str | None:
        if self._seedance_key is None:
            self._seedance_key = os.environ.get("SEEDANCE_API_KEY", "")
        return self._seedance_key or None

    @property
    def seedance_api_url(self) -> str:
        if self._seedance_api_url is None:
            self._seedance_api_url = os.environ.get("SEEDANCE_API_URL", "https://queue.fal.run")
        return self._seedance_api_url

    @property
    def seedance_model_version(self) -> str:
        if self._seedance_model_version is None:
            self._seedance_model_version = os.environ.get("SEEDANCE_MODEL_VERSION", "2.0")
        return self._seedance_model_version

    @property
    def seedance_variant(self) -> str:
        if self._seedance_variant is None:
            self._seedance_variant = os.environ.get("SEEDANCE_VARIANT", "standard")
        return self._seedance_variant

    @property
    def test_video_dir(self) -> str:
        return os.environ.get("TEST_VIDEO_DIR", self.DEFAULT_TEST_VIDEO_DIR)

    def get_ffmpeg_path(self) -> str:
        return os.environ.get("FFMPEG_PATH", "ffmpeg")

    def get_ffprobe_path(self) -> str:
        return os.environ.get("FFPROBE_PATH", "ffprobe")


# 全局单例
config = Config()
