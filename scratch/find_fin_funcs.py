import os, re
from pathlib import Path

reception_file = Path(r"C:\Users\amin\Desktop\zarai1_pyside\core\reception.py")
with open(reception_file, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f.readlines(), 1):
        if "def " in line and any(w in line.lower() for w in ["compta", "financial", "revenue", "expense", "summary", "stats", "balance"]):
            print(f"Line {idx}: {line.strip()}")
