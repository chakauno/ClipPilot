@echo off
setlocal
cd /d "%~dp0"
title ClipPilot - Check PC Requirements
echo CLIPPILOT PC CHECK
echo.
echo Checking Python virtual environment...
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" --version
  ".venv\Scripts\python.exe" -c "import streamlit, yt_dlp, faster_whisper; print('Python dependencies: OK')"
) else (
  echo Not installed yet: run 01_INSTALL_CLIPPILOT_WINDOWS.bat
)
echo.
echo Checking FFmpeg...
where ffmpeg
where ffprobe
echo.
echo Checking optional Deno runtime...
if exist ".venv\Scripts\deno.exe" (
  ".venv\Scripts\deno.exe" --version
) else (
  where deno
)
echo.
echo Done. If something is missing, run 01_INSTALL_CLIPPILOT_WINDOWS.bat.
pause
