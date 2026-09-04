import os
import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
ISCC = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
ISS = BASE_DIR / "installer_setup.iss"

print("1. Running PyInstaller...")
res_pyi = subprocess.run([sys.executable, "build_exe.py"], cwd=str(BASE_DIR), capture_output=True, text=True)
print(res_pyi.stdout)
if res_pyi.returncode != 0:
    print("PyInstaller error:", res_pyi.stderr)
    sys.exit(1)

print("2. Running Inno Setup...")
res_iscc = subprocess.run([ISCC, str(ISS)], cwd=str(BASE_DIR), capture_output=True, text=True)
print(res_iscc.stdout)
if res_iscc.returncode != 0:
    print("ISCC error:", res_iscc.stderr)
    sys.exit(1)

target = BASE_DIR / "dist_installer" / "CabinetNotarial_Setup_v1.0.4.exe"
if target.exists():
    print(f"BUILD SUCCESSFUL! Final Installer: {target} ({target.stat().st_size} bytes)")
else:
    print("BUILD FAILED: Target installer not found.")
