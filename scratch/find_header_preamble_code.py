import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for contract template header and preamble generation code:")
for root, dirs, files in os.walk(BASE_DIR):
    if ".git" in root or ".venv" in root or "scratch" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if "مكتب الأستاذ" in content or "وجليسه عدلا" in content or "المحكمة الابتدائية" in content or "office_profile" in content:
                    lines = content.splitlines()
                    rel = fp.relative_to(BASE_DIR)
                    print(f"\nFound in {rel}:")
                    for idx, line in enumerate(lines, 1):
                        if any(k in line for k in ["مكتب الأستاذ", "وجليسه عدلا", "المحكمة الابتدائية", "NOTAIRE", "dibaia", "preamble", "header"]):
                            if len(line.strip()) < 140:
                                print(f"  Line {idx}: {line.strip()}")
            except Exception:
                pass
