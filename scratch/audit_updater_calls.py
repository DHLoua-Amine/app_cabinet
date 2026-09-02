import os
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

symbols = [
    "check_for_update",
    "download_and_verify_update",
    "apply_update_and_restart",
    "prompt_user_update",
    "is_update_channel_configured",
    "GITHUB_REPO_RELEASES"
]

results = {s: [] for s in symbols}

for root, dirs, files in os.walk(BASE_DIR):
    if "__pycache__" in root or ".git" in root or "scratch" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            p = Path(root) / f
            try:
                txt = p.read_text(encoding="utf-8")
                for s in symbols:
                    if s in txt:
                        lines = [i + 1 for i, line in enumerate(txt.splitlines()) if s in line]
                        results[s].append((str(p.relative_to(BASE_DIR)), lines))
            except Exception as e:
                pass

print("="*70)
print(" 🔍 SEARCH RESULTS FOR UPDATER SYMBOLS ACROSS THE CODEBASE")
print("="*70)
for s, occurrences in results.items():
    print(f"\n--- Symbol: {s} ---")
    if not occurrences:
        print("  ❌ NO OCCURRENCES FOUND!")
    else:
        for file_rel, line_nums in occurrences:
            print(f"  📄 {file_rel}: lines {line_nums}")
