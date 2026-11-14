# ClipPilot — Windows PC edition + free cloud deployment files

**Start here on Windows:** open `START_HERE_WINDOWS.txt` and follow **Option A**.

This app can run locally on your Windows computer, or you can deploy it to a free Streamlit Community Cloud account and use the URL on your phone. It transcribes speech using open-source `faster-whisper`, finds candidate highlights with free transcript scoring, and creates 720×1280 vertical MP4 clips with optional subtitles using FFmpeg. No paid AI service is needed for the local app.

**To run on your PC:** install Python 3.12; extract this ZIP; double-click `01_INSTALL_CLIPPILOT_WINDOWS.bat` and then `02_START_CLIPPILOT.bat`. If FFmpeg is not installed, the installer offers to install it via Windows Package Manager. Instructions and troubleshooting are in `START_HERE_WINDOWS.txt`.

**To host online:** upload `app.py`, `highlights.py`, `video_tools.py`, `requirements.txt`, `packages.txt`, and `.streamlit/config.toml` to a private GitHub repo, and deploy `app.py` at https://share.streamlit.io/. Set `APP_PASSWORD` and `CLIPPILOT_HOSTED = "1"` in Streamlit secrets. **A successful live deployment is not guaranteed by the free plan's limits.**

**Limits:** Some YouTube links may fail even on a local computer, depending on the video's availability and YouTube's download restrictions. Only use videos you are authorized to download and reuse. Highlight ranking is transcript-based (not visual scene analysis) and may miss important silent moments. Clips are for you to review and upload to TikTok manually.
