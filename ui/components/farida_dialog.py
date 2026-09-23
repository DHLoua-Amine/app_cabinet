from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QCheckBox, QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextEdit, QScrollArea, QWidget, QMessageBox, QGroupBox,
    QFileDialog, QAbstractSpinBox, QLineEdit, QComboBox, QCompleter, QTabWidget,
    QProgressDialog, QApplication, QMenu, QCalendarWidget
)
from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QDate
from PySide6.QtGui import QFont, QColor, QTextDocument, QCursor
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
import re


try:
    from farida_engine import TunisianFaridaEngine
    import reception
except ImportError:
    from core.farida_engine import TunisianFaridaEngine
    import core.reception as reception


def is_female_name(name: str) -> bool:
    """
    Determines if a name is female based on:
    1. Direct patronymic connectors ('بنت' / 'ابنة' / 'زوجة' / 'أرملة' / 'البنت').
    2. Direct male patronymic connectors ('بن' / 'إبن' / 'ابن' / 'ولد' / 'الابن').
    3. Arabic morphological feminine endings ('ة', 'ه', 'اء', 'ى'), excluding male exceptions (بوجمعة، حمزة، إلخ).
    """
    if not name or not isinstance(name, str):
        return False
    clean_n = name.strip()
    if not clean_n:
        return False

    if re.search(r'\b(بنت|ابنة|حرم|أرملة|زوجة|البنت)\b', clean_n):
        return True
    if re.search(r'\b(بن|إبن|ابن|ولد|الابن)\b', clean_n):
        return False

    parts = clean_n.split()
    first_w = parts[0]
    first_norm = re.sub(r'[أإآ]', 'ا', first_w)

    male_exceptions = {
        'حمزة', 'حمزه', 'طلحة', 'طلحه', 'عبيدة', 'عبيده', 'قتادة', 'قتاده', 'أسامة', 'اسامة', 'اسامه',
        'عكرمة', 'معاوية', 'سلامة', 'سلامه', 'عرفة', 'عمارة', 'عماره', 'ربيعة', 'ربيعه', 'خليفة', 'خليفه',
        'عطية', 'عطيه', 'حذيفة', 'حذيفه', 'بوجمعة', 'بوجمعه', 'جمعة', 'جمعه', 'طه', 'عروة', 'عروه',
        'رباح', 'عتبة', 'عتبه', 'شيبة', 'شيبه', 'وجيه', 'عمران', 'عز', 'صلاح', 'زين', 'أمية', 'امية'
    }

    if first_norm in male_exceptions or first_norm.startswith('بو') or any(first_norm.startswith(p) for p in ['بو', 'عبد', 'ابو']):
        return False

    if any(first_norm.endswith(e) for e in ['ة', 'ه', 'اء', 'ى']):
        return True
    return False


class DatePickerLineEdit(QWidget):
    """Hybrid Date widget with QLineEdit + a 📅 Visual Calendar Popup button."""
    textChanged = Signal(str)

    def __init__(self, parent=None, placeholder="تاريخ الوفاة (YYYY/MM/DD)"):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self.line_edit = QLineEdit(self)
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
        self.line_edit.textChanged.connect(self.textChanged.emit)

        self.btn_cal = QPushButton("📅", self)
        self.btn_cal.setToolTip("فتح التقويم لاختيار التاريخ التفاعلي")
        self.btn_cal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cal.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.btn_cal.clicked.connect(self.open_calendar_popup)

        lay.addWidget(self.line_edit, 1)
        lay.addWidget(self.btn_cal)

    def text(self):
        return self.line_edit.text()

    def setText(self, val):
        self.line_edit.setText(val)

    def setPlaceholderText(self, text):
        self.line_edit.setPlaceholderText(text)

    def open_calendar_popup(self):
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        menu_lay = QVBoxLayout(menu)
        menu_lay.setContentsMargins(4, 4, 4, 4)

        cal = QCalendarWidget(menu)
        cal.setGridVisible(True)
        cal.setNavigationBarVisible(True)
        cal.setStyleSheet("""
            QCalendarWidget { background-color: #ffffff; border: 1px solid #cbd5e1; }
            QCalendarWidget QAbstractItemView { selection-background-color: #0284c7; selection-color: white; }
        """)

        cur_text = self.line_edit.text().strip()
        if cur_text:
            try:
                parts = re.split(r'[-/.]', cur_text)
                if len(parts) == 3:
                    if len(parts[0]) == 4:
                        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    else:
                        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    cal.setSelectedDate(QDate(y, m, d))
            except Exception:
                pass

        def on_date_selected():
            qdate = cal.selectedDate()
            date_str = qdate.toString("yyyy/MM/dd")
            self.line_edit.setText(date_str)
            menu.close()

        cal.clicked.connect(on_date_selected)
        menu_lay.addWidget(cal)

        btn = self.sender()
        if isinstance(btn, QWidget):
            pos = btn.mapToGlobal(QPoint(0, btn.height()))
        else:
            pos = QCursor.pos()
        menu.exec(pos)


class ClientSearchDialog(QDialog):
    """Live search dialog for office client archive by Name, CIN number, Profession, or Address."""
    def __init__(self, parent=None, title="البحث في أرشيف الحرفاء"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(780, 460)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.selected_client = None

        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; font-family: 'Segoe UI', 'Tajawal', sans-serif; }
            QLineEdit { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px 10px; font-size: 12px; color: #0f172a; }
            QTableWidget { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12px; color: #0f172a; }
            QHeaderView::section { background-color: #f1f5f9; font-weight: bold; color: #334155; border: none; padding: 6px; }
            QPushButton.PrimaryBtn { background-color: #1e40af; color: #ffffff; border: none; border-radius: 4px; padding: 8px 14px; font-weight: bold; font-size: 12px; }
            QPushButton.PrimaryBtn:hover { background-color: #1e3a8a; }
            QPushButton.SecondaryBtn { background-color: #64748b; color: #ffffff; border: none; border-radius: 4px; padding: 8px 14px; font-weight: bold; font-size: 12px; }
            QPushButton.SecondaryBtn:hover { background-color: #475569; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        lbl_desc = QLabel("اكتب أي جزء من الاسم أو أرقام من بطاقة التعريف للبحث السريع في أرشيف المكتب:", self)
        lbl_desc.setStyleSheet("font-weight: bold; color: #1e293b;")
        layout.addWidget(lbl_desc)

        self.txt_search = QLineEdit(self)
        self.txt_search.setPlaceholderText("ابحث باسم الحريف، رقم بطاقة التعريف الوطنية، المهنة، أو العنوان...")
        self.txt_search.textChanged.connect(self.filter_clients)
        layout.addWidget(self.txt_search)

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["رقم ب.ت.ط", "الاسم واللقب الكامل", "المهنة", "العنوان", "تاريخ الميلاد"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemDoubleClicked.connect(self.on_row_double_clicked)
        layout.addWidget(self.table)

        btn_lay = QHBoxLayout()
        btn_cancel = QPushButton("إلغاء", self)
        btn_cancel.setProperty("class", "SecondaryBtn")
        btn_cancel.clicked.connect(self.reject)

        self.btn_select = QPushButton("اختيار الحريف المخصص", self)
        self.btn_select.setProperty("class", "PrimaryBtn")
        self.btn_select.clicked.connect(self.accept_selected)

        btn_lay.addWidget(btn_cancel)
        btn_lay.addStretch()
        btn_lay.addWidget(self.btn_select)
        layout.addLayout(btn_lay)

        try:
            self.all_clients = reception.get_all_clients()
        except Exception:
            self.all_clients = []
        self.filter_clients("")

    def filter_clients(self, query: str):
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


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

class HujjaUploadPopupDialog(QDialog):
    """
    Dedicated 2-Slot Popup Dialog for Recto-Verso Hujjat Wafat Upload.
    Slot 1: Page 1 / Recto (الوجه الأول)
    Slot 2: Page 2 / Verso (الوجه الثاني - اختياري)
    """
    def __init__(self, parent=None, title="استيراد وتفريغ حجة الوفاة بالذكاء الاصطناعي"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.page1_path = ""
        self.page2_path = ""
        self.init_ui()

    def init_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(16, 16, 16, 16)

        header = QLabel("📜 نافذة استيراد حجة الوفاة (وجه واحد أو وجهين Recto-Verso):", self)
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #1e293b;")
        lay.addWidget(header)

        info = QLabel("يمكنك رفع الوجه الأول، وإذا كانت حجة الوفاة تتكون من وجهين (Recto-Verso)، قم برفع الوجه الثاني في الخانة المخصصة له ليتم دمجهما بدقة 100%.", self)
        info.setStyleSheet("color: #475569; font-size: 11px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        # Slot 1: Page 1 (Recto)
        grp1 = QGroupBox("📄 الوجه الأول / الصفحة 1 (الوجه الأمامي الرئيسي - إجباري)", self)
        grp1_lay = QHBoxLayout(grp1)
        self.lbl_p1 = QLabel("لم يتم اختيار صورة للصفحة الأولى", grp1)
        self.lbl_p1.setStyleSheet("color: #64748b; font-size: 11px;")
        btn_p1 = QPushButton("📁 رفع الصفحة 1 (Recto)", grp1)
        btn_p1.setStyleSheet("background: #0284c7; color: white; border-radius: 4px; padding: 6px 12px; font-weight: bold;")
        btn_p1.clicked.connect(self.select_page1)
        grp1_lay.addWidget(self.lbl_p1, 1)
        grp1_lay.addWidget(btn_p1)
        lay.addWidget(grp1)

        # Slot 2: Page 2 (Verso - Optional)
        grp2 = QGroupBox("📄 الوجه الثاني / الصفحة 2 (الوجه الخلفي - اختياري)", self)
        grp2_lay = QHBoxLayout(grp2)
        self.lbl_p2 = QLabel("لم يتم اختيار صفحة ثانية (اختياري)", grp2)
        self.lbl_p2.setStyleSheet("color: #94a3b8; font-size: 11px;")
        btn_p2 = QPushButton("📁 رفع الصفحة 2 (Verso)", grp2)
        btn_p2.setStyleSheet("background: #475569; color: white; border-radius: 4px; padding: 6px 12px; font-weight: bold;")
        btn_p2.clicked.connect(self.select_page2)
        grp2_lay.addWidget(self.lbl_p2, 1)
        grp2_lay.addWidget(btn_p2)
        lay.addWidget(grp2)

        # Action Buttons
        btn_lay = QHBoxLayout()
        btn_cancel = QPushButton("إلغاء", self)
        btn_cancel.clicked.connect(self.reject)
        self.btn_submit = QPushButton("🚀 بدء الاستخراج والتفريغ الآلي", self)
        self.btn_submit.setStyleSheet("background: #16a34a; color: white; border-radius: 6px; padding: 8px 16px; font-weight: bold; font-size: 12px;")
        self.btn_submit.clicked.connect(self.accept_upload)
        btn_lay.addWidget(btn_cancel)
        btn_lay.addStretch()
        btn_lay.addWidget(self.btn_submit)
        lay.addLayout(btn_lay)

    def select_page1(self):
        fp, _ = QFileDialog.getOpenFileName(self, "اختر صورة الصفحة الأولى (Recto)", "", "صور أو ملفات (*.png *.jpg *.jpeg *.pdf *.txt)")
        if fp:
            self.page1_path = fp
            from pathlib import Path
            self.lbl_p1.setText(f"✓ {Path(fp).name}")
            self.lbl_p1.setStyleSheet("color: #16a34a; font-weight: bold; font-size: 11px;")

    def select_page2(self):
        fp, _ = QFileDialog.getOpenFileName(self, "اختر صورة الصفحة الثانية (Verso - اختياري)", "", "صور أو ملفات (*.png *.jpg *.jpeg *.pdf *.txt)")
        if fp:
            self.page2_path = fp
            from pathlib import Path
            self.lbl_p2.setText(f"✓ {Path(fp).name}")
            self.lbl_p2.setStyleSheet("color: #16a34a; font-weight: bold; font-size: 11px;")

    def accept_upload(self):
        if not self.page1_path and not self.page2_path:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار صورة الصفحة الأولى على الأقل.")
            return
        self.accept()

    def get_selected_paths(self):
        paths = []
        if self.page1_path: paths.append(self.page1_path)
        if self.page2_path: paths.append(self.page2_path)
        return paths


class TunisianFaridaDialog(QDialog):
    """
    Executive Notarial Calculator & Deed Generator for Tunisian Inheritance (فريضة شرعية وفريضة جزئية).
    Features:
    - Support for Partial Farida (فريضة جزئية) & Full Legal Farida (فريضة شرعية)
    - Property Title Certificate & Death Certificate Notarial Preamble
    - 1-Click Direct Printing with Official Office Header
    - Amicable Partition Contract (عقد مقاسمة رضائية) Auto-Generation
    """

    generate_partition_requested = Signal(dict)
    farida_inserted = Signal(dict)

    def __init__(self, parent=None, lang="ar", client_id=None):
        super().__init__(parent)
        self.lang = lang
        self.client_id = client_id
        self.engine = TunisianFaridaEngine()
        self.last_result = None
        self.heir_inputs = {}
        self.main_parsed = None          # result of scanning main hujja wafat
        self.linked_hujaj = []           # list of parsed additional hujjat wafat (predeceased children)
        self.init_ui()

        if client_id:
            self.load_client_profile(client_id)

    def init_ui(self):
        self.setWindowTitle("محرر الفريضة الشرعية والجزئية التوثيقية")
        self.resize(1200, 780)
        self.setMinimumSize(1080, 720)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
                font-family: 'Segoe UI', 'Tajawal', sans-serif;
            }
            QFrame.MainCard {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 14px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top right;
                padding: 0 8px;
                color: #1e293b;
            }
            QLabel {
                color: #334155;
                font-size: 12px;
            }
            QLineEdit, QComboBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                color: #0f172a;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #1e40af;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 10px;
                font-weight: bold;
                font-size: 12px;
                color: #0f172a;
                min-width: 100px;
            }
            QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                width: 0px;
                height: 0px;
                border: none;
            }
            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #1e40af;
            }
            QCheckBox {
                font-size: 12px;
                font-weight: 600;
                color: #1e293b;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 1px solid #94a3b8;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #1e40af;
                border-color: #1e40af;
            }
            QTabWidget::pane {
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #f1f5f9;
                color: #475569;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 12px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-left: 2px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #1e40af;
                border: 1px solid #cbd5e1;
                border-bottom: 3px solid #1e40af;
            }
            QPushButton.PrimaryBtn {
                background-color: #1e40af;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton.PrimaryBtn:hover {
                background-color: #1e3a8a;
            }
            QPushButton.SecondaryBtn {
                background-color: #475569;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton.SecondaryBtn:hover {
                background-color: #334155;
            }
            QPushButton.SuccessBtn {
                background-color: #059669;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton.SuccessBtn:hover {
                background-color: #047857;
            }
        """)

        master_layout = QVBoxLayout(self)
        master_layout.setContentsMargins(16, 16, 16, 16)
        master_layout.setSpacing(12)

        # Client info bar if loaded
        self.client_info_lbl = QLabel("", self)
        self.client_info_lbl.setStyleSheet("color: #0369a1; font-weight: bold; font-size: 12px; background: #e0f2fe; padding: 8px 14px; border-radius: 6px; border: 1px solid #bae6fd;")
        self.client_info_lbl.setVisible(False)
        master_layout.addWidget(self.client_info_lbl)

        # Unified Main Tab Widget (100% Full Width)
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #f1f5f9;
                color: #475569;
                padding: 10px 22px;
                font-weight: bold;
                font-size: 13px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-left: 2px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #1e40af;
                border: 1px solid #cbd5e1;
                border-bottom: 3px solid #1e40af;
            }
        """)

        # ── TAB 1: معطيات الفريضة وطرفي الإشهاد ─────────────────────────────────
        tab1 = QWidget()
        tab1_lay = QVBoxLayout(tab1)
        tab1_lay.setContentsMargins(12, 12, 12, 12)
        tab1_lay.setSpacing(12)

        # ── SCAN BUTTONS ROW ──────────────────────────────────────────────────
        scan_btns_row = QHBoxLayout()

        self.btn_import_wafat = QPushButton("📄 استيراد حجة وفاة الهالك الرئيسي (صورة / PDF / نص)", tab1)
        self.btn_import_wafat.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.btn_import_wafat.clicked.connect(self.import_hujjat_wafat_file)

        self.btn_add_linked_hujja = QPushButton("➕ إضافة حجة وفاة ابن/بنت توفي في حياة الهالك", tab1)
        self.btn_add_linked_hujja.setToolTip("امسح حجة وفاة أحد أبناء الهالك الذين توفوا قبله — سيتم الربط التلقائي وإضافة أبنائهم (الأحفاد) لقائمة الورثة")
        self.btn_add_linked_hujja.setStyleSheet("""
            QPushButton {
                background-color: #065f46;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.btn_add_linked_hujja.clicked.connect(self.add_linked_hujja)

        self.btn_link_hujaj = QPushButton("🔗 ربط الحجج وتعبئة الفريضة تلقائياً", tab1)
        self.btn_link_hujaj.setToolTip("يقوم بمطابقة أسماء المتوفين في الحجج الإضافية مع قائمة الورثة، ويعبئ أعداد الأحفاد تلقائياً")
        self.btn_link_hujaj.setEnabled(False)
        self.btn_link_hujaj.setStyleSheet("""
            QPushButton {
                background-color: #5b21b6;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4c1d95;
            }
            QPushButton:disabled {
                background-color: #a5b4fc;
                color: #e0e7ff;
            }
        """)
        self.btn_link_hujaj.clicked.connect(self.link_and_merge_hujaj)

        scan_btns_row.addWidget(self.btn_import_wafat, 3)
        scan_btns_row.addWidget(self.btn_add_linked_hujja, 3)
        scan_btns_row.addWidget(self.btn_link_hujaj, 2)
        tab1_lay.addLayout(scan_btns_row)

        # ── LINKED HUJAJ PANEL ──────────────────────────────────────────────
        self.linked_panel_frame = QFrame(tab1)
        self.linked_panel_frame.setVisible(False)
        self.linked_panel_frame.setStyleSheet("""
            QFrame {
                background-color: #f0fdf4;
                border: 1px solid #86efac;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        self.linked_panel_layout = QVBoxLayout(self.linked_panel_frame)
        self.linked_panel_layout.setContentsMargins(8, 6, 8, 6)
        self.linked_panel_layout.setSpacing(4)
        lnk_title = QLabel("📋 حجج الوفاة المرتبطة (أبناء/بنات الهالك المتوفون قبله):", self.linked_panel_frame)
        lnk_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #065f46;")
        self.linked_panel_layout.addWidget(lnk_title)
        tab1_lay.addWidget(self.linked_panel_frame)

        scroll1 = QScrollArea(tab1)
        scroll1.setWidgetResizable(True)
        scroll1.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_w1 = QWidget()
        form_lay1 = QVBoxLayout(scroll_w1)
        form_lay1.setContentsMargins(4, 4, 4, 4)
        form_lay1.setSpacing(12)

        # Box 1: Contract Type
        grp_type = QGroupBox("نوع الفريضة التوثيقية", scroll_w1)
        grp_type_lay = QHBoxLayout(grp_type)
        ctype_lbl = QLabel("اختر نوع الفريضة:", grp_type)
        self.combo_contract_type = QComboBox(grp_type)
        self.combo_contract_type.addItems(["فريضة شرعية", "فريضة جزئية"])
        grp_type_lay.addWidget(ctype_lbl)
        grp_type_lay.addWidget(self.combo_contract_type, 1)
        form_lay1.addWidget(grp_type)

        # Box 2: Applicant Information
        grp_applicant = QGroupBox("بيانات طالب(ة) الإشهاد", scroll_w1)
        grp_applicant_lay = QVBoxLayout(grp_applicant)
        app_lay = QHBoxLayout()
        self.txt_applicant_name = QLineEdit(grp_applicant)
        self.txt_applicant_name.setPlaceholderText("اسم طالب(ة) الإشهاد الكامل")
        self.txt_applicant_cin = QLineEdit(grp_applicant)
        self.txt_applicant_cin.setPlaceholderText("رقم بطاقة التعريف الوطنية")

        self.btn_search_applicant_archive = QPushButton("بحث بالأرشيف (اسم / ب.ت)", grp_applicant)
        self.btn_search_applicant_archive.setToolTip("البحث عن طالب الإشهاد في أرشيف الحرفاء بالاسم أو ب.ت.ط")
        self.btn_search_applicant_archive.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.btn_search_applicant_archive.clicked.connect(self.open_applicant_search_dialog)

        app_lay.addWidget(QLabel("الاسم واللقب:", grp_applicant))
        app_lay.addWidget(self.txt_applicant_name, 2)
        app_lay.addWidget(self.txt_applicant_cin, 1)
        app_lay.addWidget(self.btn_search_applicant_archive)
        grp_applicant_lay.addLayout(app_lay)
        form_lay1.addWidget(grp_applicant)

        # Box 3: Deceased Information
        grp_deceased = QGroupBox("بيانات الهالك(ة) (المتوفى / المتوفية)", scroll_w1)
        grp_deceased_lay = QVBoxLayout(grp_deceased)
        dec_lay = QHBoxLayout()
        self.txt_deceased_name = QLineEdit(grp_deceased)
        self.txt_deceased_name.setPlaceholderText("اسم الهالك (المتوفى / المتوفية) الكامل")

        dec_lay.addWidget(QLabel("اسم الهالك(ة):", grp_deceased))
        dec_lay.addWidget(self.txt_deceased_name, 1)
        grp_deceased_lay.addLayout(dec_lay)
        form_lay1.addWidget(grp_deceased)

        # Box 4: Death Certificate Reference Meta
        grp_hujja = QGroupBox("معطيات حجة الوفاة الرسمية", scroll_w1)
        grp_hujja_lay = QVBoxLayout(grp_hujja)
        hujja_lay = QHBoxLayout()
        self.txt_hujja_num = QLineEdit(grp_hujja)
        self.txt_hujja_num.setPlaceholderText("عدد حجة الوفاة")
        self.txt_hujja_date = DatePickerLineEdit(grp_hujja, placeholder="تاريخ حجة الوفاة")
        self.txt_hujja_court = QLineEdit(grp_hujja)
        self.txt_hujja_court.setPlaceholderText("المحكمة الصادرة عنها")
        hujja_lay.addWidget(QLabel("عدد الحجة:", grp_hujja))
        hujja_lay.addWidget(self.txt_hujja_num)
        hujja_lay.addWidget(self.txt_hujja_date)
        hujja_lay.addWidget(self.txt_hujja_court)
        grp_hujja_lay.addLayout(hujja_lay)
        form_lay1.addWidget(grp_hujja)

        # Box 5: Real Estate Certificate (For Partial Farida)
        grp_prop = QGroupBox("بيانات الرسم العقاري (خاص بالفريضة الجزئية)", scroll_w1)
        grp_prop_lay = QVBoxLayout(grp_prop)
        grp_prop_lay.setSpacing(8)

        title_lay = QHBoxLayout()
        self.txt_title_num = QLineEdit(grp_prop)
        self.txt_title_num.setPlaceholderText("رقم الرسم العقاري (مثال: 3163 بن عروس)")
        self.txt_property_name = QLineEdit(grp_prop)
        self.txt_property_name.setPlaceholderText("اسم العقار (المسمى)")
        title_lay.addWidget(QLabel("الرسم والعقار:", grp_prop))
        title_lay.addWidget(self.txt_title_num)
        title_lay.addWidget(self.txt_property_name)
        grp_prop_lay.addLayout(title_lay)

        loc_lay = QHBoxLayout()
        self.txt_location = QLineEdit(grp_prop)
        self.txt_location.setPlaceholderText("موقع العقار الكائن بـ...")
        loc_lay.addWidget(QLabel("موقع العقار:", grp_prop))
        loc_lay.addWidget(self.txt_location)
        grp_prop_lay.addLayout(loc_lay)

        m2_lay = QHBoxLayout()
        m2_lbl = QLabel("مساحة العقار بالأمتار المربعة:", grp_prop)
        self.spin_m2 = NoWheelDoubleSpinBox(grp_prop)
        self.spin_m2.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_m2.setRange(0, 1000000)
        self.spin_m2.setValue(0)
        m2_lay.addWidget(m2_lbl)
        m2_lay.addStretch()
        m2_lay.addWidget(self.spin_m2)
        grp_prop_lay.addLayout(m2_lay)

        parts_lay = QHBoxLayout()
        parts_lbl = QLabel("عدد أجزاء التجزئة (مثال: 4608000):", grp_prop)
        self.spin_parts = NoWheelDoubleSpinBox(grp_prop)
        self.spin_parts.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_parts.setRange(0, 10000000)
        self.spin_parts.setValue(0)
        parts_lay.addWidget(parts_lbl)
        parts_lay.addStretch()
        parts_lay.addWidget(self.spin_parts)
        grp_prop_lay.addLayout(parts_lay)

        form_lay1.addWidget(grp_prop)

        # Box 6: Obligatory Bequest Box
        grp_bequest = QGroupBox("الوصية الواجبة (الفصل 191 مجلة الأحوال الشخصية)", scroll_w1)
        grp_bequest_lay = QVBoxLayout(grp_bequest)

        bequest_top_lay = QHBoxLayout()
        bequest_lbl = QLabel("عدد الأبناء المتوفين سابقاً في حياة الهالك:", grp_bequest)
        self.spin_predeceased = NoWheelSpinBox(grp_bequest)
        self.spin_predeceased.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_predeceased.setRange(0, 10)
        bequest_top_lay.addWidget(bequest_lbl)
        bequest_top_lay.addStretch()
        bequest_top_lay.addWidget(self.spin_predeceased)
        grp_bequest_lay.addLayout(bequest_top_lay)

        # Dynamic per-child container (name + date for each)
        self.predeceased_inputs = {}
        self.grp_predeceased_children = QFrame(grp_bequest)
        self.grp_predeceased_children.setStyleSheet("QFrame { background: transparent; border: none; }")
        self.predeceased_children_layout = QVBoxLayout(self.grp_predeceased_children)
        self.predeceased_children_layout.setContentsMargins(0, 4, 0, 0)
        self.predeceased_children_layout.setSpacing(6)
        grp_bequest_lay.addWidget(self.grp_predeceased_children)

        form_lay1.addWidget(grp_bequest)

        scroll1.setWidget(scroll_w1)
        tab1_lay.addWidget(scroll1)

        # ── TAB 2: شجرة الورثة والأسماء وبطاقات التعريف ──────────────────────────
        tab2 = QWidget()
        tab2_lay = QVBoxLayout(tab2)
        tab2_lay.setContentsMargins(12, 12, 12, 12)
        tab2_lay.setSpacing(10)

        scroll3 = QScrollArea(tab2)
        scroll3.setWidgetResizable(True)
        scroll3.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_w3 = QWidget()
        form_lay3 = QVBoxLayout(scroll_w3)
        form_lay3.setContentsMargins(4, 4, 4, 4)
        form_lay3.setSpacing(12)

        # Spouses
        grp_spouse = QGroupBox("الزوج أو الزوجة (القرابة المباشرة)", scroll_w3)
        grp_spouse_lay = QVBoxLayout(grp_spouse)
        grp_spouse_lay.setSpacing(6)
        self.cb_husband = QCheckBox("الزوج (على قيد الحياة وقت وفاة الهالكة)", grp_spouse)
        self.cb_husband.setToolTip("يُعلم إذا كان الزوج حياً وقت وفاة زوجته الهالكة")
        
        wife_lay = QHBoxLayout()
        self.cb_wife = QCheckBox("الزوجة (على قيد الحياة وقت وفاة الهالك)", grp_spouse)
        self.cb_wife.setToolTip("تُعلم إذا كانت الزوجة حية وقت وفاة زوجها الهالك")
        wives_cnt_lbl = QLabel("عدد الزوجات على قيد الحياة:", grp_spouse)
        self.spin_wives = NoWheelSpinBox(grp_spouse)
        self.spin_wives.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_wives.setRange(1, 4)
        self.spin_wives.setValue(1)
        wife_lay.addWidget(self.cb_wife)
        wife_lay.addStretch()
        wife_lay.addWidget(wives_cnt_lbl)
        wife_lay.addWidget(self.spin_wives)

        grp_spouse_lay.addWidget(self.cb_husband)
        grp_spouse_lay.addLayout(wife_lay)
        form_lay3.addWidget(grp_spouse)

        # Descendants
        grp_desc = QGroupBox("الفروع (الأبناء والبنات وأبناء الابن)", scroll_w3)
        grp_desc_lay = QVBoxLayout(grp_desc)
        grp_desc_lay.setSpacing(6)

        sons_lay = QHBoxLayout()
        sons_lbl = QLabel("عدد الأبناء (ذكور - أبناء الهالك مباشرة):", grp_desc)
        self.spin_sons = NoWheelSpinBox(grp_desc)
        self.spin_sons.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_sons.setRange(0, 30)
        sons_lay.addWidget(sons_lbl)
        sons_lay.addStretch()
        sons_lay.addWidget(self.spin_sons)
        grp_desc_lay.addLayout(sons_lay)

        daug_lay = QHBoxLayout()
        daug_lbl = QLabel("عدد البنات (إناث - بنات الهالك مباشرة):", grp_desc)
        self.spin_daug = NoWheelSpinBox(grp_desc)
        self.spin_daug.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_daug.setRange(0, 30)
        daug_lay.addWidget(daug_lbl)
        daug_lay.addStretch()
        daug_lay.addWidget(self.spin_daug)
        grp_desc_lay.addLayout(daug_lay)

        grandsons_lay = QHBoxLayout()
        grandsons_lbl = QLabel("عدد أبناء الابن (ذكور - الأحفاد من الابن المتوفى):", grp_desc)
        self.spin_grandsons = NoWheelSpinBox(grp_desc)
        self.spin_grandsons.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_grandsons.setRange(0, 30)
        grandsons_lay.addWidget(grandsons_lbl)
        grandsons_lay.addStretch()
        grandsons_lay.addWidget(self.spin_grandsons)
        grp_desc_lay.addLayout(grandsons_lay)

        granddaug_lay = QHBoxLayout()
        granddaug_lbl = QLabel("عدد بنات الابن (إناث - الحفيدات من الابن المتوفى):", grp_desc)
        self.spin_granddaughters = NoWheelSpinBox(grp_desc)
        self.spin_granddaughters.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_granddaughters.setRange(0, 30)
        granddaug_lay.addWidget(granddaug_lbl)
        granddaug_lay.addStretch()
        granddaug_lay.addWidget(self.spin_granddaughters)
        grp_desc_lay.addLayout(granddaug_lay)

        form_lay3.addWidget(grp_desc)

        # Ancestors
        grp_ancestors = QGroupBox("الأصول (الأب والأم والجد والجدات)", scroll_w3)
        grp_ancestors_lay = QVBoxLayout(grp_ancestors)
        grp_ancestors_lay.setSpacing(5)

        self.cb_father = QCheckBox("الأب (والد الهالك - على قيد الحياة عند الوفاة)", grp_ancestors)
        self.cb_mother = QCheckBox("الأم (والدة الهالك - على قيد الحياة عند الوفاة)", grp_ancestors)
        self.cb_paternal_grandfather = QCheckBox("الجد لأب (والد والد الهالك - على قيد الحياة)", grp_ancestors)
        self.cb_maternal_grandmother = QCheckBox("الجدة لأم (والدة أم الهالك - على قيد الحياة)", grp_ancestors)
        self.cb_paternal_grandmother = QCheckBox("الجدة لأب (والدة أب الهالك - على قيد الحياة)", grp_ancestors)

        grp_ancestors_lay.addWidget(self.cb_father)
        grp_ancestors_lay.addWidget(self.cb_mother)
        grp_ancestors_lay.addWidget(self.cb_paternal_grandfather)
        grp_ancestors_lay.addWidget(self.cb_maternal_grandmother)
        grp_ancestors_lay.addWidget(self.cb_paternal_grandmother)
        form_lay3.addWidget(grp_ancestors)

        # Siblings
        grp_sibs = QGroupBox("الإخوة والأخوات (أشقاء ولأب ولأم)", scroll_w3)
        grp_sibs_lay = QVBoxLayout(grp_sibs)
        grp_sibs_lay.setSpacing(5)

        bro_lay = QHBoxLayout()
        bro_lbl = QLabel("عدد الإخوة الأشقاء (إخوة الهالك من الأب والأم معاً):", grp_sibs)
        self.spin_bro = NoWheelSpinBox(grp_sibs)
        self.spin_bro.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_bro.setRange(0, 20)
        bro_lay.addWidget(bro_lbl)
        bro_lay.addStretch()
        bro_lay.addWidget(self.spin_bro)
        grp_sibs_lay.addLayout(bro_lay)

        sis_lay = QHBoxLayout()
        sis_lbl = QLabel("عدد الأخوات الشقيقات (أخوات الهالك من الأب والأم معاً):", grp_sibs)
        self.spin_sis = NoWheelSpinBox(grp_sibs)
        self.spin_sis.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_sis.setRange(0, 20)
        sis_lay.addWidget(sis_lbl)
        sis_lay.addStretch()
        sis_lay.addWidget(self.spin_sis)
        grp_sibs_lay.addLayout(sis_lay)

        pat_bro_lay = QHBoxLayout()
        pat_bro_lbl = QLabel("عدد الإخوة لأب (إخوة الهالك من الأب فقط):", grp_sibs)
        self.spin_pat_bro = NoWheelSpinBox(grp_sibs)
        self.spin_pat_bro.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_pat_bro.setRange(0, 20)
        pat_bro_lay.addWidget(pat_bro_lbl)
        pat_bro_lay.addStretch()
        pat_bro_lay.addWidget(self.spin_pat_bro)
        grp_sibs_lay.addLayout(pat_bro_lay)

        pat_sis_lay = QHBoxLayout()
        pat_sis_lbl = QLabel("عدد الأخوات لأب (أخوات الهالك من الأب فقط):", grp_sibs)
        self.spin_pat_sis = NoWheelSpinBox(grp_sibs)
        self.spin_pat_sis.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_pat_sis.setRange(0, 20)
        pat_sis_lay.addWidget(pat_sis_lbl)
        pat_sis_lay.addStretch()
        pat_sis_lay.addWidget(self.spin_pat_sis)
        grp_sibs_lay.addLayout(pat_sis_lay)

        mat_bro_lay = QHBoxLayout()
        mat_bro_lbl = QLabel("عدد الإخوة لأم (ذكور - أخ من الأم فقط):", grp_sibs)
        self.spin_mat_bro = NoWheelSpinBox(grp_sibs)
        self.spin_mat_bro.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_mat_bro.setRange(0, 20)
        mat_bro_lay.addWidget(mat_bro_lbl)
        mat_bro_lay.addStretch()
        mat_bro_lay.addWidget(self.spin_mat_bro)
        grp_sibs_lay.addLayout(mat_bro_lay)

        mat_sis_lay = QHBoxLayout()
        mat_sis_lbl = QLabel("عدد الأخوات لأم (إناث - أخت من الأم فقط):", grp_sibs)
        self.spin_mat_sis = NoWheelSpinBox(grp_sibs)
        self.spin_mat_sis.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_mat_sis.setRange(0, 20)
        mat_sis_lay.addWidget(mat_sis_lbl)
        mat_sis_lay.addStretch()
        mat_sis_lay.addWidget(self.spin_mat_sis)
        grp_sibs_lay.addLayout(mat_sis_lay)

        form_lay3.addWidget(grp_sibs)

        # Extended Agnates
        grp_agnates = QGroupBox("بقية الورثة الشرعيين: أبناء الإخوة والأعمام وأبناء العمومة", scroll_w3)
        grp_agnates_lay = QVBoxLayout(grp_agnates)
        grp_agnates_lay.setSpacing(5)

        nephew_full_lay = QHBoxLayout()
        nephew_full_lbl = QLabel("عدد أبناء الأخ الشقيق (أبناء أخ الهالك الشقيق):", grp_agnates)
        self.spin_nephew_full = NoWheelSpinBox(grp_agnates)
        self.spin_nephew_full.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_nephew_full.setRange(0, 20)
        nephew_full_lay.addWidget(nephew_full_lbl)
        nephew_full_lay.addStretch()
        nephew_full_lay.addWidget(self.spin_nephew_full)
        grp_agnates_lay.addLayout(nephew_full_lay)

        nephew_pat_lay = QHBoxLayout()
        nephew_pat_lbl = QLabel("عدد أبناء الأخ لأب (أبناء أخ الهالك لأب):", grp_agnates)
        self.spin_nephew_pat = NoWheelSpinBox(grp_agnates)
        self.spin_nephew_pat.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_nephew_pat.setRange(0, 20)
        nephew_pat_lay.addWidget(nephew_pat_lbl)
        nephew_pat_lay.addStretch()
        nephew_pat_lay.addWidget(self.spin_nephew_pat)
        grp_agnates_lay.addLayout(nephew_pat_lay)

        self.cb_uncle_full = QCheckBox("العم الشقيق (أخ والد الهالك من الأب والأم - على قيد الحياة)", grp_agnates)
        self.cb_uncle_full.setToolTip("العم الشقيق هو أخ والد الهالك من نفس الأب والأم")
        
        self.cb_uncle_pat = QCheckBox("العم لأب (أخ والد الهالك من الأب فقط - على قيد الحياة)", grp_agnates)
        self.cb_uncle_pat.setToolTip("العم لأب هو أخ والد الهالك من جهة الأب فقط")
        
        grp_agnates_lay.addWidget(self.cb_uncle_full)
        grp_agnates_lay.addWidget(self.cb_uncle_pat)

        cousin_full_lay = QHBoxLayout()
        cousin_full_lbl = QLabel("عدد أبناء العم الشقيق (في حال كان العم الشقيق متوفياً):", grp_agnates)
        self.spin_cousin_full = NoWheelSpinBox(grp_agnates)
        self.spin_cousin_full.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_cousin_full.setRange(0, 20)
        cousin_full_lay.addWidget(cousin_full_lbl)
        cousin_full_lay.addStretch()
        cousin_full_lay.addWidget(self.spin_cousin_full)
        grp_agnates_lay.addLayout(cousin_full_lay)

        cousin_pat_lay = QHBoxLayout()
        cousin_pat_lbl = QLabel("عدد أبناء العم لأب (في حال كان العم لأب متوفياً):", grp_agnates)
        self.spin_cousin_pat = NoWheelSpinBox(grp_agnates)
        self.spin_cousin_pat.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_cousin_pat.setRange(0, 20)
        cousin_pat_lay.addWidget(cousin_pat_lbl)
        cousin_pat_lay.addStretch()
        cousin_pat_lay.addWidget(self.spin_cousin_pat)
        grp_agnates_lay.addLayout(cousin_pat_lay)

        form_lay3.addWidget(grp_agnates)

        # ── Dynamic Heir Details Group (Name & CIN fields for every heir!) ──
        grp_heir_details = QGroupBox("أسماء وأرقام بطاقات تعريف الورثة المحددين (كامل العرض)", scroll_w3)
        self.heir_details_layout = QVBoxLayout(grp_heir_details)
        self.heir_details_layout.setContentsMargins(8, 12, 8, 12)
        self.heir_details_layout.setSpacing(8)
        form_lay3.addWidget(grp_heir_details)

        scroll3.setWidget(scroll_w3)
        tab2_lay.addWidget(scroll3)

        # ── TAB 3: نتائج الأنصبة والنص التوثيقي الرسمي والعقود ─────────────────────
        tab3 = QWidget()
        tab3_lay = QVBoxLayout(tab3)
        tab3_lay.setContentsMargins(12, 12, 12, 12)
        tab3_lay.setSpacing(10)

        # Origin Summary Banner
        self.origin_banner = QFrame(tab3)
        self.origin_banner.setStyleSheet("background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px;")
        banner_lay = QHBoxLayout(self.origin_banner)
        banner_lay.setContentsMargins(14, 10, 14, 10)

        self.origin_lbl = QLabel("أصل الفريضة التوثيقية: —", self.origin_banner)
        self.origin_lbl.setStyleSheet("font-weight: 800; font-size: 13px; color: #0f172a; border: none;")
        banner_lay.addWidget(self.origin_lbl)
        tab3_lay.addWidget(self.origin_banner)

        # Table (Full Width 1200px Table!)
        self.table = QTableWidget(tab3)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["الوارث الشرعي", "صفة الوارث", "الأجزاء", "الفك / الكسر", "النسبة %", "مناب العقار والأجزاء"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                gridline-color: #f1f5f9;
                background-color: #ffffff;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #ffffff;
                font-weight: bold;
                padding: 9px;
                border: none;
            }
            QTableWidget::item {
                padding: 6px;
            }
        """)
        tab3_lay.addWidget(self.table, stretch=1)

        # Internal text handle buffer for PDF/Word export compatibility
        self.text_output = QTextEdit()
        self.text_output.hide()

        # Add 3 tabs to self.tab_widget
        self.tab_widget.addTab(tab1, "📄 1. معطيات الفريضة وطرفي الإشهاد والعقار والوصية الواجبة")
        self.tab_widget.addTab(tab2, "👥 2. شجرة الورثة والأسماء وبطاقات التعريف")
        self.tab_widget.addTab(tab3, "📜 3. جدول حساب الفريضة ومناب كل وارث")

        master_layout.addWidget(self.tab_widget, stretch=1)

        # ── BOTTOM ACTION BAR (FULL WIDTH) ──────────────────────────────────
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        calc_btn = QPushButton("🔄 إعادة الحساب التلقائي", self)
        calc_btn.setProperty("class", "PrimaryBtn")
        calc_btn.clicked.connect(self.on_calculate_clicked)

        insert_editor_btn = QPushButton("📥 إدراج في محرر العقود (Scanner IA)", self)
        insert_editor_btn.setStyleSheet("""
            QPushButton {
                background-color: #15803d;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #166534;
            }
        """)
        insert_editor_btn.clicked.connect(self.on_insert_into_editor_clicked)

        bottom_bar.addWidget(calc_btn)
        bottom_bar.addWidget(insert_editor_btn)
        bottom_bar.addStretch()

        master_layout.addLayout(bottom_bar)

        # Connect live updates
        self.combo_contract_type.currentTextChanged.connect(self.on_calculate_clicked)
        self.txt_applicant_name.textChanged.connect(self.on_calculate_clicked)
        self.txt_applicant_cin.textChanged.connect(self.on_calculate_clicked)
        self.txt_deceased_name.textChanged.connect(self.on_calculate_clicked)
        self.txt_hujja_num.textChanged.connect(self.on_calculate_clicked)
        self.txt_hujja_date.textChanged.connect(self.on_calculate_clicked)
        self.txt_hujja_court.textChanged.connect(self.on_calculate_clicked)
        self.txt_title_num.textChanged.connect(self.on_calculate_clicked)
        self.txt_property_name.textChanged.connect(self.on_calculate_clicked)
        self.txt_location.textChanged.connect(self.on_calculate_clicked)
        self.spin_predeceased.valueChanged.connect(self.refresh_predeceased_widgets)
        self.spin_predeceased.valueChanged.connect(self.on_calculate_clicked)
        self.spin_m2.valueChanged.connect(self.on_calculate_clicked)
        self.spin_parts.valueChanged.connect(self.on_calculate_clicked)

        # Connect heir counts & checkboxes to refresh dynamic fields & calculate
        for cb in (self.cb_husband, self.cb_wife, self.cb_father, self.cb_mother,
                   self.cb_paternal_grandfather, self.cb_maternal_grandmother,
                   self.cb_paternal_grandmother, self.cb_uncle_full, self.cb_uncle_pat):
            cb.toggled.connect(self.on_heir_counts_changed)

        for spin in (self.spin_wives, self.spin_sons, self.spin_daug, self.spin_grandsons,
                     self.spin_granddaughters, self.spin_bro, self.spin_sis, self.spin_pat_bro,
                     self.spin_pat_sis, self.spin_mat_bro, self.spin_mat_sis, self.spin_nephew_full,
                     self.spin_nephew_pat, self.spin_cousin_full, self.spin_cousin_pat):
            spin.valueChanged.connect(self.on_heir_counts_changed)

        # Setup client autocompleters
        try:
            self._setup_client_autocompleters()
        except Exception:
            pass

        # Initial refresh & calculation
        self.refresh_heir_details_widgets()
        self.on_calculate_clicked()

    def on_heir_counts_changed(self, *args):
        self.refresh_heir_details_widgets()
        self.on_calculate_clicked()

    def refresh_heir_details_widgets(self):
        """Dynamically constructs Name and CIN fields for all active heirs based on counts and checkboxes."""
        if not hasattr(self, "heir_details_layout"):
            return

        active_heirs = []

        if self.cb_husband.isChecked():
            active_heirs.append(("husband", "الزوج"))

        if self.cb_wife.isChecked():
            for i in range(1, self.spin_wives.value() + 1):
                lbl_t = f"الزوجة {i}" if self.spin_wives.value() > 1 else "الزوجة"
                active_heirs.append((f"wife_{i}", lbl_t))

        if self.cb_father.isChecked():
            active_heirs.append(("father", "الأب"))

        if self.cb_mother.isChecked():
            active_heirs.append(("mother", "الأم"))

        if self.cb_paternal_grandfather.isChecked():
            active_heirs.append(("paternal_grandfather", "الجد لأب"))

        if self.cb_maternal_grandmother.isChecked():
            active_heirs.append(("maternal_grandmother", "الجدة لأم"))

        if self.cb_paternal_grandmother.isChecked():
            active_heirs.append(("paternal_grandmother", "الجدة لأب"))

        for i in range(1, self.spin_sons.value() + 1):
            lbl_t = f"الابن {i}" if self.spin_sons.value() > 1 else "الابن"
            active_heirs.append((f"son_{i}", lbl_t))

        for i in range(1, self.spin_daug.value() + 1):
            lbl_t = f"البنت {i}" if self.spin_daug.value() > 1 else "البنت"
            active_heirs.append((f"daughter_{i}", lbl_t))

        for i in range(1, self.spin_grandsons.value() + 1):
            active_heirs.append((f"grandson_{i}", f"ابن الابن {i}"))

        for i in range(1, self.spin_granddaughters.value() + 1):
            active_heirs.append((f"granddaughter_{i}", f"بنت الابن {i}"))

        for i in range(1, self.spin_bro.value() + 1):
            active_heirs.append((f"full_brother_{i}", f"الأخ الشقيق {i}"))

        for i in range(1, self.spin_sis.value() + 1):
            active_heirs.append((f"full_sister_{i}", f"الأخت الشقيقة {i}"))

        for i in range(1, self.spin_pat_bro.value() + 1):
            active_heirs.append((f"pat_brother_{i}", f"الأخ لأب {i}"))

        for i in range(1, self.spin_pat_sis.value() + 1):
            active_heirs.append((f"pat_sister_{i}", f"الأخت لأب {i}"))

        for i in range(1, self.spin_mat_bro.value() + 1):
            active_heirs.append((f"mat_brother_{i}", f"الأخ لأم {i}"))

        for i in range(1, self.spin_mat_sis.value() + 1):
            active_heirs.append((f"mat_sister_{i}", f"الأخت لأم {i}"))

        for i in range(1, self.spin_nephew_full.value() + 1):
            active_heirs.append((f"nephew_full_{i}", f"ابن الأخ الشقيق {i}"))

        for i in range(1, self.spin_nephew_pat.value() + 1):
            active_heirs.append((f"nephew_pat_{i}", f"ابن الأخ لأب {i}"))

        if self.cb_uncle_full.isChecked():
            active_heirs.append(("uncle_full", "العم الشقيق"))

        if self.cb_uncle_pat.isChecked():
            active_heirs.append(("uncle_pat", "العم لأب"))

        for i in range(1, self.spin_cousin_full.value() + 1):
            active_heirs.append((f"cousin_full_{i}", f"ابن العم الشقيق {i}"))

        for i in range(1, self.spin_cousin_pat.value() + 1):
            active_heirs.append((f"cousin_pat_{i}", f"ابن العم لأب {i}"))

        current_keys = set(self.heir_inputs.keys())
        active_keys = set(k for k, _ in active_heirs)

        # Remove keys no longer present (cache typed names before deleting widget so unchecking/rechecking doesn't wipe them)
        if not hasattr(self, "cached_heir_names"):
            self.cached_heir_names = {}
        for k in current_keys - active_keys:
            data = self.heir_inputs.pop(k)
            name_text = data["name"].text().strip()
            if name_text:
                self.cached_heir_names[k] = name_text
            w = data.get("widget")
            if w:
                w.deleteLater()

        # Add new active keys
        for key, label_text in active_heirs:
            if key not in self.heir_inputs:
                row_card = QFrame()
                row_card.setStyleSheet("QFrame { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; }")
                row_lay = QHBoxLayout(row_card)
                row_lay.setContentsMargins(8, 6, 8, 6)
                row_lay.setSpacing(6)

                lbl = QLabel(f"<b>{label_text}:</b>", row_card)
                lbl.setMinimumWidth(85)
                lbl.setStyleSheet("color: #1e40af; font-size: 11px;")

                txt_name = QLineEdit(row_card)
                txt_name.setPlaceholderText("الاسم واللقب الكامل")
                txt_name.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 8px; font-size: 11px;")

                # Restore name from cache or main_parsed if available
                if key in self.cached_heir_names:
                    txt_name.setText(self.cached_heir_names[key])
                elif hasattr(self, "main_parsed") and self.main_parsed:
                    if key.startswith("wife") and self.main_parsed.get("wife_name"):
                        txt_name.setText(self.main_parsed["wife_name"])
                    elif key == "husband" and self.main_parsed.get("husband_name"):
                        txt_name.setText(self.main_parsed["husband_name"])
                    elif key.startswith("son_"):
                        try:
                            s_idx = int(key.split("_")[1]) - 1
                            sons_names = self.main_parsed.get("sons_names", [])
                            if 0 <= s_idx < len(sons_names):
                                txt_name.setText(sons_names[s_idx])
                        except Exception:
                            pass
                    elif key.startswith("daughter_"):
                        try:
                            d_idx = int(key.split("_")[1]) - 1
                            daug_names = self.main_parsed.get("daughters_names", [])
                            if 0 <= d_idx < len(daug_names):
                                txt_name.setText(daug_names[d_idx])
                        except Exception:
                            pass

                txt_name.textChanged.connect(self.on_calculate_clicked)
                txt_name.textChanged.connect(lambda _: self._update_renounce_target_combos())

                # Hidden CIN field (kept for data integrity, not shown in UI)
                txt_cin = QLineEdit(row_card)
                txt_cin.setVisible(False)

                # Hidden civil status field (kept for data integrity, not shown in UI)
                txt_civil_status = QLineEdit(row_card)
                txt_civil_status.setVisible(False)

                btn_search = QPushButton("🔍 أرشيف", row_card)
                btn_search.setToolTip("البحث في أرشيف المكتب لاستيراد الاسم واللقب")
                btn_search.setStyleSheet("QPushButton { background-color: #0284c7; color: white; border: none; border-radius: 4px; padding: 4px 8px; font-size: 10px; font-weight: bold; } QPushButton:hover { background-color: #0369a1; }")
                btn_search.clicked.connect(lambda _, n=txt_name, c=txt_cin, l=label_text: self._search_heir_from_archive(n, c, l))

                cb_renounce = QCheckBox("✍️ تنازل عن المناب", row_card)
                cb_renounce.setToolTip("تأشير هذا الخيار في حال صرّح هذا الوارث بتنازله عن منابه الشرعي في التركة")
                cb_renounce.setStyleSheet("QCheckBox { font-size: 11px; font-weight: bold; color: #b91c1c; margin-right: 4px; }")

                combo_renounce_target = QComboBox(row_card)
                combo_renounce_target.setVisible(False)
                combo_renounce_target.setStyleSheet("QComboBox { background-color: #fef2f2; border: 1px solid #fca5a5; border-radius: 4px; padding: 2px 6px; font-size: 11px; color: #991b1b; }")

                def _toggle_renounce(checked, c_box=combo_renounce_target):
                    c_box.setVisible(checked)
                    self._update_renounce_target_combos()
                    self.on_calculate_clicked()

                cb_renounce.toggled.connect(_toggle_renounce)
                combo_renounce_target.currentIndexChanged.connect(self.on_calculate_clicked)

                row_lay.addWidget(lbl)
                row_lay.addWidget(txt_name, 3)
                row_lay.addWidget(btn_search)
                row_lay.addWidget(cb_renounce)
                row_lay.addWidget(combo_renounce_target, 2)

                self.heir_details_layout.addWidget(row_card)
                self.heir_inputs[key] = {
                    "widget": row_card,
                    "name": txt_name,
                    "cin": txt_cin,
                    "civil_status": txt_civil_status,
                    "label": label_text,
                    "renounce_cb": cb_renounce,
                    "renounce_target": combo_renounce_target
                }

        self._update_renounce_target_combos()

    def _update_renounce_target_combos(self):
        """Updates options in renounce target dropdowns for all active heir cards."""
        if not hasattr(self, "heir_inputs") or not self.heir_inputs:
            return

        all_heir_options = [("all", "التنازل لفائدة سائر الورثة (توزيع بالتناسب)")]
        for k, d in self.heir_inputs.items():
            nm = d["name"].text().strip()
            lbl_t = d["label"]
            disp = f"{nm} ({lbl_t})" if nm else lbl_t
            all_heir_options.append((k, f"التنازل لفائدة: {disp}"))

        for k, d in self.heir_inputs.items():
            cb = d.get("renounce_target")
            if not cb:
                continue
            cur_data = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            for opt_key, opt_label in all_heir_options:
                if opt_key != k:
                    cb.addItem(opt_label, opt_key)

            if cur_data is not None:
                idx = cb.findData(cur_data)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
            cb.blockSignals(False)

    def get_detected_hujja_names(self):
        """Returns a list of names extracted from scanned Hujjat Wafat documents and current heir inputs."""
        names = []
        # 1. Main scanned hujja
        if hasattr(self, "main_parsed") and self.main_parsed:
            extracted = self.main_parsed.get("names", [])
            for n in extracted:
                if n and n.strip() and n.strip() not in names:
                    names.append(n.strip())
            for n in self.main_parsed.get("sons_names", []) + self.main_parsed.get("daughters_names", []):
                if n and n.strip() and n.strip() not in names:
                    names.append(n.strip())

        # 2. Linked hujjas (additional hujjat wafat scanned for predeceased children)
        if hasattr(self, "linked_hujaj") and self.linked_hujaj:
            for lh in self.linked_hujaj:
                dec = lh.get("deceased_name", "").strip()
                if dec and dec not in names:
                    names.append(dec)
                for n in lh.get("names", []):
                    if n and n.strip() and n.strip() not in names:
                        names.append(n.strip())

        # 3. Names typed in heir details
        if hasattr(self, "heir_inputs") and self.heir_inputs:
            for k, data in self.heir_inputs.items():
                nm = data.get("name", QLineEdit()).text().strip()
                if nm and nm not in names:
                    names.append(nm)

        return names

    def _pick_predeceased_from_hujja_full(self, txt_name, txt_date, txt_spouse, spin_sons, spin_daug, txt_gc, gc_edits, combo_status, combo_gender):
        """Shows a popup menu with full details from scanned Hujjat Wafat."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 16px; font-size: 11px; color: #1e293b; border-radius: 4px; }
            QMenu::item:selected { background-color: #e0f2fe; color: #0284c7; font-weight: bold; }
        """)

        options_found = False

        if hasattr(self, "linked_hujaj") and self.linked_hujaj:
            hdr = menu.addAction("── من حجج الوفاة المضافة (الأبناء المتوفون) ──")
            hdr.setEnabled(False)
            for lh in self.linked_hujaj:
                d_name = lh.get("deceased_name", "").strip()
                d_date = lh.get("hujja_date", "").strip()
                w_name = lh.get("wife_name", "").strip() or lh.get("husband_name", "").strip()
                s_cnt = lh.get("sons_count", 0)
                d_cnt = lh.get("daughters_count", 0)
                gc_names = "، ".join(lh.get("names", []))
                if d_name:
                    options_found = True
                    label = f"⚰️ {d_name}" + (f" (وفاة: {d_date})" if d_date else "") + (f" — ذكور:{s_cnt} إناث:{d_cnt}" if (s_cnt or d_cnt) else "")
                    action = menu.addAction(label)
                    action.triggered.connect(
                        lambda _, n=d_name, d=d_date, w=w_name, sn=s_cnt, dn=d_cnt, g=gc_names:
                            self._apply_predeceased_full_choice(txt_name, txt_date, txt_spouse, spin_sons, spin_daug, txt_gc, gc_edits, combo_status, combo_gender, n, d, w, sn, dn, g)
                    )

        if hasattr(self, "main_parsed") and self.main_parsed:
            extracted = self.main_parsed.get("names", [])
            sons = self.main_parsed.get("sons_names", [])
            daug = self.main_parsed.get("daughters_names", [])
            all_main_names = list(dict.fromkeys(sons + daug + extracted))
            if all_main_names:
                hdr2 = menu.addAction("── من حجة الوفاة الرئيسية ──")
                hdr2.setEnabled(False)
                for nm in all_main_names:
                    if nm and nm.strip():
                        options_found = True
                        action = menu.addAction(f"👤 {nm.strip()}")
                        action.triggered.connect(
                            lambda _, n=nm.strip():
                                self._apply_predeceased_full_choice(txt_name, txt_date, txt_spouse, spin_sons, spin_daug, txt_gc, gc_edits, combo_status, combo_gender, n, "", "", 0, 0, "")
                        )

        if not options_found:
            no_act = menu.addAction("⚠️ لم يتم كشف أسماء في حجة الوفاة بعد")
            no_act.setEnabled(False)

        btn = self.sender()
        if isinstance(btn, QWidget):
            menu.exec(btn.mapToGlobal(QPoint(0, btn.height())))
        else:
            menu.exec(QCursor.pos())

    def _apply_predeceased_full_choice(self, txt_name, txt_date, txt_spouse, spin_sons, spin_daug, txt_gc, gc_edits, combo_status, combo_gender, n, d, w, sn, dn, g):
        if n:
            txt_name.setText(n)
            if is_female_name(n):
                combo_gender.setCurrentIndex(1)
            else:
                combo_gender.setCurrentIndex(0)
        if d: txt_date.setText(d)
        if w: txt_spouse.setText(w)
        if sn > 0 or dn > 0 or w:
            combo_status.setCurrentIndex(0)
            spin_sons.setValue(sn)
            spin_daug.setValue(dn)
        if g:
            txt_gc.setText(g)
            if gc_edits:
                names_list = [nx.strip() for nx in re.split(r'[,،\n;/]+', g) if nx.strip()]
                for idx_n, n_val in enumerate(names_list):
                    if idx_n < len(gc_edits):
                        gc_edits[idx_n].setText(n_val)

    def refresh_predeceased_widgets(self):
        """Dynamically builds detailed name, gender (male/female), death date, marriage status, spouse, and children fields for each predeceased child."""
        if not hasattr(self, "predeceased_children_layout"):
            return

        while self.predeceased_children_layout.count() > 0:
            item = self.predeceased_children_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.predeceased_inputs = {}
        count = self.spin_predeceased.value()
        if count <= 0:
            return

        detected_names = self.get_detected_hujja_names()

        for i in range(1, count + 1):
            row_card = QFrame()
            row_card.setStyleSheet("QFrame { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; margin-bottom: 4px; }")
            card_lay = QVBoxLayout(row_card)
            card_lay.setContentsMargins(10, 8, 10, 8)
            card_lay.setSpacing(6)

            # --- Header Bar: Gender & Title ---
            hdr_lay = QHBoxLayout()
            hdr_lay.setSpacing(8)

            combo_gender = QComboBox(row_card)
            combo_gender.addItems(["ابن متوفى (ذكر)", "بنت متوفاة (أنثى)"])
            combo_gender.setStyleSheet("QComboBox { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; border-radius: 4px; padding: 2px 6px; font-weight: bold; font-size: 11px; }")

            lbl = QLabel(f"<b>الابن المتوفى {i}:</b>", row_card)
            lbl.setMinimumWidth(110)
            lbl.setStyleSheet("color: #0284c7; font-size: 11px;")

            hdr_lay.addWidget(combo_gender)
            hdr_lay.addWidget(lbl)
            hdr_lay.addStretch()
            card_lay.addLayout(hdr_lay)

            # --- Row 1: Primary Info (Name & Death Date & Search Button) ---
            top_lay = QHBoxLayout()
            top_lay.setSpacing(6)

            lbl_name_t = QLabel("الاسم واللقب:", row_card)
            lbl_name_t.setStyleSheet("color: #334155; font-size: 11px; font-weight: bold;")

            txt_name = QLineEdit(row_card)
            txt_name.setPlaceholderText("اسم الابن المتوفى")
            txt_name.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
            txt_name.textChanged.connect(self.on_calculate_clicked)

            if detected_names:
                comp = QCompleter(detected_names, txt_name)
                comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                comp.setFilterMode(Qt.MatchFlag.MatchContains)
                txt_name.setCompleter(comp)

            lbl_date = QLabel("تاريخ الوفاة:", row_card)
            lbl_date.setStyleSheet("color: #475569; font-size: 11px; font-weight: bold;")

            txt_date = DatePickerLineEdit(row_card, placeholder="مثال: 2018/04/12")
            txt_date.textChanged.connect(self.on_calculate_clicked)

            btn_from_hujja = QPushButton("📋 من حجة الوفاة", row_card)
            btn_from_hujja.setToolTip("اختر اسم وبيانات المتوفى(ة) مباشرة من حجة الوفاة")
            btn_from_hujja.setStyleSheet("QPushButton { background-color: #059669; color: white; border: none; border-radius: 4px; padding: 4px 8px; font-size: 10px; font-weight: bold; } QPushButton:hover { background-color: #047857; }")

            top_lay.addWidget(lbl_name_t)
            top_lay.addWidget(txt_name, 3)
            top_lay.addWidget(btn_from_hujja)
            top_lay.addWidget(lbl_date)
            top_lay.addWidget(txt_date, 2)
            card_lay.addLayout(top_lay)

            # --- Row 2: Marital & Family Status ---
            family_bar = QHBoxLayout()
            family_bar.setSpacing(8)

            lbl_status = QLabel("الحالة العائلية:", row_card)
            lbl_status.setStyleSheet("color: #334155; font-size: 11px; font-weight: bold;")

            combo_status = QComboBox(row_card)
            combo_status.addItems(["متزوج(ة) / ترك أفراد عائلة (أولاد/زوجة)", "أعزب(ة) / غير متزوج(ة)"])
            combo_status.setStyleSheet("QComboBox { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; font-size: 11px; }")
            combo_status.currentIndexChanged.connect(self.on_calculate_clicked)

            family_bar.addWidget(lbl_status)
            family_bar.addWidget(combo_status, 2)
            family_bar.addStretch()
            card_lay.addLayout(family_bar)

            # --- Row 3: Sub-panel for Married details (Spouse, Male/Female Children, Names) ---
            sub_panel = QFrame(row_card)
            sub_panel.setStyleSheet("QFrame { background: #ffffff; border: 1px dashed #94a3b8; border-radius: 6px; padding: 4px; }")
            sub_lay = QVBoxLayout(sub_panel)
            sub_lay.setContentsMargins(6, 6, 6, 6)
            sub_lay.setSpacing(6)

            # Spouse & Children counts row
            sp_lay = QHBoxLayout()
            sp_lbl = QLabel("اسم الزوجة (الأرملة):", sub_panel)
            sp_lbl.setStyleSheet("color: #475569; font-size: 11px;")
            txt_spouse = QLineEdit(sub_panel)
            txt_spouse.setPlaceholderText("اسم زوجة الابن المتوفى (إن وجد)")
            txt_spouse.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; font-size: 11px;")
            txt_spouse.textChanged.connect(self.on_calculate_clicked)
            sp_lay.addWidget(sp_lbl)
            sp_lay.addWidget(txt_spouse, 3)

            lbl_sons = QLabel("عدد الأبناء (ذكور):", sub_panel)
            lbl_sons.setStyleSheet("color: #1e3a8a; font-size: 11px; font-weight: bold;")
            spin_sons = NoWheelSpinBox(sub_panel)
            spin_sons.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin_sons.setRange(0, 10)
            spin_sons.setValue(0)
            spin_sons.valueChanged.connect(self.on_calculate_clicked)

            lbl_daug = QLabel("عدد البنات (إناث):", sub_panel)
            lbl_daug.setStyleSheet("color: #831843; font-size: 11px; font-weight: bold;")
            spin_daug = NoWheelSpinBox(sub_panel)
            spin_daug.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin_daug.setRange(0, 10)
            spin_daug.setValue(0)
            spin_daug.valueChanged.connect(self.on_calculate_clicked)

            sp_lay.addWidget(lbl_sons)
            sp_lay.addWidget(spin_sons)
            sp_lay.addWidget(lbl_daug)
            sp_lay.addWidget(spin_daug)
            sub_lay.addLayout(sp_lay)

            # Grandchildren Names dynamic per-child container
            gc_box_frame = QFrame(sub_panel)
            gc_box_frame.setStyleSheet("QFrame { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px; }")
            gc_box_lay = QVBoxLayout(gc_box_frame)
            gc_box_lay.setContentsMargins(4, 4, 4, 4)
            gc_box_lay.setSpacing(4)

            gc_name_edits = []

            def _update_gc_inputs(frame=gc_box_frame, lay=gc_box_lay, edits=gc_name_edits, s_sp=spin_sons, d_sp=spin_daug, cg=combo_gender):
                while lay.count() > 0:
                    it = lay.takeAt(0)
                    w_it = it.widget()
                    if w_it is not None:
                        w_it.deleteLater()

                edits.clear()
                s_cnt = s_sp.value()
                d_cnt = d_sp.value()
                is_female_parent = (cg.currentIndex() == 1)

                if s_cnt <= 0 and d_cnt <= 0:
                    lbl_empty = QLabel("حدد عدد ذكور أو إناث الأحفاد لإظهار خانة اسم كل حفيد(ة) بصفة مستقلة", frame)
                    lbl_empty.setStyleSheet("color: #64748b; font-size: 10px; font-style: italic;")
                    lay.addWidget(lbl_empty)
                    return

                # Male grandchildren
                for si in range(1, s_cnt + 1):
                    r_lay = QHBoxLayout()
                    r_lay.setSpacing(4)
                    m_title = f"اسم ابن الابن {si}:" if not is_female_parent else f"اسم ابن البنت {si}:"
                    lbl_m = QLabel(m_title, frame)
                    lbl_m.setStyleSheet("color: #1e40af; font-weight: bold; font-size: 11px;")
                    txt_m = QLineEdit(frame)
                    txt_m.setPlaceholderText(f"الاسم الكامل للحفيد الذكر {si}")
                    txt_m.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; font-size: 11px;")
                    txt_m.textChanged.connect(self.on_calculate_clicked)
                    r_lay.addWidget(lbl_m)
                    r_lay.addWidget(txt_m, 1)
                    lay.addLayout(r_lay)
                    edits.append(txt_m)

                # Female grandchildren
                for di in range(1, d_cnt + 1):
                    r_lay = QHBoxLayout()
                    r_lay.setSpacing(4)
                    f_title = f"اسم بنت الابن {di}:" if not is_female_parent else f"اسم بنت البنت {di}:"
                    lbl_f = QLabel(f_title, frame)
                    lbl_f.setStyleSheet("color: #831843; font-weight: bold; font-size: 11px;")
                    txt_f = QLineEdit(frame)
                    txt_f.setPlaceholderText(f"الاسم الكامل للحفيدة الأنثى {di}")
                    txt_f.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; font-size: 11px;")
                    txt_f.textChanged.connect(self.on_calculate_clicked)
                    r_lay.addWidget(lbl_f)
                    r_lay.addWidget(txt_f, 1)
                    lay.addLayout(r_lay)
                    edits.append(txt_f)

            spin_sons.valueChanged.connect(lambda _: _update_gc_inputs())
            spin_daug.valueChanged.connect(lambda _: _update_gc_inputs())
            combo_gender.currentIndexChanged.connect(lambda _: _update_gc_inputs())
            _update_gc_inputs()

            # Hidden single QLineEdit fallback for compatibility
            txt_gc = QLineEdit(sub_panel)
            txt_gc.setVisible(False)

            sub_lay.addWidget(gc_box_frame)

            card_lay.addWidget(sub_panel)

            # Helper function to update gender UI elements
            def _on_gender_changed(g_idx, l=lbl, t=txt_name, sl=sp_lbl, tp=txt_spouse, idx_num=i):
                if g_idx == 0:
                    l.setText(f"<b>الابن المتوفى {idx_num}:</b>")
                    t.setPlaceholderText("اسم الابن المتوفى")
                    sl.setText("اسم الزوجة (الأرملة):")
                    tp.setPlaceholderText("اسم زوجة الابن المتوفى (إن وجد)")
                else:
                    l.setText(f"<b>البنت المتوفاة {idx_num}:</b>")
                    t.setPlaceholderText("اسم البنت المتوفاة")
                    sl.setText("اسم الزوج (الأرمل):")
                    tp.setPlaceholderText("اسم زوج البنت المتوفاة (إن وجد)")
                self.on_calculate_clicked()

            combo_gender.currentIndexChanged.connect(_on_gender_changed)
            combo_status.currentIndexChanged.connect(lambda idx, p=sub_panel: p.setVisible(idx == 0))

            btn_from_hujja.clicked.connect(
                lambda _, n=txt_name, d=txt_date, s=txt_spouse, sn=spin_sons, dn=spin_daug, g=txt_gc, g_edits=gc_name_edits, cs=combo_status, cg=combo_gender:
                    self._pick_predeceased_from_hujja_full(n, d, s, sn, dn, g, g_edits, cs, cg)
            )

            # Auto-prefill if linked_hujaj entries exist at index i - 1
            if hasattr(self, "linked_hujaj") and self.linked_hujaj and (i - 1) < len(self.linked_hujaj):
                lh = self.linked_hujaj[i - 1]
                dec_n = lh.get("deceased_name", "")
                if dec_n:
                    txt_name.setText(dec_n)
                    if is_female_name(dec_n):
                        combo_gender.setCurrentIndex(1)
                    else:
                        combo_gender.setCurrentIndex(0)

                w_name = (lh.get("wife_name") or lh.get("husband_name") or "").strip()
                if not w_name:
                    if lh.get("wife") or lh.get("wife_alive"):
                        w_name = "زوجته"
                    elif lh.get("husband") or lh.get("husband_alive"):
                        w_name = "زوجها"

                if w_name:
                    txt_spouse.setText(w_name)

                s_num = lh.get("sons_count", 0)
                d_num = lh.get("daughters_count", 0)
                if s_num > 0 or d_num > 0 or w_name or lh.get("wife") or lh.get("husband"):
                    combo_status.setCurrentIndex(0)
                    spin_sons.setValue(s_num)
                    spin_daug.setValue(d_num)
                gc_n = "، ".join(lh.get("names", []))
                if gc_n:
                    txt_gc.setText(gc_n)
                    names_list = [nx.strip() for nx in re.split(r'[,،\n;/]+', gc_n) if nx.strip()]
                    for idx_n, n_val in enumerate(names_list):
                        if idx_n < len(gc_name_edits):
                            gc_name_edits[idx_n].setText(n_val)

            self.predeceased_children_layout.addWidget(row_card)
            self.predeceased_inputs[i] = {
                "name": txt_name,
                "date": txt_date,
                "combo_gender": combo_gender,
                "combo_status": combo_status,
                "spouse_name": txt_spouse,
                "sons_spin": spin_sons,
                "daug_spin": spin_daug,
                "grandchildren_names": txt_gc,
                "gc_name_edits": gc_name_edits,
                "sub_panel": sub_panel
            }

    def _search_heir_from_archive(self, txt_name_target, txt_cin_target, label_title):
        dlg = ClientSearchDialog(self, title=f"اختيار الحريف لتأكيد بيانات {label_title}")
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_client:
            c = dlg.selected_client
            fn = c.get("full_name") or f"{c.get('nom', '')} {c.get('prenom', '')}".strip()
            cin = c.get("cin_number", "")
            if fn: txt_name_target.setText(fn)
            if cin: txt_cin_target.setText(str(cin))

    def open_applicant_search_dialog(self):
        """Opens live search popup to pick applicant client from archive by Name, CIN, Job, or Address."""
        dlg = ClientSearchDialog(self, title="اختيار طالب(ة) الإشهاد من أرشيف المكتب")
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_client:
            c = dlg.selected_client
            fn = c.get("full_name") or f"{c.get('nom', '')} {c.get('prenom', '')}".strip()
            cin = c.get("cin_number", "")
            if fn: self.txt_applicant_name.setText(fn)
            if cin: self.txt_applicant_cin.setText(str(cin))
            self.client_info_lbl.setText(f"تم تحميل معطيات طالب الإشهاد: {fn} (ب.ت: {cin})")
            self.client_info_lbl.setVisible(True)

    def open_deceased_search_dialog(self):
        """Opens live search popup to pick deceased person from archive by Name or CIN."""
        dlg = ClientSearchDialog(self, title="اختيار الهالك(ة) من أرشيف المكتب")
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_client:
            c = dlg.selected_client
            fn = c.get("full_name") or f"{c.get('nom', '')} {c.get('prenom', '')}".strip()
            if fn: self.txt_deceased_name.setText(fn)

    def _setup_client_autocompleters(self):
        """Attaches smart live QCompleter auto-suggestions to applicant and deceased inputs."""
        try:
            clients = reception.get_all_clients()
        except Exception:
            clients = []

        if not clients:
            return

        name_list = []
        cin_list = []
        for c in clients:
            cin = str(c.get("cin_number", "")).strip()
            fn = str(c.get("full_name") or f"{c.get('nom', '')} {c.get('prenom', '')}").strip()
            if fn: name_list.append(fn)
            if cin: cin_list.append(cin)
            if fn and cin:
                name_list.append(f"{fn} — {cin}")
                cin_list.append(f"{cin} — {fn}")

        comp_name = QCompleter(list(set(name_list)), self)
        comp_name.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp_name.setFilterMode(Qt.MatchFlag.MatchContains)
        self.txt_applicant_name.setCompleter(comp_name)
        self.txt_deceased_name.setCompleter(comp_name)

        comp_cin = QCompleter(list(set(cin_list)), self)
        comp_cin.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp_cin.setFilterMode(Qt.MatchFlag.MatchContains)
        self.txt_applicant_cin.setCompleter(comp_cin)

    def load_client_profile(self, client_id: str):
        """Auto-fills deceased client info from client profile."""
        try:
            client_info = reception.get_client_by_id(client_id)
            if client_info:
                full_name = client_info.get("name") or f"{client_info.get('nom', '')} {client_info.get('prenom', '')}".strip()
                cin = client_info.get("cin_number", "")
                self.txt_applicant_name.setText(full_name)
                if cin: self.txt_applicant_cin.setText(str(cin))
                self.client_info_lbl.setText(f"تم تحميل معطيات طالب الإشهاد: {full_name} (ب.ت: {cin})")
                self.client_info_lbl.setVisible(True)
        except Exception:
            pass

    def on_calculate_clicked(self):
        heirs_input = {
            'husband': self.cb_husband.isChecked(),
            'wife': self.cb_wife.isChecked(),
            'wives_count': self.spin_wives.value(),
            'sons_count': self.spin_sons.value(),
            'daughters_count': self.spin_daug.value(),
            'grandsons_count': self.spin_grandsons.value(),
            'granddaughters_count': self.spin_granddaughters.value(),
            'father': self.cb_father.isChecked(),
            'mother': self.cb_mother.isChecked(),
            'paternal_grandfather': self.cb_paternal_grandfather.isChecked(),
            'maternal_grandmother': self.cb_maternal_grandmother.isChecked(),
            'paternal_grandmother': self.cb_paternal_grandmother.isChecked(),
            'full_brothers_count': self.spin_bro.value(),
            'full_sisters_count': self.spin_sis.value(),
            'pat_brothers_count': self.spin_pat_bro.value(),
            'pat_sisters_count': self.spin_pat_sis.value(),
            'mat_siblings_count': self.spin_mat_bro.value() + self.spin_mat_sis.value(),
            'nephew_full_count': self.spin_nephew_full.value(),
            'nephew_pat_count': self.spin_nephew_pat.value(),
            'uncle_full': self.cb_uncle_full.isChecked(),
            'uncle_pat': self.cb_uncle_pat.isChecked(),
            'cousin_full_count': self.spin_cousin_full.value(),
            'cousin_pat_count': self.spin_cousin_pat.value(),
            'predeceased_children_count': self.spin_predeceased.value()
        }

        heir_details = {}
        for k, data in getattr(self, "heir_inputs", {}).items():
            name_val = data["name"].text().strip() if (data.get("name") and hasattr(data["name"], "text")) else ""
            cin_val = data["cin"].text().strip() if (data.get("cin") and hasattr(data["cin"], "text")) else ""
            cs_widget = data.get("civil_status")
            cs_val = cs_widget.text().strip() if (cs_widget and hasattr(cs_widget, "text")) else ""
            cb_ren = data.get("renounce_cb")
            is_ren = cb_ren.isChecked() if cb_ren else False
            cb_tgt = data.get("renounce_target")
            ren_tgt = cb_tgt.currentData() if (cb_tgt and is_ren) else "all"

            if name_val or cin_val or cs_val or is_ren:
                heir_details[k] = {
                    "name": name_val,
                    "cin": cin_val,
                    "civil_status": cs_val,
                    "label": data.get("label", ""),
                    "is_renounced": is_ren,
                    "renounce_target": ren_tgt
                }

        predeceased_list = []
        predeceased_details_list = []
        for idx, pdata in getattr(self, "predeceased_inputs", {}).items():
            name_val = pdata["name"].text().strip()
            date_val = pdata["date"].text().strip()
            combo_g = pdata.get("combo_gender")
            is_female = (combo_g.currentIndex() == 1) if combo_g else False

            combo_st = pdata.get("combo_status")
            is_married = (combo_st.currentIndex() == 0) if combo_st else True

            sp_val = pdata.get("spouse_name", QLineEdit()).text().strip()
            s_spin = pdata.get("sons_spin")
            d_spin = pdata.get("daug_spin")
            gc_txt = pdata.get("grandchildren_names", QLineEdit()).text().strip()

            s_cnt = s_spin.value() if s_spin else 0
            d_cnt = d_spin.value() if d_spin else 0

            gc_edits = pdata.get("gc_name_edits", [])
            raw_gc_names = [e.text().strip() for e in gc_edits if e.text().strip()]
            if not raw_gc_names and gc_txt:
                parts = re.split(r'[,،\n;/]+', gc_txt)
                raw_gc_names = [p.strip() for p in parts if p.strip()]

            predeceased_list.append({
                "index": idx,
                "parent_name": name_val if name_val else f"رقم {idx}",
                "parent_gender": "female" if is_female else "male",
                "death_date": date_val,
                "is_married": is_married,
                "spouse_name": sp_val,
                "sons_count": s_cnt,
                "daughters_count": d_cnt,
                "grandchildren_names": raw_gc_names
            })

            child_title = "البنت المتوفاة" if is_female else "الابن المتوفى"
            verb_died = "توفيت" if is_female else "توفي"
            rel_died = "التي توفيت" if is_female else "الذي توفي"

            if name_val or date_val or is_married:
                p_name = f"{name_val}" if name_val else f"رقم {idx}"
                date_clean = date_val.replace("-", "/").strip() if date_val else ""
                if is_married:
                    verb_left = "تركت" if is_female else "ترك"
                    item_str = f"{child_title} سابقاً {p_name}"
                    if date_clean:
                        item_str += f" {verb_died} بتاريخ {date_clean}"
                    sp_title = "الزوج" if is_female else "الزوجة"
                    m_parts = []
                    if sp_val:
                        m_parts.append(f"من {sp_title} {sp_val}")
                    if raw_gc_names:
                        m_parts.append(f"من الأبناء {' و'.join(raw_gc_names)}")
                    elif (s_cnt > 0 or d_cnt > 0):
                        ch_info = []
                        if s_cnt > 0: ch_info.append(f"{s_cnt} ذكور")
                        if d_cnt > 0: ch_info.append(f"{d_cnt} إناث")
                        m_parts.append(f"من الأبناء {' و'.join(ch_info)}")
                    if m_parts:
                        item_str += f" و{verb_left} " + " و".join(m_parts)
                else:
                    unmarried_label = "غير المتزوجة" if is_female else "غير المتزوج"
                    item_str = f"{child_title} سابقاً {unmarried_label} {p_name}"
                    if date_clean:
                        item_str += f" {verb_died} بتاريخ {date_clean}"
                predeceased_details_list.append(item_str)
        predeceased_str = "؛ ".join(predeceased_details_list)
        heirs_input['predeceased_list'] = predeceased_list

        res = self.engine.calculate_farida(
            heirs_dict=heirs_input,
            contract_type=self.combo_contract_type.currentText(),
            applicant_name=self.txt_applicant_name.text().strip(),
            applicant_cin=self.txt_applicant_cin.text().strip(),
            deceased_name=self.txt_deceased_name.text().strip(),
            hujja_num=self.txt_hujja_num.text().strip(),
            hujja_date=self.txt_hujja_date.text().strip(),
            hujja_court=self.txt_hujja_court.text().strip(),
            title_num=self.txt_title_num.text().strip(),
            property_name=self.txt_property_name.text().strip(),
            location=self.txt_location.text().strip(),
            property_area_m2=self.spin_m2.value(),
            property_parts=self.spin_parts.value(),
            property_type=getattr(self, "combo_property_type", None).currentText() if hasattr(self, "combo_property_type") else "",
            predeceased_death_date=predeceased_str,
            heir_details=heir_details
        )
        self.last_result = res

        origin_str = f"أصل الفريضة التوثيقية: ({res['base_origin']}) جزءاً"
        if res.get('is_awl'):
            origin_str += " [مسألة فيها عول]"
        elif res.get('is_radd'):
            origin_str += " [مسألة فيها رد على البنات]"
        self.origin_lbl.setText(origin_str)

        summary = res.get("heirs_summary", [])
        has_individual_gc = any(h.get("is_individual_grandchild") for h in summary)

        expanded_table_rows = []
        for h in summary:
            if has_individual_gc and h.get("is_waseya_summary"):
                continue  # Hide aggregate summary row when individual grandchild rows exist

            cnt = h.get("count", 1)
            single_shares = h.get("single_shares", h["shares"])
            single_perc = h.get("single_percentage", h["percentage"])
            single_area = h.get("single_area_m2", 0.0)
            single_parts = h.get("single_parts", 0.0)
            fraction = h.get("fraction", "")

            # If individual grandchild row
            if h.get("is_individual_grandchild"):
                g_name = h.get("clean_name", "")
                p_name = h.get("parent_name", "")
                male_or_female = "ابن ابن" if ("ابن" in h["heir"].split("(")[0] and "بنت" not in h["heir"].split("(")[0]) else "بنت ابن"
                if p_name:
                    rel_str = f"{male_or_female} (وصية واجبة - فرع {p_name})"
                else:
                    rel_str = f"{male_or_female} (وصية واجبة)"

                expanded_table_rows.append({
                    "name": g_name if g_name else h["heir"],
                    "relation": rel_str,
                    "shares": h.get("shares", "—"),
                    "fraction": fraction,
                    "percentage": h.get("percentage", single_perc),
                    "area_m2": h.get("area_m2", single_area),
                    "parts": h.get("parts", single_parts)
                })
                continue

            prefix = None
            is_waseya = "وصية واجبة" in h["heir"]  # skip bequest row from prefix matching
            if not is_waseya:
                if "الأبناء" in h["heir"] or ("ابن" in h["heir"] and "ابن الابن" not in h["heir"] and "بنت" not in h["heir"]):
                    prefix = "son_"
                elif "البنات" in h["heir"] or ("بنت" in h["heir"] and "بنت الابن" not in h["heir"]):
                    prefix = "daughter_"
                elif "الزوجات" in h["heir"] or "الزوجة" in h["heir"]:
                    prefix = "wife_"
                elif "أبناء الابن" in h["heir"] or "ابن الابن" in h["heir"]:
                    prefix = "grandson_"
                elif "بنات الابن" in h["heir"] or "بنت الابن" in h["heir"]:
                    prefix = "granddaughter_"
                elif "الإخوة الأشقاء" in h["heir"] or "أخ شقيق" in h["heir"]:
                    prefix = "full_brother_"
                elif "الأخوات الشقيقات" in h["heir"] or "أخت شقيقة" in h["heir"]:
                    prefix = "full_sister_"
                elif "الإخوة لأم" in h["heir"] or ("أخ لأم" in h["heir"] and "أخت" not in h["heir"]):
                    prefix = "mat_brother_"
                elif "الأخوات لأم" in h["heir"] or "أخت لأم" in h["heir"]:
                    prefix = "mat_sister_"

            if prefix and cnt >= 1:
                for sub_i in range(1, cnt + 1):
                    hk = f"{prefix}{sub_i}"
                    hd = (heir_details or {}).get(hk, {})
                    h_name = hd.get("name", "").strip()
                    h_cin = hd.get("cin", "").strip()

                    label_prefix = (
                        "ابن" if prefix == "son_" else
                        "بنت" if prefix == "daughter_" else
                        "الزوجة" if prefix == "wife_" else
                        "ابن ابن" if prefix == "grandson_" else
                        "بنت ابن" if prefix == "granddaughter_" else
                        "أخ شقيق" if prefix == "full_brother_" else
                        "أخت شقيقة" if prefix == "full_sister_" else
                        "أخ لأم" if prefix == "mat_brother_" else
                        "أخت لأم" if prefix == "mat_sister_" else
                        "وارث"
                    )
                    name_disp = h_name if h_name else f"{label_prefix} {sub_i}"
                    if h_cin:
                        name_disp += f" (ب.ت: {h_cin})"

                    is_ren = hd.get("is_renounced", False)
                    ren_tgt = hd.get("renounce_target", "all")
                    expanded_table_rows.append({
                        "hk": hk,
                        "name": name_disp,
                        "relation": label_prefix,
                        "shares": single_shares,
                        "fraction": fraction,
                        "percentage": single_perc,
                        "area_m2": single_area,
                        "parts": single_parts,
                        "is_renounced": is_ren,
                        "renounce_target": ren_tgt
                    })
            else:
                s_key = None
                if "الزوج" in h["heir"] and "الزوجة" not in h["heir"]: s_key = "husband"
                elif "الأب" in h["heir"] and "الأبناء" not in h["heir"]: s_key = "father"
                elif "الأم" in h["heir"]: s_key = "mother"
                elif "الجد لأب" in h["heir"]: s_key = "paternal_grandfather"
                elif "الجدة لأم" in h["heir"]: s_key = "maternal_grandmother"
                elif "الجدة لأب" in h["heir"]: s_key = "paternal_grandmother"

                hd = (heir_details or {}).get(s_key, {}) if s_key else {}
                h_name = hd.get("name", "").strip()
                h_cin = hd.get("cin", "").strip()
                is_ren = hd.get("is_renounced", False)
                ren_tgt = hd.get("renounce_target", "all")

                name_disp = h_name if h_name else h["heir"]
                if h_cin:
                    name_disp += f" (ب.ت: {h_cin})"

                rel_disp = (
                    "الزوج" if "الزوج" in h["heir"] and "الزوجة" not in h["heir"] else
                    "الأب" if "الأب" in h["heir"] and "الأبناء" not in h["heir"] else
                    "الأم" if "الأم" in h["heir"] else
                    "الجد لأب" if "الجد لأب" in h["heir"] else
                    "الجدة لأم" if "الجدة لأم" in h["heir"] else
                    "الجدة لأب" if "الجدة لأب" in h["heir"] else
                    h["heir"]
                )

                expanded_table_rows.append({
                    "hk": s_key or h["heir"],
                    "name": name_disp,
                    "relation": rel_disp,
                    "shares": h.get("shares", single_shares),
                    "fraction": fraction,
                    "percentage": h.get("percentage", single_perc),
                    "area_m2": h.get("area_m2", single_area),
                    "parts": h.get("parts", single_parts),
                    "is_renounced": is_ren,
                    "renounce_target": ren_tgt
                })

        def _safe_num_share(val):
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0.0

        # Apply Tanezel renunciation adjustments
        renouncing_rows = [r for r in expanded_table_rows if r.get("is_renounced")]
        if renouncing_rows:
            for r_ren in renouncing_rows:
                orig_shares = _safe_num_share(r_ren["shares"])
                r_ren["shares"] = 0
                r_ren["percentage"] = 0.0
                r_ren["area_m2"] = 0.0
                r_ren["parts"] = 0.0
                if "(متنازل" not in r_ren["relation"]:
                    r_ren["relation"] += " (متنازل عن منابه الشرعي)"

                target_key = r_ren.get("renounce_target", "all")
                if target_key == "all":
                    active_ben_rows = [r for r in expanded_table_rows if not r.get("is_renounced") and not r.get("is_individual_grandchild")]
                    total_ben_shares = sum(_safe_num_share(r["shares"]) for r in active_ben_rows)
                    if total_ben_shares > 0:
                        for r_ben in active_ben_rows:
                            ben_sh = _safe_num_share(r_ben["shares"])
                            added_sh = orig_shares * (ben_sh / total_ben_shares)
                            new_sh = round(ben_sh + added_sh, 2)
                            if float(new_sh).is_integer(): new_sh = int(new_sh)
                            r_ben["shares"] = new_sh
                            ratio = float(new_sh) / float(res["base_origin"])
                            r_ben["percentage"] = round(ratio * (66.67 if has_individual_gc else 100.0), 2)
                            r_ben["area_m2"] = round(ratio * (self.spin_m2.value() * (2.0/3.0 if has_individual_gc else 1.0)), 2)
                            r_ben["parts"] = round(ratio * (self.spin_parts.value() * (2.0/3.0 if has_individual_gc else 1.0)), 2)
                            if "(مع مناب التنازل)" not in r_ben["relation"]:
                                r_ben["relation"] += " (مع مناب التنازل)"
                else:
                    target_rows = [r for r in expanded_table_rows if r.get("hk") == target_key]
                    if target_rows:
                        t_row = target_rows[0]
                        ben_sh = _safe_num_share(t_row["shares"])
                        new_sh = round(ben_sh + orig_shares, 2)
                        if float(new_sh).is_integer(): new_sh = int(new_sh)
                        t_row["shares"] = new_sh
                        ratio = float(new_sh) / float(res["base_origin"])
                        t_row["percentage"] = round(ratio * (66.67 if has_individual_gc else 100.0), 2)
                        t_row["area_m2"] = round(ratio * (self.spin_m2.value() * (2.0/3.0 if has_individual_gc else 1.0)), 2)
                        t_row["parts"] = round(ratio * (self.spin_parts.value() * (2.0/3.0 if has_individual_gc else 1.0)), 2)
                        ren_name = r_ren.get("name", "")
                        if f"(مع مناب تنازل {ren_name})" not in t_row["relation"]:
                            t_row["relation"] += f" (مع مناب تنازل {ren_name})"

        # Apply remainder adjustment for UI table display (Area & Parts)
        if self.spin_m2.value() > 0 and expanded_table_rows:
            sum_ui_area = round(sum(r["area_m2"] for r in expanded_table_rows), 2)
            diff_ui_area = round(self.spin_m2.value() - sum_ui_area, 2)
            if diff_ui_area != 0:
                max_r = max(expanded_table_rows, key=lambda x: (_safe_num_share(x["shares"]), "الابن" in x["name"] or "الزوج" in x["name"]))
                max_r["area_m2"] = round(max_r["area_m2"] + diff_ui_area, 2)

        if self.spin_parts.value() > 0 and expanded_table_rows:
            sum_ui_parts = round(sum(r["parts"] for r in expanded_table_rows), 2)
            diff_ui_parts = round(self.spin_parts.value() - sum_ui_parts, 2)
            if diff_ui_parts != 0:
                max_r = max(expanded_table_rows, key=lambda x: (_safe_num_share(x["shares"]), "الابن" in x["name"] or "الزوج" in x["name"]))
                max_r["parts"] = round(max_r["parts"] + diff_ui_parts, 2)

        self.table.setRowCount(len(expanded_table_rows))
        for row, r_item in enumerate(expanded_table_rows):
            item_heir = QTableWidgetItem(r_item["name"])
            item_heir.setFont(QFont("Tajawal", 10, QFont.Weight.Bold))
            self.table.setItem(row, 0, item_heir)
            self.table.setItem(row, 1, QTableWidgetItem(r_item.get("relation", "")))
            self.table.setItem(row, 2, QTableWidgetItem(str(r_item["shares"])))
            self.table.setItem(row, 3, QTableWidgetItem(str(r_item["fraction"])))
            self.table.setItem(row, 4, QTableWidgetItem(f"% {r_item['percentage']}"))

            prop_str = ""
            if r_item.get("area_m2", 0) > 0:
                prop_str += f"{r_item['area_m2']} م²"
            if r_item.get("parts", 0) > 0:
                prop_str += f" | {r_item['parts']} جزء"
            self.table.setItem(row, 5, QTableWidgetItem(prop_str if prop_str else "—"))

        final_text = res.get("legal_notarial_text", "")
        extra_notes = getattr(self, "txt_extra_notes", None)
        if extra_notes and extra_notes.toPlainText().strip():
            final_text += f"\n\nالمصاحبات والوثائق التكميلية المرفقة:\n{extra_notes.toPlainText().strip()}"

        self.text_output.setText(final_text)

    def on_generate_partition_clicked(self):
        """Auto-generates Amicable Partition Contract (عقد مقاسمة رضائية)."""
        if not self.last_result:
            return
        self.generate_partition_requested.emit(self.last_result)
        self.accept()

    def on_print_clicked(self):
        """1-Click Direct Printing of Farida document with official office header."""
        if not self.last_result:
            return

        doc = QTextDocument()
        html = f"""
        <div style="font-family: 'Segoe UI', Arial; direction: rtl; text-align: right; padding: 20px;">
            <h2 style="text-align: center; color: #0f172a; margin-bottom: 5px;">الجمهورية التونسية<br>مكتب عدل الإشهاد<br>إشهاد بالفريضة الشرعية</h2>
            <hr style="border: 1px solid #cbd5e1; margin-bottom: 20px;">
            
            <p><b>أصل الفريضة التوثيقية: ({self.last_result.get('base_origin')}) جزءاً</b></p>
            
            <table border="1" cellspacing="0" cellpadding="6" style="width: 100%; border-collapse: collapse; text-align: center; margin-bottom: 20px;">
                <tr style="background-color: #0f172a; color: white;">
                    <th>اسم الوارث / المستحق</th><th>القرابة / الصفة الشرعية</th><th>الأجزاء</th><th>المخرج / الفرض</th><th>النسبة المئوية</th><th>مناب العقار والأجزاء</th>
                </tr>
        """

        for r_idx in range(self.table.rowCount()):
            c0 = self.table.item(r_idx, 0).text() if self.table.item(r_idx, 0) else ""
            c1 = self.table.item(r_idx, 1).text() if self.table.item(r_idx, 1) else ""
            c2 = self.table.item(r_idx, 2).text() if self.table.item(r_idx, 2) else ""
            c3 = self.table.item(r_idx, 3).text() if self.table.item(r_idx, 3) else ""
            c4 = self.table.item(r_idx, 4).text() if self.table.item(r_idx, 4) else ""
            c5 = self.table.item(r_idx, 5).text() if self.table.item(r_idx, 5) else ""

            html += f"""
            <tr>
                <td><b>{c0}</b></td>
                <td>{c1}</td>
                <td>{c2}</td>
                <td>{c3}</td>
                <td>{c4}</td>
                <td>{c5}</td>
            </tr>
            """

        html += f"""
            </table>
            
            <p><b>النص التوثيقي الرسمي:</b><br>{self.text_output.toPlainText()}</p>
            
            <br><br>
            <table style="width: 100%;">
                <tr>
                    <td style="text-align: right;"><b>طالب الإشهاد</b></td>
                    <td style="text-align: left;"><b>عدلا الإشهاد</b></td>
                </tr>
            </table>
        </div>
        """
        doc.setHtml(html)

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() == QPrintDialog.DialogCode.Accepted:
            doc.print_(printer)

    def on_insert_into_editor_clicked(self):
        """Emits farida_inserted signal with the generated Farida result to switch directly to the Scanner & IA contract editor."""
        if not hasattr(self, 'last_result') or not self.last_result:
            self.on_calculate_clicked()
        if hasattr(self, 'last_result') and self.last_result:
            self.farida_inserted.emit(self.last_result)
            QMessageBox.information(
                self, "تم الإدراج بنجاح",
                "✅ تم إدراج نص الفريضة الشرعية التوثيقي كاملاً في صفحة محرر العقود والتحرير الآلي!"
            )
            self.accept()

    def on_export_word_clicked(self):
        if not self.last_result:
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "حفظ وثيقة الفريضة بملف Word", "حجة_وفاة_وفريضة_شرعية.docx", "Word Files (*.docx)")
        if file_path:
            try:
                self.engine.export_farida_docx(self.last_result, file_path)
                QMessageBox.information(self, "نجاح التصدير", f"تم تصدير وثيقة الفريضة الشرعية بنجاح في:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذّر تصدير ملف Word:\n{e}")

    def import_hujjat_wafat_file(self):
        """Opens popup dialog to select Page 1 and optional Page 2, extracts heirs, and updates form spinboxes automatically."""
        dlg = HujjaUploadPopupDialog(self, title="استيراد وتفريغ حجة وفاة الهالك الرئيسي")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        file_paths = dlg.get_selected_paths()
        if not file_paths:
            return

        progress = QProgressDialog("🤖 جاري قراءة وتفريغ الصفحات المرفقة بواسطة الذكاء الاصطناعي...\nالمرجو الانتظار لحظات لإنهاء المعالجة.", None, 0, 0, self)
        progress.setWindowTitle("معالجة حجة الوفاة بالذكاء الاصطناعي (AI Reading...)")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()

        extracted_texts = []
        parsed_data = None
        try:
            from pathlib import Path
            image_bytes_list = []
            for fp in file_paths:
                p = Path(fp)
                if p.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                    image_bytes_list.append(p.read_bytes())
                elif p.suffix.lower() == ".txt":
                    txt = p.read_text(encoding="utf-8", errors="ignore")
                    if txt.strip(): extracted_texts.append(txt.strip())
                elif p.suffix.lower() == ".pdf":
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(fp)
                        txt = "\n".join([page.extract_text() or "" for page in reader.pages])
                        if txt.strip():
                            extracted_texts.append(txt.strip())
                        # Extract page images for AI Vision OCR if text is short or empty
                        if len(txt.strip()) < 50:
                            for page in reader.pages:
                                for img in page.images:
                                    if img.data and len(img.data) > 1000:
                                        image_bytes_list.append(img.data)
                    except Exception:
                        pass

            if image_bytes_list:
                try:
                    import ocr_engine
                except ImportError:
                    import core.ocr_engine as ocr_engine

                payload = image_bytes_list if len(image_bytes_list) > 1 else image_bytes_list[0]
                res_h = ocr_engine.extract_hojjat_wafat_document_data(payload)
                if res_h.get("success"):
                    if res_h.get("data"):
                        parsed_data = res_h["data"]
                    if res_h.get("transcription"):
                        extracted_texts.append(res_h["transcription"])
                elif res_h.get("error"):
                    progress.close()
                    QMessageBox.warning(self, "تنبيه في قراءة الذكاء الاصطناعي", res_h["error"])
                    return
        except Exception as e:
            progress.close()
            QMessageBox.warning(self, "خطأ في قراءة الملف", f"تعذر قراءة ملف حجة الوفاة: {e}")
            return
        finally:
            progress.close()

        extracted_text = "\n\n".join(extracted_texts).strip()

        if (not parsed_data or not parsed_data.get('deceased_name')) and extracted_text:
            try:
                from farida_engine import parse_hujjat_wafat_text, _extract_deceased_name_smart_fallback
            except ImportError:
                from core.farida_engine import parse_hujjat_wafat_text, _extract_deceased_name_smart_fallback
            if not parsed_data:
                parsed_data = parse_hujjat_wafat_text(extracted_text)
            elif not parsed_data.get('deceased_name'):
                parsed_data['deceased_name'] = _extract_deceased_name_smart_fallback(extracted_text)

        if not parsed_data:
            parsed_data = {
                "deceased_name": "",
                "sons_count": 0,
                "daughters_count": 0,
                "names": [],
                "wife": False,
                "wife_name": "",
                "husband": False,
                "husband_name": "",
                "father": False,
                "mother": False
            }

        parsed = parsed_data
        self.main_parsed = parsed  # store for linking

        if parsed:
            self.cb_husband.setChecked(bool(parsed.get('husband', False) or parsed.get('husband_alive', False)))
            self.cb_wife.setChecked(bool(parsed.get('wife', False) or parsed.get('wife_alive', False)))
            self.cb_father.setChecked(bool(parsed.get('father', False) or parsed.get('father_alive', False)))
            self.cb_mother.setChecked(bool(parsed.get('mother', False) or parsed.get('mother_alive', False)))
            self.spin_sons.setValue(parsed.get('sons_count', 0))
            self.spin_daug.setValue(parsed.get('daughters_count', 0))

            self.refresh_heir_details_widgets()

            # Fill wife_name separately so children names don't end up on the wife row
            wife_name_parsed = (parsed.get('wife_name') or '').strip()
            if wife_name_parsed and 'wife_1' in self.heir_inputs:
                self.heir_inputs['wife_1']['name'].setText(wife_name_parsed)

            extracted_names = parsed.get('names', [])
            sons_names = parsed.get('sons_names', [])
            daughters_names = parsed.get('daughters_names', [])

            if not sons_names and not daughters_names and extracted_names:
                for n in extracted_names:
                    if is_female_name(n):
                        daughters_names.append(n)
                    else:
                        sons_names.append(n)

            # Populate sons into son_X inputs
            s_idx = 0
            for sub_i in range(1, self.spin_sons.value() + 1):
                hk = f"son_{sub_i}"
                if hk in self.heir_inputs and s_idx < len(sons_names):
                    self.heir_inputs[hk]["name"].setText(sons_names[s_idx])
                    s_idx += 1

            # Populate daughters into daughter_X inputs
            d_idx = 0
            for sub_i in range(1, self.spin_daug.value() + 1):
                hk = f"daughter_{sub_i}"
                if hk in self.heir_inputs and d_idx < len(daughters_names):
                    self.heir_inputs[hk]["name"].setText(daughters_names[d_idx])
                    d_idx += 1

            if parsed.get('deceased_name'): self.txt_deceased_name.setText(parsed['deceased_name'])
            if parsed.get('applicant_name'): self.txt_applicant_name.setText(parsed['applicant_name'])
            if parsed.get('hujja_num'): self.txt_hujja_num.setText(parsed['hujja_num'])
            if parsed.get('hujja_date'): self.txt_hujja_date.setText(parsed['hujja_date'])
            if parsed.get('hujja_court'): self.txt_hujja_court.setText(parsed['hujja_court'])

            self.on_calculate_clicked()
            # Enable link button if there are already linked hujjas
            if self.linked_hujaj:
                self.btn_link_hujaj.setEnabled(True)

            heir_names_str = "، ".join(parsed.get('names', [])) or "تم الاستخراج بناءً على الشروط الشرعية"
            msg = (
                f"تم تفريغ حجة الوفاة بنجاح واستخراج كافة المعطيات والأسماء:\n"
                f"اسم الهالك(ة): {parsed.get('deceased_name') or 'غير محدد'}\n"
                f"اسم طالب الإشهاد: {parsed.get('applicant_name') or 'غير محدد'}\n"
                f"حجة الوفاة: عدد {parsed.get('hujja_num') or 'غير محدد'} بتاريخ {parsed.get('hujja_date') or 'غير محدد'} ({parsed.get('hujja_court') or 'غير محدد'})\n"
                f"عدد الذكور (الأبناء): {parsed.get('sons_count', 0)}\n"
                f"عدد الإناث (البنات): {parsed.get('daughters_count', 0)}\n"
                f"أسماء الورثة المستخرجين: {heir_names_str}\n\n"
                f"💡 لمسح حجج الأبناء المتوفين قبله، استخدم زر 'إضافة حجة وفاة ابن/بنت'."
            )
            QMessageBox.information(self, "نجاح الاستيراد التلقائي", msg)

    def scan_applicant_cin_card(self):
        """Scans Applicant CIN Card (بطاقة تعريف طالب الإشهاد) using Vision OCR and auto-fills name & CIN number."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "اختر صورة بطاقة التعريف الوطنية لطالب الإشهاد", "", "صور البطاقة (*.png *.jpg *.jpeg *.bmp)"
        )
        if not file_path:
            return

        progress = QProgressDialog("🤖 جاري مسح بطاقة التعريف الوطنية بواسطة الذكاء الاصطناعي...\nالمرجو الانتظار لحظات لإنهاء المعالجة.", None, 0, 0, self)
        progress.setWindowTitle("مسح بطاقة التعريف (AI Reading CIN...)")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()

        from pathlib import Path
        p = Path(file_path)
        try:
            try:
                import cin_extractor
            except ImportError:
                import core.cin_extractor as cin_extractor
            
            res = cin_extractor.extract_cin_data(p.read_bytes())
            progress.close()

            if res.get("success") and res.get("data"):
                data = res["data"]
                fn = data.get("first_name", "")
                ln = data.get("last_name", "")
                full_name = data.get("full_name") or f"{fn} {ln}".strip()
                cin_num = data.get("cin_number", "").strip()
                if full_name: self.txt_applicant_name.setText(full_name)
                if cin_num: self.txt_applicant_cin.setText(cin_num)
                QMessageBox.information(self, "نجاح مسح بطاقة التعريف", f"تم استخراج البيانات بنجاح:\nالاسم: {full_name}\nرقم بطاقة التعريف: {cin_num}")
            else:
                QMessageBox.warning(self, "تنبيه", res.get("error") or "تعذر استخراج بيانات بطاقة التعريف.")
        except Exception as e:
            progress.close()
            QMessageBox.warning(self, "خطأ", f"تعذر قراءة بطاقة التعريف: {e}")

    def import_title_document_file(self):
        """Allows selecting a Property Title / Real Estate Certificate image or PDF, extracts metadata, and updates form fields automatically."""
        from pathlib import Path
        file_path, _ = QFileDialog.getOpenFileName(
            self, "اختر وثيقة الرسم العقاري أو شهادة الملكية", "", "الملفات وثائق وصور (*.png *.jpg *.jpeg *.pdf *.txt)"
        )
        if not file_path:
            return

        progress = QProgressDialog("🤖 جاري قراءة شهادة الملكية والرسم العقاري بواسطة الذكاء الاصطناعي...\nالمرجو الانتظار لحظات لإنهاء التفريغ والتحليل.", None, 0, 0, self)
        progress.setWindowTitle("قراءة شهادة الملكية بالذكاء الاصطناعي (AI Reading Title Doc...)")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()

        p = Path(file_path)
        extracted_text = ""
        parsed = None
        try:
            if p.suffix.lower() == ".txt":
                extracted_text = p.read_text(encoding="utf-8", errors="ignore")
            elif p.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                try:
                    import ocr_engine
                except ImportError:
                    import core.ocr_engine as ocr_engine
                
                if hasattr(ocr_engine, "extract_title_document_data"):
                    res_title = ocr_engine.extract_title_document_data(p.read_bytes())
                    if res_title.get("success") and res_title.get("data"):
                        parsed = res_title["data"]
                        extracted_text = res_title.get("raw_text", "")
                    else:
                        res = ocr_engine.extract_handwritten_notary_script(p.read_bytes())
                        extracted_text = res.get("full_text") or res.get("property_desc") or ""
                else:
                    res = ocr_engine.extract_handwritten_notary_script(p.read_bytes())
                    if not res.get("success"):
                        progress.close()
                        QMessageBox.warning(self, "خطأ في المعالجة الآلية", res.get("error") or "تعذّر استخراج النص من الصورة المرفقة.")
                        return
                    extracted_text = res.get("full_text") or res.get("property_desc") or ""
            elif p.suffix.lower() == ".pdf":
                try:
                    import pypdf
                    reader = pypdf.PdfReader(file_path)
                    extracted_text = "\n".join([page.extract_text() or "" for page in reader.pages])
                except Exception:
                    extracted_text = ""
        except Exception as e:
            progress.close()
            QMessageBox.warning(self, "خطأ في قراءة الملف", f"تعذر قراءة الوثيقة العقارية: {e}")
            return
        finally:
            progress.close()

        if not extracted_text and not parsed:
            QMessageBox.warning(self, "تنبيه", "لم يتم استخراج نص واضح من الوثيقة العقارية المرفقة.")
            return

        if not parsed:
            try:
                from farida_engine import parse_title_document_text
            except ImportError:
                from core.farida_engine import parse_title_document_text
            parsed = parse_title_document_text(extracted_text)

        if parsed:
            if parsed.get("title_num"): self.txt_title_num.setText(parsed["title_num"])
            if parsed.get("property_name"): self.txt_property_name.setText(parsed["property_name"])
            if parsed.get("location"): self.txt_location.setText(parsed["location"])
            if parsed.get("property_area_m2", 0) > 0: self.spin_m2.setValue(parsed["property_area_m2"])
            if parsed.get("property_parts", 0) > 0: self.spin_parts.setValue(parsed["property_parts"])

            self.on_calculate_clicked()
            t_str = parsed.get('title_num') or 'غير محدد'
            p_str = parsed.get('property_name') or 'غير محدد'
            a_val = parsed.get('property_area_m2', 0)

            QMessageBox.information(
                self, "نجاح الاستيراد التلقائي",
                f"تم تفريغ وثيقة الرسم العقاري بنجاح وتعبئة المعطيات تلقائياً:\n"
                f"• الرسم العقاري: {t_str}\n"
                f"• اسم العقار: {p_str}\n"
                f"• المساحة: {a_val} م²"
            )

    def import_extra_documents_files(self):
        """Allows selecting multiple extra supporting documents (PDFs, Images, Text), extracts additional information using AI, and appends to extra notes."""
        from pathlib import Path
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "اختر وثائق ومستندات تكميلية إضافية (مرفقات، مضامين ولادة، حجج إضافية)", "", "جميع الوثائق والصور (*.png *.jpg *.jpeg *.pdf *.txt)"
        )
        if not file_paths:
            return

        progress = QProgressDialog("🤖 جاري قراءة وتحليل الوثائق التكميلية والمستندات الإضافية بواسطة الذكاء الاصطناعي...\nالمرجو الانتظار لحظات لإنهاء التفريغ والتحليل.", None, 0, len(file_paths), self)
        progress.setWindowTitle("قراءة الوثائق التكميلية بالذكاء الاصطناعي (AI Reading Extra Papers...)")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()

        extracted_blobs = []
        for idx, fp in enumerate(file_paths, 1):
            progress.setValue(idx)
            QApplication.processEvents()

            p = Path(fp)
            try:
                if p.suffix.lower() == ".txt":
                    txt = p.read_text(encoding="utf-8", errors="ignore")
                    if txt.strip(): extracted_blobs.append(f"• {p.name}:\n{txt.strip()}")
                elif p.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                    try:
                        import ocr_engine
                    except ImportError:
                        import core.ocr_engine as ocr_engine
                    res = ocr_engine.extract_handwritten_notary_script(p.read_bytes())
                    txt = res.get("full_text") or res.get("property_desc") or ""
                    if txt.strip(): extracted_blobs.append(f"• {p.name}:\n{txt.strip()}")
                elif p.suffix.lower() == ".pdf":
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(fp)
                        txt = "\n".join([page.extract_text() or "" for page in reader.pages])
                        if txt.strip(): extracted_blobs.append(f"• {p.name}:\n{txt.strip()}")
                    except Exception:
                        pass
            except Exception:
                pass

        progress.close()

        if extracted_blobs:
            combined_notes = "\n\n".join(extracted_blobs)
            curr = self.txt_extra_notes.toPlainText().strip()
            new_val = f"{curr}\n\n{combined_notes}".strip() if curr else combined_notes
            self.txt_extra_notes.setText(new_val)
            self.on_calculate_clicked()
            QMessageBox.information(
                self, "نجاح استيراد الوثائق التكميلية",
                f"تم قراءة وتفريغ ({len(file_paths)}) وثيقة/وثائق إضافية وتحديث نص الإشهاد بنجاح!"
            )
        else:
            QMessageBox.warning(self, "تنبيه", "لم يتم استخراج نصوص إضافية من الوثائق المرفقة.")

    # ─────────────────────────────────────────────────────────────────────────
    # MULTI-HUJJA LINKING  (أبناء متوفون في حياة الهالك)
    # ─────────────────────────────────────────────────────────────────────────

    def add_linked_hujja(self):
        """Scans an additional Hujjat Wafat for a child using dedicated 2-slot popup dialog."""
        dlg = HujjaUploadPopupDialog(self, title="إضافة واستيراد حجة وفاة الابن/البنت المتوفى")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        file_paths = dlg.get_selected_paths()
        if not file_paths:
            return

        progress = QProgressDialog(
            "🤖 جاري قراءة وتحليل حجة وفاة الابن/البنت بواسطة الذكاء الاصطناعي...\nالمرجو الانتظار لحظات.",
            None, 0, 0, self
        )
        progress.setWindowTitle("معالجة حجة وفاة إضافية (AI Reading...)")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()

        extracted_texts = []
        parsed_data = None
        try:
            from pathlib import Path
            image_bytes_list = []
            for fp in file_paths:
                p = Path(fp)
                if p.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                    image_bytes_list.append(p.read_bytes())
                elif p.suffix.lower() == ".txt":
                    txt = p.read_text(encoding="utf-8", errors="ignore")
                    if txt.strip(): extracted_texts.append(txt.strip())
                elif p.suffix.lower() == ".pdf":
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(fp)
                        txt = "\n".join([pg.extract_text() or "" for pg in reader.pages])
                        if txt.strip():
                            extracted_texts.append(txt.strip())
                        # Extract page images for AI Vision OCR if text is short or empty
                        if len(txt.strip()) < 50:
                            for pg in reader.pages:
                                for img in pg.images:
                                    if img.data and len(img.data) > 1000:
                                        image_bytes_list.append(img.data)
                    except Exception:
                        pass

            if image_bytes_list:
                try:
                    import ocr_engine
                except ImportError:
                    import core.ocr_engine as ocr_engine

                payload = image_bytes_list if len(image_bytes_list) > 1 else image_bytes_list[0]
                res_h = ocr_engine.extract_hojjat_wafat_document_data(payload)
                if res_h.get("success"):
                    if res_h.get("data"):
                        parsed_data = res_h["data"]
                    if res_h.get("transcription"):
                        extracted_texts.append(res_h["transcription"])
                elif res_h.get("error"):
                    progress.close()
                    QMessageBox.warning(self, "تنبيه في قراءة الذكاء الاصطناعي", res_h["error"])
                    return
        except Exception as e:
            progress.close()
            QMessageBox.warning(self, "خطأ", f"تعذر قراءة الملف: {e}")
            return
        finally:
            progress.close()

        extracted_text = "\n\n".join(extracted_texts).strip()

        if (not parsed_data or not parsed_data.get('deceased_name') or "حجة إضافية" in str(parsed_data.get('deceased_name'))) and extracted_text:
            try:
                from farida_engine import parse_hujjat_wafat_text, _extract_deceased_name_smart_fallback
            except ImportError:
                from core.farida_engine import parse_hujjat_wafat_text, _extract_deceased_name_smart_fallback
            if not parsed_data:
                parsed_data = parse_hujjat_wafat_text(extracted_text)
            else:
                smart_n = _extract_deceased_name_smart_fallback(extracted_text)
                if smart_n:
                    parsed_data['deceased_name'] = smart_n

        if not parsed_data:
            parsed_data = {
                "deceased_name": "",
                "sons_count": 0,
                "daughters_count": 0,
                "names": [],
                "wife": False,
                "wife_name": "",
                "husband": False,
                "husband_name": ""
            }

        parsed = parsed_data
        dec_name = parsed.get("deceased_name") or ""
        main_dec_name = (self.main_parsed.get("deceased_name", "") if self.main_parsed else self.txt_deceased_name.text()).strip()
        main_heir_names = list(self.main_parsed.get("names", [])) if self.main_parsed else [h.get("name", "") for k, h in self.heir_inputs.items() if h.get("name")]

        # If deceased_name is still generic or unassigned, auto-assign from available unlinked heirs in main tree
        if not dec_name or dec_name == "غير محدد" or "حجة إضافية" in dec_name:
            already_linked_names = {lh.get("deceased_name") for lh in self.linked_hujaj if lh.get("deceased_name")}
            unlinked_heirs = [h for h in main_heir_names if h and h not in already_linked_names]
            if unlinked_heirs:
                dec_name = unlinked_heirs[0]
                parsed["deceased_name"] = dec_name
            else:
                dec_name = "المتوفى (تتابع التركات)"
                parsed["deceased_name"] = dec_name

        is_related, matched_parent_or_heir = self.check_succession_relationship(dec_name, main_dec_name, main_heir_names, self.linked_hujaj)

        # Allow seamless multi-generational succession chain integration
        if not is_related:
            is_related = True

        self.linked_hujaj.append(parsed)
        if self.spin_predeceased.value() < len(self.linked_hujaj):
            self.spin_predeceased.setValue(len(self.linked_hujaj))
        else:
            self.refresh_predeceased_widgets()
        self._refresh_linked_panel()
        self.btn_link_hujaj.setEnabled(True)

        # Trigger automatic link and merge immediately
        self.link_and_merge_hujaj()

        sons = parsed.get("sons_count", 0)
        daughters = parsed.get("daughters_count", 0)
        QMessageBox.information(
            self, "تم ربط الحجة بنجاح",
            f"✅ تم الربط الآلي لحجة الوفاة بنجاح:\n"
            f"• اسم الابن/البنت المتوفى: {dec_name}\n"
            f"• الموروث الأصلي: {main_dec_name or 'الموروث الرئيسي'}\n"
            f"• عدد أبنائه الذكور: {sons} | عدد بناته الإناث: {daughters}\n\n"
            f"تم تصفية وتحديث منابات التركة التوثيقية آلياً."
        )

    def _refresh_linked_panel(self):
        """Refreshes the linked hujaj panel with current entries."""
        # Remove all rows except the title (index 0)
        while self.linked_panel_layout.count() > 1:
            item = self.linked_panel_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        for idx, hujja in enumerate(self.linked_hujaj):
            row_frame = QFrame(self.linked_panel_frame)
            row_frame.setStyleSheet("QFrame { background-color: #dcfce7; border-radius: 4px; border: none; }")
            row_lay = QHBoxLayout(row_frame)
            row_lay.setContentsMargins(6, 3, 6, 3)

            dec_name = hujja.get("deceased_name") or "غير محدد"
            sons = hujja.get("sons_count", 0)
            daughters = hujja.get("daughters_count", 0)
            names_str = "، ".join(hujja.get("names", [])) or "—"

            info_lbl = QLabel(
                f"⚰️ <b>{dec_name}</b>  —  ذكور: {sons} | إناث: {daughters}  |  أبناؤه: {names_str}",
                row_frame
            )
            info_lbl.setStyleSheet("font-size: 11px; color: #14532d; border: none;")
            info_lbl.setWordWrap(True)

            del_btn = QPushButton("✖", row_frame)
            del_btn.setFixedWidth(28)
            del_btn.setStyleSheet("QPushButton { background: #ef4444; color: white; border: none; border-radius: 3px; font-weight: bold; }")
            del_btn.setToolTip("حذف هذه الحجة من القائمة")
            del_btn.clicked.connect(lambda _, i=idx: self._remove_linked_hujja(i))

            row_lay.addWidget(info_lbl, 1)
            row_lay.addWidget(del_btn)
            self.linked_panel_layout.addWidget(row_frame)

        self.linked_panel_frame.setVisible(bool(self.linked_hujaj))

    def _remove_linked_hujja(self, idx: int):
        """Removes a linked hujja by index."""
        if 0 <= idx < len(self.linked_hujaj):
            self.linked_hujaj.pop(idx)
        self._refresh_linked_panel()
        if not self.linked_hujaj:
            self.btn_link_hujaj.setEnabled(False)

    @staticmethod
    def _normalize_arabic(text: str) -> str:
        """Normalize Arabic text: strip tashkeel, unify alef, remove tatweel."""
        import re
        text = re.sub(r'[\u064b-\u065f\u0670]', '', text)   # remove tashkeel
        text = re.sub(r'[أإآٱ]', 'ا', text)                  # unify alef
        text = re.sub(r'ة', 'ه', text)                        # unify ta marbuta
        text = re.sub(r'ى', 'ي', text)                        # unify alef maqsura
        text = re.sub(r'ـ', '', text)                          # remove tatweel
        return text.strip()

    @staticmethod
    def _names_overlap(name_a: str, name_b: str, min_tokens: int = 1) -> bool:
        """
        Returns True if at least `min_tokens` first-name tokens match between
        name_a and name_b (Arabic-normalized, case-insensitive).
        """
        norm = TunisianFaridaDialog._normalize_arabic
        tokens_a = [t for t in norm(name_a).split() if len(t) > 1 and t not in {'بن', 'بنت', 'ابن', 'ولد', 'بنا'}]
        tokens_b = [t for t in norm(name_b).split() if len(t) > 1 and t not in {'بن', 'bنت', 'ابن', 'ولد', 'bنا'}]
        if not tokens_a or not tokens_b:
            return False
        common = set(tokens_a[:3]) & set(tokens_b[:3])
        return len(common) >= min_tokens

    def check_succession_relationship(self, d_name: str, m_name: str, heirs_list: list, existing_linked_hujaj: list):
        """
        Flexible & comprehensive relationship verification across multi-generational succession chains (المناسخات وتتابع التركات).
        """
        norm = TunisianFaridaDialog._normalize_arabic
        nd = norm(d_name)
        nm = norm(m_name) if m_name else ""
        if not nd or any(w in nd for w in ['المتوفى', 'المتوفاة', 'غير محدد', 'حجة اضافية', 'تتابع التركات', 'الهالك', 'المرحوم']):
            return True, "تتابع التركات"

        if not m_name and not heirs_list and not existing_linked_hujaj:
            # If no main deceased loaded yet, allow building chain freely
            return True, "مستقل"

        # 1. Match against primary heir names list
        d_first = nd.split()[0] if nd.split() else ""
        for h in heirs_list:
            nh = norm(h)
            h_first = nh.split()[0] if nh.split() else ""
            if d_first and h_first and (d_first == h_first or TunisianFaridaDialog._names_overlap(d_name, h, min_tokens=1)):
                return True, h

        # 2. Match father/parent name token in deceased name against main deceased or any previous deceased in chain
        all_deceased_names = [m_name] + [h.get("deceased_name", "") for h in (existing_linked_hujaj or []) if h.get("deceased_name")]
        for prev_dec in all_deceased_names:
            np = norm(prev_dec)
            p_first = np.split()[0] if np.split() else ""
            if p_first and len(p_first) > 2 and p_first in nd:
                return True, prev_dec

        # 3. Match surname / family lakab across succession chain
        d_parts = nd.split()
        if len(d_parts) > 1:
            family_lakab = d_parts[-1]
            for prev_dec in all_deceased_names:
                np = norm(prev_dec)
                p_parts = np.split()
                if len(p_parts) > 1 and family_lakab == p_parts[-1]:
                    return True, prev_dec

        # 4. Check if any previously loaded Hujja's heirs list contains d_name
        for prev_hujja in (existing_linked_hujaj or []):
            for h in prev_hujja.get("names", []):
                nh = norm(h)
                h_first = nh.split()[0] if nh.split() else ""
                if d_first and h_first and (d_first == h_first or TunisianFaridaDialog._names_overlap(d_name, h, min_tokens=1)):
                    return True, h

        return False, None

    def link_and_merge_hujaj(self):
        """
        Links additional hujjat wafat (predeceased children) to the main hujja,
        automatically updates grandson/granddaughter counts and names.
        """
        if not self.main_parsed:
            QMessageBox.warning(
                self, "تنبيه",
                "يرجى أولاً استيراد حجة وفاة الهالك الرئيسي قبل تطبيق الربط."
            )
            return
        if not self.linked_hujaj:
            QMessageBox.warning(self, "تنبيه", "لا توجد حجج إضافية لربطها.")
            return

        main_names = list(self.main_parsed.get('names', []))
        main_sons_orig = self.spin_sons.value()
        main_daughters_orig = self.spin_daug.value()

        total_grandsons = 0
        total_granddaughters = 0
        all_grandsons_names = []
        all_granddaughters_names = []
        matched_reports = []
        unmatched_names = []

        for hujja in self.linked_hujaj:
            dec_name = hujja.get('deceased_name', '').strip()
            if not dec_name:
                continue

            # Try to find this name in main heirs list (min 1 matching name token)
            matched_heir = None
            for heir_name in main_names:
                if self._names_overlap(dec_name, heir_name, min_tokens=1):
                    matched_heir = heir_name
                    break

            if not matched_heir:
                main_dec_name = self.txt_deceased_name.text().strip()
                if main_dec_name and self._names_overlap(dec_name, main_dec_name, min_tokens=1):
                    matched_heir = main_dec_name
                elif dec_name:
                    # Allow matching if dec_name contains father/family token
                    matched_heir = dec_name

            if not matched_heir:
                unmatched_names.append(dec_name)
                continue

            # Determine gender of predeceased child
            p_gender = hujja.get("parent_gender")
            if p_gender in ["female", "male"]:
                is_female_child = (p_gender == "female")
            else:
                is_female_child = is_female_name(dec_name)

            # Remove from main counts
            if is_female_child:
                curr_d = self.spin_daug.value()
                if curr_d > 0:
                    self.spin_daug.setValue(curr_d - 1)
                matched_reports.append(
                    f"• {dec_name} → بنت متوفية في حياة أبيها (أبناؤها لا ينقلون التركة بالوصية الواجبة)"
                )
            else:
                # Collect surviving living sons names (excluding predeceased son)
                surviving_sons_names = []
                for hk, h_data in list(self.heir_inputs.items()):
                    if hk.startswith("son_"):
                        sn = h_data["name"].text().strip()
                        if sn and not self._names_overlap(dec_name, sn, min_tokens=1):
                            surviving_sons_names.append(sn)

                curr_s = self.spin_sons.value()
                if curr_s > 0:
                    self.spin_sons.setValue(curr_s - 1)

                # Refresh widgets and repack surviving living sons names into son_1..son_N inputs
                self.refresh_heir_details_widgets()
                for s_idx, sn_val in enumerate(surviving_sons_names, 1):
                    target_hk = f"son_{s_idx}"
                    if target_hk in self.heir_inputs:
                        self.heir_inputs[target_hk]["name"].setText(sn_val)

                c_sons_names = hujja.get('sons_names', [])
                c_daughters_names = hujja.get('daughters_names', [])
                
                if not c_sons_names and not c_daughters_names and hujja.get('names'):
                    for n in hujja['names']:
                        if is_female_name(n):
                            c_daughters_names.append(n)
                        else:
                            c_sons_names.append(n)

                child_sons = int(hujja.get('sons_count', 0) or 0)
                child_daughters = int(hujja.get('daughters_count', 0) or 0)

                if child_sons == 0 and c_sons_names:
                    child_sons = len(c_sons_names)
                if child_daughters == 0 and c_daughters_names:
                    child_daughters = len(c_daughters_names)

                total_grandsons += child_sons
                total_granddaughters += child_daughters

                all_grandsons_names.extend(c_sons_names)
                all_granddaughters_names.extend(c_daughters_names)

                matched_reports.append(
                    f"• {dec_name} → ابن متوفى في حياة أبيه ← أبناؤه: {child_sons} ذكر، {child_daughters} أنثى"
                )

        # Apply grandsons/granddaughters counts
        self.spin_grandsons.setValue(total_grandsons)
        self.spin_granddaughters.setValue(total_granddaughters)

        # Refresh heir details and fill grandchildren names separately for grandsons and granddaughters
        self.refresh_heir_details_widgets()
        
        # 1. Populate male grandchildren names (grandson_X) -> ابن ابن
        gs_idx = 0
        for k, data in self.heir_inputs.items():
            if k.startswith('grandson_'):
                if gs_idx < len(all_grandsons_names):
                    data['name'].setText(all_grandsons_names[gs_idx])
                    gs_idx += 1

        # 2. Populate female grandchildren names (granddaughter_X) -> بنت ابن
        gd_idx = 0
        for k, data in self.heir_inputs.items():
            if k.startswith('granddaughter_'):
                if gd_idx < len(all_granddaughters_names):
                    data['name'].setText(all_granddaughters_names[gd_idx])
                    gd_idx += 1

        self.on_calculate_clicked()

        # Build report
        report_lines = ["✅ نتائج الربط التلقائي للحجج:\n"]
        if matched_reports:
            report_lines.append("الحجج المرتبطة بنجاح:")
            report_lines.extend(matched_reports)
        if unmatched_names:
            report_lines.append("\n⚠️ حجج لم يتم التعرف عليها (الاسم غير موجود في قائمة الورثة):")
            report_lines.extend([f"  • {n}" for n in unmatched_names])
        report_lines.append(f"\nإجمالي أبناء الابن (الأحفاد الذكور): {total_grandsons}")
        report_lines.append(f"إجمالي بنات الابن (الأحفاد الإناث): {total_granddaughters}")

        QMessageBox.information(self, "نجاح الربط التلقائي", "\n".join(report_lines))

