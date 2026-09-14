from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QCheckBox, QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextEdit, QScrollArea, QWidget, QMessageBox, QGroupBox,
    QFileDialog, QAbstractSpinBox, QLineEdit, QComboBox, QCompleter, QTabWidget,
    QProgressDialog, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

try:
    from farida_engine import TunisianFaridaEngine
    import reception
except ImportError:
    from core.farida_engine import TunisianFaridaEngine
    import core.reception as reception


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

    def __init__(self, parent=None, lang="ar", client_id=None):
        super().__init__(parent)
        self.lang = lang
        self.client_id = client_id
        self.engine = TunisianFaridaEngine()
        self.last_result = None
        self.heir_inputs = {}
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

        self.btn_import_wafat = QPushButton("استيراد وتفريغ حجة وفاة تلقائياً (صورة / PDF / نص)", tab1)
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
        tab1_lay.addWidget(self.btn_import_wafat)

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

        self.btn_scan_applicant_cin = QPushButton("مسح بطاقة التعريف الوطنية", grp_applicant)
        self.btn_scan_applicant_cin.setToolTip("مسح بطاقة التعريف الوطنية لطالب الإشهاد بالذكاء الاصطناعي")
        self.btn_scan_applicant_cin.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.btn_scan_applicant_cin.clicked.connect(self.scan_applicant_cin_card)

        app_lay.addWidget(QLabel("الاسم واللقب:", grp_applicant))
        app_lay.addWidget(self.txt_applicant_name, 2)
        app_lay.addWidget(self.txt_applicant_cin, 1)
        app_lay.addWidget(self.btn_search_applicant_archive)
        app_lay.addWidget(self.btn_scan_applicant_cin)
        grp_applicant_lay.addLayout(app_lay)
        form_lay1.addWidget(grp_applicant)

        # Box 3: Deceased Information
        grp_deceased = QGroupBox("بيانات الهالك(ة) (المتوفى / المتوفية)", scroll_w1)
        grp_deceased_lay = QVBoxLayout(grp_deceased)
        dec_lay = QHBoxLayout()
        self.txt_deceased_name = QLineEdit(grp_deceased)
        self.txt_deceased_name.setPlaceholderText("اسم الهالك (المتوفى / المتوفية) الكامل")
        self.btn_search_deceased_archive = QPushButton("بحث بالأرشيف", grp_deceased)
        self.btn_search_deceased_archive.setToolTip("البحث عن الهالك في أرشيف الحرفاء بالاسم")
        self.btn_search_deceased_archive.setStyleSheet("""
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
        self.btn_search_deceased_archive.clicked.connect(self.open_deceased_search_dialog)

        dec_lay.addWidget(QLabel("اسم الهالك(ة):", grp_deceased))
        dec_lay.addWidget(self.txt_deceased_name, 3)
        dec_lay.addWidget(self.btn_search_deceased_archive)
        grp_deceased_lay.addLayout(dec_lay)
        form_lay1.addWidget(grp_deceased)

        # Box 4: Death Certificate Reference Meta
        grp_hujja = QGroupBox("معطيات حجة الوفاة الرسمية", scroll_w1)
        grp_hujja_lay = QVBoxLayout(grp_hujja)
        hujja_lay = QHBoxLayout()
        self.txt_hujja_num = QLineEdit(grp_hujja)
        self.txt_hujja_num.setPlaceholderText("عدد حجة الوفاة")
        self.txt_hujja_date = QLineEdit(grp_hujja)
        self.txt_hujja_date.setPlaceholderText("تاريخ حجة الوفاة")
        self.txt_hujja_court = QLineEdit(grp_hujja)
        self.txt_hujja_court.setPlaceholderText("المحكمة الصادرة عنها")
        hujja_lay.addWidget(QLabel("بيانات الحجة:", grp_hujja))
        hujja_lay.addWidget(self.txt_hujja_num)
        hujja_lay.addWidget(self.txt_hujja_date)
        hujja_lay.addWidget(self.txt_hujja_court)
        grp_hujja_lay.addLayout(hujja_lay)
        form_lay1.addWidget(grp_hujja)

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

        mat_sib_lay = QHBoxLayout()
        mat_sib_lbl = QLabel("عدد الإخوة/الأخوات لأم (إخوة الهالك من الأم فقط):", grp_sibs)
        self.spin_mat_bro_sis = NoWheelSpinBox(grp_sibs)
        self.spin_mat_bro_sis.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_mat_bro_sis.setRange(0, 20)
        mat_sib_lay.addWidget(mat_sib_lbl)
        mat_sib_lay.addStretch()
        mat_sib_lay.addWidget(self.spin_mat_bro_sis)
        grp_sibs_lay.addLayout(mat_sib_lay)

        form_lay3.addWidget(grp_sibs)

        # Extended Agnates
        grp_agnates = QGroupBox("العصبات: أبناء الإخوة والأعمام وأبناء العمومة", scroll_w3)
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

        # ── TAB 3: الرسم العقاري والوصية الواجبة ─────────────────────────────────
        tab3 = QWidget()
        tab3_lay = QVBoxLayout(tab3)
        tab3_lay.setContentsMargins(12, 12, 12, 12)
        tab3_lay.setSpacing(10)

        # Import Title Document button
        self.btn_import_title = QPushButton("🏠 استيراد وتفريغ شهادة الملكية والوثائق العقارية تلقائياً (صورة / PDF)", tab3)
        self.btn_import_title.setStyleSheet("""
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
        self.btn_import_title.clicked.connect(self.import_title_document_file)
        tab3_lay.addWidget(self.btn_import_title)

        scroll2 = QScrollArea(tab3)
        scroll2.setWidgetResizable(True)
        scroll2.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_w2 = QWidget()
        form_lay2 = QVBoxLayout(scroll_w2)
        form_lay2.setContentsMargins(4, 4, 4, 4)
        form_lay2.setSpacing(12)

        # Real Estate Certificate (For Partial Farida)
        grp_prop = QGroupBox("بيانات الرسم العقاري (خاص بالفريضة الجزئية)", scroll_w2)
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

        prop_type_lay = QHBoxLayout()
        prop_type_lbl = QLabel("تصنيف العقار الجبائي والقانوني:", grp_prop)
        self.combo_property_type = QComboBox(grp_prop)
        self.combo_property_type.addItems([
            "مسكن رئيسي (إعفاء جبائي في حدود 1000 م²)",
            "أرض فلاحية (خاضعة لمجلة الأراضي الفلاحية 83-87)",
            "أرض معدة للبناء",
            "عقار تجاري / مهني",
            "عقار عام / غير محدد"
        ])
        prop_type_lay.addWidget(prop_type_lbl)
        prop_type_lay.addWidget(self.combo_property_type, 1)
        grp_prop_lay.addLayout(prop_type_lay)

        form_lay2.addWidget(grp_prop)

        # Obligatory Bequest Box
        grp_bequest = QGroupBox("الوصية الواجبة (الفصل 191 مجلة الأحوال الشخصية)", scroll_w2)
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

        bequest_date_lay = QHBoxLayout()
        bequest_date_lbl = QLabel("تاريخ وفاة الابن / البنت المتوفى سابقاً:", grp_bequest)
        self.txt_predeceased_date = QLineEdit(grp_bequest)
        self.txt_predeceased_date.setPlaceholderText("تاريخ الوفاة (مثال: 15/04/2018)")
        bequest_date_lay.addWidget(bequest_date_lbl)
        bequest_date_lay.addWidget(self.txt_predeceased_date, 1)
        grp_bequest_lay.addLayout(bequest_date_lay)

        form_lay2.addWidget(grp_bequest)

        # Box 3: Extra Supporting Documents
        grp_extra = QGroupBox("📂 الوثائق والمستندات التكميلية الإضافية (مرفقات ومضامين)", scroll_w2)
        grp_extra_lay = QVBoxLayout(grp_extra)
        
        self.btn_import_extra_docs = QPushButton("📂 استيراد وثائق ومستندات تكميلية إضافية (مضامين ولادة / حجج / صور / PDF)", grp_extra)
        self.btn_import_extra_docs.setStyleSheet("""
            QPushButton {
                background-color: #0d9488;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #0f766e;
            }
        """)
        self.btn_import_extra_docs.clicked.connect(self.import_extra_documents_files)
        grp_extra_lay.addWidget(self.btn_import_extra_docs)

        self.txt_extra_notes = QTextEdit(grp_extra)
        self.txt_extra_notes.setPlaceholderText("ملاحظات ومعطيات إضافية مستخرجة من الوثائق التكميلية والمستندات المرفقة...")
        self.txt_extra_notes.setMaximumHeight(80)
        self.txt_extra_notes.setStyleSheet("QTextEdit { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px; font-size: 11px; }")
        self.txt_extra_notes.textChanged.connect(self.on_calculate_clicked)
        grp_extra_lay.addWidget(self.txt_extra_notes)
        
        form_lay2.addWidget(grp_extra)

        scroll2.setWidget(scroll_w2)
        tab3_lay.addWidget(scroll2)

        # ── TAB 4: نتائج الأنصبة والنص التوثيقي الرسمي والعقود ─────────────────────
        tab4 = QWidget()
        tab4_lay = QVBoxLayout(tab4)
        tab4_lay.setContentsMargins(12, 12, 12, 12)
        tab4_lay.setSpacing(10)

        # Origin Summary Banner
        self.origin_banner = QFrame(tab4)
        self.origin_banner.setStyleSheet("background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px;")
        banner_lay = QHBoxLayout(self.origin_banner)
        banner_lay.setContentsMargins(14, 10, 14, 10)

        self.origin_lbl = QLabel("أصل الفريضة التوثيقية: —", self.origin_banner)
        self.origin_lbl.setStyleSheet("font-weight: 800; font-size: 13px; color: #0f172a; border: none;")
        banner_lay.addWidget(self.origin_lbl)
        tab4_lay.addWidget(self.origin_banner)

        # Table (Full Width 1200px Table!)
        self.table = QTableWidget(tab4)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["الوارث الشرعي", "السهام", "الفك / الكسر", "النسبة %", "مناب العقار والأجزاء"])
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
        tab4_lay.addWidget(self.table, stretch=3)

        # Text Output
        text_hdr = QLabel("النص التوثيقي الرسمي لحجة الوفاة والفريضة (عدول الإشهاد):", tab4)
        text_hdr.setStyleSheet("font-weight: bold; font-size: 12px; color: #1e293b;")
        tab4_lay.addWidget(text_hdr)

        self.text_output = QTextEdit(tab4)
        self.text_output.setReadOnly(False)
        self.text_output.setStyleSheet("""
            QTextEdit {
                font-size: 12px;
                line-height: 1.5;
                background-color: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 10px;
                color: #0f172a;
            }
            QTextEdit:focus {
                border: 1px solid #1e40af;
            }
        """)
        tab4_lay.addWidget(self.text_output, stretch=3)

        # Add all 4 tabs to self.tab_widget
        self.tab_widget.addTab(tab1, "📄 1. معطيات الفريضة وطرفي الإشهاد")
        self.tab_widget.addTab(tab2, "👥 2. شجرة الورثة والأسماء وبطاقات التعريف")
        self.tab_widget.addTab(tab3, "🏠 3. الرسم العقاري والوصية الواجبة")
        self.tab_widget.addTab(tab4, "📜 4. نتائج الأنصبة والنص التوثيقي الرسمي والعقود")

        master_layout.addWidget(self.tab_widget, stretch=1)

        # ── BOTTOM ACTION BAR (FULL WIDTH) ──────────────────────────────────
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        calc_btn = QPushButton("🔄 إعادة الحساب التلقائي", self)
        calc_btn.setProperty("class", "PrimaryBtn")
        calc_btn.clicked.connect(self.on_calculate_clicked)

        gen_partition_btn = QPushButton("🟢 تحرير عقد مقاسمة رضائية", self)
        gen_partition_btn.setProperty("class", "SuccessBtn")
        gen_partition_btn.clicked.connect(self.on_generate_partition_clicked)

        print_btn = QPushButton("🖨️ طباعة الفريضة", self)
        print_btn.setProperty("class", "SecondaryBtn")
        print_btn.clicked.connect(self.on_print_clicked)

        export_word_btn = QPushButton("📄 تصدير Word", self)
        export_word_btn.setProperty("class", "SecondaryBtn")
        export_word_btn.clicked.connect(self.on_export_word_clicked)

        close_btn = QPushButton("❌ إغلاق", self)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #334155;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #cbd5e1;
            }
        """)
        close_btn.clicked.connect(self.accept)

        bottom_bar.addWidget(calc_btn)
        bottom_bar.addWidget(gen_partition_btn)
        bottom_bar.addWidget(print_btn)
        bottom_bar.addWidget(export_word_btn)
        bottom_bar.addStretch()
        bottom_bar.addWidget(close_btn)

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
                     self.spin_pat_sis, self.spin_mat_bro_sis, self.spin_nephew_full,
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

        for i in range(1, self.spin_mat_bro_sis.value() + 1):
            active_heirs.append((f"mat_sibling_{i}", f"الأخ/الأخت لأم {i}"))

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

        # Remove keys no longer present
        for k in current_keys - active_keys:
            data = self.heir_inputs.pop(k)
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
                txt_name.textChanged.connect(self.on_calculate_clicked)

                txt_cin = QLineEdit(row_card)
                txt_cin.setPlaceholderText("رقم ب.ت.ط")
                txt_cin.setFixedWidth(100)
                txt_cin.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
                txt_cin.textChanged.connect(self.on_calculate_clicked)

                txt_civil_status = QLineEdit(row_card)
                txt_civil_status.setPlaceholderText("مرجع رسم الولادة (مثال: رسم عدد 1042 ببلدية فوشانة)")
                txt_civil_status.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
                txt_civil_status.textChanged.connect(self.on_calculate_clicked)

                btn_search = QPushButton("🔍 أرشيف", row_card)
                btn_search.setToolTip("البحث في أرشيف المكتب لاستيراد الاسم ورقم ب.ت.ط")
                btn_search.setStyleSheet("QPushButton { background-color: #0284c7; color: white; border: none; border-radius: 4px; padding: 4px 8px; font-size: 10px; font-weight: bold; } QPushButton:hover { background-color: #0369a1; }")
                btn_search.clicked.connect(lambda _, n=txt_name, c=txt_cin, l=label_text: self._search_heir_from_archive(n, c, l))

                row_lay.addWidget(lbl)
                row_lay.addWidget(txt_name, 2)
                row_lay.addWidget(txt_cin, 1)
                row_lay.addWidget(txt_civil_status, 2)
                row_lay.addWidget(btn_search)

                self.heir_details_layout.addWidget(row_card)
                self.heir_inputs[key] = {
                    "widget": row_card,
                    "name": txt_name,
                    "cin": txt_cin,
                    "civil_status": txt_civil_status,
                    "label": label_text
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
            'mat_siblings_count': self.spin_mat_bro_sis.value(),
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
            name_val = data["name"].text().strip()
            cin_val = data["cin"].text().strip()
            cs_val = data.get("civil_status").text().strip() if "civil_status" in data else ""
            if name_val or cin_val or cs_val:
                heir_details[k] = {
                    "name": name_val,
                    "cin": cin_val,
                    "civil_status": cs_val,
                    "label": data["label"]
                }

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
            predeceased_death_date=getattr(self, "txt_predeceased_date", None).text().strip() if hasattr(self, "txt_predeceased_date") else "",
            heir_details=heir_details
        )
        self.last_result = res

        origin_str = f"أصل الفريضة التوثيقية: ({res['base_origin']}) سهماً"
        if res.get('is_awl'):
            origin_str += " [مسألة فيها عول]"
        elif res.get('is_radd'):
            origin_str += " [مسألة فيها رد على البنات]"
        self.origin_lbl.setText(origin_str)

        summary = res.get("heirs_summary", [])
        expanded_table_rows = []
        for h in summary:
            cnt = h.get("count", 1)
            single_shares = h.get("single_shares", h["shares"])
            single_perc = h.get("single_percentage", h["percentage"])
            single_area = h.get("single_area_m2", 0.0)
            single_parts = h.get("single_parts", 0.0)
            fraction = h.get("fraction", "")

            prefix = None
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

            if prefix and cnt >= 1:
                for sub_i in range(1, cnt + 1):
                    hk = f"{prefix}{sub_i}"
                    hd = (heir_details or {}).get(hk, {})
                    h_name = hd.get("name", "").strip()
                    h_cin = hd.get("cin", "").strip()

                    label_prefix = "الابن" if prefix == "son_" else ("البنت" if prefix == "daughter_" else ("الزوجة" if prefix == "wife_" else "الوارث"))
                    disp_name = f"{label_prefix} {h_name}" if h_name else f"{label_prefix} {sub_i}"
                    if h_cin:
                        disp_name += f" (ب.ت.و: {h_cin})"

                    expanded_table_rows.append({
                        "name": disp_name,
                        "shares": single_shares,
                        "fraction": fraction,
                        "percentage": single_perc,
                        "area_m2": single_area,
                        "parts": single_parts
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

                disp_name = f"{h['heir']} {h_name}".strip() if h_name else h["heir"]
                if h_cin:
                    disp_name += f" (ب.ت.و: {h_cin})"

                expanded_table_rows.append({
                    "name": disp_name,
                    "shares": h.get("shares", single_shares),
                    "fraction": fraction,
                    "percentage": h.get("percentage", single_perc),
                    "area_m2": h.get("area_m2", single_area),
                    "parts": h.get("parts", single_parts)
                })

        self.table.setRowCount(len(expanded_table_rows))
        for row, r_item in enumerate(expanded_table_rows):
            item_heir = QTableWidgetItem(r_item["name"])
            item_heir.setFont(QFont("Tajawal", 10, QFont.Weight.Bold))
            self.table.setItem(row, 0, item_heir)
            self.table.setItem(row, 1, QTableWidgetItem(str(r_item["shares"])))
            self.table.setItem(row, 2, QTableWidgetItem(str(r_item["fraction"])))
            self.table.setItem(row, 3, QTableWidgetItem(f"% {r_item['percentage']}"))

            prop_str = ""
            if r_item.get("area_m2", 0) > 0:
                prop_str += f"{r_item['area_m2']} م²"
            if r_item.get("parts", 0) > 0:
                prop_str += f" | {r_item['parts']} جزء"
            self.table.setItem(row, 4, QTableWidgetItem(prop_str if prop_str else "—"))

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
            
            <p><b>أصل الفريضة التوثيقية: ({self.last_result.get('base_origin')}) سهماً</b></p>
            
            <table border="1" cellspacing="0" cellpadding="6" style="width: 100%; border-collapse: collapse; text-align: center; margin-bottom: 20px;">
                <tr style="background-color: #0f172a; color: white;">
                    <th>الوارث الشرعي</th><th>السهام</th><th>المخرج</th><th>النسبة</th><th>مناب العقار للأجزاء</th>
                </tr>
        """

        for h in self.last_result.get("heirs_summary", []):
            prop_str = ""
            if h.get("area_m2", 0) > 0:
                prop_str += f"{h['area_m2']} م²"
            if h.get("parts", 0) > 0:
                prop_str += f" | {h['parts']} جزء"
            if not prop_str:
                prop_str = "—"

            html += f"""
            <tr>
                <td><b>{h['heir']}</b></td>
                <td>{h['shares']}</td>
                <td>{h['fraction']}</td>
                <td>%{h['percentage']}</td>
                <td>{prop_str}</td>
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
        """Allows selecting a Hujjat Wafat image or PDF, extracts heirs, and updates form spinboxes automatically."""
        from pathlib import Path
        file_path, _ = QFileDialog.getOpenFileName(
            self, "اختر ملف أو صورة حجة الوفاة", "", "الملفات وثائق وصور (*.png *.jpg *.jpeg *.pdf *.txt)"
        )
        if not file_path:
            return

        progress = QProgressDialog("🤖 جاري قراءة وتحليل حجة الوفاة بواسطة الذكاء الاصطناعي...\nالمرجو الانتظار لحظات لإنهاء التفريغ الآلي.", None, 0, 0, self)
        progress.setWindowTitle("معالجة المستند بالذكاء الاصطناعي (AI is reading...)")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()

        p = Path(file_path)
        extracted_text = ""
        try:
            if p.suffix.lower() == ".txt":
                extracted_text = p.read_text(encoding="utf-8", errors="ignore")
            elif p.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                try:
                    import ocr_engine
                except ImportError:
                    import core.ocr_engine as ocr_engine
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
            QMessageBox.warning(self, "خطأ في قراءة الملف", f"تعذر قراءة ملف حجة الوفاة: {e}")
            return
        finally:
            progress.close()

        if not extracted_text:
            QMessageBox.warning(self, "تنبيه", "لم يتم استخراج نص واضح من الملف المرفق.")
            return

        try:
            from farida_engine import parse_hujjat_wafat_text
        except ImportError:
            from core.farida_engine import parse_hujjat_wafat_text

        parsed = parse_hujjat_wafat_text(extracted_text)

        if parsed:
            self.cb_husband.setChecked(bool(parsed.get('husband', False)))
            self.cb_wife.setChecked(bool(parsed.get('wife', False)))
            self.cb_father.setChecked(bool(parsed.get('father', False)))
            self.cb_mother.setChecked(bool(parsed.get('mother', False)))
            self.spin_sons.setValue(parsed.get('sons_count', 0))
            self.spin_daug.setValue(parsed.get('daughters_count', 0))

            self.refresh_heir_details_widgets()

            extracted_names = parsed.get('names', [])
            if extracted_names:
                n_idx = 0
                for k, data in self.heir_inputs.items():
                    if n_idx < len(extracted_names):
                        data["name"].setText(extracted_names[n_idx])
                        n_idx += 1

            if parsed.get('deceased_name'): self.txt_deceased_name.setText(parsed['deceased_name'])
            if parsed.get('applicant_name'): self.txt_applicant_name.setText(parsed['applicant_name'])
            if parsed.get('applicant_cin'): self.txt_applicant_cin.setText(parsed['applicant_cin'])
            if parsed.get('hujja_num'): self.txt_hujja_num.setText(parsed['hujja_num'])
            if parsed.get('hujja_date'): self.txt_hujja_date.setText(parsed['hujja_date'])
            if parsed.get('hujja_court'): self.txt_hujja_court.setText(parsed['hujja_court'])

            self.on_calculate_clicked()

            heir_names_str = "، ".join(parsed.get('names', [])) or "تم الاستخراج بناءً على الشروط الشرعية"
            msg = (
                f"تم تفريغ حجة الوفاة بنجاح واستخراج كافة المعطيات والأسماء:\n"
                f"اسم الهالك(ة): {parsed.get('deceased_name') or 'غير محدد'}\n"
                f"اسم طالب الإشهاد: {parsed.get('applicant_name') or 'غير محدد'}\n"
                f"حجة الوفاة: عدد {parsed.get('hujja_num') or 'غير محدد'} بتاريخ {parsed.get('hujja_date') or 'غير محدد'} ({parsed.get('hujja_court') or 'غير محدد'})\n"
                f"عدد الذكور (الأبناء): {parsed.get('sons_count', 0)}\n"
                f"عدد الإناث (البنات): {parsed.get('daughters_count', 0)}\n"
                f"أسماء الورثة المستخرجين: {heir_names_str}"
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


