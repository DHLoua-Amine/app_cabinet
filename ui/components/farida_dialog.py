from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QCheckBox, QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextEdit, QScrollArea, QWidget, QMessageBox, QGroupBox,
    QFileDialog, QAbstractSpinBox
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
    Executive Notarial Calculator for Tunisian Inheritance Shares & Estate Division.
    Features:
    - 1-Click Direct Auto-Insert into Active Contract
    - Auto-Fill Deceased Data from Client Profile
    - 1-Click Direct Printing with Official Office Header
    - Amicable Partition Contract (عقد مقاسمة رضائية) Auto-Generation
    """

    farida_inserted = Signal(dict)
    generate_partition_requested = Signal(dict)

    def __init__(self, parent=None, lang="ar", client_id=None):
        super().__init__(parent)
        self.lang = lang
        self.client_id = client_id
        self.engine = TunisianFaridaEngine()
        self.last_result = None
        self.init_ui()

        if client_id:
            self.load_client_profile(client_id)

    def init_ui(self):
        self.setWindowTitle("حاسبة الفريضة الشرعية والتركات")
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
        master_layout.setContentsMargins(20, 20, 20, 20)
        master_layout.setSpacing(15)

        # ── MAIN CONTENT (2 COLUMNS) ─────────────────────────────────────────
        body_layout = QHBoxLayout()
        body_layout.setSpacing(15)

        # =====================================================================
        # LEFT COLUMN: FORM INPUTS
        # =====================================================================
        left_card = QFrame(self)
        left_card.setProperty("class", "MainCard")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(10)

        sec_title1 = QLabel("1. بيانات التركة والورثة والخصومات قبل القسمة:", left_card)
        sec_title1.setStyleSheet("font-weight: 800; font-size: 13px; color: #0f172a;")
        left_layout.addWidget(sec_title1)

        # Client info bar if loaded
        self.client_info_lbl = QLabel("", left_card)
        self.client_info_lbl.setStyleSheet("color: #0369a1; font-weight: bold; font-size: 11px;")
        self.client_info_lbl.setVisible(False)
        left_layout.addWidget(self.client_info_lbl)

        # Import Hujjat Wafat button
        self.btn_import_wafat = QPushButton("📁 استيراد وتفريغ حجة وفاة تلقائياً (صورة / PDF / نص)", left_card)
        self.btn_import_wafat.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.btn_import_wafat.clicked.connect(self.import_hujjat_wafat_file)
        left_layout.addWidget(self.btn_import_wafat)

        scroll = QScrollArea(left_card)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_widget = QWidget()
        form_lay = QVBoxLayout(scroll_widget)
        form_lay.setContentsMargins(5, 5, 5, 5)
        form_lay.setSpacing(8)

        # 1. Deductions & Net Estate
        grp_estate = QGroupBox("التركة والديون والخصومات", scroll_widget)
        grp_estate_lay = QVBoxLayout(grp_estate)
        grp_estate_lay.setSpacing(6)

        gross_lay = QHBoxLayout()
        gross_lbl = QLabel("إجمالي التركة الجملي:", grp_estate)
        self.spin_gross = NoWheelDoubleSpinBox(grp_estate)
        self.spin_gross.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_gross.setRange(0, 1000000000)
        self.spin_gross.setValue(0)
        gross_lay.addWidget(gross_lbl)
        gross_lay.addStretch()
        gross_lay.addWidget(self.spin_gross)
        grp_estate_lay.addLayout(gross_lay)

        funeral_lay = QHBoxLayout()
        funeral_lbl = QLabel("مصاريف الجنازة والتجهيز:", grp_estate)
        self.spin_funeral = NoWheelDoubleSpinBox(grp_estate)
        self.spin_funeral.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_funeral.setRange(0, 10000000)
        self.spin_funeral.setValue(0)
        funeral_lay.addWidget(funeral_lbl)
        funeral_lay.addStretch()
        funeral_lay.addWidget(self.spin_funeral)
        grp_estate_lay.addLayout(funeral_lay)

        debts_lay = QHBoxLayout()
        debts_lbl = QLabel("الديون المتعلقة بالتركة:", grp_estate)
        self.spin_debts = NoWheelDoubleSpinBox(grp_estate)
        self.spin_debts.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_debts.setRange(0, 100000000)
        self.spin_debts.setValue(0)
        debts_lay.addWidget(debts_lbl)
        debts_lay.addStretch()
        debts_lay.addWidget(self.spin_debts)
        grp_estate_lay.addLayout(debts_lay)

        self.net_lbl = QLabel("صافي التركة المعد للقسمة: 0.000 TND", grp_estate)
        self.net_lbl.setStyleSheet("font-weight: 800; color: #047857; font-size: 12px; margin-top: 4px;")
        grp_estate_lay.addWidget(self.net_lbl)
        form_lay.addWidget(grp_estate)

        # 2. Obligatory Bequest
        grp_bequest = QGroupBox("الوصية الواجبة", scroll_widget)
        grp_bequest_lay = QHBoxLayout(grp_bequest)
        bequest_lbl = QLabel("عدد الأبناء المتوفين سابقاً:", grp_bequest)
        self.spin_predeceased = NoWheelSpinBox(grp_bequest)
        self.spin_predeceased.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_predeceased.setRange(0, 10)
        grp_bequest_lay.addWidget(bequest_lbl)
        grp_bequest_lay.addStretch()
        grp_bequest_lay.addWidget(self.spin_predeceased)
        form_lay.addWidget(grp_bequest)

        # 3. Real Estate Mapping
        grp_prop = QGroupBox("توزيع مناب العقار بالأمتار والأجزاء", scroll_widget)
        grp_prop_lay = QVBoxLayout(grp_prop)
        grp_prop_lay.setSpacing(6)

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
        parts_lbl = QLabel("عدد أجزاء التجزئة:", grp_prop)
        self.spin_parts = NoWheelDoubleSpinBox(grp_prop)
        self.spin_parts.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_parts.setRange(0, 10000000)
        self.spin_parts.setValue(0)
        parts_lay.addWidget(parts_lbl)
        parts_lay.addStretch()
        parts_lay.addWidget(self.spin_parts)
        grp_prop_lay.addLayout(parts_lay)
        form_lay.addWidget(grp_prop)

        # 4. Spouses
        grp_spouse = QGroupBox("الزوج أو الزوجة", scroll_widget)
        grp_spouse_lay = QVBoxLayout(grp_spouse)
        grp_spouse_lay.setSpacing(6)
        self.cb_husband = QCheckBox("الزوج (على قيد الحياة عند الوفاة)", grp_spouse)
        
        wife_lay = QHBoxLayout()
        self.cb_wife = QCheckBox("الزوجة (على قيد الحياة عند الوفاة)", grp_spouse)
        wives_cnt_lbl = QLabel("عدد الزوجات:", grp_spouse)
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
        form_lay.addWidget(grp_spouse)

        # 5. Descendants
        grp_desc = QGroupBox("الفروع (الأبناء والبنات وأحفاد الابن)", scroll_widget)
        grp_desc_lay = QVBoxLayout(grp_desc)
        grp_desc_lay.setSpacing(6)

        sons_lay = QHBoxLayout()
        sons_lbl = QLabel("عدد الأبناء (ذكور):", grp_desc)
        self.spin_sons = NoWheelSpinBox(grp_desc)
        self.spin_sons.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_sons.setRange(0, 30)
        sons_lay.addWidget(sons_lbl)
        sons_lay.addStretch()
        sons_lay.addWidget(self.spin_sons)
        grp_desc_lay.addLayout(sons_lay)

        daug_lay = QHBoxLayout()
        daug_lbl = QLabel("عدد البنات (إناث):", grp_desc)
        self.spin_daug = NoWheelSpinBox(grp_desc)
        self.spin_daug.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_daug.setRange(0, 30)
        daug_lay.addWidget(daug_lbl)
        daug_lay.addStretch()
        daug_lay.addWidget(self.spin_daug)
        grp_desc_lay.addLayout(daug_lay)

        grandsons_lay = QHBoxLayout()
        grandsons_lbl = QLabel("عدد أبناء الابن (ذكور):", grp_desc)
        self.spin_grandsons = NoWheelSpinBox(grp_desc)
        self.spin_grandsons.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_grandsons.setRange(0, 30)
        grandsons_lay.addWidget(grandsons_lbl)
        grandsons_lay.addStretch()
        grandsons_lay.addWidget(self.spin_grandsons)
        grp_desc_lay.addLayout(grandsons_lay)

        granddaug_lay = QHBoxLayout()
        granddaug_lbl = QLabel("عدد بنات الابن (إناث):", grp_desc)
        self.spin_granddaughters = NoWheelSpinBox(grp_desc)
        self.spin_granddaughters.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_granddaughters.setRange(0, 30)
        granddaug_lay.addWidget(granddaug_lbl)
        granddaug_lay.addStretch()
        granddaug_lay.addWidget(self.spin_granddaughters)
        grp_desc_lay.addLayout(granddaug_lay)

        form_lay.addWidget(grp_desc)

        # 6. Ancestors
        grp_ancestors = QGroupBox("الأصول (الأب والأم والجدات والجد لأب)", scroll_widget)
        grp_ancestors_lay = QVBoxLayout(grp_ancestors)
        grp_ancestors_lay.setSpacing(5)

        self.cb_father = QCheckBox("الأب (على قيد الحياة)", grp_ancestors)
        self.cb_mother = QCheckBox("الأم (على قيد الحياة)", grp_ancestors)
        self.cb_paternal_grandfather = QCheckBox("الجد لأب", grp_ancestors)
        self.cb_maternal_grandmother = QCheckBox("الجدة لأم", grp_ancestors)
        self.cb_paternal_grandmother = QCheckBox("الجدة لأب", grp_ancestors)

        grp_ancestors_lay.addWidget(self.cb_father)
        grp_ancestors_lay.addWidget(self.cb_mother)
        grp_ancestors_lay.addWidget(self.cb_paternal_grandfather)
        grp_ancestors_lay.addWidget(self.cb_maternal_grandmother)
        grp_ancestors_lay.addWidget(self.cb_paternal_grandmother)
        form_lay.addWidget(grp_ancestors)

        # 7. Siblings
        grp_sibs = QGroupBox("الإخوة والأخوات (أشقاء ولأب ولأم)", scroll_widget)
        grp_sibs_lay = QVBoxLayout(grp_sibs)
        grp_sibs_lay.setSpacing(5)

        bro_lay = QHBoxLayout()
        bro_lbl = QLabel("عدد الإخوة الأشقاء:", grp_sibs)
        self.spin_bro = NoWheelSpinBox(grp_sibs)
        self.spin_bro.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_bro.setRange(0, 20)
        bro_lay.addWidget(bro_lbl)
        bro_lay.addStretch()
        bro_lay.addWidget(self.spin_bro)
        grp_sibs_lay.addLayout(bro_lay)

        sis_lay = QHBoxLayout()
        sis_lbl = QLabel("عدد الأخوات الشقيقات:", grp_sibs)
        self.spin_sis = NoWheelSpinBox(grp_sibs)
        self.spin_sis.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_sis.setRange(0, 20)
        sis_lay.addWidget(sis_lbl)
        sis_lay.addStretch()
        sis_lay.addWidget(self.spin_sis)
        grp_sibs_lay.addLayout(sis_lay)

        pat_bro_lay = QHBoxLayout()
        pat_bro_lbl = QLabel("عدد الإخوة لأب:", grp_sibs)
        self.spin_pat_bro = NoWheelSpinBox(grp_sibs)
        self.spin_pat_bro.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_pat_bro.setRange(0, 20)
        pat_bro_lay.addWidget(pat_bro_lbl)
        pat_bro_lay.addStretch()
        pat_bro_lay.addWidget(self.spin_pat_bro)
        grp_sibs_lay.addLayout(pat_bro_lay)

        pat_sis_lay = QHBoxLayout()
        pat_sis_lbl = QLabel("عدد الأخوات لأب:", grp_sibs)
        self.spin_pat_sis = NoWheelSpinBox(grp_sibs)
        self.spin_pat_sis.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_pat_sis.setRange(0, 20)
        pat_sis_lay.addWidget(pat_sis_lbl)
        pat_sis_lay.addStretch()
        pat_sis_lay.addWidget(self.spin_pat_sis)
        grp_sibs_lay.addLayout(pat_sis_lay)

        mat_sib_lay = QHBoxLayout()
        mat_sib_lbl = QLabel("عدد الإخوة/الأخوات لأم:", grp_sibs)
        self.spin_mat_bro_sis = NoWheelSpinBox(grp_sibs)
        self.spin_mat_bro_sis.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_mat_bro_sis.setRange(0, 20)
        mat_sib_lay.addWidget(mat_sib_lbl)
        mat_sib_lay.addStretch()
        mat_sib_lay.addWidget(self.spin_mat_bro_sis)
        grp_sibs_lay.addLayout(mat_sib_lay)

        form_lay.addWidget(grp_sibs)

        # 8. Extended Agnates (أبناء الإخوة والعمومة)
        grp_agnates = QGroupBox("العصبات: أبناء الإخوة والعمومة", scroll_widget)
        grp_agnates_lay = QVBoxLayout(grp_agnates)
        grp_agnates_lay.setSpacing(5)

        nephew_full_lay = QHBoxLayout()
        nephew_full_lbl = QLabel("عدد أبناء الأخ الشقيق:", grp_agnates)
        self.spin_nephew_full = NoWheelSpinBox(grp_agnates)
        self.spin_nephew_full.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_nephew_full.setRange(0, 20)
        nephew_full_lay.addWidget(nephew_full_lbl)
        nephew_full_lay.addStretch()
        nephew_full_lay.addWidget(self.spin_nephew_full)
        grp_agnates_lay.addLayout(nephew_full_lay)

        nephew_pat_lay = QHBoxLayout()
        nephew_pat_lbl = QLabel("عدد أبناء الأخ لأب:", grp_agnates)
        self.spin_nephew_pat = NoWheelSpinBox(grp_agnates)
        self.spin_nephew_pat.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_nephew_pat.setRange(0, 20)
        nephew_pat_lay.addWidget(nephew_pat_lbl)
        nephew_pat_lay.addStretch()
        nephew_pat_lay.addWidget(self.spin_nephew_pat)
        grp_agnates_lay.addLayout(nephew_pat_lay)

        self.cb_uncle_full = QCheckBox("العم الشقيق (على قيد الحياة)", grp_agnates)
        self.cb_uncle_pat = QCheckBox("العم لأب (على قيد الحياة)", grp_agnates)
        grp_agnates_lay.addWidget(self.cb_uncle_full)
        grp_agnates_lay.addWidget(self.cb_uncle_pat)

        cousin_full_lay = QHBoxLayout()
        cousin_full_lbl = QLabel("عدد أبناء العم الشقيق:", grp_agnates)
        self.spin_cousin_full = NoWheelSpinBox(grp_agnates)
        self.spin_cousin_full.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_cousin_full.setRange(0, 20)
        cousin_full_lay.addWidget(cousin_full_lbl)
        cousin_full_lay.addStretch()
        cousin_full_lay.addWidget(self.spin_cousin_full)
        grp_agnates_lay.addLayout(cousin_full_lay)

        cousin_pat_lay = QHBoxLayout()
        cousin_pat_lbl = QLabel("عدد أبناء العم لأب:", grp_agnates)
        self.spin_cousin_pat = NoWheelSpinBox(grp_agnates)
        self.spin_cousin_pat.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_cousin_pat.setRange(0, 20)
        cousin_pat_lay.addWidget(cousin_pat_lbl)
        cousin_pat_lay.addStretch()
        cousin_pat_lay.addWidget(self.spin_cousin_pat)
        grp_agnates_lay.addLayout(cousin_pat_lay)

        form_lay.addWidget(grp_agnates)

        scroll.setWidget(scroll_widget)
        left_layout.addWidget(scroll)

        calc_btn = QPushButton("حساب الفريضة والأنصبة الشرعية", left_card)
        calc_btn.setProperty("class", "PrimaryBtn")
        calc_btn.clicked.connect(self.on_calculate_clicked)
        left_layout.addWidget(calc_btn)

        body_layout.addWidget(left_card, stretch=5)

        # =====================================================================
        # RIGHT COLUMN: RESULTS & ACTION BUTTONS
        # =====================================================================
        right_card = QFrame(self)
        right_card.setProperty("class", "MainCard")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(10)

        sec_title2 = QLabel("2. الأنصبة الشرعية وصياغة الفصل التوثيقي لحجة الوفاة:", right_card)
        sec_title2.setStyleSheet("font-weight: 800; font-size: 13px; color: #0f172a;")
        right_layout.addWidget(sec_title2)

        # Origin Summary Banner
        self.origin_banner = QFrame(right_card)
        self.origin_banner.setStyleSheet("background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px;")
        banner_lay = QHBoxLayout(self.origin_banner)
        banner_lay.setContentsMargins(12, 8, 12, 8)

        self.origin_lbl = QLabel("أصل الفريضة التوثيقية: —", self.origin_banner)
        self.origin_lbl.setStyleSheet("font-weight: 800; font-size: 13px; color: #0f172a; border: none;")
        banner_lay.addWidget(self.origin_lbl)
        right_layout.addWidget(self.origin_banner)

        # Table
        self.table = QTableWidget(right_card)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["الوارث الشرعي", "السهام", "المخرج", "النسبة", "المبلغ الفعلي", "مناب العقار"])
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
                padding: 8px;
                border: none;
            }
            QTableWidget::item {
                padding: 6px;
            }
        """)
        right_layout.addWidget(self.table, stretch=2)

        # Text Output
        text_hdr = QLabel("النص التوثيقي الرسمي لحجة الوفاة (عدول الإشهاد):", right_card)
        text_hdr.setStyleSheet("font-weight: bold; font-size: 12px; color: #1e293b;")
        right_layout.addWidget(text_hdr)

        self.text_output = QTextEdit(right_card)
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
        right_layout.addWidget(self.text_output, stretch=2)

        # Action Buttons Row 1 (Auto-Insert & Partition Generation)
        row1_box = QHBoxLayout()
        row1_box.setSpacing(8)

        insert_btn = QPushButton("إدراج مباشر في العقد الحالي", right_card)
        insert_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                font-weight: bold;
                padding: 10px 16px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        insert_btn.clicked.connect(self.on_insert_direct_clicked)

        gen_partition_btn = QPushButton("تحرير عقد مقاسمة رضائية", right_card)
        gen_partition_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                font-weight: bold;
                padding: 10px 16px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        gen_partition_btn.clicked.connect(self.on_generate_partition_clicked)

        row1_box.addWidget(insert_btn)
        row1_box.addWidget(gen_partition_btn)
        right_layout.addLayout(row1_box)

        # Action Buttons Row 2 (Word Export, Print, Close)
        row2_box = QHBoxLayout()
        row2_box.setSpacing(8)

        print_btn = QPushButton("طباعة الفريضة", right_card)
        print_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: white;
                font-weight: bold;
                padding: 10px 16px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1e293b;
            }
        """)
        print_btn.clicked.connect(self.on_print_clicked)

        export_word_btn = QPushButton("Word تصدير", right_card)
        export_word_btn.setStyleSheet("""
            QPushButton {
                background-color: #475569;
                color: white;
                font-weight: bold;
                padding: 10px 16px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)
        export_word_btn.clicked.connect(self.on_export_word_clicked)

        close_btn = QPushButton("إغلاق", right_card)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e2e8f0;
                color: #334155;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #cbd5e1;
            }
        """)
        close_btn.clicked.connect(self.accept)

        row2_box.addWidget(print_btn)
        row2_box.addWidget(export_word_btn)
        row2_box.addWidget(close_btn)
        right_layout.addLayout(row2_box)

        body_layout.addWidget(right_card, stretch=6)
        master_layout.addLayout(body_layout)

        # Connect live updates
        self.spin_gross.valueChanged.connect(self.on_calculate_clicked)
        self.spin_funeral.valueChanged.connect(self.on_calculate_clicked)
        self.spin_debts.valueChanged.connect(self.on_calculate_clicked)
        self.spin_predeceased.valueChanged.connect(self.on_calculate_clicked)
        self.spin_m2.valueChanged.connect(self.on_calculate_clicked)
        self.spin_parts.valueChanged.connect(self.on_calculate_clicked)
        self.cb_husband.toggled.connect(self.on_calculate_clicked)
        self.cb_wife.toggled.connect(self.on_calculate_clicked)
        self.spin_wives.valueChanged.connect(self.on_calculate_clicked)
        self.cb_father.toggled.connect(self.on_calculate_clicked)
        self.cb_mother.toggled.connect(self.on_calculate_clicked)
        self.cb_paternal_grandfather.toggled.connect(self.on_calculate_clicked)
        self.cb_maternal_grandmother.toggled.connect(self.on_calculate_clicked)
        self.cb_paternal_grandmother.toggled.connect(self.on_calculate_clicked)
        self.spin_sons.valueChanged.connect(self.on_calculate_clicked)
        self.spin_daug.valueChanged.connect(self.on_calculate_clicked)
        self.spin_grandsons.valueChanged.connect(self.on_calculate_clicked)
        self.spin_granddaughters.valueChanged.connect(self.on_calculate_clicked)
        self.spin_bro.valueChanged.connect(self.on_calculate_clicked)
        self.spin_sis.valueChanged.connect(self.on_calculate_clicked)
        self.spin_pat_bro.valueChanged.connect(self.on_calculate_clicked)
        self.spin_pat_sis.valueChanged.connect(self.on_calculate_clicked)
        self.spin_mat_bro_sis.valueChanged.connect(self.on_calculate_clicked)
        self.spin_nephew_full.valueChanged.connect(self.on_calculate_clicked)
        self.spin_nephew_pat.valueChanged.connect(self.on_calculate_clicked)
        self.cb_uncle_full.toggled.connect(self.on_calculate_clicked)
        self.cb_uncle_pat.toggled.connect(self.on_calculate_clicked)
        self.spin_cousin_full.valueChanged.connect(self.on_calculate_clicked)
        self.spin_cousin_pat.valueChanged.connect(self.on_calculate_clicked)

        # Initial calculation
        self.on_calculate_clicked()

    def load_client_profile(self, client_id: str):
        """Auto-fills deceased client info from client profile."""
        try:
            client_info = reception.get_client_by_id(client_id)
            if client_info:
                full_name = client_info.get("name") or f"{client_info.get('nom', '')} {client_info.get('prenom', '')}".strip()
                cin = client_info.get("cin_number", "—")
                self.client_info_lbl.setText(f"تم تحميل معطيات الهالك: {full_name} (b.ت: {cin})")
                self.client_info_lbl.setVisible(True)
        except Exception:
            pass

    def on_calculate_clicked(self):
        gross = self.spin_gross.value()
        funeral = self.spin_funeral.value()
        debts = self.spin_debts.value()
        net = max(0.0, gross - (funeral + debts))

        self.net_lbl.setText(f"صافي التركة المعد للقسمة: {net:,.3f} TND")

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

        res = self.engine.calculate_farida(
            heirs_dict=heirs_input,
            gross_estate=gross,
            funeral_expenses=funeral,
            debts=debts,
            property_area_m2=self.spin_m2.value(),
            property_parts=self.spin_parts.value()
        )
        self.last_result = res

        origin_str = f"أصل الفريضة التوثيقية: ({res['base_origin']}) سهماً"
        if res.get('is_awl'):
            origin_str += " [مسألة فيها عول]"
        elif res.get('is_radd'):
            origin_str += " [مسألة فيها رد على البنات]"
        self.origin_lbl.setText(origin_str)

        summary = res.get("heirs_summary", [])
        self.table.setRowCount(len(summary))
        for row, h in enumerate(summary):
            cnt = h.get("count", 1)
            if cnt > 1:
                if "الأبناء" in h["heir"]:
                    unit_label = "لكل ابن واحد"
                elif "البنات" in h["heir"]:
                    unit_label = "لكل بنت واحدة"
                elif "الزوجات" in h["heir"]:
                    unit_label = "لكل زوجة واحدة"
                elif "أبناء الابن" in h["heir"]:
                    unit_label = "لكل ابن ابن واحد"
                elif "بنات الابن" in h["heir"]:
                    unit_label = "لكل بنت ابن واحدة"
                elif "الإخوة" in h["heir"]:
                    unit_label = "لكل أخ واحد"
                elif "الأخوات" in h["heir"]:
                    unit_label = "لكل أخت واحدة"
                else:
                    unit_label = f"لكل فرد واحد"
                item_heir = QTableWidgetItem(f"{h['heir']} (عدد {cnt})")
                item_heir.setFont(QFont("Tajawal", 10, QFont.Weight.Bold))
                self.table.setItem(row, 0, item_heir)

                self.table.setItem(row, 1, QTableWidgetItem(f"{h['single_shares']} ({unit_label})"))
                self.table.setItem(row, 2, QTableWidgetItem(f"{h['fraction']}"))
                self.table.setItem(row, 3, QTableWidgetItem(f"% {h['single_percentage']} ({unit_label})"))

                amt_item = QTableWidgetItem(f"{h['single_amount']:,.3f} TND ({unit_label})")
                amt_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                amt_item.setForeground(QColor("#0f172a"))
                self.table.setItem(row, 4, amt_item)

                prop_str = ""
                if h.get("single_area_m2", 0) > 0:
                    prop_str += f"{h['single_area_m2']} م² ({unit_label})"
                if h.get("single_parts", 0) > 0:
                    prop_str += f" | {h['single_parts']} جزء ({unit_label})"
                self.table.setItem(row, 5, QTableWidgetItem(prop_str if prop_str else "—"))
            else:
                item_heir = QTableWidgetItem(str(h["heir"]))
                item_heir.setFont(QFont("Tajawal", 10, QFont.Weight.Bold))
                self.table.setItem(row, 0, item_heir)
                self.table.setItem(row, 1, QTableWidgetItem(str(h['shares'])))
                self.table.setItem(row, 2, QTableWidgetItem(f"{h['fraction']}"))
                self.table.setItem(row, 3, QTableWidgetItem(f"% {h['percentage']}"))

                amt_item = QTableWidgetItem(f"{h['amount']:,.3f} TND")
                amt_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                amt_item.setForeground(QColor("#0f172a"))
                self.table.setItem(row, 4, amt_item)

                prop_str = ""
                if h.get("area_m2", 0) > 0:
                    prop_str += f"{h['area_m2']} م²"
                if h.get("parts", 0) > 0:
                    prop_str += f" | {h['parts']} جزء"
                self.table.setItem(row, 5, QTableWidgetItem(prop_str if prop_str else "—"))

        self.text_output.setText(res.get("legal_notarial_text", ""))

    def on_insert_direct_clicked(self):
        """1-Click Direct Auto-Insert into active contract editor."""
        if not self.last_result:
            return
        self.farida_inserted.emit(self.last_result)
        QMessageBox.information(self, "تم الإدراج", "تم إدراج النص التوثيقي ومنابات الورثة مباشرة في العقد الحالي بنجاح!")
        self.accept()

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
            <h2 style="text-align: center; color: #0f172a; margin-bottom: 5px;">الجمهورية التونسية<br>مكتب عدل الإشهاد<br>إشهاد بالفريضة الشرعية والتركات</h2>
            <hr style="border: 1px solid #cbd5e1; margin-bottom: 20px;">
            
            <p><b>1. بيان التركة والتكاليف:</b><br>
            • إجمالي التركة الجملي: {self.last_result.get('gross_estate', 0):,.3f} TND<br>
            • مصاريف الجنازة والديون: {self.last_result.get('total_deductions', 0):,.3f} TND<br>
            • <b>صافي التركة المعد للقسمة: {self.last_result.get('net_estate', 0):,.3f} TND</b></p>
            
            <p><b>2. أصل الفريضة التوثيقية: ({self.last_result.get('base_origin')}) سهماً</b></p>
            
            <table border="1" cellspacing="0" cellpadding="6" style="width: 100%; border-collapse: collapse; text-align: center; margin-bottom: 20px;">
                <tr style="background-color: #0f172a; color: white;">
                    <th>الوارث الشرعي</th><th>السهام</th><th>المخرج</th><th>النسبة</th><th>المبلغ بالدينار</th><th>مناب العقار</th>
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
                <td>{h['amount']:,.3f} TND</td>
                <td>{prop_str}</td>
            </tr>
            """

        html += f"""
            </table>
            
            <p><b>3. النص التوثيقي الرسمي:</b><br>{self.last_result.get('legal_notarial_text', '')}</p>
            
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

        p = Path(file_path)
        extracted_text = ""
        try:
            if p.suffix.lower() == ".txt":
                extracted_text = p.read_text(encoding="utf-8", errors="ignore")
            elif p.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                from ocr_engine import extract_handwritten_notary_script
                res = extract_handwritten_notary_script(p.read_bytes())
                extracted_text = res.get("full_text") or res.get("property_desc") or str(res)
            elif p.suffix.lower() == ".pdf":
                try:
                    import pypdf
                    reader = pypdf.PdfReader(file_path)
                    extracted_text = "\n".join([page.extract_text() or "" for page in reader.pages])
                except Exception:
                    extracted_text = ""
        except Exception as e:
            QMessageBox.warning(self, "خطأ في قراءة الملف", f"تعذر قراءة ملف حجة الوفاة: {e}")
            return

        if not extracted_text:
            QMessageBox.warning(self, "تنبيه", "لم يتم استخراج نص واضح من الملف المرفق.")
            return

        from farida_engine import parse_hujjat_wafat_text
        parsed = parse_hujjat_wafat_text(extracted_text)

        if parsed:
            if 'husband' in parsed: self.cb_husband.setChecked(bool(parsed['husband']))
            if 'wife' in parsed: self.cb_wife.setChecked(bool(parsed['wife']))
            if 'father' in parsed: self.cb_father.setChecked(bool(parsed['father']))
            if 'mother' in parsed: self.cb_mother.setChecked(bool(parsed['mother']))
            if parsed.get('sons_count', 0) > 0: self.spin_sons.setValue(parsed['sons_count'])
            if parsed.get('daughters_count', 0) > 0: self.spin_daug.setValue(parsed['daughters_count'])

            self.on_calculate_clicked()
            QMessageBox.information(
                self, "نجاح الاستيراد التلقائي",
                f"تم تفريغ حجة الوفاة بنجاح والتكون الآلي للورثة:\n"
                f"• أبناء: {parsed.get('sons_count', 0)}\n"
                f"• بنات: {parsed.get('daughters_count', 0)}\n"
                f"• زوج/زوجة: {'نعم' if (parsed.get('husband') or parsed.get('wife')) else 'لا'}"
            )

