import sys
from pathlib import Path
BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMenu
from PySide6.QtCore import Qt

import contract_templates

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Cascading Contract Menu")
        self.resize(600, 400)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)

        selectors_box = QHBoxLayout()
        self.lbl_type = QLabel("نوع العقد :")
        self.lbl_type.setStyleSheet("font-size:13px; font-weight:700; color:#1e293b;")

        self.type_btn = QPushButton("اختر نوع العقد...")
        self.type_btn.setFixedHeight(36)
        self.type_btn.setMinimumWidth(320)
        self.type_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 13px;
                font-weight: bold;
                text-align: right;
            }
            QPushButton:hover {
                background-color: #f8fafc;
                border-color: #94a3b8;
            }
        """)

        selectors_box.addWidget(self.lbl_type)
        selectors_box.addWidget(self.type_btn)
        lay.addLayout(selectors_box)

        self.populate_contract_menu()

    def populate_contract_menu(self):
        self.contract_menu = QMenu(self)
        self.contract_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.contract_menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QMenu::item {
                padding: 8px 24px 8px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #e0f2fe;
                color: #0369a1;
            }
        """)

        for cat_name, contracts in contract_templates.CONTRACT_CATEGORIES.items():
            sub_menu = self.contract_menu.addMenu(cat_name)
            sub_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            sub_menu.setStyleSheet(self.contract_menu.styleSheet())
            for c in contracts:
                action = sub_menu.addAction(c)
                action.triggered.connect(lambda checked=False, contract=c: self.select_contract_type(contract))

        self.type_btn.setMenu(self.contract_menu)

    def select_contract_type(self, contract):
        print(f"Selected Contract Type: {contract}")
        self.type_btn.setText(contract)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = TestWindow()
    w.show()
    print("Cascading Menu initialized cleanly!")
