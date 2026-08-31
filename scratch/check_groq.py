import os
import glob
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("=== SEARCHING FOR GROQ & TRANSCRIPTION ENGINE IN CODEBASE ===")
py_files = glob.glob(str(BASE_DIR / "**" / "*.py"), recursive=True)

groq_matches = []
for pf in py_files:
    rel = os.path.relpath(pf, BASE_DIR)
    with open(pf, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        if "groq" in content.lower():
            for line_no, line in enumerate(content.splitlines(), 1):
                if "groq" in line.lower():
                    groq_matches.append((rel, line_no, line.strip()))

print(f"Total Groq Matches Found: {len(groq_matches)}")
for r, l, text in groq_matches:
    print(f"  - {r}:{l} -> {text}")

trans_file = BASE_DIR / "core" / "transcription_engine.py"
print(f"\nDoes core/transcription_engine.py exist? {trans_file.exists()}")
if trans_file.exists():
    with open(trans_file, "r", encoding="utf-8", errors="ignore") as f:
        print("First 30 lines of core/transcription_engine.py:")
        print("\n".join(f.readlines()[:30]))
