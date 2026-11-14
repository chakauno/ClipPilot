"""Find and score self-contained, speech-driven video highlight candidates."""

from __future__ import annotations

import re

HOOK_WORDS = (
    "but then", "here's why", "heres why", "the truth", "the secret",
    "what happened", "the problem", "the reason", "you won't believe",
    "important", "amazing", "unbelievable", "biggest", "never", "always",
    "finally", "suddenly", "however", "instead", "surprise", "mistake",
    "learned", "watch this", "the answer", "this is how", "first time",
    "pero entonces", "la verdad", "el secreto", "el problema",
    "por eso", "no vas a creer", "increíble", "importante", "nunca",
    "siempre", "finalmente", "de repente", "sin embargo", "así fue",
    "lo que pasó", "el motivo", "el error", "resulta que", "después",
)
FILLER_WORDS = {"um", "uh", "erm", "hmm", "eh", "este", "em", "mmm"}


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds // 60) % 60:02d}:{seconds % 60:02d}"


def score_text(text: str, duration: float) -> float:
    lower = text.lower()
    words = re.findall(r"\b[\wÀ-ÿ'-]+\b", lower)
    if duration <= 0 or not words:
        return 0.0
    wps = len(words) / duration
    density = min(wps, 3.3) * 1.2
    hooks = sum(1 for phrase in HOOK_WORDS if phrase in lower)
    question = 1.3 if "?" in text or "¿" in text else 0
    excitement = 0.9 if "!" in text or "¡" in text else 0
    structure = 0.8 if any(p in text for p in (".", "?", "!")) else 0
    numbers = 0.8 if re.search(r"\d", text) else 0
    filler = sum(1 for word in words if word in FILLER_WORDS)
    return round(density + min(hooks, 4) * 1.8 + question + excitement + structure + numbers - filler * 0.3, 3)


def candidates_for(segments: list[dict], target_seconds: int, duration: float) -> list[dict]:
    """Use transcript boundaries to avoid cutting off a spoken thought."""
    segments = [s for s in segments if s.get("text", "").strip() and s["end"] > s["start"]]
    if not segments:
        return []
    out: list[dict] = []
    seen: set[tuple[int, int]] = set()
    max_seconds = min(65, max(target_seconds + 9, round(target_seconds * 1.2)))
    min_seconds = min(12, target_seconds * 0.55)

    if duration < target_seconds:
        text = " ".join(s["text"].strip() for s in segments)
        return [{"id": 0, "start": 0.0, "end": round(duration, 2),
                 "text": text, "score": score_text(text, duration)}]

    for i in range(0, len(segments), 2):
        start = max(0.0, float(segments[i]["start"]) - 0.3)
        collected: list[dict] = []
        for segment in segments[i:]:
            if float(segment["end"]) - start > max_seconds:
                break
            collected.append(segment)
            length = float(segment["end"]) - start
            sentence_end = segment["text"].strip().endswith((".", "!", "?", "。", "！", "？"))
            if length >= target_seconds and (sentence_end or length >= target_seconds + 6):
                break
        if not collected:
            continue
        end = min(duration, float(collected[-1]["end"]) + 0.35)
        length = end - start
        if length < min_seconds or length > 66:
            continue
        key = (round(start), round(end))
        if key in seen:
            continue
        seen.add(key)
        text = " ".join(s["text"].strip() for s in collected).strip()
        if len(text.split()) < 9:
            continue
        out.append({"id": len(out), "start": round(start, 2), "end": round(end, 2),
                    "text": text, "score": score_text(text, length)})
    return sorted(out, key=lambda c: c["score"], reverse=True)


def overlap_fraction(a: dict, b: dict) -> float:
    overlap = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    return overlap / max(0.001, min(a["end"] - a["start"], b["end"] - b["start"]))


def nonoverlapping(candidates: list[dict], count: int) -> list[dict]:
    chosen: list[dict] = []
    for candidate in candidates:
        if all(overlap_fraction(candidate, old) < 0.22 for old in chosen):
            chosen.append(dict(candidate))
        if len(chosen) >= count:
            break
    return sorted(chosen, key=lambda c: c["start"])


def pick_highlights(segments: list[dict], target_seconds: int, duration: float,
                    count: int) -> tuple[list[dict], str]:
    """Offline rule-based clip ranking. No paid API, no network LLM calls."""
    candidates = candidates_for(segments, target_seconds, duration)
    if not candidates:
        return [], "none"
    selected = nonoverlapping(candidates, count)
    for c in selected:
        c.setdefault("title", "Highlight")
        c.setdefault("reason", "Chosen from speech cues and transcript structure")
    return selected, "free transcript-based ranking"
