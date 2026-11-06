# Video Toolkit 项目说明

## 一、项目概述
Video Toolkit 是一款功能强大的视频处理工具，支持视频分析拆解、AI全新视频生成、视频拼接转场等全流程操作。核心特性是模块化设计、配置驱动，支持零代码扩展新的AI视频生成模型。

---

## 二、核心业务流程
### 完整工作流：从视频文件到全新AI视频
```
输入视频 → 分析拆解 → [可选]读取历史拆解结果 → 选择AI模型 → 生成新视频片段 → 拼接转场 → 输出最终视频
```

### 流程明细
1. **视频分析**：输入视频文件，生成包含场景、关键帧、镜头语言、风格画像的分析简报（AnalysisBrief）
2. **视频拆解**：按场景/时间间隔拆解视频为片段，生成所有片段文件、关键帧图片、索引文件
3. **模型配置**：读取`~/.video-toolkit/models.config.yml`模型配置文件，自动注册符合要求的AI生成Provider
4. **视频生成**：
   - 优先使用用户选择的模型
   - 支持降级到其他可用模型（Seedance → Kling → FLUX图片+动画）
   - 每个场景独立生成全新视频片段，自动标准化格式
5. **视频拼接**：合并所有生成片段，支持自定义转场、TTS旁白、字幕、背景音乐
6. **输出结果**：生成最终视频，保存生成记录和prompt信息

---

## 三、核心模块说明
### 1. 分析模块 (`src/video_toolkit/analysis`)
- 功能：多维度分析视频，生成统一的AnalysisBrief
- 输出：场景列表、关键帧、字幕、节奏特征、风格画像、镜头语言参数
- 特性：支持自定义分析适配器，兼容OpenMontage分析格式

### 2. 拆解模块 (`src/video_toolkit/decomposition`)
- 功能：按场景/时间间隔/自定义范围拆解视频
- 输出：
  - 视频片段：`/segments/segment_000x.mp4`
  - 关键帧：`/keyframes/keyframe_000x.png`
  - 索引文件：`decomposition_index.json`（包含所有片段的元数据）

### 3. 生成模块 (`src/video_toolkit/generation`)
- 核心驱动：基于分析简报驱动AI生成全新视频
- 模型管理：
  - 完全配置化驱动，新增模型无需修改代码
  - 支持任意OpenAI兼容接口自动适配
  - 支持Seedance/Kling/FLUX等主流视频生成模型
  - 自动降级机制：用户指定模型失败时自动切换其他可用模型
- 生成策略：
  - `video_first`：优先视频生成，失败降级到图片+动画
  - `image_animation`：始终使用FLUX图片+Ken Burns动画

### 4. 拼接模块 (`src/video_toolkit/composition`)
- 功能：合并多个视频片段，添加转场、音频、字幕
- 特性：
  - 支持10种转场效果（淡入淡出、滑动、缩放等）
  - 支持TTS旁白自动生成和混音
  - 支持自定义字幕样式和位置
  - 支持背景音乐添加和音量控制

### 5. 配置模块 (`src/video_toolkit/config`)
- 功能：统一管理所有配置，支持模型配置文件自动加载
- 默认路径：`~/.video-toolkit/models.config.yml`
- 特性：首次运行自动创建默认配置，支持API Key环境变量和直接配置两种方式

---

## 四、使用说明
### 安装依赖
```bash
pip install -r requirements.txt
```

### 核心命令
```bash
# 1. 分析视频
video-toolkit analyze input.mp4 -o analysis.json

# 2. 查看可用模型
video-toolkit list-models

# 3. 生成全新视频（使用指定模型）
video-toolkit regenerate input.mp4 -a analysis.json -o output.mp4 --model seedance-2.5-standard

# 4. dry-run模式预览生成效果
video-toolkit regenerate input.mp4 --dry-run

# 5. 拆分视频
video-toolkit decompose input.mp4 --mode scene -o ./output_dir
```

### 模型配置示例
在`~/.video-toolkit/models.config.yml`中添加：
```yaml
config:
  defaultVideoModel: seedance-2.5-standard
  providers:
    seedance_2_5:
      displayName: "Seedance 2.5"
      apiKeyEnv: SEEDANCE_API_KEY
      baseURL: https://queue.fal.run
      models:
        - id: seedance-2.5-standard
          name: Seedance 2.5标准版
          version: "2.5"
          variant: standard
          supports:
            - text_to_video
```

---

## 五、扩展性说明
1. **新增模型**：只需要在模型配置文件中添加符合要求的Provider和模型配置，无需修改任何代码
2. **新增功能**：采用适配器模式，所有核心功能都支持自定义适配器扩展
3. **接口兼容**：完全兼容OpenAI API协议，任何支持该协议的Provider都可以零成本接入

---

## 六、校验通过的全流程检查点
✅ 分析模块输出包含所有必需的镜头语言字段  
✅ 拆解模块生成的索引文件可被后续流程正确读取  
✅ 模型配置文件自动加载，符合要求的Provider自动注册  
✅ 生成模块优先使用用户选择模型，失败自动降级  
✅ 所有生成的视频片段格式标准化，符合拼接要求  
✅ 拼接模块支持所有配置的转场和音频参数  
✅ 异常处理覆盖所有环节，错误信息清晰提示  
✅ 文件路径管理正确，临时文件自动清理  
✅ 支持历史分析结果复用，无需重复分析

---

## 七、常见问题
**Q: 新增的模型配置后无法识别？**
A: 检查：1. provider的`api`字段是否为`openai-completions`；2. 模型配置中`supports`字段是否包含至少一个生成能力；3. 对应的API Key是否已配置。

**Q: 生成视频失败自动降级？**
A: 已内置降级逻辑：用户指定模型 → Seedance其他版本 → Kling → FLUX图片+动画，无需手动干预。

**Q: 支持自定义OpenAI兼容接口吗？**
A: 完全支持，只需要配置`baseURL`和`defaultModelId`即可，无需开发专用适配器。
