# Video Toolkit

> 视频拆解与生成工具 — Video Decomposition and Generation Toolkit

基于 OpenMontage 理念构建的视频分析与重组工具，支持场景检测、关键帧提取、语音转录、运动分类和节奏分析。

## 功能特性

- **视频分析** — 自动检测场景边界、提取关键帧、分析节奏
- **语音转录** — 集成 faster-whisper，支持多语言语音识别
- **运动分类** — 基于光流分析区分静态图像 / 动态视频片段
- **视频拆解** — 按场景或时间间隔切割视频为片段
- **视频合成** — 拼接片段并添加转场效果、背景音乐
- **AI 辅助** — 集成 FAL.AI / OpenAI / ElevenLabs 生成图片、视频、音频

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-org/video-toolkit.git
cd video-toolkit

# 安装核心依赖
pip install -e .

# 安装 OpenMontage 适配器依赖（可选）
pip install -e ".[openmontage]"

# 安装全部可选依赖
pip install -e ".[all]"
```

### 使用 CLI

```bash
# 查看视频信息
video-toolkit info path/to/video.mp4

# 分析视频（自动选择适配器）
video-toolkit analyze path/to/video.mp4 --report-dir ./output

# 使用 OpenMontage 适配器
video-toolkit analyze path/to/video.mp4 -a openmontage --report-dir ./output

# 按场景拆解视频
video-toolkit decompose path/to/video.mp4 -m scenes -o ./segments

# 合成视频
video-toolkit compose segment1.mp4 segment2.mp4 -o output.mp4

# AI 生成
video-toolkit ai "a sunset over mountains" --type image -o output.png
```

### 使用 Python API

```python
from video_toolkit.analysis import AnalysisManager
from video_toolkit.analysis.openmontage_adapter import OpenMontageAdapter

# 获取适配器实例
adapter = AnalysisManager.get_adapter(
    name="openmontage",
    video_path="path/to/video.mp4",
    output_dir="./output"
)

# 执行完整分析
brief = adapter.analyze(
    depth="standard",
    max_keyframes=20,
    save_report=True
)

# 查看结果
print(f"场景数: {len(brief.scenes)}")
print(f"关键帧数: {len(brief.keyframes)}")
print(f"转录: {brief.transcript.full_text[:200]}")
```

## 输出目录结构

使用 `--report-dir` 时，分析结果自动按视频文件名创建子目录：

```
output/
└── my_video/                    # 以视频文件名命名的子目录
    ├── analysis.json            # 完整分析数据 (JSON)
    ├── summary.md               # 人工可读摘要 (Markdown)
    ├── transcript.txt           # 字幕/转录纯文本
    ├── transcript.json          # 字幕/转录结构化数据
    ├── scenes.json              # 场景列表
    ├── pacing.json              # 节奏特征
    └── keyframes/               # 关键帧图片目录
        ├── keyframe_0000_s01.00.jpg
        ├── keyframe_0001_s03.50.jpg
        └── ...
```

每次分析不同视频时，结果会保存到不同的子目录，互不干扰。

## 依赖说明

### 核心依赖

| 包 | 用途 |
|---|---|
| opencv-python | 视频读写、图像处理 |
| ffmpeg-python | FFmpeg 封装 |
| Pillow | 图像处理 |
| numpy | 数值计算 |
| pydantic | 数据模型验证 |
| click / rich | CLI 框架与 UI |

### OpenMontage 适配器专用依赖

| 包 | 用途 |
|---|---|
| faster-whisper | 语音转录（Whisper 加速版） |
| scenedetect | 场景检测 |
| av | 音视频解码（PyAV） |

### 可选依赖分组

| 分组 | 命令 | 包含 |
|---|---|---|
| audio | `pip install -e ".[audio]"` | librosa, soundfile |
| whisper | `pip install -e ".[whisper]"` | faster-whisper |
| openmontage | `pip install -e ".[openmontage]"` | faster-whisper, scenedetect, av |
| ai | `pip install -e ".[ai]"` | torch, transformers |
| dev | `pip install -e ".[dev]"` | pytest, black, ruff, mypy |
| all | `pip install -e ".[all]"` | 全部可选运行时依赖 |

## 适配器架构

项目采用适配器模式，支持多种分析后端：

| 适配器 | 说明 |
|---|---|
| `custom` | 纯本地 OpenCV + FFmpeg 实现 |
| `openmontage` | 调用 OpenMontage 分析工具链（PySceneDetect + faster-whisper） |

## 环境变量

| 变量 | 说明 |
|---|---|
| `OPENMONTAGE_PATH` | OpenMontage 仓库本地路径 |

## License

[MIT](LICENSE)
