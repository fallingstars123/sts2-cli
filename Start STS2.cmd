@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\python\pythonw.exe" (
    echo Download and fully extract the Windows portable release ZIP from GitHub Releases.
    echo https://github.com/fallingstars123/sts2-cli/releases/latest
    pause
    exit /b 1
)
set "PYTHONHOME=%~dp0runtime\python"
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
start "" "%~dp0runtime\python\pythonw.exe" -B -X utf8 "%~dp0STS2 Launcher.pyw"
