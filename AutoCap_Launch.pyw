import subprocess
import sys
import os

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(base_dir, "scripts", "AutoCaption.py")
    req_path = os.path.join(base_dir, "requirements.txt")
    
    # Kiểm tra các thư viện cơ bản
    try:
        import PySide6
        import faster_whisper
        deps_installed = True
    except ImportError:
        deps_installed = False

    if not deps_installed:
        if sys.platform == "win32":
            import ctypes
            # Hiện thông báo cho người dùng biết
            msg = "Lần đầu tiên khởi chạy cần cài đặt các thư viện cần thiết (PySide6, faster-whisper).\n\nMột cửa sổ cài đặt sẽ được mở, vui lòng chờ quá trình tải xuống hoàn tất (có thể mất vài phút)."
            ctypes.windll.user32.MessageBoxW(0, msg, "AutoCaption - Đang cài đặt", 0x40)
            
            # Cài đặt qua requirements.txt
            install_cmd = f'"{sys.executable}" -m pip install -r "{req_path}"'
            # Chạy trong cửa sổ mới và chờ hoàn tất
            subprocess.run(f'start /wait cmd /c "{install_cmd}"', shell=True)
        else:
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_path])

    # Tự động tìm pythonw.exe (phiên bản ẩn console của Python)
    python_exe = sys.executable
    if python_exe.lower().endswith("python.exe"):
        pythonw = python_exe[:-10] + "pythonw.exe"
        if os.path.exists(pythonw):
            python_exe = pythonw
            
    # Chạy script AutoCaption.py hoàn toàn ẩn dưới nền
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen([python_exe, script_path], cwd=base_dir, creationflags=creation_flags)
