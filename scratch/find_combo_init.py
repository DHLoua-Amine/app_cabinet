import os
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

files_to_check = [
    BASE_DIR / "ui" / "pages" / "register_page.py",
    BASE_DIR / "ui" / "pages" / "scanner_page.py",
    BASE_DIR / "ui" / "pages" / "fiche_client_page.py",
    BASE_DIR / "core" / "contract_templates.py",
]

for fp in files_to_check:
    if fp.exists():
        content = fp.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        rel = fp.relative_to(BASE_DIR)
        print(f"\nChecking {rel}:")
        for idx, line in enumerate(lines, 1):
            if any(k in line for k in ["SERVICE_TYPES", "CONTRACT_TYPES", "CATEGORIES", "service_type", "type_combo", "service_combo", "QMenu"]):
                if len(line.strip()) < 140 and not line.strip().startswith("#"):
                    print(f"  Line {idx}: {line.strip()}")
