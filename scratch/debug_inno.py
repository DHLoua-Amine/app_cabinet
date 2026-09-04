import os
import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
SPEC = BASE_DIR / "CabinetNotarialZarai.spec"
DIST_DIR = BASE_DIR / "dist" / "CabinetNotarialZarai"
ISCC = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
ISS = BASE_DIR / "installer_setup.iss"

print("1. Cleaning old build & dist...")
for d in [BASE_DIR / "build", BASE_DIR / "dist", BASE_DIR / "dist_installer"]:
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)

print("2. Running PyInstaller...")
res = subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", str(SPEC)], cwd=str(BASE_DIR), capture_output=True, text=True)
print("PyInstaller returncode:", res.returncode)

files = list(DIST_DIR.rglob("*"))
file_count = len([f for f in files if f.is_file()])
total_bytes = sum(f.stat().st_size for f in files if f.is_file())
print(f"DIST_DIR file count: {file_count}, total MB: {total_bytes / (1024*1024):.2f} MB")

print("\n3. Running Inno Setup...")
iscc_res = subprocess.run([ISCC, str(ISS)], cwd=str(BASE_DIR), capture_output=True, text=True)
print("ISCC returncode:", iscc_res.returncode)
print("ISCC STDOUT:")
print(iscc_res.stdout)
print("ISCC STDERR:")
print(iscc_res.stderr)

installer = BASE_DIR / "dist_installer" / "CabinetNotarial_Setup_v1.0.4.exe"
if installer.exists():
    print(f"\nFINAL INSTALLER EXIST! Size: {installer.stat().st_size / (1024*1024):.2f} MB ({installer.stat().st_size} bytes)")
else:
    print("\nFINAL INSTALLER DOES NOT EXIST!")
