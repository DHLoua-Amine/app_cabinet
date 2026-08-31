import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for 'trial' or 'TRIAL' in all python files:")
for root, dirs, files in os.walk(BASE_DIR):
    if ".venv" in root or ".git" in root or "scratch" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
                for idx, line in enumerate(lines, 1):
                    if "trial" in line.lower():
                        rel = fp.relative_to(BASE_DIR)
                        print(f"  {rel}:{idx}: {line.strip()}")
            except Exception:
                pass
