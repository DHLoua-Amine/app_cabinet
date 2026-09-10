import os, sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('core'))

from PySide6.QtWidgets import QApplication

def test_pages():
    print("--- TESTING ALL PAGE INITIALIZATIONS ---")
    app = QApplication.instance() or QApplication(sys.argv)

    import core.reception as reception
    reception.init_db()

    from ui.pages.home_page import HomePage
    from ui.pages.presence_page import PresencePage
    from ui.pages.clients_page import ClientsPage
    from ui.pages.fiche_client_page import FicheClientPage
    from ui.pages.register_page import RegisterPage
    from ui.pages.accounting_page import AccountingPage
    from ui.pages.scanner_page import ScannerPage
    from ui.pages.settings_page import SettingsPage

    pages = [
        ("HomePage", HomePage),
        ("PresencePage", PresencePage),
        ("ClientsPage", ClientsPage),
        ("FicheClientPage", FicheClientPage),
        ("RegisterPage", RegisterPage),
        ("AccountingPage", AccountingPage),
        ("ScannerPage", ScannerPage),
        ("SettingsPage", SettingsPage)
    ]

    for name, cls in pages:
        try:
            w = cls()
            print(f"[OK] {name} initialized cleanly!")
        except Exception as e:
            print(f"[FAIL] {name} raised exception: {e}")
            raise e

    print("--- ALL 8 PAGES PASSED INITIALIZATION & IMPORT TEST ---")

if __name__ == "__main__":
    test_pages()
