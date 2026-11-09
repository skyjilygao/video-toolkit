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
git clone https://github.com/skyjilygao/video-toolkit.git
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

# Dry-Run 全流程测试（本地视频或在线 URL；不调用大模型、不拼接）
video-toolkit dryrun path/to/video.mp4 -o ./dryrun_output
video-toolkit dryrun "https://youtube.com/shorts/xxxxxx" -o ./dryrun_output

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
| youtube | `pip install -e ".[youtube]"` | yt-dlp, youtube-transcript-api |
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

## Testing

### 快速开始

```bash
cd video-toolkit

# 全流程 E2E 测试（30 个用例，无真实 API 请求）
python -m pytest tests/test_e2e_pipeline.py -v --tb=short

# 全量单元测试
python -m pytest tests/ -v --tb=short

# 一键脚本
python run_e2e_test.py
```

### Dry-Run 全流程测试（可复用）

`video-toolkit dryrun` 将完整流程串成一条命令（可复用，更换视频源即可重跑）：

```bash
# 完整流程: 获取视频源 → 分析 → 场景拆解 → 输出大模型调用参数
video-toolkit dryrun path/to/video.mp4 -o ./dryrun_output
video-toolkit dryrun "https://youtube.com/shorts/xxxxxx" -o ./dryrun_output
```

- 输入源：本地路径、YouTube URL（`yt-dlp`）、HTTP(S) 直链
- 在线源下载后自动校验（FFprobe）与失败重试，避免损坏文件进入后续分析；
  `DirectUrlSource` 会拒绝把 HTML 页面当作视频保存
- **不调用大模型**（无真实网络请求）、**不拼接**；全部中间结果写入 `output_dir`，
  其中 `generation/llm_calls.json` 包含每个场景的完整大模型调用参数（含 prompt）

输出目录结构:

```
dryrun_output/
├── README.md                  # 流程摘要
├── downloaded/                # 在线视频下载目录
├── analysis/<video>/          # 分析报告 (analysis.json / summary.md / keyframes/...)
├── decomposition/             # 拆解索引 + 原画面片段
└── generation/
    ├── llm_calls.json         # 全部大模型调用参数（含 prompt）
    ├── llm_calls.md           # 可读版
    └── prompts.txt            # 场景 prompt 列表
```

### 覆盖率跟踪

详见 [TEST_BACKLOG.md](TEST_BACKLOG.md) — 完整的测试跟踪清单：

- ✅ **已覆盖**: E2E 全流程、模型配置驱动、场景拆解、Mock AI 再生、转场拼接
- ❌ **待补充**: TTS 旁白链路、图片动画降级、字幕烧录、BGM 混音、OpenMontage适配、转场多样性、CLI 命令等
- 📋 **缺陷记录**: 测试过程中发现并修复的 6 个 Bug（含根因与修复方案）

### 给后续 Agent 的协作指引

> 如果你是接手本项目的 Agent，请优先阅读 [`TEST_BACKLOG.md`](TEST_BACKLOG.md)：
>
> 1. **了解测试现状**: 查看 "✅ 已测试项" 确认哪些功能稳定可靠
> 2. **认领未完成项**: 从 "❌ 未测试项" 中挑选任务，将 `[ ]` 修改为 `[x] + PR链接`
> 3. **新增测试规范**:
>    - 使用 `tests/fixtures/mock_ai_generator.py` 中的 Mock 类，**绝不调用真实 API**
>    - 测试视频通过 FFmpeg 合成，**不依赖外部文件**
>    - E2E 测试使用 `tmp_path` 隔离，需在 `tests/test_e2e_pipeline.py` 的 `TestE2EPipeline` 类中新增方法
>    - 代码操作必须显式指定 `encoding="utf-8"`（Windows 兼容）
> 4. **Bug 修复必须附测试用例**: 修复同时新增 `test_xxx_regression` 防止回归
> 5. **状态同步**: 完成测试后同步更新 `TEST_BACKLOG.md` 和 pytest.ini 的 markers


## License

[MIT](LICENSE)
