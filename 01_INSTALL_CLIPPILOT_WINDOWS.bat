@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ClipPilot - First Time Windows Setup
cls
echo =========================================
echo       CLIPPILOT - WINDOWS SETUP
echo =========================================
echo.
echo This setup only needs to be completed once.
echo Your computer needs internet for installing packages.
echo.

REM Prefer Python 3.12 for compatibility with speech recognition.
set "PYTHON_CMD="
py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.12"
if not defined PYTHON_CMD (
    python -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo [!] Python 3.12 is not detected on this computer.
    echo.
    echo First install Python 3.12 from this official website:
    echo https://www.python.org/downloads/release/python-31210/
    echo IMPORTANT: Check "Add python.exe to PATH" during installation.
    echo Then close this window and run this setup file again.
    echo.
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)
echo [OK] Found Python 3.12.
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating a private Python environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto failed
) else (
    echo [1/3] Python environment already exists.
)

echo.
echo [2/3] Installing ClipPilot packages. The first install can take time.
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo.
echo [3/3] Checking for FFmpeg and FFprobe...
where ffmpeg >nul 2>&1
if errorlevel 1 goto missing_ffmpeg
where ffprobe >nul 2>&1
if errorlevel 1 goto missing_ffmpeg
echo [OK] FFmpeg and FFprobe found.
goto success

:missing_ffmpeg
echo [!] FFmpeg is required to create MP4 files.
echo.
where winget >nul 2>&1
if errorlevel 1 goto ffmpeg_manual
choice /C YN /M "Install FFmpeg with Windows Package Manager now"
if errorlevel 2 goto ffmpeg_manual
winget install --id Gyan.FFmpeg --exact --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto ffmpeg_manual
echo.
echo FFmpeg installation was requested.
echo Close this window and run the setup AGAIN so the new PATH is found.
pause
exit /b 0

:ffmpeg_manual
echo Please install FFmpeg, which includes ffprobe.
echo Official install info: https://ffmpeg.org/download.html
start "" "https://ffmpeg.org/download.html"
echo After installing, close this window and run setup again.
pause
exit /b 1

:success
echo.
echo =========================================
echo [SUCCESS] ClipPilot is installed on your PC.
echo NEXT: double-click 02_START_CLIPPILOT.bat
echo =========================================
pause
exit /b 0

:failed
echo.
echo [ERROR] Setup did not finish. Check the error printed above.
echo You can run this setup again to retry.
pause
exit /b 1
