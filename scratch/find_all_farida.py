import os
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for 'farida' / 'الفريضة' across ui/:")
for root, dirs, files in os.walk(BASE_DIR / "ui"):
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if "farida" in content.lower() or "الفريضة" in content:
                    lines = content.splitlines()
                    rel = fp.relative_to(BASE_DIR)
                    print(f"\nChecking {rel}:")
                    for idx, line in enumerate(lines, 1):
                        if any(k in line.lower() for k in ["farida", "الفريضة"]):
                            if len(line.strip()) < 140 and "import" not in line and "def " not in line:
                                print(f"  Line {idx}: {line.strip()}")
            except Exception:
                pass
