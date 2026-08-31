import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for database path / network share code:")
for root, dirs, files in os.walk(BASE_DIR):
    if ".venv" in root or ".git" in root or "scratch" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if "portable_data_path" in content or "NOTARY_DATA_DIR" in content or "réseau" in content.lower() or "network" in content.lower() or "share" in content.lower():
                    lines = content.splitlines()
                    for idx, line in enumerate(lines, 1):
                        if any(k in line for k in ["portable_data_path", "NOTARY_DATA_DIR", "DATA_DIR", "network", "Network", "share", "Share"]):
                            if "import" not in line and "logger" not in line:
                                rel = fp.relative_to(BASE_DIR)
                                print(f"  {rel}:{idx}: {line.strip()[:100]}")
            except Exception:
                pass
