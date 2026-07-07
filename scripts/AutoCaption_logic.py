#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoCaption Core Logic
Handles Whisper audio transcription (local CPU/GPU) and SRT generation.
"""

import os

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
    total_millis = int(round(max(0.0, seconds) * 1000))
    millis = total_millis % 1000
    total_secs = total_millis // 1000
    secs = total_secs % 60
    total_mins = total_secs // 60
    minutes = total_mins % 60
    hours = total_mins // 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def transcribe(input_path, language, model, log_fn=print, cancel_event=None, progress_callback=None, **kwargs):
    """Whisper transcription with incremental progress and cancellation check"""
    try:
        log_fn(f"Processing audio: {input_path}")

        # Check if the file contains an audio stream to prevent faster-whisper IndexError
        try:
            import av
            with av.open(input_path) as container:
                if not container.streams.audio:
                    log_fn("ERROR: The input file does not contain any audio tracks to transcribe.")
                    return None, "No audio tracks found"
        except Exception as av_err:
            # Let it proceed to transcribe in case Whisper can decode it using other fallbacks
            pass
        
        # Default transcription options, allows overrides via kwargs
        options = {
            "language": language if language and language != "auto" else None,
            "beam_size": 5,
            "vad_filter": True
        }
        options.update(kwargs)
        
        segments, info = model.transcribe(input_path, **options)
        
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
        import traceback
        tb = traceback.format_exc()
        log_fn(f"ERROR during transcription: {e}\n{tb}")
        return None, str(e)

def build_srt(segments):
    """Format segments list into standard SRT text"""
    return "\n".join(
        f"{i}\n{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}\n{seg.text.strip()}\n"
        for i, seg in enumerate(segments, 1)
    )

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
