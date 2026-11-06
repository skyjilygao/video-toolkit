# ============================================================================
# video-toolkit 统一命令入口
#
# 无论使用 CatPaw / Cursor / Trae / CodeBuddy / Claude Code / Copilot，
# 标准动作都通过 `make <target>` 执行，保证跨工具动作一致。
#
# Windows 无 make 时：使用等价脚本 `powershell -File scripts/dev.ps1 <target>`
# ============================================================================

PYTHON ?= python

.PHONY: help install install-dev test test-cov lint format typecheck check clean

help: ## 显示所有可用命令
	@echo "用法: make <target>"
	@echo ""
	@echo "  install       安装核心依赖 (pip install -e .)"
	@echo "  install-dev   安装开发模式依赖 (pip install -e \".[dev]\")"
	@echo "  test          运行全部测试 (pytest)"
	@echo "  test-cov      运行测试并生成覆盖率报告"
	@echo "  lint          Ruff 静态检查并自动修复"
	@echo "  format        Black 格式化"
	@echo "  typecheck     mypy 类型检查"
	@echo "  check         提交前完整检查 (lint + typecheck + test)"
	@echo "  clean         清理缓存与临时产物"

install: ## 安装核心依赖
	$(PYTHON) -m pip install -e .

install-dev: ## 安装开发模式依赖（测试/格式化/Lint）
	$(PYTHON) -m pip install -e ".[dev]"

test: ## 运行全部测试
	$(PYTHON) -m pytest

test-cov: ## 运行测试并生成覆盖率报告
	$(PYTHON) -m pytest --cov=video_toolkit --cov-report=term-missing

lint: ## Ruff 静态检查并自动修复
	$(PYTHON) -m ruff check --fix src/ tests/

format: ## Black 格式化
	$(PYTHON) -m black src/ tests/

typecheck: ## mypy 类型检查
	$(PYTHON) -m mypy src/

check: lint typecheck test ## 提交前完整检查（lint + 类型 + 测试）
	@echo "✅ 检查通过，可以提交"

clean: ## 清理 Python 缓存与测试临时产物
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.mypy_cache']]; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
