import os
import sys
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

from config import DATA_DIR, save_ai_engine, load_ai_engine

print("Updating AI preferences file to gemini-2.5-flash...")
save_ai_engine("gemini", "gemini-2.5-flash")
provider, model = load_ai_engine()
print(f"[SUCCESS] Current Active AI Engine: {provider} | {model}")
