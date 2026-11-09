# AGENTS.md — AI Agent 开发规则

本文档为 AI Agent / Coding Assistant 提供项目开发 video-toolkit 时必须遵守的规则。任何 AI 助手或自动化工具在处理本项目的代码时，必须严格遵循以下规则。

---

## 0. 通用协作规则（最高优先级）

> 本文件是 video-toolkit 开发规则的**唯一事实来源（SSOT）**。CatPaw、Cursor、Trae、CodeBuddy、Claude Code、Copilot、Windsurf 等 AI 工具均通过各自配置文件引用本文件，切换工具不改变开发模式。

- **语言选择**：开发前必须先确认使用哪种开发语言，并严格遵守该语言的开发规范、标准框架布局。禁止所有代码写在一个文件内、搜索文件散落同一目录等反模式。
- **备份**：修改任何代码文件前必须先备份，格式 `原文件名.bak{yyyyMMddHHmm}`，与源文件同目录（详见 3.1）
- **变更说明**：修改后必须给出修改依据（为什么改、改了什么）与影响范围（哪些模块/功能受影响）（详见 3.2）
- **沟通语言**：所有信息用中文沟通（代码注释可中英混合）

---

## 1. 项目概述

**video-toolkit** 是一个视频拆解与生成工具，核心功能包括：
- 视频分析（场景检测、关键帧提取、语音转录、运动分类、节奏分析）
- 视频拆解（按场景/间隔切割）
- 视频合成（片段拼接+转场）
- AI 辅助生成（图片、视频、音频）

**核心设计理念**：适配器模式 — 分析功能通过 `BaseAnalysisAdapter` 抽象基类定义统一接口，不同后端（custom / openmontage）各自实现。

---

## 2. 项目结构规则

```
video-toolkit/
├── pyproject.toml          # PEP 621 项目配置（依赖、元数据、构建入口）
├── README.md               # 项目说明文档
├── LICENSE                 # MIT 许可证
├── AGENTS.md               # 本文件 —— AI 开发规则
├── requirements.txt        # 兼容性依赖清单（pip install -r 使用）
├── src/
│   └── video_toolkit/
│       ├── __init__.py     # 导出 __version__
│       ├── __main__.py     # python -m video_toolkit 入口
│       ├── cli.py          # Click CLI 入口（video-toolkit / vt 命令）
│       ├── config.py       # 全局配置管理
│       ├── core/           # 底层视频操作（VideoAnalyzer —— OpenCV/FFmpeg 封装）
│       ├── analysis/       # 适配器层
│       │   ├── base.py         # BaseAnalysisAdapter 抽象基类 + analyze() 高层入口
│       │   ├── manager.py      # AnalysisManager（适配器注册与发现）
│       │   ├── exporter.py     # AnalysisExporter（报告文件导出）
│       │   ├── custom_adapter.py  # 纯本地实现适配器
│       │   └── openmontage_adapter.py  # OpenMontage 适配器（含自动安装）
│       ├── models/         # Pydantic 数据模型
│       │   ├── analysis.py     # AnalysisBrief, SceneBrief, TranscriptResult 等
│       │   ├── video.py        # VideoMetadata 等
│       │   └── composition.py  # CompositionConfig 等
│       ├── composition/    # 视频合成
│       ├── decomposition/  # 视频拆解
│       └── ai/             # AI 生成服务（FAL, OpenAI, ElevenLabs）
├── tests/                  # pytest 测试
└── docs/                   # 额外文档
```

**规则**：
- 所有源代码必须在 `src/video_toolkit/` 下，不允许直接在根目录放模块
- 新增适配器必须放在 `src/video_toolkit/analysis/` 下并注册到 `manager.py`
- 模型变更必须更新 `models/analysis.py` 中对应的 Pydantic 类
- 禁止修改 `src/video_toolkit.egg-info/` 目录（自动生成）

---

## 3. 代码修改规则

### 3.1 备份规则（强制）
**修改任何代码文件前必须先备份**：
- 备份格式：`原文件名.bak{yyyyMMddHHmm}`
- 示例：修改 `cli.py` → 备份为 `cli.py.bak202611041620`
- 备份必须与源文件在同一目录

### 3.2 修改后要求
- 必须给出**修改依据**（为什么改、改了什么）
- 必须给出**影响范围**（哪些模块/功能会受影响）
- 信息必须用中文沟通，代码注释可中英混合

### 3.3 代码风格
- Python 版本最低要求：3.14.5（`pyproject.toml` 中 `requires-python = ">=3.14.5"`）
- 行宽：100 字符（`black` 和 `ruff` 统一配置）
- 类型注解：所有公共函数必须有类型提示
- 字符串风格：优先使用 f-string，避免 % 格式化
- Import 顺序：标准库 → 第三方 → 项目内部（`ruff` 自动排序）

### 3.4 数据模型规则
- 所有分析结果模型使用 Pydantic v2（`pydantic>=2.0`）
- 字段使用 `Field(default_factory=...)` 提供默认值
- 枚举类型使用 `Literal[...]` 定义
- 类必须包含 docstring 说明

### 3.5 错误处理规则
- 适配器方法必须有 `try-except` 包裹，失败时必须提供降级方案
- 禁止静默吞掉异常 — 至少用 `console.print("[dim]...[/dim]")` 输出调试信息
- 外部命令（subprocess）必须设置 `timeout` 参数
- 文件操作必须使用 `encoding="utf-8"`

---

## 4. 适配器开发规则

### 4.1 创建新适配器
1. 继承 `BaseAnalysisAdapter`
2. 实现抽象方法：`transcribe()`, `detect_scenes()`, `extract_keyframes()`
3. 可选重写：`classify_motion()`, `analyze_audio_energy()`, `compute_pacing()`
4. 使用 `@register_adapter("name")` 装饰器注册
5. 在 `pyproject.toml` 的 `optional-dependencies` 中添加对应依赖分组

### 4.2 适配器降级原则
- OpenMontage 适配器必须提供 `_fallback_*` 系列方法作为降级方案
- 降级逻辑使用 `CustomAdapter` 的本地实现
- 降级失败返回空结果而非抛异常

### 4.3 自动安装逻辑
- OpenMontage 适配器的 `_discover_openmontage()` 必须包含自动 clone 逻辑
- 自动安装仅执行一次（后续发现路径后不再重复）
- 安装过程必须有 4 步：clone → install deps → verify → add to sys.path

---

## 5. 导出报告规则

### 5.1 输出目录结构
每次分析必须按视频文件名创建独立子目录：
```
<output_dir>/
└── <video_basename>/         # 自动以视频文件名创建
    ├── analysis.json
    ├── summary.md
    ├── transcript.txt / .json
    ├── scenes.json
    ├── pacing.json
    └── keyframes/
```

**规则**：
- 子目录名从视频文件名推导（去除扩展名，替换不安全字符）
- 关键帧图片必须复制到报告目录下的 `keyframes/` 子目录
- JSON 文件必须使用 `ensure_ascii=False` + `indent=2`

### 5.2 文件名安全化
- 使用 `_sanitize_name()` / `_derive_video_subdir()` 函数处理
- 不安全字符替换为下划线：`re.sub(r'[^\w\u4e00-\u9fff\-.]', '_', stem)`
- 连续下划线合并：`re.sub(r'_+', '_', safe)`
- 空文件名降级为 `"untitled"`

---

## 6. 依赖管理规则

### 6.1 添加新依赖
1. 在 `pyproject.toml` 的 `[project.dependencies]` 或 `[project.optional-dependencies]` 中添加
2. 同步在 `requirements.txt` 中添加（保持兼容）
3. 标注用途说明

### 6.2 依赖分组
| 分组 | 说明 |
|---|---|
| audio | 音频分析（librosa, soundfile） |
| whisper | 语音转录（faster-whisper） |
| openmontage | OpenMontage 完整工具链 |
| ai | AI 生成服务 |
| dev | 开发工具（测试/Lint） |
| all | 全部运行时可选依赖 |

### 6.3 版本约束
- 使用 `>=` 指定最低兼容版本
- 避免使用 `==` 或 `<` 限制（除非已知冲突）
- `av` 包特别注意：`>=11` 且与 `faster-whisper` 版本兼容

---

## 7. CLI 规则

### 7.1 命令结构
- 使用 `click` 框架，命令组通过 `@main.command()` 定义
- 命令帮助文本使用 `\b` 保持段落格式
- 所有路径参数使用 `type=click.Path(exists=True)` 验证

### 7.2 输出规范
- 使用 `rich.console.Console` 输出彩色信息
- 使用 `rich.table.Table` 展示表格数据
- 错误信息使用 `[red]` 标签
- 调试信息使用 `[dim]` 标签

### 7.3 适配器选择逻辑
`auto` 模式的选择优先级：
1. 检查 `_find_openmontage_path()` 是否返回有效路径
2. 是 → 使用 `openmontage`
3. 否 → 降级为 `custom`
4. 用户显式选择时不经过 auto 逻辑

---

## 8. 测试规则

### 8.1 测试文件放置
- 测试文件在 `tests/` 目录下，模块结构镜像 `src/`
- 测试文件命名：`test_*.py`
- 测试函数命名：`test_*`

### 8.2 运行测试
```bash
# 全部测试
python -m pytest

# 指定模块
python -m pytest tests/test_core/

# 覆盖率
python -m pytest --cov=video_toolkit
```

### 8.3 端到端测试
CLI 内置 `test` 命令执行端到端验证，按阶段验证：元数据 → 场景检测 → 拆解 → 合成。

---

## 9. Git 提交规则

### 9.1 Commit Message 格式
```
<type>: <中文描述>

<可选的详细说明>
```

类型：
- `feat`: 新功能
- `fix`: 修复
- `refactor`: 重构
- `docs`: 文档
- `chore`: 构建/依赖
- `test`: 测试

### 9.2 版本 Tag
- 使用语义版本：`v0.1.0`, `v0.2.0` 等
- Tag 在功能稳定后打

---

## 10. 安全规则

### 10.1 禁止事项
- 禁止在代码中硬编码 API Key 或 Token
- 禁止将 `.env` 等敏感文件提交到 Git
- 禁止在日志/输出中打印完整密钥
- 禁止未经验证直接执行外部脚本

### 10.2 子进程安全
- `subprocess.run()` 必须设置 `timeout`
- 不直接将用户输入拼接到 shell 命令中（使用列表形式传参）
- Git clone 必须使用 `--depth 1` 浅克隆节省带宽

---

## 11. OpenMontage 适配器特殊规则

### 11.1 路径查找优先级
1. `OPENMONTAGE_PATH` 环境变量
2. video-toolkit 同级目录 `OpenMontage/`
3. Python 导入探测（`import tools.analysis`）
4. 常见位置（`~/OpenMontage` 等）

### 11.2 自动安装触发条件
- `_find_openmontage_path()` 返回 `None` 时
- 自动安装目标：`video-toolkit` 同级目录下的 `OpenMontage/`

### 11.3 Av 包兼容性
- `av>=19` 移除了 `metadata_errors` 参数
- `faster_whisper.audio` 中若出现该参数需手动移除修复
- 建议使用 `av>=11` 而非固定为最新版

---

## 12. 文档维护

### 12.1 必须同步修改的文档
- 新增 CLI 命令 → 更新 `README.md`
- 新增数据模型 → 更新 `AGENTS.md` 数据模型部分
- 新增依赖 → 更新 `pyproject.toml` + `requirements.txt` + `README.md`
- 修改导出结构 → 更新 `AGENTS.md` 第 5 节

### 12.2 注释要求
- 所有公共类/方法必须有 docstring
- 关键算法步骤需要行内注释
- 适配器方法来源标注（如 `# 来自 OpenMontage tools/analysis/scene_detect.py`）

---

## 速查表

> 统一命令入口：优先使用 `make <target>`（Windows 无 make 时用 `powershell -File scripts/dev.ps1 <target>`），保证跨 AI 工具动作一致。

| 操作 | 命令 |
|---|---|
| 统一入口 | `make <target>` / `powershell -File scripts/dev.ps1 <target>` |
| 安装开发模式 | `make install-dev` |
| 运行测试 | `make test` |
| 覆盖率报告 | `make test-cov` |
| 代码格式化 | `make format` |
| 静态检查修复 | `make lint` |
| 类型检查 | `make typecheck` |
| 提交前完整检查 | `make check` |
| 清理缓存 | `make clean` |
| 分析视频 | `video-toolkit analyze video.mp4 --report-dir ./output` |
| 查看可用模型 | `video-toolkit list-models` |
| 查看版本 | `video-toolkit --version` |
| 适配器列表 | 查看 `src/video_toolkit/analysis/` 下注册器 |
