#Requires -Version 7.0
<#
.SYNOPSIS
    打包成单文件 exe：dist\QuizCopilot.exe
.EXAMPLE
    pwsh -File .\build.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    # CI 上没有虚拟环境，退回当前解释器
    $python = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1).Source
}
if (-not $python -or -not (Test-Path $python)) { throw "找不到 Python，先运行 .\setup.ps1" }

& $python -c "import PyInstaller" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "安装 PyInstaller …"
    & $python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 安装失败" }
}

# 这些模块本项目用不到，排除掉能显著减小体积
$excludes = @(
    "tkinter", "unittest", "doctest", "pydoc", "matplotlib", "pandas", "scipy", "IPython",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtNetworkAuth", "PySide6.QtBluetooth",
    "PySide6.QtSensors", "PySide6.QtSerialPort"
)

$pyArgs = @("--noconfirm", "--clean", "--onefile", "--noconsole", "--name", "QuizCopilot")
foreach ($m in $excludes) { $pyArgs += @("--exclude-module", $m) }
$pyArgs += "run.py"

Write-Host "开始打包 …"
& $python -m PyInstaller @pyArgs
if ($LASTEXITCODE -ne 0) { throw "打包失败" }

$exe = Join-Path $root "dist\QuizCopilot.exe"
if (-not (Test-Path $exe)) { throw "打包失败：找不到 $exe" }

$mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "完成：$exe  ($mb MB)" -ForegroundColor Green
