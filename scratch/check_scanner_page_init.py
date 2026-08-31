import sys
from pathlib import Path

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

from PySide6.QtWidgets import QApplication
import permissions
permissions.session.sign_in("admin", permissions.ROLE_ADMIN, "Notaire")

app = QApplication.instance() or QApplication(sys.argv)

from ui.pages.scanner_page import ScannerPage
print("Instantiating ScannerPage...")
page = ScannerPage()
print("ScannerPage instantiated cleanly with zero errors!")
