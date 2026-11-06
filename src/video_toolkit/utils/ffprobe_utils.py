"""FFprobe 工具函数 — 获取视频元数据."""

from __future__ import annotations

import json
import subprocess
from typing import Any


def get_video_info(video_path: str) -> dict[str, Any]:
    """获取视频信息（宽、高、帧率、时长等）.

    Parameters
    ----------
    video_path : str
        视频文件路径

    Returns
    -------
    dict
        {
            "width": int,
            "height": int,
            "fps": float,
            "duration": float,
            "codec": str,
            "bitrate": int,
            "has_audio": bool,
        }
    """
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
    except Exception:
        return _empty_info()

    info: dict[str, Any] = {
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "duration": 0.0,
        "codec": "",
        "bitrate": 0,
        "has_audio": False,
    }

    # 从 format 获取时长
    fmt = data.get("format", {})
    info["duration"] = float(fmt.get("duration", 0))
    info["bitrate"] = int(fmt.get("bit_rate", 0))

    # 从 streams 获取视频/音频信息
    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type", "")
        if codec_type == "video" and not info["codec"]:
            info["width"] = int(stream.get("width", 0))
            info["height"] = int(stream.get("height", 0))
            info["codec"] = stream.get("codec_name", "")

            # 帧率
            r_frame_rate = stream.get("r_frame_rate", "0/1")
            if "/" in r_frame_rate:
                num, den = r_frame_rate.split("/")
                try:
                    info["fps"] = float(num) / float(den) if float(den) > 0 else 0.0
                except (ValueError, ZeroDivisionError):
                    info["fps"] = 0.0

        elif codec_type == "audio":
            info["has_audio"] = True

    return info


def _empty_info() -> dict[str, Any]:
    return {
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "duration": 0.0,
        "codec": "",
        "bitrate": 0,
        "has_audio": False,
    }
