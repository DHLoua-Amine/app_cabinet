import sys
import os
import subprocess
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
target_exe = BASE_DIR / "dist" / "DATLY" / "DATLY.exe"
icon_path = BASE_DIR / "assets" / "app_icon.ico"

desktop_dir = Path(os.environ.get("USERPROFILE", r"C:\Users\amin")) / "Desktop"
shortcut_path = desktop_dir / "DATLY.lnk"

print("=== CREATING DESKTOP SHORTCUT FOR DATLY ===")
print(f"Target Executable: {target_exe}")
print(f"Icon Path:         {icon_path}")
print(f"Desktop Shortcut:  {shortcut_path}")

ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "{target_exe}"
$Shortcut.WorkingDirectory = "{target_exe.parent}"
$Shortcut.IconLocation = "{icon_path}"
$Shortcut.Description = "DATLY — المنظومة العدلية الذكية"
$Shortcut.Save()
"""

res = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
print("PowerShell Exit Code:", res.returncode)

if shortcut_path.exists():
    print(f"[SUCCESS] Desktop shortcut created successfully at: {shortcut_path}")
else:
    print("[ERROR] Could not create shortcut:", res.stderr)
