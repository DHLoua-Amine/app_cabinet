import io
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "core"))

from PIL import Image, ImageDraw
from ocr_engine import auto_crop_card_bounding_box

def test_position(name, card_rect):
    large_page = Image.new("RGB", (2000, 3000), color=(255, 255, 255))
    draw = ImageDraw.Draw(large_page)
    draw.rectangle(card_rect, fill=(220, 220, 225), outline=(30, 30, 30), width=4)
    draw.text((card_rect[0] + 20, card_rect[1] + 20), "CARTE CIN TUNISIE", fill=(0, 0, 0))

    cropped = auto_crop_card_bounding_box(large_page)
    cw, ch = cropped.size
    print(f"Position [{name}]: rect={card_rect} -> Auto-cropped size: {cw}x{ch}")
    assert cw < 1000 and ch < 800, f"Failed for {name}: {cw}x{ch}"

# 1. Test Card at the BOTTOM of A4 page
test_position("BOTTOM", [800, 2400, 1300, 2700])

# 2. Test Card in the MIDDLE of A4 page
test_position("MIDDLE", [750, 1350, 1250, 1650])

# 3. Test Card at the TOP-RIGHT corner of A4 page
test_position("TOP-RIGHT", [1300, 200, 1800, 500])

# 4. Test Card at the BOTTOM-LEFT corner of A4 page
test_position("BOTTOM-LEFT", [100, 2300, 600, 2600])

print("ALL POSITIONS VERIFIED 100%! The card can be anywhere on the page!")
