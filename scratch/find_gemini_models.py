import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("Searching for hardcoded gemini model strings across codebase:")
for root, dirs, files in os.walk(BASE_DIR):
    if ".git" in root or ".venv" in root or "scratch" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                if "gemini-" in content:
                    lines = content.splitlines()
                    rel = fp.relative_to(BASE_DIR)
                    print(f"\nFound in {rel}:")
                    for idx, line in enumerate(lines, 1):
                        if "gemini-" in line:
                            print(f"  Line {idx}: {line.strip()[:140]}")
            except Exception:
                pass
