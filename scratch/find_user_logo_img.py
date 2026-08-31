import os
from pathlib import Path

art_dir = Path(r"C:\Users\amin\.gemini\antigravity\brain\eb85a7e8-ee26-4dae-aba4-6f7e82bfa620")
print("Searching for recent image files in artifact directory:")
for f in art_dir.glob("*"):
    if f.suffix.lower() in [".png", ".jpg", ".jpeg"]:
        print(f"  {f.name} ({f.stat().st_size} bytes)")
