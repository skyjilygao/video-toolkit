"""测试配置与 fixtures."""

import os

import pytest


def get_test_video_dir():
    """获取测试视频目录."""
    return os.environ.get(
        "TEST_VIDEO_DIR",
        r"\\192.168.88.121\.n8n-files\video_download\video\2026-11-02\20261102",
    )


def find_test_video():
    """查找一个测试视频."""
    from pathlib import Path

    test_dir = get_test_video_dir()
    if not os.path.exists(test_dir):
        return None

    for f in Path(test_dir).rglob("*.mp4"):
        return str(f)
    return None


@pytest.fixture
def test_video_dir():
    """测试视频目录 fixture."""
    return get_test_video_dir()


@pytest.fixture
def test_video():
    """单个测试视频 fixture."""
    return find_test_video()


@pytest.fixture
def skip_if_no_video(test_video):
    """如果没有测试视频则跳过."""
    if test_video is None:
        pytest.skip("未找到测试视频，请设置 TEST_VIDEO_DIR 环境变量")
    return test_video
