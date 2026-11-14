@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ClipPilot - TikTok Clip Creator
cls
if not exist ".venv\Scripts\python.exe" (
    echo ClipPilot is not installed yet.
    echo Double-click 01_INSTALL_CLIPPILOT_WINDOWS.bat first.
    pause
    exit /b 1
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo FFmpeg is missing. Run 01_INSTALL_CLIPPILOT_WINDOWS.bat again.
    pause
    exit /b 1
)
where ffprobe >nul 2>&1
if errorlevel 1 (
    echo FFprobe is missing. Run 01_INSTALL_CLIPPILOT_WINDOWS.bat again.
    pause
    exit /b 1
)
REM Make the Deno executable installed by pip easy for yt-dlp to find.
set "PATH=%CD%\.venv\Scripts;%PATH%"
echo ===========================================
echo ClipPilot is opening in your web browser.
echo If it does not open, visit http://localhost:8501
echo Keep this black window open while using ClipPilot.
echo Close the window when you are finished.
echo ===========================================
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless false
if errorlevel 1 (
  echo.
  echo Could not launch ClipPilot. Please try running setup again.
  pause
)
