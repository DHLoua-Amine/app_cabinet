import os
from pathlib import Path

pages_dir = Path(r"C:\Users\amin\Desktop\zarai1_pyside\ui\pages")
if pages_dir.exists():
    for f in pages_dir.glob("*.py"):
        print(f.name)
