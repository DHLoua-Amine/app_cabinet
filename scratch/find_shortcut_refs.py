import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for shortcut or desktop references:")
for root, dirs, files in os.walk(BASE_DIR):
    if ".git" in root or ".venv" in root or "scratch" in root:
        continue
    for f in files:
        if f.endswith((".py", ".bat", ".ps1", ".vbs", ".iss")):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if "shortcut" in content.lower() or "desktop" in content.lower() or "lnk" in content.lower():
                    lines = content.splitlines()
                    rel = fp.relative_to(BASE_DIR)
                    print(f"\nFound in {rel}:")
                    for idx, line in enumerate(lines, 1):
                        if any(k in line.lower() for k in ["shortcut", "desktop", "lnk", "cabinetnotarial"]):
                            if len(line.strip()) < 140:
                                print(f"  Line {idx}: {line.strip()}")
            except Exception:
                pass
