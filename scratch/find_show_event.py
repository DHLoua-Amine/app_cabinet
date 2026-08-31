import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
scanner_file = BASE_DIR / "ui" / "pages" / "scanner_page.py"
content = scanner_file.read_text(encoding="utf-8", errors="ignore")
lines = content.splitlines()

for idx, line in enumerate(lines, 1):
    if "showEvent" in line or "header_label" in line:
        print(f"  Line {idx}: {line.strip()[:100]}")
