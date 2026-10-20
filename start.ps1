#Requires -Version 7.0
<#
.SYNOPSIS
    运行 QuizCopilot（不打包，直接从源码跑）。
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) { throw "找不到虚拟环境，先运行 .\setup.ps1" }

if (Test-Path $pythonw) {
    Start-Process -FilePath $pythonw -ArgumentList (Join-Path $root "run.py") -WorkingDirectory $root
} else {
    & $python (Join-Path $root "run.py")
}
