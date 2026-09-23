import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'c:\Users\amin\Desktop\zarai1_pyside\core')
sys.path.insert(0, r'c:\Users\amin\Desktop\zarai1_pyside')

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

def mock_msg(title, text):
    print(f"MSG [{title}]: {text}")

QMessageBox.information = lambda parent, title, text: mock_msg(title, text)
QMessageBox.warning = lambda parent, title, text: mock_msg(title, text)
QMessageBox.critical = lambda parent, title, text: mock_msg(title, text)
QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes

import permissions
permissions.session.sign_in("admin", "admin")

import reception
from ui.pages.scanner_page import ScannerPage

app = QApplication([])
page = ScannerPage()
page.load_clients_list()

target_cid = "1153071"
found_item = False
for i in range(page.archive_list.count()):
    item = page.archive_list.item(i)
    if item.data(Qt.ItemDataRole.UserRole) == target_cid:
        item.setCheckState(Qt.CheckState.Checked)
        found_item = True
    else:
        item.setCheckState(Qt.CheckState.Unchecked)

assert found_item, f"Client {target_cid} not found in archive_list!"

page.dossier_combo.setCurrentIndex(0)
page.var_dossier_num.setText("2026-99")

# Set valid contract text (> 200 chars)
page.ocr_edited_text = (
    "الحمد لله في يوم الإثنين السابع عشر من ربيع الأول سنة ثمان وأربعين وأربعمائة وألف هـ الموافق لـالرابع عشر من سبتمبر سنة ألفين وست وعشرين. "
    "انعقد بين الطرف الأول البائع: السيد علي بن أحمد Zarai المولود بـ تونس بطاقة تعريفه عدد 01234567. "
    "والطرف الثاني المشترية: السيدة مريم بنت صالح بطاقة تعريفها عدد 07654321. "
    "الفصل الأول: باع واحال الطرف الأول تحت سائر الضمانات الفعلية والقانونية للطرف الثاني جميع القطعة الفلاحية الكائنة بـ الكاف. "
    "الفصل الثاني: تم البيع نظير ثمن جملي قدره خمسة آلاف دينار (5000 د.ت) قبضها البائع بذكره. "
    "وأبرم العقد بين طرفيه وتلي فوافقا وأمضيا والله الموفق."
)
page.archive_to_clients()

cases = reception.get_client_cases(target_cid)
case_ids = [c["case_id"] for c in cases]
print("FOUND CLIENT DOSSIERS IN DB:", case_ids)

assert "2026-99" in case_ids, "Custom dossier ID '2026-99' was not created in DB!"

# Check client documents
docs = reception.get_client_documents_list(target_cid)
doc_names = [d["name"] for d in docs]
print("SAVED DOCUMENTS FOR CLIENT 1153071:")
for n in doc_names:
    print("  - Doc:", n)

assert any("2026-99" in n for n in doc_names), "Document missing custom dossier number!"

# Select client 1153071 in p1 combo so update_dossiers_combo finds it
cb = page._party_cards['p1'][0]['combo']
idx = cb.findData(target_cid)
if idx >= 0:
    cb.setCurrentIndex(idx)

# Now update combo and verify auto-fill
page.update_dossiers_combo()
combo_idx = page.dossier_combo.findData("2026-99")
assert combo_idx > 0, "Custom dossier 2026-99 not found in combo after refresh!"
page.dossier_combo.setCurrentIndex(combo_idx)
assert page.var_dossier_num.text() == "2026-99", "Dossier num input text did not update to 2026-99!"
assert page.var_dossier_num.isEnabled() == False, "Dossier num input should be disabled for existing dossier!"

print("\nSUCCESS: Custom dossier number 2026-99 verified and working 100%!")
