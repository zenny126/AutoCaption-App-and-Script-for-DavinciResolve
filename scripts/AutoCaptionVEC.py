#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import threading
from PySide6 import QtWidgets, QtCore, QtGui
from faster_whisper import WhisperModel
import argostranslate.package
import argostranslate.translate

STRINGS = {
    "vi": {
        "title": "AutoCaption VEC",
        "input_file": "File đầu vào",
        "output_folder": "Thư mục lưu",
        "src_lang": "Ngôn ngữ nguồn",
        "model": "Model",
        "output_files": "File output",
        "trans_lang": "Ngôn ngữ dịch",
        "browse": "Chọn file...",
        "start": "Tạo phụ đề",
        "cancel": "Hủy",
        "open_folder": "Mở thư mục",
        "auto": "Tự động phát hiện",
        "lang_vi": "Tiếng Việt",
        "lang_en": "English",
        "lang_zh": "中文",
        "one_file": "1 file phụ đề",
        "two_files": "2 file phụ đề (gốc + dịch)",
    },
    "en": {
        "title": "AutoCaption VEC",
        "input_file": "Input file",
        "output_folder": "Output folder",
        "src_lang": "Source language",
        "model": "Model",
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
        "one_file": "1 subtitle file",
        "two_files": "2 subtitle files (original + translated)",
    },
    "zh": {
        "title": "AutoCaption VEC",
        "input_file": "输入文件",
        "output_folder": "输出文件夹",
        "src_lang": "源语言",
        "model": "模型",
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
    }
}

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]


def transcribe(input_path, language, model_size, log_fn, cancel_event):
    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(input_path, language=language if language != "auto" else None)
        segments_list = list(segments)
        detected = info.language
        log_fn(f"Detected language: {detected}, segments: {len(segments_list)}")
        return segments_list, detected
    except Exception as e:
        log_fn(f"ERROR transcribe: {e}")
        return None, None


def ensure_argos_package(src, tgt, log_fn):
    try:
        log_fn(f"Installing translation package {src} -> {tgt}...")
        argostranslate.package.update_package_index()
        available_packages = argostranslate.package.get_available_packages()
        pkg = None
        for p in available_packages:
            if p.from_code == src and p.to_code == tgt:
                pkg = p
                break
        if pkg:
            argostranslate.package.install_package(pkg)
            log_fn(f"Installed {src} -> {tgt}")
            return True
        log_fn(f"Package {src} -> {tgt} not found")
        return False
    except Exception as e:
        log_fn(f"ERROR install package: {e}")
        return False


def translate_segments(segments, src_lang, tgt_lang, log_fn, cancel_event, progress_fn=None):
    try:
        if not ensure_argos_package(src_lang, tgt_lang, log_fn):
            return None
        
        translated = []
        total = len(segments)
        for i, seg in enumerate(segments):
            if cancel_event.is_set():
                return None
            trans_text = argostranslate.translate.translate(seg.text, src_lang, tgt_lang)
            translated.append(type('Segment', (), {'start': seg.start, 'end': seg.end, 'text': trans_text})())
            if progress_fn and (i + 1) % 5 == 0:
                progress_fn(int(100 * (i + 1) / total))
        return translated
    except Exception as e:
        log_fn(f"ERROR translate: {e}")
        return None


def build_srt(segments):
    srt = ""
    for i, seg in enumerate(segments, 1):
        start_ms = int(seg.start * 1000)
        end_ms = int(seg.end * 1000)
        start_str = f"{start_ms // 3600000:02d}:{(start_ms % 3600000) // 60000:02d}:{(start_ms % 60000) // 1000:02d},{start_ms % 1000:03d}"
        end_str = f"{end_ms // 3600000:02d}:{(end_ms % 3600000) // 60000:02d}:{(end_ms % 60000) // 1000:02d},{end_ms % 1000:03d}"
        srt += f"{i}\n{start_str} --> {end_str}\n{seg.text}\n\n"
    return srt


def save_srt(path, srt_text, log_fn):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(srt_text)
        log_fn(f"Saved: {path}")
        return True
    except Exception as e:
        log_fn(f"ERROR save: {e}")
        return False


class Worker(QtCore.QObject):
    log_signal = QtCore.Signal(str)
    progress_signal = QtCore.Signal(int)
    finished_signal = QtCore.Signal(bool, object)
    error_signal = QtCore.Signal(str)

    def __init__(self, input_file, output_folder, src_lang, model_size, output_files, trans_lang):
        super().__init__()
        self.input_file = input_file
        self.output_folder = output_folder
        self.src_lang = src_lang
        self.model_size = model_size
        self.output_files = output_files
        self.trans_lang = trans_lang
        self.cancel_event = threading.Event()

    def run(self):
        try:
            saved_paths = []
            
            self.log_signal.emit(f"Transcribing: {self.input_file}")
            segments, detected = transcribe(self.input_file, self.src_lang, self.model_size, self.log_signal.emit, self.cancel_event)
            
            if segments is None:
                self.finished_signal.emit(False, None)
                return

            self.progress_signal.emit(30)
            base_name = os.path.splitext(os.path.basename(self.input_file))[0]
            
            srt_path = os.path.join(self.output_folder, f"{base_name}_{detected}.srt")
            if save_srt(srt_path, build_srt(segments), self.log_signal.emit):
                saved_paths.append(srt_path)
                self.progress_signal.emit(50)

            if self.output_files == 1 and self.trans_lang != detected:
                self.log_signal.emit(f"Translating to {self.trans_lang}...")
                trans_segments = translate_segments(segments, detected, self.trans_lang, self.log_signal.emit, self.cancel_event, self.progress_signal.emit)
                
                if trans_segments:
                    srt_trans = os.path.join(self.output_folder, f"{base_name}_{self.trans_lang}.srt")
                    if save_srt(srt_trans, build_srt(trans_segments), self.log_signal.emit):
                        saved_paths.append(srt_trans)
                        self.progress_signal.emit(100)

            self.finished_signal.emit(True, saved_paths)
        except Exception as e:
            self.error_signal.emit(str(e))
            self.finished_signal.emit(False, None)


class App(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self._ui_lang = "vi"
        self._running = False
        self._worker_thread = None
        self._worker = None
        self._setup_theme()
        self._build_ui()
        self._refresh_lang()

    def _setup_theme(self):
        QtWidgets.QApplication.setStyle("Fusion")
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#070b14"))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#e6eef6"))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#0f172a"))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#111827"))
        palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor("#0f172a"))
        palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor("#e6eef6"))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#e6eef6"))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor("#111827"))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#e6eef6"))
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#2563eb"))
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
        
        content.addWidget(right_card, 0)

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

        # Model
        model_row = QtWidgets.QHBoxLayout()
        self._lbl_model = QtWidgets.QLabel()
        self._cmb_model = QtWidgets.QComboBox()
        self._cmb_model.addItems(MODEL_SIZES)
        self._cmb_model.setCurrentIndex(3)
        model_row.addWidget(self._lbl_model, 0)
        model_row.addWidget(self._cmb_model, 1)
        parent_layout.addLayout(model_row)

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
        self._cmb_trans.setEnabled(False)
        trans_row.addWidget(self._lbl_trans, 0)
        trans_row.addWidget(self._cmb_trans, 1)
        parent_layout.addLayout(trans_row)

        parent_layout.addSpacing(12)

        # Progress
        self._progress = QtWidgets.QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setStyleSheet("QProgressBar { border: 1px solid #1f2937; border-radius: 8px; text-align: center; background-color: #111827; } QProgressBar::chunk { background-color: #2563eb; border-radius: 8px; }")
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

        # Apply styles
        control_style = "QLineEdit, QComboBox { background-color: #111827; color: #e2e8f0; border: 1px solid #1f2937; border-radius: 10px; padding: 8px 10px; } QComboBox::drop-down { border: none; } QComboBox QAbstractItemView { background-color: #111827; color: #e2e8f0; selection-background-color: #2563eb; }"
        self._input_edit.setStyleSheet(control_style)
        self._output_edit.setStyleSheet(control_style)
        self._cmb_src_lang.setStyleSheet(control_style)
        self._cmb_model.setStyleSheet(control_style)
        self._cmb_out_files.setStyleSheet(control_style)
        self._cmb_trans.setStyleSheet(control_style)

        btn_style_accent = "QPushButton { background-color: #2563eb; color: white; border: none; border-radius: 10px; padding: 8px 12px; } QPushButton:hover { background-color: #1d4ed8; } QPushButton:disabled { background-color: #374151; color: #9ca3af; }"
        btn_style = "QPushButton { background-color: #1f2937; color: white; border: none; border-radius: 10px; padding: 8px 12px; } QPushButton:hover { background-color: #2d3748; } QPushButton:disabled { background-color: #374151; color: #9ca3af; }"

        self._btn_browse_input.setStyleSheet(btn_style)
        self._btn_browse_output.setStyleSheet(btn_style)
        self._btn_start.setStyleSheet(btn_style_accent)
        self._btn_cancel.setStyleSheet(btn_style)
        self._btn_open.setStyleSheet(btn_style)

        # Connections
        self._btn_browse_input.clicked.connect(self._browse_input)
        self._btn_browse_output.clicked.connect(self._browse_output)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_open.clicked.connect(self._open_output_folder)

    def _build_log(self, parent_layout):
        label = QtWidgets.QLabel("Subtitles")
        label.setStyleSheet("font-weight: 600; color: #f8fafc;")
        parent_layout.addWidget(label)
        
        self._log_text = QtWidgets.QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setFont(QtGui.QFont("Consolas", 10))
        self._log_text.setPlainText("Your subtitles will appear here\nwhen finished transcribing")
        self._log_text.setStyleSheet("QTextEdit { background-color: #111827; color: #e2e8f0; border: 1px solid #1f2937; border-radius: 14px; padding: 10px; }")
        parent_layout.addWidget(self._log_text, 1)

    def _refresh_lang(self):
        s = STRINGS[self._ui_lang]
        self.setWindowTitle(s["title"])
        self._lbl_input.setText(s["input_file"])
        self._btn_browse_input.setText(s["browse"])
        self._lbl_output.setText(s["output_folder"])
        self._btn_browse_output.setText(s["browse"])
        self._lbl_src_lang.setText(s["src_lang"])
        self._lbl_model.setText(s["model"])
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
        self._cmb_out_files.setCurrentIndex(getattr(self, "_out_files_idx", 0))
        self._cmb_out_files.blockSignals(False)

        trans_options = [s["lang_en"], s["lang_vi"], s["lang_zh"]]
        self._cmb_trans.blockSignals(True)
        self._cmb_trans.clear()
        self._cmb_trans.addItems(trans_options)
        self._cmb_trans.setCurrentIndex(getattr(self, "_trans_idx", 0))
        self._cmb_trans.blockSignals(False)

    def _on_ui_lang_change(self):
        langs = ["vi", "en", "zh"]
        self._ui_lang = langs[self._lang_combo.currentIndex()]
        self._refresh_lang()

    def _on_out_files_change(self):
        self._out_files_idx = self._cmb_out_files.currentIndex()
        self._cmb_trans.setEnabled(self._out_files_idx == 1)

    def _browse_input(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select video/audio file", "", "Media Files (*.mp4 *.avi *.mov *.mp3 *.wav)")
        if path:
            self._input_edit.setText(path)

    def _browse_output(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select output folder")
        if path:
            self._output_edit.setText(path)

    def _on_start(self):
        if not self._input_edit.text() or not self._output_edit.text():
            QtWidgets.QMessageBox.warning(self, "Error", "Please select input file and output folder")
            return

        self._running = True
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._progress.setValue(0)

        src_idx = self._cmb_src_lang.currentIndex()
        src_lang = ["auto", "vi", "en", "zh"][src_idx]
        model_size = self._cmb_model.currentText()
        output_files = self._cmb_out_files.currentIndex()
        trans_lang = ["en", "vi", "zh"][self._cmb_trans.currentIndex()]

        self._worker = Worker(self._input_edit.text(), self._output_edit.text(), src_lang, model_size, output_files, trans_lang)
        self._worker_thread = QtCore.QThread()
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.log_signal.connect(self._on_log)
        self._worker.progress_signal.connect(self._on_progress)
        self._worker.finished_signal.connect(self._on_finished)

        self._worker_thread.start()

    def _on_cancel(self):
        if self._worker:
            self._worker.cancel_event.set()
        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)

    def _on_log(self, msg):
        self._log_text.append(msg)

    def _on_progress(self, percent):
        self._progress.setValue(percent)

    def _on_finished(self, success, paths):
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()

        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)

        if success:
            QtWidgets.QMessageBox.information(self, "Success", f"Subtitles created successfully!")
            self._log_text.clear()
        else:
            QtWidgets.QMessageBox.critical(self, "Error", "Process failed or cancelled")

    def _open_output_folder(self):
        path = self._output_edit.text()
        if path and os.path.isdir(path):
            os.startfile(path)


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
