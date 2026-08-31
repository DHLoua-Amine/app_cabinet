import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for contract types across entire codebase:")
for root, dirs, files in os.walk(BASE_DIR):
    if ".git" in root or ".venv" in root or "scratch" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if "حجة وفاة" in content or "عقد بيع" in content or "عقد هبة" in content:
                    lines = content.splitlines()
                    rel = fp.relative_to(BASE_DIR)
                    print(f"\nFound in {rel}:")
                    for idx, line in enumerate(lines, 1):
                        if any(k in line for k in ["حجة وفاة", "عقد بيع", "عقد هبة", "عقد مقاسمة", "عقد تنازل"]):
                            print(f"  Line {idx}: {line.strip()[:100]}")
            except Exception:
                pass
