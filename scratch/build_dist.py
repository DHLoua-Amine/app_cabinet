import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("=== REBUILDING PACKAGED EXECUTABLE 'DATLY.exe' WITH PYINSTALLER ===")
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm", "--onedir", "--windowed",
    "--name=DATLY",
    "--icon=assets/app_icon.ico",
    "--add-data=assets;assets",
    "--add-data=core/models;core/models",
    "main.py"
]

res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)
print("PyInstaller Exit Code:", res.returncode)
if res.returncode == 0:
    print("Build Succeeded for DATLY.exe!")
else:
    print("Build Stderr:\n", res.stderr[-1000:])
