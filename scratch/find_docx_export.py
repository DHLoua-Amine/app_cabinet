import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for docx export & font settings across codebase:")
for root, dirs, files in os.walk(BASE_DIR):
    if ".git" in root or ".venv" in root or "scratch" in root: continue
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if "docx" in content.lower() or "font" in content.lower() or "traditional arabic" in content.lower():
                    for idx, line in enumerate(content.splitlines(), 1):
                        if any(k in line.lower() for k in ["export", "docx", "font_name", "fontsize", "traditional"]):
                            print(f"{fp.relative_to(BASE_DIR)} L{idx}: {line.strip()[:100]}")
            except Exception: pass
