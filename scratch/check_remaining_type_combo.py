import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Checking for remaining type_combo in scanner_page.py:")
scanner_file = BASE_DIR / "ui" / "pages" / "scanner_page.py"
content = scanner_file.read_text(encoding="utf-8", errors="ignore")
lines = content.splitlines()

found = 0
for idx, line in enumerate(lines, 1):
    if "type_combo" in line:
        found += 1
        print(f"  Line {idx}: {line.strip()}")

print(f"Total remaining type_combo occurrences: {found}")
