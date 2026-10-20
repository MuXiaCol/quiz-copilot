@echo off
REM QuizCopilot launcher (ASCII only on purpose)
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "run.py"
) else (
    echo Python venv not found. Run setup.ps1 first.
    pause
)
