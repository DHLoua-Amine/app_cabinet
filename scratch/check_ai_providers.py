import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")

print("=== AI EXTRACTOR & PROVIDERS AUDIT ===")
for fname in ["core/ai_extractor.py", "core/cin_extractor.py", "core/config.py"]:
    p = BASE_DIR / fname
    if p.exists():
        print(f"\n--- {fname} ---")
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            for idx, line in enumerate(lines, 1):
                if any(w in line.lower() for w in ["provider", "gemini", "groq", "openai", "mistral", "api_key"]):
                    print(f"  Line {idx}: {line.strip()}")
