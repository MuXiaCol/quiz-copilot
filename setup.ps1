#Requires -Version 7.0
<#
.SYNOPSIS
    安装运行环境：建虚拟环境 + 装依赖。
.EXAMPLE
    pwsh -File .\setup.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "创建虚拟环境 .venv …"
    $base = $null
    foreach ($cand in @(
        "C:\Users\$env:USERNAME\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe",
        (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    )) {
        if ($cand -and (Test-Path $cand)) { $base = $cand; break }
    }
    if (-not $base) { throw "找不到 Python 3.10+，请先安装并加入 PATH" }
    & $base -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败" }
}

Write-Host "安装依赖 …"
& $python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
& $python -m pip install -r (Join-Path $root "requirements.txt") -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }

Write-Host ""
Write-Host "完成。启动方式：pwsh -File .\start.ps1" -ForegroundColor Green
Write-Host "（或者直接双击 run.cmd）"
