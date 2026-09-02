import sys
import json
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

from PySide6.QtWidgets import QApplication
import updater
from ui.pages.settings_page import SettingsPage

app = QApplication.instance() or QApplication(sys.argv)

page = SettingsPage()
page.show()

print("Initial download_update_btn isHidden:", page.download_update_btn.isHidden())

# Simulate update info returned
mock_up = {
    "version": "v1.0.1-test",
    "changelog": "Release test pour vérification automatique.",
    "download_url": "https://github.com/DHLoua-Amine/app_cabinet/releases/download/v1.0.1-test/update.zip",
    "sha256_url": "https://github.com/DHLoua-Amine/app_cabinet/releases/download/v1.0.1-test/SHA256SUMS.txt",
    "asset_name": "update.zip",
    "asset_size": 1234567
}

page.on_update_checked(mock_up)

print("\n--- After on_update_checked(mock_up) ---")
print("Status label text:", page.update_status.text())
print("download_update_btn isHidden:", page.download_update_btn.isHidden())
print("download_update_btn enabled:", page.download_update_btn.isEnabled())
print("download_update_btn text:", page.download_update_btn.text())

assert page.download_update_btn.isHidden() == False
assert "v1.0.1-test" in page.update_status.text()
print("\n✅ ITEM 2 UI BUTTON TEST PASSED 100%!")
