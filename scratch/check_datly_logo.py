import sys
from pathlib import Path
from PIL import Image

art_dir = Path(r"C:\Users\amin\.gemini\antigravity\brain\eb85a7e8-ee26-4dae-aba4-6f7e82bfa620")
images = [
    art_dir / "media__1788018845218.png",
    art_dir / "media__1788018576757.png",
]

for img_path in images:
    if img_path.exists():
        im = Image.open(img_path)
        print(f"{img_path.name}: format={im.format}, size={im.size}, mode={im.mode}")
