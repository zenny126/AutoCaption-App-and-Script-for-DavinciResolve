#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
transcribe_local.py
Tạo phụ đề SRT bằng Whisper chạy LOCAL (faster-whisper) - HOÀN TOÀN MIỄN PHÍ,
không cần API key, không cần internet (sau khi đã tải model lần đầu).

Cài đặt (chạy 1 lần):
    pip install faster-whisper

Cách dùng:
    python transcribe_local.py <input_media_file> <output_srt_file> [language] [model_size]

language:   mã ISO-639-1 (vi, en, zh...) hoặc để trống để tự nhận diện.
model_size: tiny / base / small / medium / large-v3 (mặc định: medium)
"""

import sys
import os

# Ép output sang UTF-8 để tránh UnicodeEncodeError khi in tiếng Việt có dấu
# trên console Windows mặc định dùng bảng mã cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def format_timestamp(seconds: float) -> str:
    """Chuyển giây sang định dạng SRT: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def main():
    if len(sys.argv) < 3:
        print("Usage: python transcribe_local.py <input_media_file> <output_srt_file> [language] [model_size]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    language = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
    model_size = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else "medium"

    if not os.path.isfile(input_path):
        print(f"ERROR: Không tìm thấy file đầu vào: {input_path}")
        sys.exit(2)

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("ERROR: Chưa cài thư viện faster-whisper. Chạy: pip install faster-whisper")
        sys.exit(3)

    print(f"Đang tải model Whisper '{model_size}' (lần đầu sẽ tải về máy, có thể mất vài phút)...")
    # CPU: dùng compute_type int8 để tăng tốc đáng kể trên máy không có GPU rời.
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"Đang xử lý audio: {input_path}")
    print("Lưu ý: chạy bằng CPU nên có thể mất một khoảng thời gian, hãy kiên nhẫn chờ...")

    segments, info = model.transcribe(
        input_path,
        language=language,
        beam_size=5,
        vad_filter=True,  # lọc khoảng lặng giúp giảm phụ đề rác
    )

    print(f"Ngôn ngữ phát hiện: {info.language} (xác suất {info.language_probability:.2f})")

    srt_lines = []
    index = 1
    for segment in segments:
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        text = segment.text.strip()
        if not text:
            continue
        srt_lines.append(str(index))
        srt_lines.append(f"{start} --> {end}")
        srt_lines.append(text)
        srt_lines.append("")
        index += 1
        # In tiến độ ra console để người dùng biết script chưa bị treo.
        print(f"[{start} --> {end}] {text}")

    if index == 1:
        print("ERROR: Không nhận diện được nội dung nói nào trong file.")
        sys.exit(4)

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))
    except Exception as e:
        print(f"ERROR: Không ghi được file SRT: {e}")
        sys.exit(5)

    print(f"OK: Đã tạo file phụ đề tại {output_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
