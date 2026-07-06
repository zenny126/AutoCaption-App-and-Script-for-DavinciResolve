#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoCaption VEC GUI Launcher
Supports Whisper audio transcription (local CPU/GPU) and local Argos Translation.
"""

import sys
import os
import threading

# Disable Hugging Face symlinks warning on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import importlib.util

# Check other dependencies using find_spec (prevent Shiboken hooks causing import hang)
MISSING_DEPS = []
if importlib.util.find_spec("faster_whisper") is None:
    MISSING_DEPS.append("faster-whisper")
if importlib.util.find_spec("argostranslate") is None:
    MISSING_DEPS.append("argostranslate")

# Verify PySide6 is installed
try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    print("ERROR: PySide6 is not installed. Please install it using: pip install PySide6")
    sys.exit(1)

# CUDA check
HAS_CUDA = False
try:
    import ctranslate2
    HAS_CUDA = ctranslate2.get_cuda_device_count() > 0
except Exception:
    pass

STRINGS = {
    "vi": {
        "title": "AutoCaption VEC",
        "input_file": "File đầu vào",
        "output_folder": "Thư mục lưu",
        "src_lang": "Ngôn ngữ nguồn",
        "model": "Kích thước Model",
        "device": "Thiết bị xử lý",
        "output_files": "Số file output",
        "trans_lang": "Ngôn ngữ dịch",
        "browse": "Chọn...",
        "start": "Tạo phụ đề",
        "cancel": "Hủy",
        "open_folder": "Mở thư mục lưu",
        "auto": "Tự động phát hiện",
        "lang_vi": "Tiếng Việt",
        "lang_en": "English",
        "lang_zh": "中文",
        "one_file": "1 file phụ đề (Gốc)",
        "two_files": "2 file phụ đề (Gốc + Dịch)",
        "drag_drop": "Kéo & Thả file audio/video vào đây\n(hoặc chọn file bên dưới)",
    },
    "en": {
        "title": "AutoCaption VEC",
        "input_file": "Input file",
        "output_folder": "Output folder",
        "src_lang": "Source language",
        "model": "Model size",
        "device": "Processing Device",
        "output_files": "Output files",
        "trans_lang": "Translation language",
        "browse": "Browse...",
        "start": "Generate subtitles",
        "cancel": "Cancel",
        "open_folder": "Open folder",
        "auto": "Auto detect",
        "lang_vi": "Tiếng Việt",
        "lang_en": "English",
        "lang_zh": "中文",
        "one_file": "1 subtitle file (Original)",
        "two_files": "2 subtitle files (Original + Translation)",
        "drag_drop": "Drag & Drop audio/video file here\n(or select file below)",
    },
    "zh": {
        "title": "AutoCaption VEC",
        "input_file": "输入文件",
        "output_folder": "输出文件夹",
        "src_lang": "源语言",
        "model": "模型",
        "device": "处理设备",
        "output_files": "输出文件",
        "trans_lang": "翻译语言",
        "browse": "选择...",
        "start": "生成字幕",
        "cancel": "取消",
        "open_folder": "打开文件夹",
        "auto": "自动检测",
        "lang_vi": "Tiếng Việt",
        "lang_en": "English",
        "lang_zh": "中文",
        "one_file": "1个字幕文件",
        "two_files": "2个字幕文件(原文+翻译)",
        "drag_drop": "拖拽音频/视频文件到此处\n(或在下方选择文件)",
    }
}

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]


def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def transcribe(input_path, language, model_size, device, log_fn, cancel_event, progress_callback=None):
    """Whisper transcription with incremental progress and cancellation check"""
    try:
        from faster_whisper import WhisperModel
        compute_type = "float16" if device == "cuda" else "int8"
        log_fn(f"Loading Whisper model '{model_size}' on {device.upper()} (Compute: {compute_type})...")
        
        # Load WhisperModel
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        
        log_fn(f"Processing audio: {input_path}")
        segments, info = model.transcribe(
            input_path,
            language=language if language != "auto" else None,
            beam_size=5,
            vad_filter=True
        )
        
        detected = info.language
        total_duration = info.duration
        log_fn(f"Detected language: {detected} (Duration: {total_duration:.1f}s)")
        
        segments_list = []
        for segment in segments:
            if cancel_event.is_set():
                log_fn("Transcription cancelled by user.")
                return None, detected
            
            segments_list.append(segment)
            log_fn(f"[{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}] {segment.text.strip()}")
            
            if progress_callback and total_duration > 0:
                # Map transcription progress between 0% and 80%
                percent = min(80, int((segment.end / total_duration) * 80))
                progress_callback(percent)
                
        return segments_list, detected
    except Exception as e:
        log_fn(f"ERROR during transcription: {e}")
        return None, None


def ensure_argos_package(src, tgt, log_fn):
    """Ensure Argos Translate package is installed offline-first, fallback to download"""
    try:
        import argostranslate.translate
        import argostranslate.package
        
        def path_exists_locally(s, t):
            installed_languages = argostranslate.translate.get_installed_languages()
            from_lang = next((l for l in installed_languages if l.code == s), None)
            to_lang = next((l for l in installed_languages if l.code == t), None)
            return from_lang and to_lang and from_lang.get_translation(to_lang)

        def install_single_package(s, t):
            if path_exists_locally(s, t):
                log_fn(f"Translation package {s} -> {t} is already installed locally.")
                return True
                
            log_fn(f"Installing translation package {s} -> {t} (internet connection required first time)...")
            try:
                argostranslate.package.update_package_index()
                available_packages = argostranslate.package.get_available_packages()
                pkg = next((p for p in available_packages if p.from_code == s and p.to_code == t), None)
                if pkg:
                    argostranslate.package.install_from_path(pkg.download())
                    log_fn(f"Successfully installed language package {s} -> {t}")
                    return True
            except Exception as ex:
                log_fn(f"Warning: Failed to install package {s} -> {t}: {ex}")
            return False

        # 1. Direct path check/install
        if path_exists_locally(src, tgt):
            return True
            
        if install_single_package(src, tgt):
            return True

        # 2. Pivot path check/install via English "en"
        if src != "en" and tgt != "en":
            log_fn(f"Direct package {src} -> {tgt} not found. Attempting pivot via English ('en')...")
            ok_src_to_en = install_single_package(src, "en")
            ok_en_to_tgt = install_single_package("en", tgt)
            if ok_src_to_en and ok_en_to_tgt:
                log_fn(f"Successfully configured pivot translation path: {src} -> en -> {tgt}")
                return True

        log_fn(f"Error: Cannot establish translation path from {src} to {tgt}.")
        return False
    except Exception as e:
        log_fn(f"ERROR establishing translation path: {e}")
        return False


def translate_segments(segments, src_lang, tgt_lang, log_fn, cancel_event, progress_fn=None):
    """Translate segments one-by-one with cancellation and progress reporting"""
    try:
        if not ensure_argos_package(src_lang, tgt_lang, log_fn):
            return None
        
        import argostranslate.translate
        translated = []
        total = len(segments)
        for i, seg in enumerate(segments):
            if cancel_event.is_set():
                log_fn("Translation cancelled by user.")
                return None
                
            trans_text = argostranslate.translate.translate(seg.text, src_lang, tgt_lang)
            translated.append(type('Segment', (), {'start': seg.start, 'end': seg.end, 'text': trans_text})())
            
            if progress_fn and total > 0:
                # Map translation progress from 80% to 100%
                percent = 80 + int((i + 1) / total * 20)
                progress_fn(percent)
                
        return translated
    except Exception as e:
        log_fn(f"ERROR translating: {e}")
        return None


def build_srt(segments):
    """Format segments list into standard SRT text"""
    srt = ""
    for i, seg in enumerate(segments, 1):
        start_str = format_timestamp(seg.start)
        end_str = format_timestamp(seg.end)
        srt += f"{i}\n{start_str} --> {end_str}\n{seg.text.strip()}\n\n"
    return srt


def save_srt(path, srt_text, log_fn):
    """Write SRT text to file"""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(srt_text)
        log_fn(f"Saved: {path}")
        return True
    except Exception as e:
        log_fn(f"ERROR saving SRT file: {e}")
        return False


class DropZoneFrame(QtWidgets.QFrame):
    """Custom QFrame that handles drag and drop of media files"""
    file_dropped = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = os.path.splitext(url.toLocalFile())[1].lower()
                if ext in [".mp4", ".avi", ".mov", ".mkv", ".wav", ".mp3", ".m4a"]:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.isfile(file_path):
                self.file_dropped.emit(file_path)
                break


class Worker(QtCore.QObject):
    """Background worker handling transcription and translation tasks"""
    log_signal = QtCore.Signal(str)
    progress_signal = QtCore.Signal(int)
    finished_signal = QtCore.Signal(bool, list)
    error_signal = QtCore.Signal(str)

    def __init__(self, input_file, output_folder, src_lang, model_size, output_files, trans_lang, device):
        super().__init__()
        self.input_file = input_file
        self.output_folder = output_folder
        self.src_lang = src_lang
        self.model_size = model_size
        self.output_files = output_files
        self.trans_lang = trans_lang
        self.device = device
        self.cancel_event = threading.Event()

    def run(self):
        try:
            saved_paths = []
            
            self.log_signal.emit(f"Starting process for file: {self.input_file}")
            segments, detected = transcribe(
                self.input_file, 
                self.src_lang, 
                self.model_size, 
                self.device, 
                self.log_signal.emit, 
                self.cancel_event, 
                self.progress_signal.emit
            )
            
            if segments is None:
                self.finished_signal.emit(False, [])
                return

            self.progress_signal.emit(80)
            base_name = os.path.splitext(os.path.basename(self.input_file))[0]
            
            srt_path = os.path.join(self.output_folder, f"{base_name}_{detected}.srt")
            if save_srt(srt_path, build_srt(segments), self.log_signal.emit):
                saved_paths.append(srt_path)

            # Translation handling (if selected)
            if self.output_files == 1:  # Index 1 = 2 files (gốc + dịch)
                if self.trans_lang == detected:
                    self.log_signal.emit(f"Target language matches detected language ({detected}). Copying original subtitle.")
                    srt_trans = os.path.join(self.output_folder, f"{base_name}_{self.trans_lang}.srt")
                    if save_srt(srt_trans, build_srt(segments), self.log_signal.emit):
                        saved_paths.append(srt_trans)
                else:
                    self.log_signal.emit(f"Translating to language: {self.trans_lang}...")
                    trans_segments = translate_segments(
                        segments, 
                        detected, 
                        self.trans_lang, 
                        self.log_signal.emit, 
                        self.cancel_event, 
                        self.progress_signal.emit
                    )
                    
                    if trans_segments:
                        srt_trans = os.path.join(self.output_folder, f"{base_name}_{self.trans_lang}.srt")
                        if save_srt(srt_trans, build_srt(trans_segments), self.log_signal.emit):
                            saved_paths.append(srt_trans)
                            
            self.progress_signal.emit(100)
            self.finished_signal.emit(True, saved_paths)
        except Exception as e:
            self.error_signal.emit(str(e))
            self.finished_signal.emit(False, [])


class App(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self._ui_lang = "vi"
        self._running = False
        self._worker_thread = None
        self._worker = None
        self._out_files_idx = 0
        self._trans_idx = 0

        self._setup_theme()
        self._build_ui()
        self._load_settings()
        self._refresh_lang()

    def _setup_theme(self):
        QtWidgets.QApplication.setStyle("Fusion")
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#0f172a"))       # Slate 900
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#f8fafc"))   # Slate 50
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#020617"))         # Slate 950
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#0f172a"))
        palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor("#020617"))
        palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor("#f8fafc"))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#f8fafc"))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor("#1e293b"))       # Slate 800
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#f8fafc"))
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#3b82f6"))    # Blue 500
        palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
        QtWidgets.QApplication.setPalette(palette)

    def _build_ui(self):
        self.setWindowTitle("AutoCaption VEC")
        self.resize(1100, 750)
        self.setMinimumSize(950, 650)

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)

        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Top bar
        top = QtWidgets.QFrame(self)
        top.setStyleSheet("background-color: #0f172a; border: 1px solid #1f2937; border-radius: 16px;")
        top_layout = QtWidgets.QHBoxLayout(top)
        top_layout.setContentsMargins(16, 12, 16, 12)
        
        title = QtWidgets.QLabel("AutoCaption VEC")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #f8fafc;")
        top_layout.addWidget(title)
        top_layout.addStretch()
        
        self._lang_combo = QtWidgets.QComboBox()
        self._lang_combo.addItems(["Việt", "EN", "中文"])
        self._lang_combo.setCurrentIndex(0)
        self._lang_combo.currentIndexChanged.connect(self._on_ui_lang_change)
        top_layout.addWidget(self._lang_combo)
        main_layout.addWidget(top)

        # Content: Left (form) + Right (log)
        content = QtWidgets.QHBoxLayout()
        content.setSpacing(16)

        # Left panel: Form
        left_card = QtWidgets.QFrame(self)
        left_card.setStyleSheet("background-color: #0f172a; border: 1px solid #1f2937; border-radius: 18px;")
        left_layout = QtWidgets.QVBoxLayout(left_card)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        self._build_form(left_layout)
        content.addWidget(left_card, 1)

        # Right panel: Log
        right_card = QtWidgets.QFrame(self)
        right_card.setStyleSheet("background-color: #0f172a; border: 1px solid #1f2937; border-radius: 18px;")
        right_layout = QtWidgets.QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(8)

        self._build_log(right_layout)
        content.addWidget(right_card, 1)

        main_layout.addLayout(content, 1)

        # Status bar
        status = QtWidgets.QFrame(self)
        status.setStyleSheet("background-color: #0f172a; border: 1px solid #1f2937; border-radius: 14px;")
        status_layout = QtWidgets.QHBoxLayout(status)
        status_layout.setContentsMargins(12, 8, 12, 8)
        self._status_label = QtWidgets.QLabel("Ready")
        self._status_label.setStyleSheet("color: #cbd5e1;")
        status_layout.addWidget(self._status_label)
        main_layout.addWidget(status)

    def _build_form(self, parent_layout):
        # Drop Zone Frame
        self._drop_zone = DropZoneFrame()
        self._drop_zone.setObjectName("DropZone")
        self._drop_zone.setStyleSheet("""
            QFrame#DropZone {
                border: 2px dashed #2563eb;
                border-radius: 12px;
                background-color: #020617;
            }
            QFrame#DropZone:hover {
                border: 2px dashed #3b82f6;
                background-color: #0f172a;
            }
        """)
        self._drop_zone.setMinimumHeight(100)
        self._drop_zone.file_dropped.connect(self._on_file_dropped)
        
        drop_layout = QtWidgets.QVBoxLayout(self._drop_zone)
        self._lbl_drop = QtWidgets.QLabel()
        self._lbl_drop.setAlignment(QtCore.Qt.AlignCenter)
        self._lbl_drop.setStyleSheet("font-size: 14px; font-weight: 500; color: #94a3b8; border: none; background: transparent;")
        drop_layout.addWidget(self._lbl_drop)
        parent_layout.addWidget(self._drop_zone)

        # Input file row
        input_row = QtWidgets.QHBoxLayout()
        self._lbl_input = QtWidgets.QLabel()
        self._input_edit = QtWidgets.QLineEdit()
        self._btn_browse_input = QtWidgets.QPushButton()
        input_row.addWidget(self._lbl_input, 0)
        input_row.addWidget(self._input_edit, 1)
        input_row.addWidget(self._btn_browse_input, 0)
        parent_layout.addLayout(input_row)

        # Output folder row
        output_row = QtWidgets.QHBoxLayout()
        self._lbl_output = QtWidgets.QLabel()
        self._output_edit = QtWidgets.QLineEdit()
        self._btn_browse_output = QtWidgets.QPushButton()
        output_row.addWidget(self._lbl_output, 0)
        output_row.addWidget(self._output_edit, 1)
        output_row.addWidget(self._btn_browse_output, 0)
        parent_layout.addLayout(output_row)

        parent_layout.addSpacing(8)

        # Source language
        src_row = QtWidgets.QHBoxLayout()
        self._lbl_src_lang = QtWidgets.QLabel()
        self._cmb_src_lang = QtWidgets.QComboBox()
        src_row.addWidget(self._lbl_src_lang, 0)
        src_row.addWidget(self._cmb_src_lang, 1)
        parent_layout.addLayout(src_row)

        # Model size
        model_row = QtWidgets.QHBoxLayout()
        self._lbl_model = QtWidgets.QLabel()
        self._cmb_model = QtWidgets.QComboBox()
        self._cmb_model.addItems(MODEL_SIZES)
        self._cmb_model.setCurrentIndex(3)
        model_row.addWidget(self._lbl_model, 0)
        model_row.addWidget(self._cmb_model, 1)
        parent_layout.addLayout(model_row)

        # Device (CPU / GPU)
        device_row = QtWidgets.QHBoxLayout()
        self._lbl_device = QtWidgets.QLabel()
        self._cmb_device = QtWidgets.QComboBox()
        self._cmb_device.addItems(["CPU", "GPU (CUDA)"])
        if HAS_CUDA:
            self._cmb_device.setCurrentIndex(1)
        else:
            self._cmb_device.setCurrentIndex(0)
            self._cmb_device.setItemText(1, "GPU (CUDA) - Not Available")
            self._cmb_device.model().item(1).setEnabled(False)
        device_row.addWidget(self._lbl_device, 0)
        device_row.addWidget(self._cmb_device, 1)
        parent_layout.addLayout(device_row)

        # Output files
        out_row = QtWidgets.QHBoxLayout()
        self._lbl_out_files = QtWidgets.QLabel()
        self._cmb_out_files = QtWidgets.QComboBox()
        self._cmb_out_files.currentIndexChanged.connect(self._on_out_files_change)
        out_row.addWidget(self._lbl_out_files, 0)
        out_row.addWidget(self._cmb_out_files, 1)
        parent_layout.addLayout(out_row)

        # Translation language
        trans_row = QtWidgets.QHBoxLayout()
        self._lbl_trans = QtWidgets.QLabel()
        self._cmb_trans = QtWidgets.QComboBox()
        self._cmb_trans.currentIndexChanged.connect(self._on_trans_change)
        self._cmb_trans.setEnabled(False)
        trans_row.addWidget(self._lbl_trans, 0)
        trans_row.addWidget(self._cmb_trans, 1)
        parent_layout.addLayout(trans_row)

        parent_layout.addSpacing(12)

        # Progress bar
        self._progress = QtWidgets.QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #1f2937;
                border-radius: 8px;
                text-align: center;
                background-color: #020617;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 8px;
            }
        """)
        parent_layout.addWidget(self._progress)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(8)
        self._btn_start = QtWidgets.QPushButton()
        self._btn_cancel = QtWidgets.QPushButton()
        self._btn_cancel.setEnabled(False)
        self._btn_open = QtWidgets.QPushButton()
        btn_layout.addWidget(self._btn_start)
        btn_layout.addWidget(self._btn_cancel)
        btn_layout.addWidget(self._btn_open)
        parent_layout.addLayout(btn_layout)

        parent_layout.addStretch()

        # Styles
        control_style = """
            QLineEdit, QComboBox {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px 10px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1e293b;
                color: #f1f5f9;
                selection-background-color: #3b82f6;
            }
        """
        self._input_edit.setStyleSheet(control_style)
        self._output_edit.setStyleSheet(control_style)
        self._cmb_src_lang.setStyleSheet(control_style)
        self._cmb_model.setStyleSheet(control_style)
        self._cmb_device.setStyleSheet(control_style)
        self._cmb_out_files.setStyleSheet(control_style)
        self._cmb_trans.setStyleSheet(control_style)

        btn_style_accent = """
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            QPushButton:disabled {
                background-color: #475569;
                color: #94a3b8;
            }
        """
        btn_style = """
            QPushButton {
                background-color: #334155;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #475569;
            }
            QPushButton:pressed {
                background-color: #1e293b;
            }
            QPushButton:disabled {
                background-color: #475569;
                color: #94a3b8;
            }
        """

        self._btn_browse_input.setStyleSheet(btn_style)
        self._btn_browse_output.setStyleSheet(btn_style)
        self._btn_start.setStyleSheet(btn_style_accent)
        self._btn_cancel.setStyleSheet(btn_style)
        self._btn_open.setStyleSheet(btn_style)

        # Connect slots
        self._btn_browse_input.clicked.connect(self._browse_input)
        self._btn_browse_output.clicked.connect(self._browse_output)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_open.clicked.connect(self._open_output_folder)

    def _build_log(self, parent_layout):
        label = QtWidgets.QLabel("Subtitles / Processing Log")
        label.setStyleSheet("font-weight: 600; color: #f8fafc;")
        parent_layout.addWidget(label)
        
        self._log_text = QtWidgets.QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setFont(QtGui.QFont("Consolas", 10))
        self._log_text.setPlainText("Your subtitles and logs will appear here\nwhen finished transcribing")
        self._log_text.setStyleSheet("""
            QTextEdit {
                background-color: #020617;
                color: #f1f5f9;
                border: 1px solid #1f2937;
                border-radius: 14px;
                padding: 10px;
            }
        """)
        parent_layout.addWidget(self._log_text, 1)

    def _load_settings(self):
        """Restore previous configuration on startup"""
        settings = QtCore.QSettings("AutoCaptionVEC", "Settings")
        
        ui_lang_idx = int(settings.value("ui_lang_index", 0))
        self._lang_combo.setCurrentIndex(ui_lang_idx)
        
        self._input_edit.setText(settings.value("input_file", ""))
        self._output_edit.setText(settings.value("output_folder", ""))
        
        self._cmb_src_lang.setCurrentIndex(int(settings.value("src_lang_index", 0)))
        
        model = settings.value("model_size", "medium")
        if model in MODEL_SIZES:
            self._cmb_model.setCurrentText(model)
            
        device_idx = int(settings.value("device_index", 1 if HAS_CUDA else 0))
        if device_idx == 1 and not HAS_CUDA:
            device_idx = 0
        self._cmb_device.setCurrentIndex(device_idx)
            
        self._out_files_idx = int(settings.value("output_files_index", 0))
        self._cmb_out_files.setCurrentIndex(self._out_files_idx)
        
        self._trans_idx = int(settings.value("trans_lang_index", 0))
        self._cmb_trans.setCurrentIndex(self._trans_idx)

    def _save_settings(self):
        """Save settings configuration"""
        settings = QtCore.QSettings("AutoCaptionVEC", "Settings")
        settings.setValue("ui_lang_index", self._lang_combo.currentIndex())
        settings.setValue("input_file", self._input_edit.text())
        settings.setValue("output_folder", self._output_edit.text())
        settings.setValue("src_lang_index", self._cmb_src_lang.currentIndex())
        settings.setValue("model_size", self._cmb_model.currentText())
        settings.setValue("device_index", self._cmb_device.currentIndex())
        settings.setValue("output_files_index", self._cmb_out_files.currentIndex())
        settings.setValue("trans_lang_index", self._cmb_trans.currentIndex())

    def _refresh_lang(self):
        s = STRINGS[self._ui_lang]
        self.setWindowTitle(s["title"])
        self._lbl_drop.setText(s["drag_drop"])
        self._lbl_input.setText(s["input_file"])
        self._btn_browse_input.setText(s["browse"])
        self._lbl_output.setText(s["output_folder"])
        self._btn_browse_output.setText(s["browse"])
        self._lbl_src_lang.setText(s["src_lang"])
        self._lbl_model.setText(s["model"])
        self._lbl_device.setText(s["device"])
        self._lbl_out_files.setText(s["output_files"])
        self._lbl_trans.setText(s["trans_lang"])
        self._btn_start.setText(s["start"])
        self._btn_cancel.setText(s["cancel"])
        self._btn_open.setText(s["open_folder"])

        src_options = [s["auto"], s["lang_vi"], s["lang_en"], s["lang_zh"]]
        self._cmb_src_lang.blockSignals(True)
        self._cmb_src_lang.clear()
        self._cmb_src_lang.addItems(src_options)
        self._cmb_src_lang.blockSignals(False)

        out_options = [s["one_file"], s["two_files"]]
        self._cmb_out_files.blockSignals(True)
        self._cmb_out_files.clear()
        self._cmb_out_files.addItems(out_options)
        self._cmb_out_files.setCurrentIndex(self._out_files_idx)
        self._cmb_out_files.blockSignals(False)

        trans_options = [s["lang_en"], s["lang_vi"], s["lang_zh"]]
        self._cmb_trans.blockSignals(True)
        self._cmb_trans.clear()
        self._cmb_trans.addItems(trans_options)
        self._cmb_trans.setCurrentIndex(self._trans_idx)
        self._cmb_trans.blockSignals(False)
        self._cmb_trans.setEnabled(self._out_files_idx == 1)

    def _on_ui_lang_change(self):
        langs = ["vi", "en", "zh"]
        self._ui_lang = langs[self._lang_combo.currentIndex()]
        self._refresh_lang()

    def _on_out_files_change(self):
        self._out_files_idx = self._cmb_out_files.currentIndex()
        self._cmb_trans.setEnabled(self._out_files_idx == 1)

    def _on_trans_change(self):
        self._trans_idx = self._cmb_trans.currentIndex()

    def _on_file_dropped(self, file_path):
        self._input_edit.setText(file_path)
        if not self._output_edit.text():
            self._output_edit.setText(os.path.dirname(file_path))

    def _browse_input(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select video/audio file", "", "Media Files (*.mp4 *.avi *.mov *.mkv *.wav *.mp3 *.m4a)")
        if path:
            self._input_edit.setText(path)
            if not self._output_edit.text():
                self._output_edit.setText(os.path.dirname(path))

    def _browse_output(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select output folder")
        if path:
            self._output_edit.setText(path)

    def _on_start(self):
        if not self._input_edit.text() or not self._output_edit.text():
            QtWidgets.QMessageBox.warning(self, "Error", "Please select an input file and an output folder.")
            return

        if not os.path.isfile(self._input_edit.text()):
            QtWidgets.QMessageBox.warning(self, "Error", "Input file does not exist.")
            return

        self._save_settings()
        self._running = True
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._progress.setValue(0)
        self._log_text.clear()

        # Gather inputs
        src_idx = self._cmb_src_lang.currentIndex()
        src_lang = ["auto", "vi", "en", "zh"][src_idx]
        model_size = self._cmb_model.currentText()
        output_files = self._cmb_out_files.currentIndex()
        trans_lang = ["en", "vi", "zh"][self._cmb_trans.currentIndex()]
        
        device = "cuda" if self._cmb_device.currentIndex() == 1 and HAS_CUDA else "cpu"

        # Worker initialization
        self._worker = Worker(self._input_edit.text(), self._output_edit.text(), src_lang, model_size, output_files, trans_lang, device)
        self._worker_thread = QtCore.QThread()
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.log_signal.connect(self._on_log)
        self._worker.progress_signal.connect(self._on_progress)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.error_signal.connect(self._on_error)

        self._status_label.setText(f"Processing with Whisper ({device.upper()})...")
        self._worker_thread.start()

    def _on_cancel(self):
        self._status_label.setText("Cancelling...")
        if self._worker:
            self._worker.cancel_event.set()
        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)

    def _on_log(self, msg):
        self._log_text.append(msg)
        # Ensure log view scrolls to bottom automatically
        self._log_text.moveCursor(QtGui.QTextCursor.End)

    def _on_progress(self, percent):
        self._progress.setValue(percent)

    def _on_error(self, error_msg):
        self._log_text.append(f"\n[ERROR] {error_msg}")

    def _on_finished(self, success, paths):
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()

        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)

        if success:
            self._status_label.setText("Finished successfully!")
            paths_str = "\n".join(paths)
            QtWidgets.QMessageBox.information(
                self, 
                "Success", 
                f"Subtitles created successfully!\n\nSaved files:\n{paths_str}"
            )
        else:
            self._status_label.setText("Cancelled or failed.")
            QtWidgets.QMessageBox.warning(self, "Failed", "Process was cancelled or failed. Check the logs for details.")

    def _open_output_folder(self):
        path = self._output_edit.text()
        if path and os.path.isdir(path):
            os.startfile(path)

    def closeEvent(self, event):
        self._save_settings()
        if self._running:
            self._on_cancel()
        event.accept()


def main():
    if MISSING_DEPS:
        # Create a temporary app to show dependency error
        temp_app = QtWidgets.QApplication(sys.argv)
        msg = (
            f"Missing required Python libraries: {', '.join(MISSING_DEPS)}.\n\n"
            f"Please run the following command in terminal to install them:\n"
            f"pip install -r requirements.txt"
        )
        QtWidgets.QMessageBox.critical(None, "Dependency Error - AutoCaption VEC", msg)
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
