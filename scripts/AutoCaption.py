#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoCaption GUI Launcher
Supports Whisper audio transcription (local CPU/GPU) with batch processing.
"""

import sys
import os
import threading
import importlib.util

# Disable Hugging Face symlinks warning on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Check dependencies using find_spec (prevent Shiboken hooks causing import hang)
MISSING_DEPS = []
if importlib.util.find_spec("faster_whisper") is None:
    MISSING_DEPS.append("faster-whisper")

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

def transcribe(input_path, language, model_size, device, log_fn=print, cancel_event=None, progress_callback=None):
    """Whisper transcription with incremental progress and cancellation check"""
    try:
        from faster_whisper import WhisperModel
        compute_type = "float16" if device == "cuda" else "int8"
        log_fn(f"Loading Whisper model '{model_size}' on {device.upper()} (Compute: {compute_type})...")
        
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        
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
        log_fn(f"ERROR saving SRT file: {e}")
        return False

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]


class CardFrame(QtWidgets.QFrame):
    double_clicked = QtCore.Signal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
            }
            QFrame:hover {
                background-color: #334155;
                border: 1px solid #3b82f6;
            }
        """)
        self.setFixedSize(90, 100)
        self.setToolTip(path)
        
        card_layout = QtWidgets.QVBoxLayout(self)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(4)
        card_layout.setAlignment(QtCore.Qt.AlignCenter)
        
        # Icon label
        icon_lbl = QtWidgets.QLabel()
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        icon_provider = QtWidgets.QFileIconProvider()
        file_info = QtCore.QFileInfo(path)
        icon = icon_provider.icon(file_info)
        icon_lbl.setPixmap(icon.pixmap(40, 40))
        icon_lbl.setAlignment(QtCore.Qt.AlignCenter)
        
        # Text label
        text_lbl = QtWidgets.QLabel()
        text_lbl.setStyleSheet("font-size: 10px; color: #cbd5e1; border: none; background: transparent;")
        text_lbl.setAlignment(QtCore.Qt.AlignCenter)
        
        filename = os.path.basename(path)
        metrics = QtGui.QFontMetrics(text_lbl.font())
        elided = metrics.elidedText(filename, QtCore.Qt.ElideRight, 78)
        text_lbl.setText(elided)
        
        card_layout.addWidget(icon_lbl)
        card_layout.addWidget(text_lbl)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.path)


class SuccessPopup(QtWidgets.QDialog):
    def __init__(self, saved_paths, parent=None):
        super().__init__(parent)
        self.saved_paths = saved_paths
        
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Dialog)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        self.resize(450, 260)
        
        # Background frame
        frame = QtWidgets.QFrame(self)
        frame.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 2px solid #2563eb;
                border-radius: 16px;
            }
        """)
        
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Header
        header_layout = QtWidgets.QHBoxLayout()
        title_lbl = QtWidgets.QLabel("Success")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #3b82f6; border: none; background: transparent;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        
        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                font-size: 14px;
                border: none;
            }
            QPushButton:hover {
                color: #f8fafc;
            }
        """)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)
        layout.addLayout(header_layout)
        
        # Body
        body_lbl = QtWidgets.QLabel("Subtitles created successfully!")
        body_lbl.setStyleSheet("font-size: 14px; color: #f8fafc; border: none; background: transparent;")
        layout.addWidget(body_lbl)
        
        # File list
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #020617;
                border: 1px solid #1f2937;
                border-radius: 8px;
                color: #cbd5e1;
                font-size: 11px;
                padding: 4px;
            }
        """)
        self.list_widget.setFixedHeight(80)
        for p in saved_paths:
            item = QtWidgets.QListWidgetItem(os.path.basename(p))
            item.setToolTip(p)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
        
        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(10)
        
        open_folder_btn = QtWidgets.QPushButton("Open Folder")
        open_folder_btn.setStyleSheet("""
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
        """)
        open_folder_btn.clicked.connect(self.on_open_folder)
        
        ok_btn = QtWidgets.QPushButton("OK")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        ok_btn.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(open_folder_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)
        
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(frame)
        
    def on_open_folder(self):
        if self.saved_paths:
            dir_path = os.path.dirname(self.saved_paths[0])
            if os.path.isdir(dir_path):
                try:
                    if sys.platform == "win32":
                        os.startfile(dir_path)
                    elif sys.platform == "darwin":
                        import subprocess
                        subprocess.Popen(["open", dir_path])
                    else:
                        import subprocess
                        subprocess.Popen(["xdg-open", dir_path])
                except Exception:
                    pass
        self.accept()


class DropZoneFrame(QtWidgets.QFrame):
    """Custom QFrame that handles drag and drop of multiple media files"""
    files_dropped = QtCore.Signal(list)

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
        dropped_files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.isfile(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                if ext in [".mp4", ".avi", ".mov", ".mkv", ".wav", ".mp3", ".m4a"]:
                    dropped_files.append(file_path)
        if dropped_files:
            self.files_dropped.emit(dropped_files)


class Worker(QtCore.QObject):
    """Background worker handling multiple transcription tasks sequentially"""
    log_signal = QtCore.Signal(str)
    progress_signal = QtCore.Signal(int)
    finished_signal = QtCore.Signal(bool, list)
    error_signal = QtCore.Signal(str)

    def __init__(self, input_files, output_folder, src_lang, model_size, device):
        super().__init__()
        self.input_files = input_files
        self.output_folder = output_folder
        self.src_lang = src_lang
        self.model_size = model_size
        self.device = device
        self.cancel_event = threading.Event()

    def run(self):
        try:
            saved_paths = []
            total_files = len(self.input_files)
            
            for idx, input_file in enumerate(self.input_files):
                if self.cancel_event.is_set():
                    break
                    
                self.log_signal.emit(f"\n========================================\n"
                                     f"[{idx+1}/{total_files}] Processing: {os.path.basename(input_file)}\n"
                                     f"========================================")
                
                # Combine current file progress with overall batch progress
                def make_progress_cb(current_idx):
                    return lambda percent: self.progress_signal.emit(
                        int((current_idx * 100 + percent) / total_files)
                    )
                
                segments, detected = transcribe(
                    input_file, 
                    self.src_lang, 
                    self.model_size, 
                    self.device, 
                    self.log_signal.emit, 
                    self.cancel_event, 
                    make_progress_cb(idx)
                )
                
                if segments is None:
                    if self.cancel_event.is_set():
                        break
                    self.log_signal.emit(f"ERROR: Transcription failed for {os.path.basename(input_file)}")
                    continue
                    
                base_name = os.path.splitext(os.path.basename(input_file))[0]
                srt_path = os.path.join(self.output_folder, f"{base_name}_{detected}.srt")
                if save_srt(srt_path, build_srt(segments), self.log_signal.emit):
                    saved_paths.append(srt_path)
                    
                # Mark file progress as 100% complete
                self.progress_signal.emit(int((idx + 1) * 100 / total_files))
                
            if self.cancel_event.is_set():
                self.finished_signal.emit(False, [])
            else:
                self.finished_signal.emit(True, saved_paths)
        except Exception as e:
            self.error_signal.emit(str(e))
            self.finished_signal.emit(False, [])


class App(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self._running = False
        self._worker_thread = None
        self._worker = None

        self._setup_theme()
        self._build_ui()
        self._load_settings()

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
        self.setWindowTitle("AutoCaption")
        self.resize(600, 750)
        self.setMinimumSize(550, 650)

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
        
        title = QtWidgets.QLabel("AutoCaption")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #f8fafc;")
        top_layout.addWidget(title)
        top_layout.addStretch()
        
        self._btn_toggle_log = QtWidgets.QPushButton("Show Log")
        self._btn_toggle_log.clicked.connect(self._toggle_log_panel)
        self._btn_toggle_log.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)
        top_layout.addWidget(self._btn_toggle_log)
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
        self._log_panel = QtWidgets.QFrame(self)
        self._log_panel.setStyleSheet("background-color: #0f172a; border: 1px solid #1f2937; border-radius: 18px;")
        right_layout = QtWidgets.QVBoxLayout(self._log_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(8)

        self._build_log(right_layout)
        content.addWidget(self._log_panel, 1)

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
        self._drop_zone.setMinimumHeight(135)
        self._drop_zone.files_dropped.connect(self._on_files_dropped)
        
        drop_layout = QtWidgets.QVBoxLayout(self._drop_zone)
        drop_layout.setContentsMargins(8, 8, 8, 8)
        self._lbl_drop = QtWidgets.QLabel("Drag & Drop audio/video files here\n(or select files below)")
        self._lbl_drop.setAlignment(QtCore.Qt.AlignCenter)
        self._lbl_drop.setStyleSheet("font-size: 14px; font-weight: 500; color: #94a3b8; border: none; background: transparent;")
        drop_layout.addWidget(self._lbl_drop)

        # Scroll Area for files inside drop zone
        self._scroll_area = QtWidgets.QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFixedHeight(110)
        self._scroll_area.hide()
        
        scroll_content = QtWidgets.QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        self._files_layout = QtWidgets.QHBoxLayout(scroll_content)
        self._files_layout.setContentsMargins(4, 4, 4, 4)
        self._files_layout.setSpacing(8)
        self._files_layout.setAlignment(QtCore.Qt.AlignLeft)
        
        self._scroll_area.setWidget(scroll_content)
        drop_layout.addWidget(self._scroll_area)
        parent_layout.addWidget(self._drop_zone)

        # Input files list row
        self._lbl_input = QtWidgets.QLabel("Input files list")
        parent_layout.addWidget(self._lbl_input)

        list_row = QtWidgets.QHBoxLayout()
        self._input_list = QtWidgets.QListWidget()
        self._input_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self._input_list.setToolTip("Double click a file to remove it")
        self._input_list.setStyleSheet("""
            QListWidget {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px;
            }
        """)
        self._input_list.setMinimumHeight(120)
        self._input_list.itemDoubleClicked.connect(self._remove_list_item)
        
        list_btns = QtWidgets.QVBoxLayout()
        self._btn_browse_input = QtWidgets.QPushButton("Browse...")
        self._btn_clear_input = QtWidgets.QPushButton("✕")
        self._btn_clear_input.setToolTip("Clear all files")
        list_btns.addWidget(self._btn_browse_input)
        list_btns.addWidget(self._btn_clear_input)
        list_btns.addStretch()

        list_row.addWidget(self._input_list, 1)
        list_row.addLayout(list_btns, 0)
        parent_layout.addLayout(list_row)

        # Output folder row
        output_row = QtWidgets.QHBoxLayout()
        self._lbl_output = QtWidgets.QLabel("Output folder")
        self._output_edit = QtWidgets.QLineEdit()
        self._btn_browse_output = QtWidgets.QPushButton("Browse...")
        output_row.addWidget(self._lbl_output, 0)
        output_row.addWidget(self._output_edit, 1)
        output_row.addWidget(self._btn_browse_output, 0)
        parent_layout.addLayout(output_row)

        parent_layout.addSpacing(8)

        # Model size
        model_row = QtWidgets.QHBoxLayout()
        self._lbl_model = QtWidgets.QLabel("Model size")
        self._cmb_model = QtWidgets.QComboBox()
        self._cmb_model.addItems(MODEL_SIZES)
        self._cmb_model.setCurrentIndex(4)
        model_row.addWidget(self._lbl_model, 0)
        model_row.addWidget(self._cmb_model, 1)
        parent_layout.addLayout(model_row)

        # Device (CPU / GPU)
        device_row = QtWidgets.QHBoxLayout()
        self._lbl_device = QtWidgets.QLabel("Processing Device")
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
        self._btn_start = QtWidgets.QPushButton("Generate subtitles")
        self._btn_cancel = QtWidgets.QPushButton("Cancel")
        self._btn_cancel.setEnabled(False)
        self._btn_open = QtWidgets.QPushButton("Open folder")
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
        self._output_edit.setStyleSheet(control_style)
        self._cmb_model.setStyleSheet(control_style)
        self._cmb_device.setStyleSheet(control_style)

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
        self._btn_clear_input.setStyleSheet(btn_style)
        self._btn_browse_output.setStyleSheet(btn_style)
        self._btn_start.setStyleSheet(btn_style_accent)
        self._btn_cancel.setStyleSheet(btn_style)
        self._btn_open.setStyleSheet(btn_style)

        # Connect slots
        self._btn_browse_input.clicked.connect(self._browse_input)
        self._btn_clear_input.clicked.connect(self._clear_input_list)
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

    def _add_input_file(self, path):
        # Prevent duplicates
        for i in range(self._input_list.count()):
            item = self._input_list.item(i)
            if item.data(QtCore.Qt.UserRole) == path:
                return
                
        # Display filename only in bottom list, store full path in UserRole (no icon at bottom)
        filename = os.path.basename(path)
        item = QtWidgets.QListWidgetItem(filename)
        item.setData(QtCore.Qt.UserRole, path)
        item.setToolTip(path)
        self._input_list.addItem(item)

    def _update_drop_zone_visuals(self):
        # Clear existing widgets from self._files_layout
        while self._files_layout.count():
            item = self._files_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
                
        count = self._input_list.count()
        if count == 0:
            self._lbl_drop.show()
            self._scroll_area.hide()
        else:
            self._lbl_drop.hide()
            self._scroll_area.show()
            
            for i in range(count):
                path = self._input_list.item(i).data(QtCore.Qt.UserRole)
                card = CardFrame(path)
                card.double_clicked.connect(self._remove_file_by_path)
                self._files_layout.addWidget(card)

    def _remove_file_by_path(self, path):
        for i in range(self._input_list.count()):
            if self._input_list.item(i).data(QtCore.Qt.UserRole) == path:
                self._input_list.takeItem(i)
                break
        self._update_drop_zone_visuals()
        self._save_settings()

    def _remove_list_item(self, item):
        self._input_list.takeItem(self._input_list.row(item))
        self._update_drop_zone_visuals()
        self._save_settings()

    def _clear_input_list(self):
        self._input_list.clear()
        self._update_drop_zone_visuals()
        self._save_settings()

    def _load_settings(self):
        """Restore previous configuration on startup"""
        settings = QtCore.QSettings("AutoCaption", "Settings")
        
        # Determine default Downloads directory
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.exists(default_dir):
            default_dir = os.path.expanduser("~")
            
        self._last_input_dir = settings.value("last_input_dir", default_dir)
        self._last_output_dir = settings.value("last_output_dir", default_dir)
        
        self._output_edit.setText(settings.value("output_folder", ""))
        
        model = settings.value("model_size", "large-v3-turbo")
        if model in MODEL_SIZES:
            self._cmb_model.setCurrentText(model)
            
        device_idx = int(settings.value("device_index", 1 if HAS_CUDA else 0))
        if device_idx == 1 and not HAS_CUDA:
            device_idx = 0
        self._cmb_device.setCurrentIndex(device_idx)

        # Restore input files list
        self._input_list.clear()
        input_files = settings.value("input_files_list", [])
        if isinstance(input_files, str):
            if input_files and os.path.exists(input_files):
                self._add_input_file(input_files)
        elif isinstance(input_files, list):
            for path in input_files:
                if os.path.exists(path):
                    self._add_input_file(path)
        self._update_drop_zone_visuals()

        # Always start with log panel hidden on launch
        self._log_panel.setVisible(False)
        self.setMinimumWidth(550)
        self.resize(600, 750)

    def _save_settings(self):
        """Save settings configuration"""
        settings = QtCore.QSettings("AutoCaption", "Settings")
        settings.setValue("output_folder", self._output_edit.text())
        settings.setValue("model_size", self._cmb_model.currentText())
        settings.setValue("device_index", self._cmb_device.currentIndex())
        
        # Save input files list
        input_files = [self._input_list.item(i).data(QtCore.Qt.UserRole) for i in range(self._input_list.count())]
        settings.setValue("input_files_list", input_files)
        
        # Save last navigated directories
        if input_files and os.path.exists(os.path.dirname(input_files[0])):
            self._last_input_dir = os.path.dirname(input_files[0])
            
        output_text = self._output_edit.text()
        if output_text and os.path.exists(output_text):
            self._last_output_dir = output_text
            
        settings.setValue("last_input_dir", self._last_input_dir)
        settings.setValue("last_output_dir", self._last_output_dir)

    def _toggle_log_panel(self):
        show = not self._log_panel.isVisible()
        self._log_panel.setVisible(show)
        self.setMinimumWidth(950 if show else 550)
        self.resize(1100 if show else 600, self.height())
        self._btn_toggle_log.setText("Hide Log" if show else "Show Log")
        self._save_settings()

    def _add_files_and_update(self, paths):
        """Common logic for adding files from drop or browse"""
        for path in paths:
            self._add_input_file(path)
        self._update_drop_zone_visuals()
        if paths:
            self._last_input_dir = os.path.dirname(paths[0])
            if not self._output_edit.text():
                self._output_edit.setText(os.path.dirname(paths[0]))
                self._last_output_dir = os.path.dirname(paths[0])
        self._save_settings()

    def _on_files_dropped(self, file_paths):
        self._add_files_and_update(file_paths)

    def _browse_input(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select video/audio files", self._last_input_dir, 
            "Media Files (*.mp4 *.avi *.mov *.mkv *.wav *.mp3 *.m4a)"
        )
        if paths:
            self._add_files_and_update(paths)

    def _browse_output(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select output folder", self._last_output_dir)
        if path:
            self._output_edit.setText(path)
            self._last_output_dir = path
            self._save_settings()

    def _on_start(self):
        if self._input_list.count() == 0 or not self._output_edit.text():
            QtWidgets.QMessageBox.warning(self, "Error", "Please select input files and an output folder.")
            return

        for i in range(self._input_list.count()):
            file_path = self._input_list.item(i).data(QtCore.Qt.UserRole)
            if not os.path.isfile(file_path):
                QtWidgets.QMessageBox.warning(self, "Error", f"Input file does not exist:\n{file_path}")
                return

        self._save_settings()
        self._running = True
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._progress.setValue(0)
        self._log_text.clear()

        # Gather inputs
        src_lang = "auto"
        model_size = self._cmb_model.currentText()
        device = "cuda" if self._cmb_device.currentIndex() == 1 and HAS_CUDA else "cpu"

        # Gather input files list
        input_files = [self._input_list.item(i).data(QtCore.Qt.UserRole) for i in range(self._input_list.count())]

        # Worker initialization
        self._worker = Worker(input_files, self._output_edit.text(), src_lang, model_size, device)
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
            popup = SuccessPopup(paths, self)
            popup.exec()
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


def cli_main():
    # Configure UTF-8 output to avoid UnicodeEncodeError on Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if len(sys.argv) < 3:
        print("Usage: python AutoCaption.py <input_media_file> <output_srt_file> [language] [model_size]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    language = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
    model_size = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else "large-v3-turbo"

    print(f"DEBUG: language={language}, model_size={model_size}")

    if not os.path.isfile(input_path):
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(2)

    device = "cpu"
    if HAS_CUDA:
        device = "cuda"

    segments, detected = transcribe(input_path, language, model_size, device)
    if segments is None:
        sys.exit(4)

    srt_text = build_srt(segments)
    if not save_srt(output_path, srt_text):
        sys.exit(5)
        
    print(f"OK: Subtitle file created at {output_path}")
    sys.exit(0)


def main():
    if len(sys.argv) > 1 and sys.argv[1] != "--gui":
        cli_main()
        return
    if MISSING_DEPS:
        temp_app = QtWidgets.QApplication(sys.argv)
        msg = (
            f"Missing required Python libraries: {', '.join(MISSING_DEPS)}.\n\n"
            f"Please run the following command in terminal to install them:\n"
            f"pip install -r requirements.txt"
        )
        QtWidgets.QMessageBox.critical(None, "Dependency Error - AutoCaption", msg)
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
