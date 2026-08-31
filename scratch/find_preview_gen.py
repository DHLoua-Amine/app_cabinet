import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for contract preview text generation in scanner_page.py:")
scanner_file = BASE_DIR / "ui" / "pages" / "scanner_page.py"
content = scanner_file.read_text(encoding="utf-8", errors="ignore")
lines = content.splitlines()

for idx, line in enumerate(lines, 1):
    if "refresh_contract_preview_text" in line or "generate_contract_text" in line or "NOTARY_HEADER" in line or "preamble" in line or "dibaia" in line:
        print(f"  Line {idx}: {line.strip()[:100]}")
