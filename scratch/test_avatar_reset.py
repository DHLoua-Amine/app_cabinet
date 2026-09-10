import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "core"))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QImage, QColor
from ui.pages.fiche_client_page import FicheClientPage

app = QApplication.instance() or QApplication(sys.argv)

page = FicheClientPage(client_id="TEST_EXISTING")

# Simulate loading a client with a valid pixmap
dummy_img = QImage(100, 100, QImage.Format.Format_RGB32)
dummy_img.fill(QColor("blue"))
dummy_pm = QPixmap.fromImage(dummy_img)

page.banner_avatar.setPixmap(dummy_pm)
page.photo_preview.setPixmap(dummy_pm)

assert not page.banner_avatar.pixmap().isNull(), "Banner avatar should have pixmap"
assert not page.photo_preview.pixmap().isNull(), "Photo preview should have pixmap"

# Now switch to a new client
page.is_new = True
page.client_id = "NEW_TEST_CLIENT_99"
page.init_empty_client()
page.load_client_data()

# Verify that pixmap is completely cleared!
assert page.banner_avatar.pixmap() is None or page.banner_avatar.pixmap().isNull(), "Banner avatar pixmap was NOT cleared!"
assert page.photo_preview.pixmap() is None or page.photo_preview.pixmap().isNull(), "Photo preview pixmap was NOT cleared!"
assert page.banner_avatar.text() == "👤", f"Banner text expected 👤, got '{page.banner_avatar.text()}'"

print("SUCCESS: Avatar and photo preview reset test passed 100%!")
