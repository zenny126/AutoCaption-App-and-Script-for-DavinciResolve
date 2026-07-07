import subprocess
import sys
import os

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(base_dir, "scripts", "AutoCaption.py")
    
    # Tự động tìm pythonw.exe (phiên bản ẩn console của Python)
    python_exe = sys.executable
    if python_exe.lower().endswith("python.exe"):
        pythonw = python_exe[:-10] + "pythonw.exe"
        if os.path.exists(pythonw):
            python_exe = pythonw
            
    # Chạy script AutoCaption.py hoàn toàn ẩn dưới nền
    subprocess.Popen([python_exe, script_path], cwd=base_dir, creationflags=subprocess.CREATE_NO_WINDOW)
