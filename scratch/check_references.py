import os
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
matches = []

for root, dirs, files in os.walk(BASE_DIR):
    if "__pycache__" in root or ".git" in root or "scratch" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            p = Path(root) / f
            try:
                txt = p.read_text(encoding="utf-8")
                if "عقد اتفاق وتصالح" in txt:
                    matches.append(str(p))
            except Exception:
                pass

print("Occurrences of 'عقد اتفاق وتصالح':", matches)
