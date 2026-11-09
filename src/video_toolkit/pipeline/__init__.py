"""流程编排模块 — 端到端流水线与 Dry-Run.

提供:

- :mod:`video_toolkit.pipeline.dry_run` — 全流程 Dry-Run（不调用大模型、不拼接）
"""

from video_toolkit.pipeline.dry_run import DryRunReport, run_dry_run

__all__ = ["DryRunReport", "run_dry_run"]
