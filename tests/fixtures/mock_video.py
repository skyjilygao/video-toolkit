"""合成测试视频生成器 — 使用 FFmpeg 生成无需外部依赖的测试视频.

功能:
- generate_test_video(): 生成带场景切换的合成视频
- generate_solid_color_video(): 生成纯色视频（用于 Mock AI 生成结果）
- generate_test_image(): 生成测试图片
"""

from __future__ import annotations

import os
import subprocess
import tempfile


def _find_ffmpeg() -> str:
    """查找 FFmpeg 可执行文件."""
    for name in ("ffmpeg", "ffmpeg.exe"):
        try:
            subprocess.run(
                [name, "-version"],
                capture_output=True,
                timeout=5,
            )
            return name
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError("未找到 FFmpeg，请先安装并添加到 PATH")


def generate_test_video(
    output_path: str,
    duration: float = 15.0,
    width: int = 640,
    height: int = 360,
    fps: int = 24,
    with_audio: bool = True,
    scene_changes: list[float] | None = None,
) -> str:
    """生成带场景切换的合成测试视频.

    使用 FFmpeg testsrc + color 滤镜生成多个不同颜色的片段，
    模拟真实视频的场景切换效果。

    Parameters
    ----------
    output_path : str
        输出视频路径
    duration : float
        视频总时长（秒）
    width : int
        视频宽度
    height : int
        视频高度
    fps : int
        帧率
    with_audio : bool
        是否生成音频轨道
    scene_changes : list[float], optional
        场景切换时间点（秒），默认均匀分布

    Returns
    -------
    str
        生成的视频文件路径
    """
    ffmpeg = _find_ffmpeg()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 默认场景切换点
    if scene_changes is None:
        segment_dur = 3.0
        scene_changes = []
        t = segment_dur
        while t < duration:
            scene_changes.append(t)
            t += segment_dur

    # 构建复杂滤镜：生成多个不同颜色的片段并拼接
    colors = [
        "red",
        "blue",
        "green",
        "yellow",
        "purple",
        "orange",
        "cyan",
        "white",
    ]

    segments = []
    boundaries = [0.0] + scene_changes + [duration]

    filter_parts = []
    for i in range(len(boundaries) - 1):
        seg_start = boundaries[i]
        seg_end = boundaries[i + 1]
        seg_dur = seg_end - seg_start
        color = colors[i % len(colors)]

        # 每个片段：testsrc 动态源 + 颜色叠加 + 文字标识
        filter_parts.append(f"color=c={color}:s={width}x{height}:d={seg_dur}:r={fps}[c{i}]")
        # 在片段上叠加动态元素（移动的白点）
        filter_parts.append(
            f"[c{i}]drawtext=text='Scene {i}':fontsize=36:fontcolor=white:"
            f"x=(w-text_w)/2:y=(h-text_h)/2[seg{i}]"
        )
        segments.append(f"[seg{i}]")

    # concat 拼接所有片段
    concat_inputs = "".join(segments)
    concat_filter = f"{concat_inputs}concat=n={len(segments)}:v=1:a=0[outv]"

    filter_complex = ";".join(filter_parts + [concat_filter])

    cmd = [
        ffmpeg,
        "-y",
        "-filter_complex",
        filter_complex,
        "-map",
        "[outv]",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
    ]

    if with_audio:
        # 生成正弦波音频
        audio_filters = []
        for i in range(len(boundaries) - 1):
            seg_dur = boundaries[i + 1] - boundaries[i]
            freq = 220 * (1.2**i)  # 递增频率
            audio_filters.append(
                f"sine=frequency={freq}:duration={seg_dur}:sample_rate=44100[a{i}]"
            )
        num_audio_segments = len(boundaries) - 1
        concat_audio = "".join(f"[a{i}]" for i in range(num_audio_segments))
        concat_audio += f"concat=n={num_audio_segments}:v=0:a=1[outa]"
        full_filter = filter_complex + ";" + ";".join(audio_filters) + ";" + concat_audio

        cmd = [
            ffmpeg,
            "-y",
            "-filter_complex",
            full_filter,
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
        ]

    cmd.append(output_path)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")[-500:]
            raise RuntimeError(f"FFmpeg 生成测试视频失败: {stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg 生成测试视频超时") from None

    return output_path


def generate_solid_color_video(
    output_path: str,
    duration: float = 3.0,
    width: int = 640,
    height: int = 360,
    fps: int = 24,
    color: str = "blue",
    label: str = "AI Generated",
) -> str:
    """生成纯色短视频（用于 Mock AI 生成结果）.

    Parameters
    ----------
    output_path : str
        输出路径
    duration : float
        时长（秒）
    width : int
        宽度
    height : int
        高度
    fps : int
        帧率
    color : str
        背景颜色
    label : str
        视频上的文字标签

    Returns
    -------
    str
        生成的视频文件路径
    """
    ffmpeg = _find_ffmpeg()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={width}x{height}:d={duration}:r={fps}",
        "-vf",
        f"drawtext=text='{label}':fontsize=28:fontcolor=white:" f"x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")[-300:]
            raise RuntimeError(f"FFmpeg 生成 Mock 视频失败: {stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg 生成 Mock 视频超时") from None

    return output_path


def generate_test_image(
    output_path: str,
    width: int = 1024,
    height: int = 1024,
    color: str = "gray",
    label: str = "Test Image",
) -> str:
    """生成测试图片.

    Parameters
    ----------
    output_path : str
        输出路径
    width : int
        宽度
    height : int
        高度
    color : str
        背景颜色
    label : str
        图片上的文字

    Returns
    -------
    str
        生成的图片文件路径
    """
    ffmpeg = _find_ffmpeg()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={width}x{height}:d=1",
        "-vf",
        f"drawtext=text='{label}':fontsize=32:fontcolor=white:" f"x=(w-text_w)/2:y=(h-text_h)/2",
        "-frames:v",
        "1",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")[-300:]
            raise RuntimeError(f"FFmpeg 生成测试图片失败: {stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg 生成测试图片超时") from None

    return output_path


def get_temp_dir(prefix: str = "vt_e2e_") -> str:
    """获取临时目录."""
    return tempfile.mkdtemp(prefix=prefix)


if __name__ == "__main__":
    # 快速测试
    tmp = tempfile.mkdtemp(prefix="vt_test_")
    video_path = os.path.join(tmp, "test.mp4")
    generate_test_video(video_path, duration=10.0)
    print(f"测试视频已生成: {video_path}")
    print(f"文件大小: {os.path.getsize(video_path) / 1024:.1f} KB")
