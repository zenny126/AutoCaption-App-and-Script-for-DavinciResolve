#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoCaption PySide6 GUI Entry Point
Imports core logic and applies CSS stylesheet dynamically.
"""

import sys
import os
import gc
import threading
import importlib.util

# Verify PySide6 is installed
try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    print("ERROR: PySide6 is not installed. Please install it using: pip install PySide6")
    sys.exit(1)

# Check dependencies using find_spec (prevent Shiboken hooks causing import hang)
MISSING_DEPS = []
if importlib.util.find_spec("faster_whisper") is None:
    MISSING_DEPS.append("faster-whisper")

# Import modular logic
try:
    from AutoCaption_logic import HAS_CUDA, MODEL_SIZES, transcribe, build_srt, save_srt
except ImportError:
    # Fallback to local directory import if script location differs
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from AutoCaption_logic import HAS_CUDA, MODEL_SIZES, transcribe, build_srt, save_srt

SUPPORTED_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wav", ".mp3", ".m4a"}

def open_directory(path):
    if path and os.path.isdir(path):
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", path])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

def load_stylesheet():
    """Load styling from stylesheet file next to script"""
    css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "AutoCaption.css")
    if os.path.exists(css_path):
        try:
            with open(css_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return ""


class CardFrame(QtWidgets.QFrame):
    double_clicked = QtCore.Signal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.setFixedSize(90, 100)
        
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
        frame.setObjectName("SuccessPopupFrame")
        
        # Add glow to popup
        effect = QtWidgets.QGraphicsDropShadowEffect()
        effect.setBlurRadius(30)
        effect.setColor(QtGui.QColor("#404040"))
        effect.setOffset(0, 0)
        frame.setGraphicsEffect(effect)

        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        
        # Header
        header_layout = QtWidgets.QHBoxLayout()
        title_lbl = QtWidgets.QLabel("Success")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #FFFFFF; border: none; background: transparent;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        
        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setObjectName("SuccessCloseBtn")
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)
        layout.addLayout(header_layout)
        
        # Body
        body_lbl = QtWidgets.QLabel("Subtitles created successfully!")
        body_lbl.setStyleSheet("font-size: 14px; color: #D4D4D4; border: none; background: transparent;")
        layout.addWidget(body_lbl)
        
        # File list
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setObjectName("SuccessList")
        self.list_widget.setFixedHeight(80)
        for p in saved_paths:
            item = QtWidgets.QListWidgetItem(os.path.basename(p))
            item.setToolTip(p)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
        
        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(12)
        
        open_folder_btn = QtWidgets.QPushButton("Open Folder")
        open_folder_btn.setObjectName("SuccessOpenFolderBtn")
        open_folder_btn.clicked.connect(self.on_open_folder)
        
        ok_btn = QtWidgets.QPushButton("OK")
        ok_btn.setObjectName("SuccessOkBtn")
        ok_btn.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(open_folder_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)
        
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(frame)
        
    def on_open_folder(self):
        if self.saved_paths:
            open_directory(os.path.dirname(self.saved_paths[0]))
        self.accept()


class DropZoneFrame(QtWidgets.QFrame):
    files_dropped = QtCore.Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if os.path.splitext(url.toLocalFile())[1].lower() in SUPPORTED_EXTS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        dropped_files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.isfile(file_path) and os.path.splitext(file_path)[1].lower() in SUPPORTED_EXTS:
                dropped_files.append(file_path)
        if dropped_files:
            self.files_dropped.emit(dropped_files)


class Worker(QtCore.QObject):
    log_signal = QtCore.Signal(str)
    progress_signal = QtCore.Signal(int)
    status_signal = QtCore.Signal(str)
    finished_signal = QtCore.Signal(bool, list)
    error_signal = QtCore.Signal(str)
    model_ready_signal = QtCore.Signal(object)

    def __init__(self, input_files, output_folder, save_same_folder, src_lang, model_size, device, cached_model=None):
        super().__init__()
        self.input_files = input_files
        self.output_folder = output_folder
        self.save_same_folder = save_same_folder
        self.src_lang = src_lang
        self.model_size = model_size
        self.device = device
        self.model = cached_model
        self.cancel_event = threading.Event()

    def run(self):
        try:
            saved_paths = []
            total_files = len(self.input_files)
            
            import gc
            if self.model is None:
                try:
                    from faster_whisper import WhisperModel
                    device_str = "cuda" if "cuda" in self.device or "GPU" in self.device else "cpu"
                    compute_type = "float16" if device_str == "cuda" else "int8"
                    self.log_signal.emit(f"Loading Whisper model '{self.model_size}' on {device_str.upper()} (Compute: {compute_type})...")
                    self.model = WhisperModel(self.model_size, device=device_str, compute_type=compute_type)
                    self.model_ready_signal.emit(self.model)
                except Exception as e:
                    self.log_signal.emit(f"ERROR loading model: {e}")
                    self.error_signal.emit(f"Failed to load model: {e}")
                    self.finished_signal.emit(False, [])
                    return
            else:
                self.log_signal.emit(f"Reusing cached Whisper model '{self.model_size}'...")
            
            for idx, input_file in enumerate(self.input_files):
                if self.cancel_event.is_set():
                    break
                    
                filename = os.path.basename(input_file)
                self.status_signal.emit(f"Processing file {idx+1} of {total_files}: {filename}...")
                self.log_signal.emit(f"\n========================================\n"
                                     f"[{idx+1}/{total_files}] Processing: {filename}\n"
                                     f"========================================")
                
                def make_progress_cb(current_idx, t_files):
                    def cb(file_percent):
                        total_percent = int(((current_idx * 100) + file_percent) / t_files)
                        self.progress_signal.emit(total_percent)
                    return cb
                
                segments, detected = transcribe(
                    input_file, 
                    self.src_lang, 
                    self.model, 
                    self.log_signal.emit, 
                    self.cancel_event, 
                    make_progress_cb(idx, total_files)
                )
                
                if segments is None:
                    if self.cancel_event.is_set():
                        break
                    self.log_signal.emit(f"ERROR: Transcription failed for {filename}")
                    self.progress_signal.emit(int(((idx + 1) * 100) / total_files))
                    continue
                    
                base_name = os.path.splitext(filename)[0]
                out_dir = os.path.dirname(input_file) if self.save_same_folder else self.output_folder
                srt_path = os.path.join(out_dir, f"{base_name}_{detected}.srt")
                if save_srt(srt_path, build_srt(segments), self.log_signal.emit):
                    saved_paths.append(srt_path)
                    
                self.progress_signal.emit(int(((idx + 1) * 100) / total_files))
                
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
                
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
        self._input_files_list = []
        self._cached_model = None
        self._cached_model_key = None  # (model_size, device)

        self._setup_theme()
        self._build_ui()
        self._load_settings()

    def _setup_theme(self):
        QtWidgets.QApplication.setStyle("Fusion")
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#000000"))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#E5E5E5"))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#0A0A0A"))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#000000"))
        palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor("#0A0A0A"))
        palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor("#E5E5E5"))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#E5E5E5"))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor("#171717"))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#E5E5E5"))
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#404040"))
        palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#FFFFFF"))
        QtWidgets.QApplication.setPalette(palette)
        
        # Load external stylesheet
        style = load_stylesheet()
        if style:
            QtWidgets.QApplication.instance().setStyleSheet(style)

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
        top.setObjectName("TopBar")
        top_layout = QtWidgets.QHBoxLayout(top)
        top_layout.setContentsMargins(16, 12, 16, 12)
        
        title = QtWidgets.QLabel("AutoCaption")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #f8fafc;")
        top_layout.addWidget(title)
        top_layout.addStretch()
        
        self._btn_unload_model = QtWidgets.QPushButton("Unload Model")
        self._btn_unload_model.setObjectName("UnloadModelBtn")
        self._btn_unload_model.clicked.connect(self._unload_cached_model)
        self._btn_unload_model.setEnabled(False)
        top_layout.addWidget(self._btn_unload_model)

        self._btn_toggle_log = QtWidgets.QPushButton("Show Log")
        self._btn_toggle_log.setObjectName("ToggleLogBtn")
        self._btn_toggle_log.clicked.connect(self._toggle_log_panel)
        top_layout.addWidget(self._btn_toggle_log)
        main_layout.addWidget(top)

        # Content layout
        content = QtWidgets.QHBoxLayout()
        content.setSpacing(16)

        # Left panel (Form)
        left_card = QtWidgets.QFrame(self)
        left_card.setObjectName("LeftCard")
        left_layout = QtWidgets.QVBoxLayout(left_card)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        self._build_form(left_layout)
        content.addWidget(left_card, 1)

        # Right panel (Log)
        self._log_panel = QtWidgets.QFrame(self)
        self._log_panel.setObjectName("LogPanel")
        right_layout = QtWidgets.QVBoxLayout(self._log_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(8)

        self._build_log(right_layout)
        content.addWidget(self._log_panel, 1)

        main_layout.addLayout(content, 1)

        # Status bar
        status = QtWidgets.QFrame(self)
        status.setObjectName("StatusFrame")
        status_layout = QtWidgets.QHBoxLayout(status)
        status_layout.setContentsMargins(12, 8, 12, 8)
        self._status_label = QtWidgets.QLabel("Ready")
        self._status_label.setStyleSheet("color: #cbd5e1;")
        status_layout.addWidget(self._status_label)
        main_layout.addWidget(status)

    def _build_form(self, parent_layout):
        title_style = """
            color: #A3A3A3;
            font-weight: bold;
            font-size: 14px;
            border: none;
            background: transparent;
        """
        
        # Helper to add glow
        def add_glow(widget, color="#FFFFFF", radius=15):
            effect = QtWidgets.QGraphicsDropShadowEffect()
            effect.setBlurRadius(radius)
            effect.setColor(QtGui.QColor(color))
            effect.setOffset(0, 0)
            widget.setGraphicsEffect(effect)

        # 1. Input Media Group
        input_group = QtWidgets.QFrame()
        input_group.setProperty("class", "GroupFrame")
        input_layout = QtWidgets.QVBoxLayout(input_group)
        input_layout.setContentsMargins(20, 20, 20, 20)
        input_layout.setSpacing(12)

        input_header_layout = QtWidgets.QHBoxLayout()
        lbl_input_title = QtWidgets.QLabel("1. Input Media")
        lbl_input_title.setStyleSheet(title_style)
        input_header_layout.addWidget(lbl_input_title)
        input_header_layout.addStretch()
        
        self._btn_browse_input = QtWidgets.QPushButton("Browse")
        self._btn_browse_input.setProperty("class", "NormalBtn")
        self._btn_clear_input = QtWidgets.QPushButton("Clear")
        self._btn_clear_input.setProperty("class", "NormalBtn")
        input_header_layout.addWidget(self._btn_browse_input)
        input_header_layout.addWidget(self._btn_clear_input)
        input_layout.addLayout(input_header_layout)

        # Drop Zone Frame
        self._drop_zone = DropZoneFrame()
        self._drop_zone.setObjectName("DropZone")
        self._drop_zone.setMinimumHeight(150)
        self._drop_zone.files_dropped.connect(self._on_files_dropped)
        
        drop_layout = QtWidgets.QVBoxLayout(self._drop_zone)
        drop_layout.setContentsMargins(10, 10, 10, 10)
        self._lbl_drop = QtWidgets.QLabel("Drag & Drop audio/video files here\n(or click Browse above)")
        self._lbl_drop.setAlignment(QtCore.Qt.AlignCenter)
        self._lbl_drop.setStyleSheet("font-size: 14px; font-weight: 500; color: #737373; border: none; background: transparent;")
        drop_layout.addWidget(self._lbl_drop)

        # Scroll Area for files inside drop zone
        self._scroll_area = QtWidgets.QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFixedHeight(130)
        self._scroll_area.hide()
        
        scroll_content = QtWidgets.QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        self._files_layout = QtWidgets.QHBoxLayout(scroll_content)
        self._files_layout.setContentsMargins(4, 4, 4, 4)
        self._files_layout.setSpacing(8)
        self._files_layout.setAlignment(QtCore.Qt.AlignLeft)
        
        self._scroll_area.setWidget(scroll_content)
        drop_layout.addWidget(self._scroll_area)
        input_layout.addWidget(self._drop_zone)
        
        parent_layout.addWidget(input_group)

        # 2. Settings Group
        settings_group = QtWidgets.QFrame()
        settings_group.setProperty("class", "GroupFrame")
        settings_layout = QtWidgets.QVBoxLayout(settings_group)
        settings_layout.setContentsMargins(20, 20, 20, 20)
        settings_layout.setSpacing(14)

        lbl_settings_title = QtWidgets.QLabel("2. Settings")
        lbl_settings_title.setStyleSheet(title_style)
        settings_layout.addWidget(lbl_settings_title)

        # Output folder logic
        self._chk_same_folder = QtWidgets.QCheckBox("Save SRT in same folder as original media")
        self._chk_same_folder.setStyleSheet("color: #E5E5E5; font-weight: 500; background: transparent; border: none;")
        self._chk_same_folder.setChecked(True)
        self._chk_same_folder.toggled.connect(self._toggle_output_folder)
        settings_layout.addWidget(self._chk_same_folder)

        output_row = QtWidgets.QHBoxLayout()
        self._lbl_output = QtWidgets.QLabel("Output folder:")
        self._lbl_output.setStyleSheet("background: transparent; border: none; color: #A3A3A3;")
        self._output_edit = QtWidgets.QLineEdit()
        self._btn_browse_output = QtWidgets.QPushButton("Browse...")
        self._btn_browse_output.setProperty("class", "NormalBtn")
        output_row.addWidget(self._lbl_output, 0)
        output_row.addWidget(self._output_edit, 1)
        output_row.addWidget(self._btn_browse_output, 0)
        settings_layout.addLayout(output_row)

        # Model size
        model_row = QtWidgets.QHBoxLayout()
        self._lbl_model = QtWidgets.QLabel("Model size:")
        self._lbl_model.setStyleSheet("background: transparent; border: none; color: #A3A3A3;")
        self._cmb_model = QtWidgets.QComboBox()
        self._cmb_model.addItems(MODEL_SIZES)
        
        tooltips = [
            "tiny: Fastest speed, lowest accuracy",
            "base: Fast speed, fair accuracy",
            "small: Moderate speed, good accuracy",
            "medium: Slower speed, very good accuracy",
            "large-v3-turbo: Fast speed, high accuracy (Recommended)",
            "large-v3: Slow speed, highest accuracy"
        ]
        for i, tip in enumerate(tooltips):
            self._cmb_model.setItemData(i, tip, QtCore.Qt.ToolTipRole)
            
        self._cmb_model.setCurrentIndex(4)
        model_row.addWidget(self._lbl_model, 0)
        model_row.addWidget(self._cmb_model, 1)
        settings_layout.addLayout(model_row)

        # Device (CPU / GPU)
        device_row = QtWidgets.QHBoxLayout()
        self._lbl_device = QtWidgets.QLabel("Processing Device:")
        self._lbl_device.setStyleSheet("background: transparent; border: none; color: #A3A3A3;")
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
        settings_layout.addLayout(device_row)

        parent_layout.addWidget(settings_group)
        parent_layout.addSpacing(16)

        # 3. Actions
        self._progress = QtWidgets.QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(24)
        parent_layout.addWidget(self._progress)
        
        self._progress_anim = QtCore.QPropertyAnimation(self._progress, b"value")
        self._progress_anim.setDuration(400)
        self._progress_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(12)
        self._btn_start = QtWidgets.QPushButton("Generate Subtitles")
        self._btn_start.setObjectName("StartBtn")
        self._btn_start.setMinimumHeight(48)
        add_glow(self._btn_start, color="#404040", radius=20)
        
        self._btn_cancel = QtWidgets.QPushButton("Cancel")
        self._btn_cancel.setObjectName("CancelBtn")
        self._btn_cancel.setProperty("class", "NormalBtn")
        self._btn_cancel.setMinimumHeight(48)
        self._btn_cancel.setEnabled(False)
        
        self._btn_open = QtWidgets.QPushButton("Open Folder")
        self._btn_open.setObjectName("OpenFolderBtn")
        self._btn_open.setProperty("class", "NormalBtn")
        self._btn_open.setMinimumHeight(48)
        
        btn_layout.addWidget(self._btn_start, 2)
        btn_layout.addWidget(self._btn_cancel, 1)
        btn_layout.addWidget(self._btn_open, 1)
        parent_layout.addLayout(btn_layout)
        parent_layout.addStretch()

        # Connect slots
        self._btn_browse_input.clicked.connect(self._browse_input)
        self._btn_clear_input.clicked.connect(self._clear_input_list)
        self._btn_browse_output.clicked.connect(self._browse_output)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_open.clicked.connect(self._open_output_folder)
        
        # Initial trigger
        self._toggle_output_folder()

    def _toggle_output_folder(self):
        is_same = self._chk_same_folder.isChecked()
        self._output_edit.setEnabled(not is_same)
        self._btn_browse_output.setEnabled(not is_same)

    def _build_log(self, parent_layout):
        label = QtWidgets.QLabel("Subtitles / Processing Log")
        label.setStyleSheet("font-weight: bold; color: #A3A3A3;")
        parent_layout.addWidget(label)
        
        self._log_text = QtWidgets.QTextEdit()
        self._log_text.setObjectName("LogText")
        self._log_text.setReadOnly(True)
        self._log_text.setFont(QtGui.QFont("Consolas", 10))
        self._log_text.setPlainText("Your subtitles and logs will appear here\nwhen finished transcribing")
        parent_layout.addWidget(self._log_text, 1)

    def _add_input_file(self, path):
        if path in self._input_files_list:
            return
        self._input_files_list.append(path)

    def _update_drop_zone_visuals(self):
        while self._files_layout.count():
            item = self._files_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
                
        count = len(self._input_files_list)
        if count == 0:
            self._lbl_drop.show()
            self._scroll_area.hide()
        else:
            self._lbl_drop.hide()
            self._scroll_area.show()
            
            for path in self._input_files_list:
                card = CardFrame(path)
                card.double_clicked.connect(self._remove_file_by_path)
                self._files_layout.addWidget(card)

    def _remove_file_by_path(self, path):
        if path in self._input_files_list:
            self._input_files_list.remove(path)
            self._update_drop_zone_visuals()
            self._save_settings()

    def _clear_input_list(self):
        self._input_files_list.clear()
        self._update_drop_zone_visuals()
        self._save_settings()

    def _load_settings(self):
        settings = QtCore.QSettings("AutoCaption", "Settings")
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.exists(default_dir):
            default_dir = os.path.expanduser("~")
            
        self._last_input_dir = settings.value("last_input_dir", default_dir)
        self._last_output_dir = settings.value("last_output_dir", default_dir)
        
        self._output_edit.setText(settings.value("output_folder", ""))
        self._chk_same_folder.setChecked(settings.value("save_same_folder", True, type=bool))
        
        model = settings.value("model_size", "large-v3-turbo")
        if model in MODEL_SIZES:
            self._cmb_model.setCurrentText(model)
            
        device_idx = int(settings.value("device_index", 1 if HAS_CUDA else 0))
        if device_idx == 1 and not HAS_CUDA:
            device_idx = 0
        self._cmb_device.setCurrentIndex(device_idx)

        self._input_files_list.clear()
        input_files = settings.value("input_files_list", [])
        if isinstance(input_files, str):
            if input_files and os.path.exists(input_files):
                self._add_input_file(input_files)
        elif isinstance(input_files, list):
            for path in input_files:
                if os.path.exists(path):
                    self._add_input_file(path)
        self._update_drop_zone_visuals()

        self._log_panel.setVisible(False)
        self.setMinimumWidth(550)
        self.resize(600, 750)
        self._toggle_output_folder()

    def _save_settings(self):
        settings = QtCore.QSettings("AutoCaption", "Settings")
        settings.setValue("output_folder", self._output_edit.text())
        settings.setValue("save_same_folder", self._chk_same_folder.isChecked())
        settings.setValue("model_size", self._cmb_model.currentText())
        settings.setValue("device_index", self._cmb_device.currentIndex())
        settings.setValue("input_files_list", self._input_files_list)
        
        if self._input_files_list and os.path.exists(os.path.dirname(self._input_files_list[0])):
            self._last_input_dir = os.path.dirname(self._input_files_list[0])
            
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
        if not self._input_files_list:
            QtWidgets.QMessageBox.warning(self, "Error", "Please select input files.")
            return

        if not self._chk_same_folder.isChecked() and not self._output_edit.text():
            QtWidgets.QMessageBox.warning(self, "Error", "Please select an output folder.")
            return

        for file_path in self._input_files_list:
            if not os.path.isfile(file_path):
                QtWidgets.QMessageBox.warning(self, "Error", f"Input file does not exist:\n{file_path}")
                return

        self._save_settings()
        self._running = True
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._btn_unload_model.setEnabled(False)
        self._progress.setValue(0)
        self._log_text.clear()

        src_lang = "auto"
        model_size = self._cmb_model.currentText()
        device = "cuda" if self._cmb_device.currentIndex() == 1 and HAS_CUDA else "cpu"
        save_same = self._chk_same_folder.isChecked()

        # If settings changed, unload the old cached model
        if self._cached_model_key != (model_size, device):
            self._unload_cached_model()

        self._worker = Worker(self._input_files_list, self._output_edit.text(), save_same, src_lang, model_size, device, self._cached_model)
        self._worker_thread = QtCore.QThread()
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.log_signal.connect(self._on_log)
        self._worker.status_signal.connect(self._on_status)
        self._worker.progress_signal.connect(self._on_progress)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.error_signal.connect(self._on_error)
        self._worker.model_ready_signal.connect(self._on_model_ready)

        if self._cached_model is None:
            self._status_label.setText(f"Initializing Whisper ({device.upper()})...")
        else:
            self._status_label.setText(f"Starting Whisper transcription...")
            
        self._worker_thread.start()

    def _on_model_ready(self, model):
        self._cached_model = model
        model_size = self._cmb_model.currentText()
        device = "cuda" if self._cmb_device.currentIndex() == 1 and HAS_CUDA else "cpu"
        self._cached_model_key = (model_size, device)

    def _unload_cached_model(self):
        if self._cached_model is not None:
            self._status_label.setText("Unloading model from memory...")
            self._cached_model = None
            self._cached_model_key = None
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            self._btn_unload_model.setEnabled(False)
            self._status_label.setText("Model unloaded.")
            self._log_text.append("\n[System] Whisper model unloaded to free memory.")

    def _on_cancel(self):
        self._status_label.setText("Cancelling...")
        if self._worker:
            self._worker.cancel_event.set()
        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        if self._cached_model is not None:
            self._btn_unload_model.setEnabled(True)

    def _on_log(self, msg):
        self._log_text.append(msg)
        self._log_text.moveCursor(QtGui.QTextCursor.End)

    def _on_status(self, msg):
        self._status_label.setText(msg)

    def _on_progress(self, percent):
        self._progress_anim.stop()
        self._progress_anim.setStartValue(self._progress.value())
        self._progress_anim.setEndValue(percent)
        self._progress_anim.start()

    def _on_error(self, error_msg):
        self._log_text.append(f"\n[ERROR] {error_msg}")

    def _on_finished(self, success, paths):
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()

        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        if self._cached_model is not None:
            self._btn_unload_model.setEnabled(True)

        if success:
            self._status_label.setText("Finished successfully!")
            popup = SuccessPopup(paths, self)
            popup.exec()
        else:
            self._status_label.setText("Cancelled or failed.")
            QtWidgets.QMessageBox.warning(self, "Failed", "Process was cancelled or failed. Check the logs for details.")

    def _open_output_folder(self):
        open_directory(self._output_edit.text())

    def closeEvent(self, event):
        self._save_settings()
        if self._running:
            self._on_cancel()
        self._unload_cached_model()
        event.accept()


def cli_main():
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

    if not os.path.isfile(input_path):
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(2)

    device = "cpu"
    if HAS_CUDA:
        device = "cuda"

    # Setup Whisper Model once for CLI run
    from faster_whisper import WhisperModel
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"Loading Whisper model '{model_size}' on {device.upper()} (Compute: {compute_type})...")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    segments, detected = transcribe(input_path, language, model)
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
