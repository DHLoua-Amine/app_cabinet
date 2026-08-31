import sys
import shutil
from pathlib import Path
from PIL import Image

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
assets_dir = BASE_DIR / "assets"
assets_dir.mkdir(exist_ok=True)

art_dir = Path(r"C:\Users\amin\.gemini\antigravity\brain\eb85a7e8-ee26-4dae-aba4-6f7e82bfa620")
src_img = art_dir / "media__1788018845218.png"

print(f"Processing DATLY logo from {src_img}...")

# Copy raw logo to assets
dst_png = assets_dir / "datly_logo.png"
shutil.copy2(src_img, dst_png)
print(f"Saved {dst_png.name}")

# Open image with Pillow
im = Image.open(src_img)
if im.mode != "RGBA":
    im = im.convert("RGBA")

# Generate .ico file with multiple standard Windows sizes
ico_path = assets_dir / "app_icon.ico"
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
im.save(ico_path, format="ICO", sizes=sizes)
print(f"Generated Windows Icon: {ico_path} ({ico_path.stat().st_size} bytes)")

# Create a square icon version
width, height = im.size
size = max(width, height)
sq_im = Image.new("RGBA", (size, size), (45, 55, 60, 255)) # Dark slate matching logo bg
sq_im.paste(im, ((size - width) // 2, (size - height) // 2))

sq_png = assets_dir / "datly_square_icon.png"
sq_im.save(sq_png, format="PNG")
print(f"Generated Square Icon: {sq_png}")

print("Logo processing completed successfully!")
