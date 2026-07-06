# AutoCaption

AutoCaption creates automatic subtitles (SRT) for audio/video files using Whisper running locally (no internet required after initial model download).

The project contains two main independent components:
1. **Standalone GUI App** ([scripts/AutoCaption.py]) — A modern desktop application built with PySide6 supporting multi-file batch processing, drag & drop, card visual grids, and a toggleable log panel.
2. **DaVinci Resolve Script** ([scripts/AutoCaption4DR.lua]) — A completely standalone Lua script for DaVinci Resolve. It automatically generates subtitles for the selected audio file and imports them directly into the Media Pool and Timeline. No secondary Python files are needed in the DaVinci Scripts directory.

## Features

- ✅ **Fully Offline** after initial model download.
- ✅ **Automatic Language Detection (LID)** — Optimized for multi-lingual accuracy.
- ✅ **GPU (CUDA) Support** — Automatically falls back to CPU if no CUDA GPU is found.
- ✅ **Timestamp Capping** — Automatically prevents Whisper hallucinations by capping subtitle timestamps to the actual video duration.
- ✅ **Elegant Dark Slate Theme** designed to seamlessly match DaVinci Resolve's aesthetic.

---

## Requirements

| Requirement | Description |
|---|---|
| Python | 3.9 or higher |
| Libraries | `faster-whisper`, `PySide6` |
| Disk Space | ~1.5GB for `large-v3-turbo` model |
| GPU (Optional) | NVIDIA GPU with CUDA support for faster processing |

---

## Installation

### Step 1 — Install Python Libraries

Install the required Python dependencies by running:

```bash
pip install -r requirements.txt
```

*(This will install `faster-whisper` and `PySide6`)*

---

## Standalone GUI App (`AutoCaption.py`)

Run the desktop application:

```bash
python scripts/AutoCaption.py
```

### Usage
1. **Drag & Drop** media files (audio/video) into the top dashed zone, or click **Browse...** to select files.
2. The drop zone will display visual file cards. You can double-click any card or list item to remove it.
3. Select the **Output folder**.
4. Choose the **Model size** (defaults to `large-v3-turbo`) and **Processing Device** (GPU is selected by default if CUDA is available).
5. Click **Generate subtitles**.
6. When complete, a custom popup dialog will allow you to quickly **Open Folder** or click **OK**.
7. Toggle the **Show Log / Hide Log** button to view or hide the processing log (the window dynamically resizes to stay compact when logs are hidden).

---

## DaVinci Resolve Integration (`AutoCaption4DR.lua`)

The Lua script runs fully standalone inside DaVinci Resolve. It dynamically writes and executes its execution script in the Temp directory, so you only need to copy a single file.

### Setup & Usage
1. Copy [scripts/AutoCaption4DR.lua]to the DaVinci Resolve Scripts folder:
   - **Windows**: `C:\Users\<Username>\AppData\Roaming\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Comp\`
   - **macOS**: `/Users/<Username>/Library/Application Support/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Comp/`
   If you want to change the Whisper model or Python executable used by the DaVinci Resolve script, open `scripts/AutoCaption4DR.lua` and modify the variables at the top of the file:

```lua
local PYTHON_EXE = "python"        -- Change to "python3" on macOS if needed
local MODEL = "large-v3-turbo"     -- Change to "tiny", "base", "small", "medium", or "large-v3"
```

2. Open DaVinci Resolve and open your project.
3. In Resolve, go to **Workspace → Scripts → AutoCaption4DR**.
4. Select the media file to transcribe.
5. The subtitle (SRT) file will be generated **in the same folder** as your input video/audio.
6. The script will automatically import the SRT file into your Media Pool and append it to your Timeline.

---

## Whisper Models

| Model | Size | Speed (CPU) | Accuracy |
|-------|------|--------------|----------|
| tiny | ~75MB | Very Fast | Low |
| base | ~145MB | Fast | Fair |
| small | ~460MB | Moderate | Good |
| medium | ~1.5GB | Slow | Very Good |
| **large-v3-turbo** ⭐ | ~1.5GB | Fast | High (Recommended) |
| large-v3 | ~3GB | Very Slow | Highest |

---

---

## Directory Structure

```
AutoCaption/
├── scripts/
│   ├── AutoCaption.py          # Standalone PySide6 App
│   └── AutoCaption4DR.lua      # Standalone DaVinci Resolve Script
├── requirements.txt            # Python dependencies
└── README.md                   # This instruction file
```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `faster-whisper` not installed | Run `pip install -r requirements.txt` |
| GPU processing not working | Verify CUDA toolkit and cuDNN compatibility with CTranslate2. The app will automatically fall back to CPU if CUDA fails. |
| Subtitle extends beyond video end | Already fixed! Subtitles are capped at the media file's actual duration. |
| Lua Script fails to import to Media Pool | If automatic timeline import fails, a popup shows the SRT location so you can drag-and-drop it manually. |

---

## License

MIT
