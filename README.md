# AutoCaption VEC

Tạo phụ đề tự động (Việt / English / 中文) cho timeline trong DaVinci Resolve
(Free hoặc Studio), chạy hoàn toàn **local** bằng [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
— không cần API key, không tốn phí, không cần internet sau khi đã tải model lần đầu.

## Yêu cầu

- DaVinci Resolve (Free hoặc Studio)
- Python 3.9+ đã cài trên máy, có trong PATH
- Khoảng 1.5–3GB dung lượng trống để tải model Whisper (tải tự động lần chạy đầu)

## Cài đặt

1. Clone hoặc tải repo này về.
2. Cài thư viện Python:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy 2 file trong thư mục `scripts/` vào thư mục Scripts của DaVinci Resolve:

   **Windows:**
   ```
   %APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Comp\
   ```

   **macOS:**
   ```
   ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Comp/
   ```

   Lưu ý: `AutoCaptionVEC_Generate.lua` và `transcribe_local.py` phải nằm **cùng một thư mục**.

## Sử dụng

1. Mở DaVinci Resolve, mở project và timeline cần tạo phụ đề.
2. Vào **Workspace → Scripts → AutoCaptionVEC_Generate**.
3. Chọn file audio/video nguồn.
4. Chọn ngôn ngữ (Tiếng Việt / English / 中文 / Tự nhận diện).
5. Đợi xử lý (chạy CPU nên có thể mất vài phút tùy độ dài file và cấu hình máy) — theo dõi tiến độ trong cửa sổ Console của Resolve.
6. Phụ đề (`.srt`) được tạo và tự động thêm vào timeline. Nếu bước tự thêm thất bại, script sẽ báo đường dẫn file `.srt` để bạn tự kéo thủ công từ Media Pool vào timeline.

## Cấu hình

Mở `scripts/AutoCaptionVEC_Generate.lua`, sửa các dòng đầu file:

```lua
local PYTHON_EXE = "python"   -- đổi thành "python3" nếu cần (thường dùng trên macOS)
local MODEL_SIZE = "medium"   -- tiny / base / small / medium / large-v3
```

| Model      | Tốc độ (CPU) | Độ chính xác |
|------------|--------------|--------------|
| tiny       | Rất nhanh    | Thấp         |
| base/small | Nhanh        | Khá          |
| medium     | Trung bình   | Tốt          |
| large-v3   | Chậm         | Cao nhất     |

Trên máy không có GPU rời, khuyến nghị dùng `small` hoặc `medium` để cân bằng thời gian chờ và độ chính xác.

## Cấu trúc thư mục

```
AutoCaptionVEC/
├── scripts/
│   ├── AutoCaptionVEC_Generate.lua   # Script chạy trong Resolve (Workspace > Scripts)
│   └── transcribe_local.py            # Xử lý speech-to-text bằng Whisper local
├── requirements.txt
└── README.md
```

## License

MIT
