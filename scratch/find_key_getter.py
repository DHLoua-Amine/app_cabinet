import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

for root, dirs, files in os.walk(BASE_DIR):
    if ".git" in root or ".venv" in root or "scratch" in root: continue
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if "gemini_key" in content.lower() or "api_key" in content.lower():
                    for idx, line in enumerate(content.splitlines(), 1):
                        if any(k in line.lower() for k in ["def get_", "load_gemini", "gemini_key"]):
                            print(f"{fp.relative_to(BASE_DIR)} L{idx}: {line.strip()[:100]}")
            except Exception: pass
