# 测试跟踪清单 (Test Backlog)

> **维护说明**: 本文档跟踪 video-toolkit 项目的测试覆盖情况。
> 每次运行 `python -m pytest tests/ -v` 后，更新对应条目状态。
>
> **状态图例**:
> - [x] ✅ 已完成 — 有测试用例且通过
> - [ ] ❌ 未完成 — 尚未编写测试
> - [~] 🔶 部分完成 — 有测试但覆盖不全

---

## 📊 总体覆盖率

| 测试类型 | 覆盖状态 | 通过率 |
|---------|---------|--------|
| 单元测试 | [x] ✅ | 见 `pytest tests/test_models/` 等 |
| 集成测试 (E2E Pipeline) | [x] ✅ | 30/30 PASS |
| 全链路 Mock 测试 | [x] ✅ | 29.6s |

**覆盖流程**: 视频合成 → 场景分析 → 拆解 → AI Mock 生成 → 转场拼接 → 输出

---

## ✅ 已测试项 (Covered)

### E2E 全流程 (`tests/test_e2e_pipeline.py`)

- [x] **Stage 1 - 测试视频生成**: FFmpeg 合成含音频的多场景 MP4
- [x] **Stage 2 - 视频分析**: CustomAdapter 场景检测、关键帧提取、JSON 序列化/反序列化
- [x] **Stage 3 - 视频拆解**: VideoDecomposer 按片段切割、decomposition_index.json 保存
- [x] **Stage 4 - Mock AI 生成**: MockSeedanceGenerator、MockImageGenerator 独立测试、Provider 注册
- [x] **Stage 5 - 完整再生流水线**: 3 场景 `video_first` 模式 + `fade` 转场 + prompts 保存
- [x] **Stage 5 - 输出视频校验**: 640×360@24fps、8.4s 时长、MP4 有效性
- [x] **Stage 6 - 模型配置驱动**: YAML 加载、video/image 模型查询、ID 反向查找
- [x] **Stage 7 - 边界场景**: 空场景、单场景再生、dry-run mode、空片段合成

### 单元测试 (tests/test_generation.py)

- [x] PromptEngine: build_scene_prompt (full/modular/minimal)
- [x] PromptEngine: build_all_prompts, narration_script
- [x] PromptEngine: moderate_prompt_content
- [x] RegenerationConfig 默认值
- [x] SceneGenerationTask 状态机
- [x] GenerationAdapter: init、filter_scenes (all/first_n/indices)
- [x] GenerationAdapter: estimate_cost, derive_style_prefix

### 单元测试 (tests/test_composition/)

- [x] VideoComposer: 单片段合成、concat 模式、过渡合成、空输入

### 单元测试 (tests/test_decomposition/)

- [x] VideoDecomposer: 按场景拆解、按时间拆解、索引 JOSN

### 单元测试 (tests/test_ai/)

- [x] AIGeneratorManager: Provider 注册、自动选择、列出 providers

### 单元测试 (tests/test_models/)

- [x] VideoMetadata、SceneInfo 等模型验证

### 单元测试 (tests/test_core/)

- [x] Analyzer 基础功能

---

## ❌ 未测试项 (TODO)

### 🔴 高优先级 — 核心业务链路

- [ ] **TTS 旁白合成完整链路** (`audio_mode="tts_narration"` + Mock TTS)
  - `_generate_tts()` → `_mix_audio()` 全流程无测试
  - 需要 Mock TTS Provider（如 MockElevenLabsGenerator）
  - 预期: TTS 文本从 prompts 生成 → 合成音频 → 混入输出视频

- [ ] **`image_animation` 降级模式** (`generation_mode="image_animation"`)
  - `custom_adapter.py:247` 行 FLUX 图片 + Ken Burns 效果 从未走到
  - Mock 图片生成后 → FFmpeg zoompan 动态 → 输出视频

- [ ] **场景筛选：random / manual 模式** (`scene_selection="random"|"manual"`)
  - 只测了 `"first_n"` 和 `"all"`
  - `_filter_scenes` 中 random 种子确定性、manual 下 indices 合法性需验证

- [ ] **字幕烧录** (`burn_subtitles=True`)
  - `subtitle_style`、`subtitle_font_size`、`subtitle_color` 参数透传
  - FFmpeg `drawtext` 滤镜实际渲染效果验证

- [ ] **背景音乐混合** (`add_music=True`)
  - `composer.py: _add_background_music` 从不被触发
  - `custom_adapter.py: _mix_audio` 仅在 tts_narration 模式使用

### 🟡 中优先级 — 适配器/模块

- [ ] **OpenMontageGenerationAdapter 全流程** (`generation/openmontage_adapter.py`)
  - 20+ 方法完全未测（风格映射、场景转换、TTS、clip 合成等）
  - `validate_environment` → `regenerate` 完整路径

- [ ] **OpenMontage 分析适配器** (`analysis/openmontage_adapter.py`)
  - E2E 只用了 CustomAdapter，OpenMontage 分析路径完全未测

- [ ] **PromptEngine layer 模式**
  - `build_scene_prompt(layer_mode="subject")` 未独立测试
  - `build_scene_prompt(layer_mode="minimal")` 未独立测试

- [ ] **多种转场效果** (非 fade 的 11 种效果)
  - wipeleft/wiperight/wipedown/wipeup
  - slideleft/slideright/slideup/slidedown
  - dissolve/zoomin/zoomout/crossfade

- [ ] **多分辨率/帧率输出**
  - 只测 640×360@24fps
  - 未测: 1920×1080@30fps、1280×720@25fps 等常见配置

- [ ] **Whisper 转录端到端**
  - 当前测试 `extract_transcript=False` 跳过了
  - 需要 mock Whisper 模型或预设音频文件

- [ ] **音频能量分析**
  - 当前测试 `extract_audio_energy=False` 跳过了
  - `AudioEnergyProfile.recommended_offset_seconds` 推导逻辑

- [ ] **AnalysisExporter 报告导出**
  - 按视频文件名自动创建子目录未验证
  - summary.md / transcript.txt / scenes.json 等输出

### 🟢 低优先级 — 鲁棒性/辅助

- [ ] **CLI 全命令测试** (`cli.py`)
  - `info`, `analyze`, `decompose`, `compose`, `ai` 五个子命令

- [ ] **Generation Manager 多 Provider 调度** (`generation/manager.py`)

- [ ] **重试逻辑** (`max_retries > 0`)
  - Mock 生成失败 → 自动重试 → 成功/最终失败

- [ ] **中间文件清理** (`keep_segments=False`)
  - 临时文件是否按预期删除

- [ ] **成本估算准确性**
  - `estimate_cost` 返回值与模型配置中 pricing 的对应关系

- [ ] **不同输入格式** (MOV/AVI/MKV/WEBM)
  - 只测 MP4 输入

- [ ] **长视频处理** (>60s)
  - 片段时长裁剪 (max_clip_duration) 的实际效果

- [ ] **并发安全**
  - 多实例/多线程同时分析不同视频

---

## 📋 缺陷修复记录 (测试过程中发现)

| 日期 | 问题 | 根因 | 修复 |
|------|------|------|------|
| 2026-11-05 | Pydantic 验证失败 | 用 `type("SceneInfo",(),{})` 动态构造不被 Pydantic 识别 | 改用真实 `SceneInfo` 具名参数 |
| 2026-11-05 | JSON 解码失败 | Windows GBK 读取 UTF-8 中文 JSON | `open(..., encoding="utf-8")` |
| 2026-11-05 | mock provider 不被识别 | `validate_environment()` 创建新 Manager 绕过注入 | 复用 `self._ai_manager` |
| 2026-11-05 | shutil.copy2 失败 | 目标目录不存在 | 复制前 `os.makedirs(..., exist_ok=True)` |
| 2026-11-05 | xfade 合成匹配无流 | mock 视频无音频但滤镜要求 `[0:a]` | 新增 `_has_audio_stream` 检测, 无音频用 `-an` |
| 2026-11-05 | CompositionConfig 缺音频模式 | 无法区分 mute/tts/original | 新增 `audio_mode` 字段透传 |

---

## 🚀 运行测试

```bash
cd video-toolkit

# 全流程 E2E 测试 (推荐)
python -m pytest tests/test_e2e_pipeline.py -v --tb=short -s

# 单元测试 (全量)
python -m pytest tests/ -v --tb=short

# 一键脚本
python run_e2e_test.py
```

---

## 🤝 如何补充测试

1. 从未测试项中挑选一个，创建对应测试函数
2. 使用 `tests/fixtures/mock_ai_generator.py` 中的 Mock 类避免真实 API
3. 使用 `tests/fixtures/mock_video.py` 生成测试媒体
4. 运行: `python -m pytest tests/test_e2e_pipeline.py::TestClass::test_new -v -s`
5. 验证通过后，更新本文档将 `[ ]` → `[x]`
