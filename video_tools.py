"""Download/import video, transcribe it, and export short ready-to-post clips."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse, parse_qs


VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}


def require_tools() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError("Install FFmpeg and ensure ffmpeg and ffprobe are on your PATH. Missing: " + ", ".join(missing))


def run(cmd: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        details = completed.stderr[-1800:] or completed.stdout[-1800:]
        raise RuntimeError(f"Video processing failed: {details}")
    return completed.stdout


def probe(path: Path) -> float:
    data = json.loads(run(["ffprobe", "-v", "error", "-show_entries",
                           "format=duration:stream=codec_type", "-of", "json", str(path)]))
    if not any(stream.get("codec_type") == "video" for stream in data.get("streams", [])):
        raise ValueError("The supplied file does not contain a video stream.")
    duration = float(data.get("format", {}).get("duration", 0))
    if duration <= 0:
        raise ValueError("Could not determine video duration.")
    if duration > 2700:
        raise ValueError("This mobile version supports videos up to 45 minutes long.")
    return duration


def validate_youtube_url(url: str) -> str:
    """Normalize an actual YouTube video URL; disallow arbitrary downloader targets."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Paste a complete YouTube link beginning with https://")
    host = (parsed.hostname or "").lower()
    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
            video_id = parsed.path.split("/")[2]
        else:
            raise ValueError("Paste a link to a YouTube video, not a channel or playlist.")
    else:
        raise ValueError("Only YouTube video links are supported in this mobile app.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("That does not look like a valid YouTube video link.")
    return f"https://www.youtube.com/watch?v={video_id}"


def download_video(url: str, workdir: Path) -> Path:
    from yt_dlp import YoutubeDL

    url = validate_youtube_url(url)
    opts = {
        "outtmpl": str(workdir / "input.%(ext)s"),
        "format": "bv*[height<=720]+ba/b[height<=720]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "playlistend": 1,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "max_filesize": 600 * 1024 * 1024,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 25,
        "extract_flat": False,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info and float(info.get("duration") or 0) > 2700:
            raise ValueError("Videos longer than 45 minutes aren't supported in this mobile version.")
        ydl.download([url])
    found = [p for p in workdir.glob("input.*") if p.suffix.lower() in VIDEO_EXTS]
    if not found:
        raise RuntimeError("YouTube did not provide a downloadable video for this link. Try another video you have permission to use.")
    return max(found, key=lambda p: p.stat().st_size)


def save_upload(upload, workdir: Path) -> Path:
    suffix = Path(upload.name).suffix.lower()
    if suffix not in VIDEO_EXTS:
        raise ValueError("Unsupported format. Upload MP4, MOV, WebM, MKV, AVI, or M4V.")
    output = workdir / f"input{suffix}"
    upload.seek(0)
    with output.open("wb") as file:
        shutil.copyfileobj(upload, file, length=1024 * 1024)
    return output


def make_audio(video: Path, workdir: Path) -> Path:
    output = workdir / "audio.wav"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output)])
    return output


def transcribe(audio: Path, model, language: str | None) -> tuple[list[dict], str]:
    generator, info = model.transcribe(str(audio), beam_size=4, vad_filter=True,
                                       word_timestamps=True, language=language)
    segments = []
    for part in generator:
        words = [{"start": float(w.start), "end": float(w.end), "text": w.word}
                 for w in (part.words or []) if w.start is not None and w.end is not None]
        segments.append({"start": float(part.start), "end": float(part.end),
                         "text": part.text.strip(), "words": words})
    return segments, info.language


def caption_lines(segments: list[dict], clip_start: float, clip_end: float) -> list[dict]:
    words: list[dict] = []
    for segment in segments:
        if segment["end"] <= clip_start or segment["start"] >= clip_end:
            continue
        if segment.get("words"):
            for w in segment["words"]:
                if w["end"] > clip_start and w["start"] < clip_end:
                    words.append(w)
        else:
            words.append({"start": segment["start"], "end": segment["end"],
                          "text": segment["text"]})
    lines: list[dict] = []
    group: list[dict] = []
    for w in words:
        if group and (len(group) >= 7 or w["end"] - group[0]["start"] > 2.8 or
                      w["start"] - group[-1]["end"] > 0.75):
            lines.append(make_line(group, clip_start, clip_end))
            group = []
        group.append(w)
        if str(w["text"]).strip().endswith((".", "?", "!", "。", "？", "！")) and len(group) >= 3:
            lines.append(make_line(group, clip_start, clip_end))
            group = []
    if group:
        lines.append(make_line(group, clip_start, clip_end))
    return [line for line in lines if line["end"] - line["start"] >= 0.08 and line["text"]]


def make_line(words: list[dict], clip_start: float, clip_end: float) -> dict:
    text = "".join(str(w["text"]) for w in words).strip()
    # Whisper words normally carry leading spaces; non-word fallback may not.
    if not any(" " in str(w["text"]) for w in words):
        text = " ".join(str(w["text"]).strip() for w in words)
    return {"start": max(0.0, words[0]["start"] - clip_start),
            "end": min(clip_end - clip_start, words[-1]["end"] - clip_start),
            "text": text}


def srt_stamp(t: float) -> str:
    ms = max(0, round(t * 1000))
    return f"{ms // 3600000:02d}:{(ms // 60000) % 60:02d}:{(ms // 1000) % 60:02d},{ms % 1000:03d}"


def ass_stamp(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000:01d}:{(cs // 6000) % 60:02d}:{(cs // 100) % 60:02d}.{cs % 100:02d}"


def write_captions(lines: list[dict], outbase: Path, vertical: bool) -> tuple[Path, Path]:
    srt = outbase.with_suffix(".srt")
    ass = outbase.with_suffix(".ass")
    with srt.open("w", encoding="utf-8") as file:
        for i, line in enumerate(lines, 1):
            file.write(f"{i}\n{srt_stamp(line['start'])} --> {srt_stamp(line['end'])}\n{line['text']}\n\n")
    size = 47 if vertical else 30
    margin = 160 if vertical else 64
    ass_lines = [
        "[Script Info]", "Title: ClipPilot Captions", "ScriptType: v4.00+",
        "PlayResX: 720" if vertical else "PlayResX: 1280",
        "PlayResY: 1280" if vertical else "PlayResY: 720",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Arial,{size},&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,2,55,55,{margin},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for line in lines:
        text = re.sub(r"[{}]", "", line["text"]).replace("\\", "").replace("\n", " ")
        # Split long captions onto two centered lines for legibility.
        bits = text.split()
        if len(text) > 27 and len(bits) >= 4:
            mid = len(bits) // 2
            text = " ".join(bits[:mid]) + r"\N" + " ".join(bits[mid:])
        ass_lines.append(f"Dialogue: 0,{ass_stamp(line['start'])},{ass_stamp(line['end'])},Default,,0,0,0,,{text}")
    ass.write_text("\n".join(ass_lines) + "\n", encoding="utf-8")
    return srt, ass


def render_clip(video: Path, clip: dict, workdir: Path, index: int, segments: list[dict],
                layout: str, burn_captions: bool) -> tuple[Path, Path]:
    vertical = layout != "Original landscape"
    outbase = workdir / f"clip_{index:02d}"
    lines = caption_lines(segments, clip["start"], clip["end"])
    srt, ass = write_captions(lines, outbase, vertical)

    # Build filter with safe, fixed filenames; cwd=workdir for Windows compatibility.
    if layout == "Blurred background":
        vf = ("split=2[bg][fg];"
              "[bg]scale=720:1280:force_original_aspect_ratio=increase,"
              "crop=720:1280,boxblur=20:2[blur];"
              "[fg]scale=720:1280:force_original_aspect_ratio=decrease[sharp];"
              "[blur][sharp]overlay=(W-w)/2:(H-h)/2[v]")
        vf += f";[v]ass={ass.name}[out]" if burn_captions and lines else ";[v]null[out]"
    else:
        vf = ("scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
              if vertical else "scale=1280:720:force_original_aspect_ratio=decrease,"
              "pad=1280:720:(ow-iw)/2:(oh-ih)/2")
        if burn_captions and lines:
            vf += f",ass={ass.name}"
        vf += "[out]"

    output = outbase.with_suffix(".mp4")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(clip["start"]),
           "-i", str(video), "-t", str(clip["end"] - clip["start"]),
           "-filter_complex", vf, "-map", "[out]", "-map", "0:a:0?",
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
           str(output)]
    run(cmd, cwd=workdir)
    return output, srt


def make_zip(workdir: Path, exports: list[tuple[Path, Path]], details: dict) -> Path:
    path = workdir / "ClipPilot_Clips.zip"
    metadata = workdir / "clip_details.json"
    metadata.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    instructions = workdir / "README_CLIPS.txt"
    instructions.write_text(
        "Your clips are in MP4 format, along with optional editable SRT subtitle files.\n"
        "You can upload the MP4 files manually to TikTok, Instagram Reels, YouTube Shorts, or Facebook.\n"
        "Review cuts, captions, and content rights before publishing.\n"
        "This app does not automatically post to social platforms.\n", encoding="utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as z:
        for mp4, srt in exports:
            z.write(mp4, arcname=mp4.name)
            z.write(srt, arcname=srt.name)
        z.write(metadata, arcname=metadata.name)
        z.write(instructions, arcname=instructions.name)
    return path
