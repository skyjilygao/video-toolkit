"""分析报告导出器 — 将 AnalysisBrief 导出为多种格式便于人工检查."""

from __future__ import annotations

import json
import os
import re

from video_toolkit.models.analysis import AnalysisBrief


def _sanitize_name(name: str) -> str:
    """将视频文件名转换为安全的目录名."""
    # 移除扩展名
    stem = os.path.splitext(name)[0]
    # 替换不安全字符为下划线
    safe = re.sub(r"[^\w\u4e00-\u9fff\-.]", "_", stem)
    # 去除连续下划线
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "untitled"


class AnalysisExporter:
    """分析报告导出器.

    导出目录结构::

        output_dir/
        └── <video_name>/           # 按视频名自动创建子目录
            ├── analysis.json       # 完整分析数据 (JSON)
            ├── summary.md          # 人工可读摘要 (Markdown)
            ├── transcript.txt      # 字幕/转录纯文本
            ├── transcript.json     # 字幕/转录结构化数据
            ├── scenes.json         # 场景列表
            ├── keyframes/          # 关键帧图片目录
            │   ├── keyframe_0000.jpg
            │   ├── keyframe_0001.jpg
            │   └── ...
            └── pacing.json         # 节奏特征
    """

    def __init__(self, brief: AnalysisBrief, output_dir: str, subdir: str | None = None):
        self.brief = brief
        # 自动根据视频文件名推导子目录名
        if subdir:
            self.output_dir = os.path.join(output_dir, subdir)
        else:
            video_basename = os.path.basename(brief.video_path)
            safe_name = _sanitize_name(video_basename)
            self.output_dir = os.path.join(output_dir, safe_name)

    def save_all(self) -> dict:
        """导出所有报告文件.

        Returns
        -------
        dict
            导出的文件路径列表.
        """
        os.makedirs(self.output_dir, exist_ok=True)
        saved = {}

        # 1. 完整 JSON (程序消费)
        saved["json"] = self.save_json()

        # 2. Markdown 摘要 (人工速览)
        saved["markdown"] = self.save_markdown()

        # 3. 字幕 (纯文本 + JSON)
        if self.brief.transcript.has_transcript:
            saved["transcript_txt"] = self.save_transcript_text()
            saved["transcript_json"] = self.save_transcript_json()

        # 4. 场景列表
        if self.brief.scenes:
            saved["scenes"] = self.save_scenes()

        # 5. 节奏
        if self.brief.pacing:
            saved["pacing"] = self.save_pacing()

        # 6. 复制关键帧到报告目录
        if self.brief.keyframes:
            saved["keyframes_dir"] = self.copy_keyframes_to_report()

        return saved

    def save_json(self) -> str:
        """保存完整分析结果为 JSON."""
        file_path = os.path.join(self.output_dir, "analysis.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(
                self.brief.model_dump(),
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        return file_path

    def save_markdown(self) -> str:
        """生成 Markdown 格式的可读摘要."""
        lines = []
        b = self.brief

        lines.extend(
            [
                "# 视频分析报告",
                "",
                f"- **适配器**: {b.adapter}",
                f"- **视频**: `{b.video_path}`",
                f"- **时长**: {b.duration_seconds:.1f}s",
                f"- **分析耗时**: {b.duration_analyzed:.1f}s",
                f"- **生成时间**: {b.analyzed_at}",
                "",
            ]
        )

        # 节奏
        if b.pacing:
            lines.append("## 节奏特征")
            lines.append("")
            p = b.pacing
            lines.extend(
                [
                    "| 指标 | 值 |",
                    "|------|-----|",
                    f"| 节奏风格 | {p.pacing_style} |",
                    f"| 平均场景时长 | {p.avg_scene_duration_seconds:.1f}s |",
                    f"| 最短场景 | {p.shortest_scene_seconds:.1f}s |",
                    f"| 最长场景 | {p.longest_scene_seconds:.1f}s |",
                    f"| 剪辑频率 | {p.cuts_per_minute:.1f} cuts/min |",
                    "",
                ]
            )

        # 场景
        if b.scenes:
            lines.append(f"## 场景列表 ({len(b.scenes)} 个)")
            lines.append("")
            lines.append("| ID | 开始 | 结束 | 时长 | 运动类型 | 光流方差 |")
            lines.append("|-----|------|------|------|----------|----------|")
            for s in b.scenes:
                fv = f"{s.flow_variance:.2f}" if s.flow_variance >= 0 else "N/A"
                lines.append(
                    f"| {s.scene_index} | {s.start_time:.1f}s | {s.end_time:.1f}s | "
                    f"{s.duration:.1f}s | {s.motion_type} | {fv} |"
                )
            lines.append("")

        # 关键帧
        if b.keyframes:
            lines.append(f"## 关键帧 ({len(b.keyframes)} 个)")
            lines.append("")
            for i, kf in enumerate(b.keyframes):
                rel_path = os.path.relpath(kf.path, self.output_dir)
                kf_in_dir = os.path.join(self.output_dir, "keyframes", os.path.basename(kf.path))
                if os.path.exists(kf_in_dir):
                    rel_path = f"keyframes/{os.path.basename(kf.path)}"
                lines.append(
                    f"- **#{i}** t={kf.timestamp:.1f}s | scene={kf.scene_index} | `{rel_path}`"
                )
            lines.append("")

        # 字幕摘要
        if b.transcript.has_transcript:
            lines.append("## 字幕/转录")
            lines.append("")
            lines.append(f"- **语言**: {b.transcript.language}")
            lines.append(f"- **字数**: {b.transcript.word_count}")
            lines.append(f"- **片段数**: {len(b.transcript.segments)}")
            lines.append("")
            preview = b.transcript.full_text[:300]
            if len(b.transcript.full_text) > 300:
                preview += "..."
            lines.append("### 内容预览")
            lines.append("")
            lines.append(f"> {preview}")
            lines.append("")
            lines.append("*详见 `transcript.txt` 获取完整内容*")
            lines.append("")

        content = "\n".join(lines)
        file_path = os.path.join(self.output_dir, "summary.md")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return file_path

    def save_transcript_text(self) -> str:
        """保存字幕为纯文本 (每段一行，便于阅读)."""
        file_path = os.path.join(self.output_dir, "transcript.txt")
        t = self.brief.transcript

        lines = []
        lines.append("# 转录文本")
        lines.append(f"# 语言: {t.language} | 字数: {t.word_count} | 片段: {len(t.segments)}")
        lines.append("")

        if t.segments:
            for seg in t.segments:
                start = self._format_time(seg.start)
                end = self._format_time(seg.end)
                lines.append(f"[{start} --> {end}] {seg.text}")
        else:
            lines.append(t.full_text)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return file_path

    def save_transcript_json(self) -> str:
        """保存字幕结构化数据."""
        file_path = os.path.join(self.output_dir, "transcript.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(
                self.brief.transcript.model_dump(),
                f,
                ensure_ascii=False,
                indent=2,
            )
        return file_path

    def save_scenes(self) -> str:
        """保存场景结构化数据."""
        file_path = os.path.join(self.output_dir, "scenes.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(
                [s.model_dump() for s in self.brief.scenes],
                f,
                ensure_ascii=False,
                indent=2,
            )
        return file_path

    def save_pacing(self) -> str:
        """保存节奏特征."""
        file_path = os.path.join(self.output_dir, "pacing.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(
                self.brief.pacing.model_dump(),
                f,
                ensure_ascii=False,
                indent=2,
            )
        return file_path

    def copy_keyframes_to_report(self) -> str:
        """将关键帧图片复制到报告目录下的 keyframes/ 子目录."""
        kf_dir = os.path.join(self.output_dir, "keyframes")
        os.makedirs(kf_dir, exist_ok=True)

        import shutil

        for i, kf in enumerate(self.brief.keyframes):
            if os.path.exists(kf.path):
                # 使用有意义的命名
                basename = f"keyframe_{i:04d}_s{kf.timestamp:06.2f}.{os.path.splitext(kf.path)[1].lstrip('.')}"
                dest = os.path.join(kf_dir, basename)
                try:
                    shutil.copy2(kf.path, dest)
                except OSError:
                    pass

        return kf_dir

    @staticmethod
    def _format_time(seconds: float) -> str:
        """秒数 -> HH:MM:SS.mmm 格式."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:06.3f}"
        return f"{m:02d}:{s:06.3f}"
