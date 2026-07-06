#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoCaption Core Logic
Handles Whisper audio transcription (local CPU/GPU) and SRT generation.
"""

import sys
import os
import importlib.util

# Disable Hugging Face symlinks warning on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

MODEL_SIZES = [
    "tiny",
    "base",
    "small",
    "medium",
    "large-v3-turbo",
    "large-v3"
]

HAS_CUDA = False
try:
    import ctranslate2
    HAS_CUDA = ctranslate2.get_cuda_device_count() > 0
except Exception:
    pass

class SimpleSegment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def transcribe(input_path, language, model, log_fn=print, cancel_event=None, progress_callback=None):
    """Whisper transcription with incremental progress and cancellation check"""
    try:
        log_fn(f"Processing audio: {input_path}")
        segments, info = model.transcribe(
            input_path,
            language=language if language and language != "auto" else None,
            beam_size=5,
            vad_filter=True
        )
        
        detected = info.language
        total_duration = info.duration
        log_fn(f"Detected language: {detected} (Duration: {total_duration:.1f}s)")
        
        segments_list = []
        for segment in segments:
            if cancel_event and cancel_event.is_set():
                log_fn("Transcription cancelled by user.")
                return None, detected
            
            # Cap segment end to total duration to avoid whisper padding hallucinations
            start_capped = min(segment.start, total_duration) if total_duration else segment.start
            end_capped = min(segment.end, total_duration) if total_duration else segment.end
            
            # Avoid exporting segments that start after the total duration
            if total_duration and start_capped >= total_duration:
                continue
                
            capped_seg = SimpleSegment(start_capped, end_capped, segment.text)
            segments_list.append(capped_seg)
            log_fn(f"[{format_timestamp(capped_seg.start)} --> {format_timestamp(capped_seg.end)}] {capped_seg.text.strip()}")
            
            if progress_callback and total_duration > 0:
                percent = min(100, int((capped_seg.end / total_duration) * 100))
                progress_callback(percent)
                
        return segments_list, detected
    except Exception as e:
        log_fn(f"ERROR during transcription: {e}")
        return None, None

def build_srt(segments):
    """Format segments list into standard SRT text"""
    parts = []
    for i, seg in enumerate(segments, 1):
        parts.append(f"{i}\n{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}\n{seg.text.strip()}\n")
    return "\n".join(parts)

def save_srt(path, srt_text, log_fn=print):
    """Write SRT text to file"""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(srt_text)
        log_fn(f"Saved: {path}")
        return True
    except Exception as e:
        log_fn(f"ERROR saving SRT: {e}")
        return False
