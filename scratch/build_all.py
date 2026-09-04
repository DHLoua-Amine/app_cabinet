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

print("--- STEP 1: Building PyInstaller Exe ---")
for d in (BASE_DIR / "build", BASE_DIR / "dist"):
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)

res = subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", str(SPEC)], cwd=str(BASE_DIR))
if res.returncode != 0:
    print(f"PyInstaller failed with returncode {res.returncode}")
    sys.exit(1)

exe_path = DIST_DIR / "CabinetNotarialZarai.exe"
if not exe_path.exists():
    print(f"ERROR: {exe_path} does not exist!")
    sys.exit(1)

total_mb = sum(f.stat().st_size for f in DIST_DIR.rglob("*") if f.is_file()) / (1024*1024)
print(f"PyInstaller Success! Total dist size: {total_mb:.1f} MB")

print("\n--- STEP 2: Building Inno Setup Installer ---")
iscc_res = subprocess.run([ISCC, str(ISS)], cwd=str(BASE_DIR))
if iscc_res.returncode != 0:
    print(f"Inno Setup failed with returncode {iscc_res.returncode}")
    sys.exit(1)

installer_exe = BASE_DIR / "dist_installer" / "CabinetNotarial_Setup_v1.0.4.exe"
if installer_exe.exists():
    inst_size = os.path.getsize(installer_exe) / (1024*1024)
    print(f"\n==========================================")
    print(f"INSTALLER BUILT SUCCESSFULLY!")
    print(f"Path: {installer_exe}")
    print(f"Size: {inst_size:.2f} MB")
    print(f"==========================================")
else:
    print("ERROR: Installer exe not found!")
