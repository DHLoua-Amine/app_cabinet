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
print("1. Instantiating ScannerPage...")
page = ScannerPage()
print("2. Calling populate_contract_types()...")
page.populate_contract_types()
print("3. Calling select_contract_type('عقد بيع')...")
page.select_contract_type("عقد بيع")
print("4. Calling update_office_header()...")
page.update_office_header()
print("[SUCCESS] All ScannerPage methods executed with 0 errors!")
