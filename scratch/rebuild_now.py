import os
import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
DIST_DIR = BASE_DIR / "dist" / "CabinetNotarialZarai"
ISCC = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
ISS = BASE_DIR / "installer_setup.iss"

print("--- STEP 1: Cleaning ---")
for d in ["build", "dist", "dist_installer"]:
    path = BASE_DIR / d
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)

print("--- STEP 2: Running PyInstaller ---")
cmd_pyi = [sys.executable, "build_exe.py"]
res_pyi = subprocess.run(cmd_pyi, cwd=str(BASE_DIR), capture_output=True, text=True)
print("PyInstaller stdout:\n", res_pyi.stdout)
print("PyInstaller stderr:\n", res_pyi.stderr)

if not DIST_DIR.exists():
    print("ERROR: DIST_DIR does not exist!")
    sys.exit(1)

dist_files = list(DIST_DIR.rglob("*"))
dist_size = sum(f.stat().st_size for f in dist_files if f.is_file())
print(f"DIST_DIR file count: {len(dist_files)}, size: {dist_size / (1024*1024):.2f} MB")

print("--- STEP 3: Updating ISS path if needed & Compiling ---")
# Ensure ISS points to exact absolute path of dist
iss_content = ISS.read_text(encoding="utf-8")
new_src = f'Source: "{DIST_DIR}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs'
lines = []
for line in iss_content.splitlines():
    if line.strip().startswith("Source:"):
        lines.append(new_src)
    else:
        lines.append(line)
ISS.write_text("\n".join(lines), encoding="utf-8")

res_iscc = subprocess.run([ISCC, str(ISS)], cwd=str(BASE_DIR), capture_output=True, text=True)
print("ISCC stdout:\n", res_iscc.stdout)
print("ISCC stderr:\n", res_iscc.stderr)

installer = BASE_DIR / "dist_installer" / "CabinetNotarial_Setup_v1.0.4.exe"
if installer.exists():
    sz = installer.stat().st_size
    print(f"\nSUCCESS! Installer created: {sz} bytes ({sz / (1024*1024):.2f} MB)")
else:
    print("\nFAILED: Installer not created!")
