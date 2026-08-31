import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
scanner_file = BASE_DIR / "ui" / "pages" / "scanner_page.py"

print("=== CHECKING ACTUAL AI TRANSCRIPTION IMPLEMENTATION ===")
if scanner_file.exists():
    with open(scanner_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        for idx, line in enumerate(lines, 1):
            if "gemini" in line.lower() or "google" in line.lower() or "genai" in line.lower() or "api_key" in line.lower():
                print(f"Line {idx}: {line.strip()}")
