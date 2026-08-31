import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for Farida / back buttons in fiche_client files:")
for root, dirs, files in os.walk(BASE_DIR / "ui" / "pages"):
    for f in files:
        if "fiche" in f.lower() and f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
                rel = fp.relative_to(BASE_DIR)
                print(f"\nChecking {rel}:")
                for idx, line in enumerate(lines, 1):
                    if any(k in line for k in ["farida", "الفريضة", "back_btn", "btn_back", "رجوع"]):
                        if len(line.strip()) < 140:
                            print(f"  Line {idx}: {line.strip()}")
            except Exception:
                pass
