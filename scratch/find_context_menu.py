import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for context menu & open_fiche_client across UI code:")
for root, dirs, files in os.walk(BASE_DIR / "ui"):
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if "customContextMenuRequested" in content or "fiche" in content.lower():
                    lines = content.splitlines()
                    rel = fp.relative_to(BASE_DIR)
                    for idx, line in enumerate(lines, 1):
                        if any(k in line for k in ["customContextMenuRequested", "open_fiche", "Fiche", "ContextMenu"]):
                            if len(line.strip()) < 140:
                                print(f"  {rel}:{idx}: {line.strip()}")
            except Exception:
                pass
