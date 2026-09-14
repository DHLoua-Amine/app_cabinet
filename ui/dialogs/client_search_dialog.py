from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QHeaderView
)
from PySide6.QtCore import Qt
import reception


class ClientSearchDialog(QDialog):
    """Quick Client Search and Selection Dialog from Office Database Archive."""

    def __init__(self, parent=None, title="البحث في أرشيف الحرفاء وتحديد حريف إضافي"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(780, 480)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.selected_client = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)

        lbl = QLabel("<b>اكتب اسم الحريف أو أرقام بطاقة التعريف للبحث السريع في أرشيف المكتب:</b>")
        lbl.setStyleSheet("font-size: 13px; color: #1e3a8a;")
        layout.addWidget(lbl)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("ابحث بالاسم، رقم بطاقة التعريف، المهنة، أو العنوان...")
        self.txt_search.setFixedHeight(38)
        self.txt_search.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                color: #0f172a;
                border: 1.5px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
        """)
        self.txt_search.textChanged.connect(self.filter_clients)
        layout.addWidget(self.txt_search)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["رقم ب.ت.ط", "الاسم واللقب الكامل", "المهنة", "العنوان", "تاريخ الميلاد"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                gridline-color: #f1f5f9;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #1e3a8a;
                font-weight: bold;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #cbd5e1;
            }
            QTableWidget::item:selected {
                background-color: #e0f2fe;
                color: #0369a1;
            }
        """)
        self.table.itemDoubleClicked.connect(self.on_row_double_clicked)
        layout.addWidget(self.table)

        btn_lay = QHBoxLayout()
        self.btn_select = QPushButton("اختيار الحريف المخصص")
        self.btn_select.setFixedHeight(36)
        self.btn_select.setStyleSheet("""
            QPushButton {
                background-color: #1e40af;
                color: #ffffff;
                border-radius: 6px;
                padding: 0 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1e3a8a;
            }
        """)
        self.btn_select.clicked.connect(self.accept_selected)

        self.btn_cancel = QPushButton("إلغاء")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)

        btn_lay.addStretch()
        btn_lay.addWidget(self.btn_select)
        btn_lay.addWidget(self.btn_cancel)
        layout.addLayout(btn_lay)

        try:
            self.all_clients = reception.get_all_clients()
        except Exception:
            self.all_clients = []
        self.filter_clients("")

    def filter_clients(self, query):
        q = query.strip().lower()
        self.table.setRowCount(0)
        row = 0
        for c in self.all_clients:
            cin = str(c.get("cin_number", ""))
            fn = str(c.get("full_name") or f"{c.get('nom', '')} {c.get('prenom', '')}").strip()
            job = str(c.get("profession", ""))
            addr = str(c.get("address", ""))
            bdate = str(c.get("birth_date", ""))

            search_blob = f"{cin} {fn} {job} {addr} {bdate}".lower()
            if not q or q in search_blob:
                self.table.insertRow(row)
                item_cin = QTableWidgetItem(cin)
                item_cin.setData(Qt.ItemDataRole.UserRole, c)
                self.table.setItem(row, 0, item_cin)
                self.table.setItem(row, 1, QTableWidgetItem(fn))
                self.table.setItem(row, 2, QTableWidgetItem(job))
                self.table.setItem(row, 3, QTableWidgetItem(addr))
                self.table.setItem(row, 4, QTableWidgetItem(bdate))
                row += 1

    def on_row_double_clicked(self, item):
        self.accept_selected()

    def accept_selected(self):
        r = self.table.currentRow()
        if r < 0 and self.table.rowCount() > 0:
            r = 0
            self.table.selectRow(0)
        if r >= 0:
            item = self.table.item(r, 0)
            if item:
                self.selected_client = item.data(Qt.ItemDataRole.UserRole)
                self.accept()
