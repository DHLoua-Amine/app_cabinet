import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for contract categories in UI code:")
for root, dirs, files in os.walk(BASE_DIR / "ui"):
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if "العقود العقارية" in content or "عقد معاوضة" in content or "الأحوال الشخصية" in content:
                    lines = content.splitlines()
                    rel = fp.relative_to(BASE_DIR)
                    print(f"Found in {rel}:")
                    for idx, line in enumerate(lines, 1):
                        if any(k in line for k in ["العقود العقارية", "عقد معاوضة", "الأحوال الشخصية", "العقود التجارية"]):
                            print(f"  Line {idx}: {line.strip()[:100]}")
            except Exception:
                pass
