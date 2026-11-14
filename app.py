"""ClipPilot: browser-based highlight clipping for Windows PCs and phones."""
from __future__ import annotations

import hmac
import os
import shutil
import tempfile
import time
from pathlib import Path

import streamlit as st
from faster_whisper import WhisperModel

from highlights import fmt_time, pick_highlights
from video_tools import (download_video, make_audio, make_zip, probe,
                         render_clip, require_tools, save_upload, transcribe, validate_youtube_url)

st.set_page_config(page_title="ClipPilot | YouTube to TikTok Clips", page_icon="✂️", layout="centered")
st.markdown("""
<style>
.block-container {max-width: 960px; padding: 1.3rem 1rem 3rem;}
h1 {font-size: clamp(2rem, 7vw, 3rem) !important; line-height: 1.1; letter-spacing: -.045em;}
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {
    min-height: 3rem; border-radius: .9rem; font-weight: 700;
}
[data-testid="stTextInput"] input {font-size: 1rem; min-height: 3rem;}
[data-testid="stExpander"] {border-radius: .8rem;}
@media(max-width: 640px) {.block-container {padding-top: 1.1rem;}}
</style>
""", unsafe_allow_html=True)


def authorize() -> None:
    required = os.environ.get("APP_PASSWORD", "")
    if os.environ.get("CLIPPILOT_HOSTED") == "1" and not required:
        st.error("App owner: set APP_PASSWORD in your hosting dashboard before using the app.")
        st.stop()
    if required:
        if st.session_state.get("authorized"):
            return
        st.title("✂️ ClipPilot")
        st.write("Enter your private ClipPilot password.")
        entry = st.text_input("Password", type="password")
        if st.button("Open ClipPilot", type="primary", use_container_width=True):
            if hmac.compare_digest(entry, required):
                st.session_state["authorized"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.stop()


def clean_old_jobs(hours: int = 6) -> None:
    tmp = Path(tempfile.gettempdir())
    deadline = time.time() - hours * 3600
    for folder in tmp.glob("clippilot_mobile_*"):
        if folder.is_dir():
            try:
                if folder.stat().st_mtime < deadline:
                    shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                continue


@st.cache_resource(show_spinner="Loading speech recognition...")
def load_model(name: str) -> WhisperModel:
    return WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)


authorize()
clean_old_jobs()

st.title("✂️ ClipPilot")
st.markdown("**YouTube videos → TikTok-ready clips, on your Windows PC or phone.**")
st.write("Paste a permitted YouTube link or upload a video file. ClipPilot identifies potentially important spoken moments, creates vertical clips, and lets you download MP4s for TikTok.")

with st.form("clip_form"):
    source_mode = st.radio("Choose video source", ["Paste YouTube link", "Upload a video file"], horizontal=True,
                           help="YouTube links may not be accessible from free cloud servers. A permitted video file is a more reliable fallback.")
    url_input = ""
    video_upload = None
    if source_mode == "Paste YouTube link":
        url_input = st.text_input("YouTube video link", placeholder="https://youtu.be/xxxxxxxxxxx")
    else:
        video_upload = st.file_uploader("Upload an MP4, MOV, WebM or MKV file", type=["mp4", "mov", "webm", "mkv", "avi", "m4v"],
                                        help="Short videos are best on free hosting. Files are temporarily saved for processing.")
    st.caption("Videos with clear speech work best. Audio-only or silent scenes may not produce suitable highlights.")
    a, b = st.columns(2)
    with a:
        count = st.selectbox("Number of clips", [2, 3, 4, 5, 6], index=1)
    with b:
        target = st.selectbox("Clip length", [15, 30, 45, 60], index=1, format_func=lambda v: f"About {v} sec")
    burn_captions = st.checkbox("Add captions on the video", value=True)
    with st.expander("More settings (optional)"):
        layout = st.radio("Vertical video style", ["Blurred background", "Center crop"],
                          help="Blurred background preserves the full horizontal picture. Center crop fills the TikTok screen but can cut off people at the sides.")
        language_label = st.selectbox("Spoken language", ["Detect automatically", "English", "Spanish"])
        model_name = st.selectbox("Speech recognition", ["tiny", "base"],
                                  help="Tiny is quicker on cloud hosting; Base is usually more accurate but needs more processing power.")
    has_rights = st.checkbox("I own this video or have permission to download, edit, and reuse it.")
    submit = st.form_submit_button("✂️ Find my best clips", type="primary", use_container_width=True)

if submit:
    try:
        if source_mode == "Paste YouTube link":
            source_url = validate_youtube_url(url_input)
        elif video_upload is None:
            raise ValueError("Please select a video file to upload.")
        else:
            source_url = f"Uploaded file: {video_upload.name}"
        if not has_rights:
            raise ValueError("Confirm you own the video or have permission to reuse it.")
        require_tools()
        # Drop previous exports from the same session, if any.
        old = st.session_state.pop("results", None)
        if old:
            shutil.rmtree(old.get("workdir", ""), ignore_errors=True)
        workdir = Path(tempfile.mkdtemp(prefix="clippilot_mobile_"))
        with st.status("Preparing your clips…", expanded=True) as status:
            st.write("**Step 1 of 4:** Getting your video ready…")
            source = (download_video(source_url, workdir) if source_mode == "Paste YouTube link"
                      else save_upload(video_upload, workdir))
            duration = probe(source)
            st.write(f"Video duration: {fmt_time(duration)}")
            st.write("**Step 2 of 4:** Finding important spoken moments…")
            audio = make_audio(source, workdir)
            lang = {"Detect automatically": None, "English": "en", "Spanish": "es"}[language_label]
            segments, detected_lang = transcribe(audio, load_model(model_name), lang)
            if len(" ".join(s["text"] for s in segments).split()) < 8:
                raise ValueError("Not enough clear speech was found. Try a YouTube video with dialogue.")
            st.write(f"Speech detected: {detected_lang}")
            st.write("**Step 3 of 4:** Choosing the best clips…")
            picks, method = pick_highlights(segments, target, duration, count)
            if not picks:
                raise ValueError("No strong spoken highlights could be identified from this video.")
            st.write(f"Found {len(picks)} highlight(s) using {method}.")
            st.write("**Step 4 of 4:** Creating vertical MP4s with captions…")
            prog = st.progress(0)
            exports = []
            for i, clip in enumerate(picks, 1):
                exports.append(render_clip(source, clip, workdir, i, segments, layout, burn_captions))
                prog.progress(i / len(picks), text=f"Clip {i} of {len(picks)} ready")
            archive = make_zip(workdir, exports, {
                "source": source_url, "source_duration_seconds": duration,
                "selection_method": method, "detected_language": detected_lang, "clips": picks,
            })
            st.session_state["results"] = {
                "workdir": str(workdir),
                "archive": str(archive),
                "clips": picks,
                "videos": [str(mp4) for mp4, _ in exports],
            }
            status.update(label="Clips ready — preview or download below", state="complete", expanded=False)
        st.success("Your TikTok-ready clips are ready. Preview them, then download to your PC or phone.")
    except Exception as exc:
        st.error(f"Could not generate the clips: {exc}")
        st.caption("Some YouTube links may be unavailable to cloud servers. For permitted content, try uploading the original video file instead.")

results = st.session_state.get("results")
if results:
    files = [Path(p) for p in results["videos"]]
    if files and all(p.is_file() for p in files):
        st.divider()
        st.subheader("Your clips")
        st.caption("Press Play to preview. Use Save clip to download the MP4 to your PC or phone.")
        for i, (mp4, clip) in enumerate(zip(files, results["clips"]), 1):
            with st.container(border=True):
                st.markdown(f"**Clip {i}** · {fmt_time(clip['start'])}–{fmt_time(clip['end'])}")
                st.video(str(mp4))
                with mp4.open("rb") as fd:
                    st.download_button(f"⬇️ Save clip {i} (MP4)", fd,
                                       file_name=f"ClipPilot_TikTok_{i:02d}.mp4",
                                       mime="video/mp4", key=f"save_mp4_{i}",
                                       use_container_width=True)
                if clip.get("text"):
                    with st.expander("What happens in this clip?"):
                        st.write(clip["text"][:850])
        archive = Path(results["archive"])
        if archive.is_file():
            with archive.open("rb") as fd:
                st.download_button("⬇️ Download all clips (ZIP)", fd,
                                   file_name="ClipPilot_TikTok_Clips.zip", mime="application/zip",
                                   use_container_width=True, key="zip_download")
        st.info("**On Windows:** Click Save clip; check the Downloads folder. **On iPhone:** Download through Safari, then find the video in Files and save to Photos if needed.")

st.divider()
st.caption("The clips are suggestions, not guarantees of the most important moments. Review them before posting. This app does not connect to TikTok or upload on your behalf.")
