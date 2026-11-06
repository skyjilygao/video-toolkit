# ============================================================================
# video-toolkit unified command entry (Windows PowerShell edition)
#
# Targets are 1:1 with the Makefile; for Windows users / AI agents without make.
# Usage:
#   powershell -File scripts/dev.ps1 <target>
#   .\scripts\dev.ps1 test
#
# NOTE: keep this file ASCII-only (English) - Windows PowerShell 5.1 reads
# UTF-8-without-BOM .ps1 files as ANSI, which breaks CJK/emoji characters.
# ============================================================================

param(
    [Parameter(Position = 0)]
    [string]$Target = "help",

    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

function Show-Help {
    Write-Host "Usage: scripts/dev.ps1 <target>" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  install       Install core dependencies"
    Write-Host "  install-dev   Install dev dependencies (test/format/lint)"
    Write-Host "  test          Run all tests"
    Write-Host "  test-cov      Run tests with coverage report"
    Write-Host "  lint          Ruff static check with auto-fix"
    Write-Host "  format        Black formatting"
    Write-Host "  typecheck     mypy type check"
    Write-Host "  check         Full pre-commit check (lint + typecheck + test)"
    Write-Host "  clean         Remove caches and temp artifacts"
}

function Invoke-Python {
    param([string[]]$Arguments)
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Target) {
    "help" { Show-Help }
    "install" { Invoke-Python @("-m", "pip", "install", "-e", ".") }
    "install-dev" { Invoke-Python @("-m", "pip", "install", "-e", ".[dev]") }
    "test" { Invoke-Python @("-m", "pytest") }
    "test-cov" { Invoke-Python @("-m", "pytest", "--cov=video_toolkit", "--cov-report=term-missing") }
    "lint" { Invoke-Python @("-m", "ruff", "check", "--fix", "src/", "tests/") }
    "format" { Invoke-Python @("-m", "black", "src/", "tests/") }
    "typecheck" { Invoke-Python @("-m", "mypy", "src/") }
    "check" {
        Invoke-Python @("-m", "ruff", "check", "--fix", "src/", "tests/")
        Invoke-Python @("-m", "pytest")
        Write-Host "All checks passed, ready to commit" -ForegroundColor Green
    }
    "clean" {
        $cleanScript = @'
import shutil
import pathlib
for p in ['.pytest_cache', '.mypy_cache']:
    shutil.rmtree(p, ignore_errors=True)
for p in pathlib.Path('.').rglob('__pycache__'):
    shutil.rmtree(p, ignore_errors=True)
'@
        Invoke-Python @("-c", $cleanScript)
    }
    default {
        Write-Host "Unknown target: $Target" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
