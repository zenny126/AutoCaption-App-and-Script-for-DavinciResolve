# AutoCaption VEC

Tạo phụ đề tự động cho timeline trong **DaVinci Resolve Free & Studio**, chạy hoàn toàn **local** bằng [faster-whisper](https://github.com/SYSTRAN/faster-whisper) và dịch bằng [Argos Translate](https://github.com/argosopentech/argos-translate).

- ✅ Miễn phí hoàn toàn, không cần API key
- ✅ Không cần internet sau khi tải model lần đầu
- ✅ Hỗ trợ Tiếng Việt / English / 中文
- ✅ Xuất 1 hoặc 2 file SRT (ngôn ngữ gốc + bản dịch)
- ✅ Chạy trên DaVinci Resolve Free và Studio

---

## Yêu cầu

| Thứ | Mô tả |
|-----|-------|
| DaVinci Resolve | 18+ (Free hoặc Studio) |
| Python | 3.9 trở lên, có trong PATH |
| Dung lượng | ~1.5GB (model medium) hoặc ~3GB (model large-v3) |
| Internet | Chỉ cần lần đầu để tải model Whisper và gói dịch Argos |

---

## Cài đặt

### Bước 1 — Clone hoặc tải repo

```bash
git clone https://github.com/<your-username>/AutoCaptionVEC.git
```

hoặc tải file ZIP từ trang GitHub rồi giải nén.

### Bước 2 — Cài thư viện Python

```bash
pip install -r requirements.txt
```

Hai thư viện được cài:
- `faster-whisper` — nhận diện giọng nói (speech-to-text) chạy local
- `argostranslate` — dịch thuật chạy local (không cần Google Translate)

### Bước 3 — Copy scripts vào DaVinci Resolve

Copy **cả 2 file** trong thư mục `scripts/` vào đúng thư mục Scripts của Resolve.  
⚠️ Hai file phải nằm **cùng một thư mục**.

**Windows:**
```
%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Comp\
```

**macOS:**
```
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Comp/
```

---

## Sử dụng

1. Mở DaVinci Resolve, mở project và timeline cần tạo phụ đề.
2. Vào **Workspace → Scripts → AutoCaptionVEC_Generate**.
3. Cửa sổ chọn file hiện ra → chọn file **audio hoặc video** nguồn.
4. Cửa sổ cài đặt hiện ra, chọn:

| Tùy chọn | Mô tả |
|----------|-------|
| **Source Language** | Ngôn ngữ trong audio (Vietnamese / English / Chinese / Auto-detect) |
| **Model** | Kích thước model Whisper (xem bảng bên dưới) |
| **Output Files** | `1 File` = chỉ SRT gốc · `2 Files` = SRT gốc + SRT bản dịch |
| **Translation Language** | Ngôn ngữ đích khi chọn 2 Files |

5. Bấm **OK** và đợi xử lý — theo dõi tiến độ trong **Console** của Resolve (Workspace → Console).
6. Khi xong, file SRT được tự động thêm vào timeline. Nếu thất bại, script sẽ báo đường dẫn file SRT để bạn kéo thủ công từ Media Pool.

---

## Kích thước model Whisper

| Model | Dung lượng | Tốc độ (CPU) | Độ chính xác |
|-------|-----------|--------------|--------------|
| tiny | ~75MB | Rất nhanh | Thấp |
| base | ~145MB | Nhanh | Khá |
| small | ~460MB | Khá nhanh | Tốt |
| **medium** ⭐ | ~1.5GB | Trung bình | Tốt |
| large-v3 | ~3GB | Chậm | Cao nhất |

> Khuyến nghị dùng **medium** cho máy không có GPU rời — cân bằng tốt giữa tốc độ và độ chính xác. Model được tải tự động lần đầu chạy và cache lại để dùng cho các lần sau.

---

## Dịch thuật (File 2)

Khi chọn **2 Files**, script sẽ dịch toàn bộ phụ đề sang ngôn ngữ đích bằng Argos Translate.

- Lần đầu dịch một cặp ngôn ngữ mới (ví dụ vi→en), Argos sẽ tự tải gói ngôn ngữ (cần internet, ~50–100MB, chỉ tải 1 lần).
- Dịch chạy hoàn toàn offline sau khi đã tải gói.
- Nếu một đoạn dịch thất bại, script giữ nguyên text gốc cho đoạn đó và tiếp tục (không crash).
- Nếu không tìm thấy gói dịch cho cặp ngôn ngữ yêu cầu, script báo lỗi rõ ràng trong Console.

---

## Cấu trúc thư mục

```
AutoCaptionVEC/
├── scripts/
│   ├── AutoCaptionVEC_Generate.lua   # Script chạy trong Resolve
│   └── transcribe_local.py           # Xử lý speech-to-text + dịch
├── requirements.txt
└── README.md
```

---

## Cấu hình nâng cao

Mở `scripts/AutoCaptionVEC_Generate.lua`, sửa dòng:

```lua
local PYTHON_EXE = "python"  -- đổi thành "python3" nếu cần (thường trên macOS)
```

---

## Troubleshooting

| Lỗi | Giải pháp |
|-----|-----------|
| `faster-whisper not installed` | Chạy `pip install -r requirements.txt` |
| `argostranslate not installed` | Chạy `pip install argostranslate` |
| Không tìm thấy gói dịch | Kiểm tra internet, Argos cần tải gói lần đầu |
| Script chạy quá chậm | Đổi sang model `small` hoặc `base` trong cửa sổ cài đặt |
| `UnicodeEncodeError` | Đã được xử lý tự động trong script |
| Phụ đề không tự thêm vào timeline | Kéo thủ công file `.srt` từ Media Pool vào timeline |

---

## License

MIT
