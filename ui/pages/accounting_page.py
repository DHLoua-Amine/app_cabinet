import datetime
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDateEdit,
    QComboBox, QPushButton, QTabWidget, QTableView, QHeaderView, QFrame,
    QFileDialog, QMessageBox, QDoubleSpinBox, QRadioButton, QButtonGroup, QScrollArea,
    QDialog, QMenu
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QDate, Signal
from PySide6.QtGui import QCursor, QAction

# Import business logic
import reception
from ui.components.calendar_utils import configure_calendar
import auth
import permissions
from permissions import Cap
import pdf_generator
from style_utils import create_executive_excel

# Container styling for the two entry forms. Scoped to QFrame#FormCard for the same
# reason as RECEIPT_ROW_QSS: an unscoped border on the card is inherited by every
# input inside it, so the row ends up as a grid of nested boxes.
FORM_CARD_QSS = """
QFrame#FormCard {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}
QFrame#FormCard QLabel {
    border: none;
    background: transparent;
}
"""


# Styling for the "receipt attached?" rows on the Expenses and Salaries tabs.
# Every rule is scoped to an object name. A bare "border: 1px dashed" set on the
# frame would cascade to its children, giving the label, the button and the status
# text a dashed box each — which is what these rows used to look like.
RECEIPT_ROW_QSS = """
QFrame#ReceiptRow {
    background: #f8fafc;
    border: 1px dashed #cbd5e1;
    border-radius: 8px;
}
QFrame#ReceiptRow QLabel {
    border: none;
    background: transparent;
}
QLabel#ReceiptLabel {
    color: #334155;
    font-size: 13px;
    font-weight: 600;
}
QLabel#ReceiptStatus {
    color: #94a3b8;
    font-size: 12px;
    font-style: italic;
}
QPushButton#ReceiptButton {
    background-color: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px 14px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#ReceiptButton:hover {
    background-color: #f1f5f9;
    border-color: #94a3b8;
}
QPushButton#ReceiptButton:pressed {
    background-color: #e2e8f0;
}
"""


class FinanceTableModel(QAbstractTableModel):
    def __init__(self, data=None, headers=None, lang="ar", parent=None, keys=None):
        super().__init__(parent)
        self._data = data or []
        self.headers = headers or []
        self.lang = lang
        # Explicit column->key mapping. None keeps the old dict-order behaviour.
        self.keys = list(keys) if keys else None

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._data)):
            return None

        row_data = self._data[index.row()]
        col = index.column()

        # Column -> key mapping. self.keys is built once; deriving it per cell with
        # list(row_data.keys()) allocated a fresh list on every repaint of every cell,
        # and tied the visible columns to dict insertion order — which forced callers
        # to keep a second parallel copy of the same rows just to carry extra fields.
        keys = self.keys
        if keys is None:
            keys = list(row_data.keys())
        if col >= len(keys):
            return None

        val = row_data.get(keys[col])

        if role == Qt.ItemDataRole.DisplayRole:
            if isinstance(val, float):
                return f"{val:.3f}"
            return str(val)
            
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if self.lang == "ar":
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

        # Headers
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return None


class AccountingPage(QWidget):

    # Visible columns of the receivables table, in order. The row dicts also carry
    # lowercase detail keys, so the columns must be named rather than inferred.
    REC_COLUMNS = ["Dossier", "Client", "Téléphone", "Total", "Payé", "Reste"]
    # Rows materialised for the receivables table. The reported total is a SQL SUM
    # over every dossier, so this cap affects only what is listed, never the figure.
    REC_ROW_LIMIT = 2000
    # Emitted when the user wants to open a client's fiche from the receivables panel
    open_client_fiche = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang = auth.session_state.lang
        
        # Financial aggregates
        self.total_inflows = 0.0
        self.total_expenses = 0.0
        self.total_salaries = 0.0
        self.net_profit = 0.0
        self.total_receivables = 0.0
        
        self.inflows_list = []
        self.filtered_expenses = []
        self.filtered_salaries = []
        self.receivables_list = []
        self._rec_raw_data = []          # detail rows for the receivables panel (same objects as receivables_list)
        self._selected_rec_client_id = ""
        self._selected_rec_case_id = ""
        self.exp_photo_path = ""
        self.sal_photo_path = ""

        self.init_ui()
        self.load_data()

    def init_ui(self):
        # Base Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 20, 30, 20)
        self.main_layout.setSpacing(10)

        # ── 1. Page Header & Title (fixed, outside scroll) ───────────────────

        # ── Scroll Area wrapping all body content ─────────────────────────
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_widget = QWidget()
        # Scoped to this widget by name. Written bare ("background: transparent;")
        # Qt applies it to every descendant, and a widget stylesheet outranks the
        # application one — so every button inside lost its fill and painted the
        # default #f0f0f0 instead of its QSS colour.
        scroll_widget.setObjectName("AccountingScrollBody")
        scroll_widget.setStyleSheet("QWidget#AccountingScrollBody { background: transparent; }")
        body_layout = QVBoxLayout(scroll_widget)
        body_layout.setContentsMargins(0, 5, 0, 10)
        body_layout.setSpacing(15)
        scroll.setWidget(scroll_widget)
        self.main_layout.addWidget(scroll)

        # ── 2. Period Selection Card ────────────────────────────────────
        period_card = QFrame(scroll_widget)
        period_card.setProperty("class", "Card")
        # Not parented to period_card: it becomes the first row inside the card's
        # own vertical layout, built further down.
        period_lay = QHBoxLayout()
        period_lay.setContentsMargins(0, 0, 0, 0)
        period_lay.setSpacing(10)
        
        # Radio buttons for period
        self.period_group = QButtonGroup(self)
        self.radio_today = QRadioButton("Aujourd'hui" if self.lang == "fr" else "اليوم", period_card)
        self.radio_week = QRadioButton("Cette Semaine" if self.lang == "fr" else "هذا الأسبوع", period_card)
        self.radio_month = QRadioButton("Ce Mois" if self.lang == "fr" else "هذا الشهر", period_card)
        self.radio_all = QRadioButton("Tout le Temps" if self.lang == "fr" else "جميع الأوقات", period_card)
        self.radio_custom = QRadioButton("Par date" if self.lang == "fr" else "تحديد بالتقويم", period_card)
        
        self.radio_month.setChecked(True) # Default to current month
        
        self.period_group.addButton(self.radio_today)
        self.period_group.addButton(self.radio_week)
        self.period_group.addButton(self.radio_month)
        self.period_group.addButton(self.radio_all)
        self.period_group.addButton(self.radio_custom)

        period_lay.addWidget(self.radio_today)
        period_lay.addWidget(self.radio_week)
        period_lay.addWidget(self.radio_month)
        period_lay.addWidget(self.radio_all)
        period_lay.addWidget(self.radio_custom)

        # Date Pickers (Custom period)
        self.date_from_edit = QDateEdit(period_card)
        self.date_from_edit.setCalendarPopup(True)
        # Default the custom range to the current month rather than today..today,
        # so switching to "par date" shows a usable range immediately.
        self.date_from_edit.setDate(QDate.currentDate().addDays(-30))
        self.date_from_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_from_edit.setEnabled(False)
        configure_calendar(self.date_from_edit)

        self.date_to_edit = QDateEdit(period_card)
        self.date_to_edit.setCalendarPopup(True)
        self.date_to_edit.setDate(QDate.currentDate())
        self.date_to_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_to_edit.setEnabled(False)
        configure_calendar(self.date_to_edit)

        # Fixed, equal width so the two pickers read as a pair.
        for de in (self.date_from_edit, self.date_to_edit):
            de.setFixedWidth(140)
        period_lay.addWidget(self.date_from_edit)
        period_lay.addWidget(self.date_to_edit)

        # Signal connections for period filters
        self.radio_today.toggled.connect(self.on_period_changed)
        self.radio_week.toggled.connect(self.on_period_changed)
        self.radio_month.toggled.connect(self.on_period_changed)
        self.radio_all.toggled.connect(self.on_period_changed)
        self.radio_custom.toggled.connect(self.on_period_changed)
        # dateChanged carries a QDate. Connecting it straight to load_data(), which
        # takes no arguments, meant every calendar pick raised TypeError inside the
        # signal delivery and the page never refreshed — this is why the custom range
        # appeared to do nothing.
        self.date_from_edit.dateChanged.connect(self.on_custom_date_changed)
        self.date_to_edit.dateChanged.connect(self.on_custom_date_changed)

        # Download Actions.
        # These used to sit in the same row as five radio buttons and two date
        # pickers; on a narrower window the row overflowed and the PDF button was
        # clipped off the edge of the card. They now have their own row, so both
        # buttons are always fully visible whatever the window width.
        self.excel_btn = QPushButton("Exporter Excel", period_card)
        self.excel_btn.setProperty("class", "SecondaryButton")
        self.excel_btn.setMinimumWidth(170)
        self.excel_btn.clicked.connect(self.export_excel)

        self.pdf_btn = QPushButton("Télécharger PDF", period_card)
        self.pdf_btn.setProperty("class", "PrimaryButton")
        self.pdf_btn.setMinimumWidth(170)
        self.pdf_btn.clicked.connect(self.export_pdf)

        period_lay.addStretch()

        # Card holds two rows: filters on top, export actions underneath.
        period_outer = QVBoxLayout()
        period_outer.setContentsMargins(0, 0, 0, 0)
        period_outer.setSpacing(10)
        period_outer.addLayout(period_lay)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(10)
        if self.lang == "fr":
            actions_row.addStretch()
            actions_row.addWidget(self.excel_btn)
            actions_row.addWidget(self.pdf_btn)
        else:
            actions_row.addWidget(self.pdf_btn)
            actions_row.addWidget(self.excel_btn)
            actions_row.addStretch()
        period_outer.addLayout(actions_row)

        period_card_wrapper = QVBoxLayout(period_card)
        period_card_wrapper.setContentsMargins(15, 10, 15, 10)
        period_card_wrapper.addLayout(period_outer)

        body_layout.addWidget(period_card)

        # ── 3. KPI Metrics Rows ──────────────────────────────────────────────
        self.kpi_layout = QHBoxLayout()
        self.kpi_layout.setSpacing(12)

        self.kpi_widgets = {}
        metrics_def = [
            ("recettes", "Recettes (Madaakhil)" if self.lang == "fr" else "المقبوضات", "#ffffff", "#334155"),
            ("depenses", "Dépenses" if self.lang == "fr" else "المصاريف", "#f97316", "#f97316"),
            ("salaires", "Salaires" if self.lang == "fr" else "أجور الموظفين", "#eab308", "#eab308"),
            ("net", "Bénéfice Net" if self.lang == "fr" else "الربح الصافي", "#10b981", "#10b981"),
            ("creances", "Créances Clients" if self.lang == "fr" else "ديون الحرفاء", "#3b82f6", "#3b82f6"),
        ]

        for key, title, val_color, border_color in metrics_def:
            card = QFrame(scroll_widget)
            card.setObjectName("MetricCard")
            card.setStyleSheet(f"QFrame#MetricCard {{ background-color: #ffffff; border: 1px solid #cbd5e1; border-left: 5px solid {border_color}; border-radius: 8px; }}")
            card_lay = QVBoxLayout(card)
            card_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            lbl_title = QLabel(title, card)
            lbl_title.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 700; border: none;")
            
            text_color = "#0f172a" if val_color == "#ffffff" else val_color
            lbl_val = QLabel("0.000 DT", card)
            lbl_val.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {text_color}; border: none;")
            
            card_lay.addWidget(lbl_title)
            card_lay.addWidget(lbl_val)
            self.kpi_layout.addWidget(card)
            self.kpi_widgets[key] = (lbl_title, lbl_val)

        body_layout.addLayout(self.kpi_layout)

        # ── 4. Main QTabWidget Container ─────────────────────────────────────
        self.tabs = QTabWidget(scroll_widget)

        # Tab 1: Inflows (Recettes)
        self.tab_inflows = QWidget()
        inflows_lay = QVBoxLayout(self.tab_inflows)
        inflows_lay.setSpacing(8)

        # ── Search bar ──────────────────────────────────────────────────────────────
        search_row = QHBoxLayout()
        self.search_inflows_input = QLineEdit(self.tab_inflows)
        self.search_inflows_input.textChanged.connect(self.filter_inflows)
        search_row.addWidget(QLabel("", self.tab_inflows))
        search_row.addWidget(self.search_inflows_input, stretch=1)
        inflows_lay.addLayout(search_row)

        self.inflows_table = QTableView(self.tab_inflows)
        self.configure_table(self.inflows_table)
        inflows_lay.addWidget(self.inflows_table)
        self.tabs.addTab(self.tab_inflows, "Détails des Recettes" if self.lang == "fr" else "تفاصيل المداخيل")


        # Tab 3: Expenses (Dépenses)
        self.tab_expenses = QWidget()
        expenses_lay = QVBoxLayout(self.tab_expenses)
        
        # Expense Form Card
        exp_form_card = QFrame(self.tab_expenses)
        exp_form_card.setObjectName("FormCard")
        exp_form_card.setStyleSheet(FORM_CARD_QSS)
        exp_form_lay = QHBoxLayout(exp_form_card)
        exp_form_lay.setSpacing(15)

        # No placeholder examples inside the fields — the label above each one says
        # what it is, and example text inside a box reads like real content.
        self.exp_desc_input = QLineEdit(exp_form_card)

        self.exp_amt_spin = QDoubleSpinBox(exp_form_card)
        self.exp_amt_spin.setRange(0, 999999)
        self.exp_amt_spin.setDecimals(3)
        self.exp_amt_spin.setSingleStep(10)
        self.exp_amt_spin.setSuffix(" DT")

        self.exp_cat_combo = QComboBox(exp_form_card)

        self.add_exp_btn = QPushButton("Enregistrer la dépense", exp_form_card)
        self.add_exp_btn.setProperty("class", "PrimaryButton")
        self.add_exp_btn.clicked.connect(self.save_expense)

        # Every control the same height, and fixed widths for the short ones, so the
        # row reads as one form instead of boxes of unrelated sizes.
        for w in (self.exp_desc_input, self.exp_amt_spin, self.exp_cat_combo, self.add_exp_btn):
            w.setFixedHeight(40)
        self.exp_amt_spin.setFixedWidth(150)
        self.exp_cat_combo.setFixedWidth(200)
        self.add_exp_btn.setFixedWidth(200)

        self.lbl_exp_desc = QLabel("Description" if self.lang == "fr" else "وصف المصروف", exp_form_card)
        self.lbl_exp_amt = QLabel("Montant" if self.lang == "fr" else "المبلغ", exp_form_card)
        self.lbl_exp_cat = QLabel("Catégorie" if self.lang == "fr" else "الصنف", exp_form_card)
        for lb in (self.lbl_exp_desc, self.lbl_exp_amt, self.lbl_exp_cat):
            lb.setStyleSheet("color:#64748b; font-size:12px; font-weight:600; border:none;")

        # Each control sits under its own label.
        def _field(label, widget, stretch=0):
            col = QVBoxLayout()
            col.setSpacing(4)
            col.setContentsMargins(0, 0, 0, 0)
            col.addWidget(label)
            col.addWidget(widget)
            exp_form_lay.addLayout(col, stretch)

        _field(self.lbl_exp_desc, self.exp_desc_input, 2)
        _field(self.lbl_exp_amt, self.exp_amt_spin)
        _field(self.lbl_exp_cat, self.exp_cat_combo)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)
        btn_col.setContentsMargins(0, 0, 0, 0)
        spacer_lbl = QLabel("", exp_form_card)
        spacer_lbl.setStyleSheet("border:none;")
        btn_col.addWidget(spacer_lbl)          # keeps the button aligned with the inputs
        btn_col.addWidget(self.add_exp_btn)
        exp_form_lay.addLayout(btn_col)

        # Photo / receipt row.
        # The border is scoped to QFrame#ReceiptRow. An unscoped "border: 1px dashed"
        # set on the frame cascades to every child, so the label, the button and the
        # status text each drew their own dashed box instead of one clean row.
        exp_photo_frame = QFrame(self.tab_expenses)
        exp_photo_frame.setObjectName("ReceiptRow")
        exp_photo_frame.setStyleSheet(RECEIPT_ROW_QSS)
        exp_photo_frame.setFixedHeight(56)
        exp_photo_lay = QHBoxLayout(exp_photo_frame)
        exp_photo_lay.setContentsMargins(14, 8, 14, 8)
        exp_photo_lay.setSpacing(10)

        self.lbl_exp_receipt = QLabel("صورة الوصل :" if self.lang != "fr" else "Justificatif :",
                                      exp_photo_frame)
        self.lbl_exp_receipt.setObjectName("ReceiptLabel")

        exp_browse_btn = QPushButton("استعراض" if self.lang != "fr" else "Parcourir", exp_photo_frame)
        exp_browse_btn.setObjectName("ReceiptButton")
        exp_browse_btn.setFixedHeight(32)
        exp_browse_btn.setMinimumWidth(120)
        exp_browse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        exp_browse_btn.clicked.connect(self.browse_expense_photo)

        self.exp_photo_display = QLabel("لم يُختَر وصل بعد" if self.lang != "fr" else "Aucun justificatif",
                                        exp_photo_frame)
        self.exp_photo_display.setObjectName("ReceiptStatus")

        exp_photo_lay.addWidget(self.lbl_exp_receipt)
        exp_photo_lay.addWidget(exp_browse_btn)
        exp_photo_lay.addWidget(self.exp_photo_display, stretch=1)

        expenses_lay.addWidget(exp_form_card)
        expenses_lay.addWidget(exp_photo_frame)

        # Expenses Table
        self.expenses_table = QTableView(self.tab_expenses)
        self.configure_table(self.expenses_table)
        self.expenses_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.expenses_table.customContextMenuRequested.connect(self.show_expenses_context_menu)
        self.expenses_table.doubleClicked.connect(
            lambda idx: self.on_row_activated(self.expenses_table, idx))
        expenses_lay.addWidget(self.expenses_table)
        expenses_lay.addLayout(self.build_row_action_bar(
            "expenses", self.edit_selected_expense,
            lambda: self.open_selected_receipt(self.expenses_table),
            self.delete_selected_expense))
        
        self.tabs.addTab(self.tab_expenses, "Dépenses & Taxes" if self.lang == "fr" else "المصاريف والأداءات")

        # Tab 4: Salaries (Salaires du personnel)
        self.tab_salaries = QWidget()
        salaries_lay = QVBoxLayout(self.tab_salaries)

        # Salary Form Card
        sal_form_card = QFrame(self.tab_salaries)
        sal_form_card.setObjectName("FormCard")
        sal_form_card.setStyleSheet(FORM_CARD_QSS)
        sal_form_lay = QHBoxLayout(sal_form_card)
        sal_form_lay.setSpacing(15)

        # Labels above the fields; no example text inside the boxes.
        self.sal_name_input = QLineEdit(sal_form_card)

        self.sal_amt_spin = QDoubleSpinBox(sal_form_card)
        self.sal_amt_spin.setRange(0, 999999)
        self.sal_amt_spin.setDecimals(3)
        self.sal_amt_spin.setSingleStep(50)
        self.sal_amt_spin.setSuffix(" DT")

        self.sal_note_input = QLineEdit(sal_form_card)

        self.add_sal_btn = QPushButton("Enregistrer le salaire", sal_form_card)
        self.add_sal_btn.setProperty("class", "PrimaryButton")
        self.add_sal_btn.clicked.connect(self.save_salary)

        for w in (self.sal_name_input, self.sal_amt_spin, self.sal_note_input, self.add_sal_btn):
            w.setFixedHeight(40)
        self.sal_amt_spin.setFixedWidth(150)
        self.add_sal_btn.setFixedWidth(200)

        self.lbl_sal_name = QLabel("Employé" if self.lang == "fr" else "اسم الموظف", sal_form_card)
        self.lbl_sal_amt = QLabel("Montant" if self.lang == "fr" else "المبلغ", sal_form_card)
        self.lbl_sal_note = QLabel("Notes" if self.lang == "fr" else "ملاحظات", sal_form_card)
        for lb in (self.lbl_sal_name, self.lbl_sal_amt, self.lbl_sal_note):
            lb.setStyleSheet("color:#64748b; font-size:12px; font-weight:600; border:none;")

        def _sal_field(label, widget, stretch=0):
            col = QVBoxLayout()
            col.setSpacing(4)
            col.setContentsMargins(0, 0, 0, 0)
            col.addWidget(label)
            col.addWidget(widget)
            sal_form_lay.addLayout(col, stretch)

        _sal_field(self.lbl_sal_name, self.sal_name_input, 2)
        _sal_field(self.lbl_sal_amt, self.sal_amt_spin)
        _sal_field(self.lbl_sal_note, self.sal_note_input, 2)

        sal_btn_col = QVBoxLayout()
        sal_btn_col.setSpacing(4)
        sal_btn_col.setContentsMargins(0, 0, 0, 0)
        sal_spacer = QLabel("", sal_form_card)
        sal_spacer.setStyleSheet("border:none;")
        sal_btn_col.addWidget(sal_spacer)
        sal_btn_col.addWidget(self.add_sal_btn)
        sal_form_lay.addLayout(sal_btn_col)

        # Photo / receipt row — same scoped styling as the expenses tab.
        sal_photo_frame = QFrame(self.tab_salaries)
        sal_photo_frame.setObjectName("ReceiptRow")
        sal_photo_frame.setStyleSheet(RECEIPT_ROW_QSS)
        sal_photo_frame.setFixedHeight(56)
        sal_photo_lay = QHBoxLayout(sal_photo_frame)
        sal_photo_lay.setContentsMargins(14, 8, 14, 8)
        sal_photo_lay.setSpacing(10)

        self.lbl_sal_receipt = QLabel("صورة الوصل :" if self.lang != "fr" else "Justificatif :",
                                      sal_photo_frame)
        self.lbl_sal_receipt.setObjectName("ReceiptLabel")

        sal_browse_btn = QPushButton("استعراض" if self.lang != "fr" else "Parcourir", sal_photo_frame)
        sal_browse_btn.setObjectName("ReceiptButton")
        sal_browse_btn.setFixedHeight(32)
        sal_browse_btn.setMinimumWidth(120)
        sal_browse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        sal_browse_btn.clicked.connect(self.browse_salary_photo)

        self.sal_photo_display = QLabel("لم يُختَر وصل بعد" if self.lang != "fr" else "Aucun justificatif",
                                        sal_photo_frame)
        self.sal_photo_display.setObjectName("ReceiptStatus")

        sal_photo_lay.addWidget(self.lbl_sal_receipt)
        sal_photo_lay.addWidget(sal_browse_btn)
        sal_photo_lay.addWidget(self.sal_photo_display, stretch=1)

        salaries_lay.addWidget(sal_form_card)
        salaries_lay.addWidget(sal_photo_frame)

        # Salaries Table
        self.salaries_table = QTableView(self.tab_salaries)
        self.configure_table(self.salaries_table)
        self.salaries_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.salaries_table.customContextMenuRequested.connect(self.show_salaries_context_menu)
        self.salaries_table.doubleClicked.connect(
            lambda idx: self.on_row_activated(self.salaries_table, idx))
        salaries_lay.addWidget(self.salaries_table)
        salaries_lay.addLayout(self.build_row_action_bar(
            "salaries", self.edit_selected_salary,
            lambda: self.open_selected_receipt(self.salaries_table),
            self.delete_selected_salary))

        self.tabs.addTab(self.tab_salaries, "Salaires du Personnel" if self.lang == "fr" else "أجور الموظفين")

        # Tab 5: Receivables (Créances Clients & Restes)
        self.tab_receivables = QWidget()
        receivables_lay = QVBoxLayout(self.tab_receivables)
        
        self.receivables_table = QTableView(self.tab_receivables)
        self.configure_table(self.receivables_table)
        self.receivables_table.clicked.connect(self.on_receivable_clicked)
        receivables_lay.addWidget(self.receivables_table)

        self.rec_scope_lbl = QLabel("", self.tab_receivables)
        self.rec_scope_lbl.setWordWrap(True)
        self.rec_scope_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        receivables_lay.addWidget(self.rec_scope_lbl)

        # ── Detail panel (hidden until a row is selected) ──────────────────────────
        self.receivables_detail_frame = QFrame(self.tab_receivables)
        self.receivables_detail_frame.setObjectName("Card")
        self.receivables_detail_frame.setProperty("class", "Card")
        self.receivables_detail_frame.setVisible(False)
        rec_det_lay = QVBoxLayout(self.receivables_detail_frame)
        rec_det_lay.setContentsMargins(15, 12, 15, 12)
        rec_det_lay.setSpacing(8)

        self.rec_det_title = QLabel("", self.receivables_detail_frame)
        self.rec_det_title.setStyleSheet("font-size:14px; font-weight:800; color:#0f172a;")
        rec_det_lay.addWidget(self.rec_det_title)

        info_cols_lay = QHBoxLayout()
        self.rec_col1 = QLabel("", self.receivables_detail_frame)
        self.rec_col1.setWordWrap(True)
        self.rec_col1.setStyleSheet("font-size:12px; color:#334155; line-height:1.8;")
        self.rec_col2 = QLabel("", self.receivables_detail_frame)
        self.rec_col2.setWordWrap(True)
        self.rec_col2.setStyleSheet("font-size:12px; color:#334155; line-height:1.8;")
        self.rec_col3 = QLabel("", self.receivables_detail_frame)
        self.rec_col3.setWordWrap(True)
        self.rec_col3.setStyleSheet("font-size:12px; color:#0f172a; font-weight:700; line-height:1.8;")
        info_cols_lay.addWidget(self.rec_col1)
        info_cols_lay.addWidget(self.rec_col2)
        info_cols_lay.addWidget(self.rec_col3)
        rec_det_lay.addLayout(info_cols_lay)

        self.rec_open_btn = QPushButton(
            "Ouvrir la Fiche Client" if self.lang == "fr" else "فتح بطاقة الحريف",
            self.receivables_detail_frame
        )
        self.rec_open_btn.setProperty("class", "PrimaryButton")
        self.rec_open_btn.clicked.connect(self._open_fiche_from_receivables)
        btn_r_row = QHBoxLayout()
        btn_r_row.addStretch()
        btn_r_row.addWidget(self.rec_open_btn)
        rec_det_lay.addLayout(btn_r_row)

        receivables_lay.addWidget(self.receivables_detail_frame)

        self.tabs.addTab(self.tab_receivables, "Créances Clients & Restes" if self.lang == "fr" else "ديون الحرفاء والمتبقي")

        body_layout.addWidget(self.tabs)
        body_layout.addStretch()

        # Apply initial translations
        self.update_translations()

    def configure_table(self, table):
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)

    def update_translations(self):
        is_fr = self.lang == "fr"
        self._retitle_row_action_bars()
        
        
        # Period Radios
        self.radio_today.setText("Aujourd'hui" if is_fr else "اليوم")
        self.radio_week.setText("Cette Semaine" if is_fr else "هذا الأسبوع")
        self.radio_month.setText("Ce Mois" if is_fr else "هذا الشهر")
        self.radio_all.setText("Tout le Temps" if is_fr else "جميع الأوقات")
        self.radio_custom.setText("Par date" if is_fr else "تحديد بالتقويم")

        # Buttons
        self.excel_btn.setText("Exporter Excel" if is_fr else "تصدير إلى Excel")
        self.pdf_btn.setText("Télécharger PDF" if is_fr else "تحميل ملف PDF")

        # KPIs Header labels
        metrics_titles = [
            ("recettes", "Recettes (Madaakhil)" if is_fr else "المقبوضات"),
            ("depenses", "Dépenses" if is_fr else "المصاريف"),
            ("salaires", "Salaires" if is_fr else "أجور الموظفين"),
            ("net", "Bénéfice Net" if is_fr else "الربح الصافي"),
            ("creances", "Créances Clients" if is_fr else "ديون الحرفاء"),
        ]
        for key, title in metrics_titles:
            self.kpi_widgets[key][0].setText(title)

        # Tab titles, matched to the tab widget rather than to fixed indices — a
        # hardcoded index list silently relabels every tab if one is ever added or
        # removed, which is exactly what happened when the charts tab was dropped.
        tab_titles = [
            (self.tab_inflows, "Détails des Recettes" if is_fr else "تفاصيل المداخيل"),
            (self.tab_expenses, "Dépenses & Taxes" if is_fr else "المصاريف والأداءات"),
            (self.tab_salaries, "Salaires du Personnel" if is_fr else "أجور الموظفين"),
            (self.tab_receivables, "Créances Clients & Restes" if is_fr else "ديون الحرفاء والمتبقي"),
        ]
        for widget, title in tab_titles:
            idx = self.tabs.indexOf(widget)
            if idx >= 0:
                self.tabs.setTabText(idx, title)

        # Expense Form Category Combobox
        self.exp_cat_combo.blockSignals(True)
        self.exp_cat_combo.clear()
        if is_fr:
            cat_opts = ["Fournitures", "Loyer & Charges", "Matériel", "Taxes & Impôts", "Autre"]
        else:
            cat_opts = ["مستلزمات مكتبية", "كراء ومصاريف قارّة", "تجهيزات وصيانة", "أداءات ورسوم", "مصاريف أخرى"]
        self.exp_cat_combo.addItems(cat_opts)
        self.exp_cat_combo.blockSignals(False)

        self.add_exp_btn.setText("Enregistrer la dépense" if is_fr else "تسجيل المصروف")
        self.add_sal_btn.setText("Enregistrer le salaire" if is_fr else "تسجيل الراتب")

        # Field labels sit above the inputs; the boxes themselves stay empty.
        self.lbl_exp_desc.setText("Description" if is_fr else "وصف المصروف")
        self.lbl_exp_amt.setText("Montant" if is_fr else "المبلغ")
        self.lbl_exp_cat.setText("Catégorie" if is_fr else "الصنف")
        self.lbl_sal_name.setText("Employé" if is_fr else "اسم الموظف")
        self.lbl_sal_amt.setText("Montant" if is_fr else "المبلغ")
        self.lbl_sal_note.setText("Notes" if is_fr else "ملاحظات")

        # Layout direction
        if is_fr:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    def on_custom_date_changed(self, _qdate=None):
        """Reloads when a calendar date changes. Accepts the QDate the signal carries."""
        if self.radio_custom.isChecked():
            self.load_data()

    def on_period_changed(self):
        # Enable/Disable date picker inputs based on selection
        is_custom = self.radio_custom.isChecked()
        self.date_from_edit.setEnabled(is_custom)
        self.date_to_edit.setEnabled(is_custom)
        self.load_data()

    def get_period_dates(self):
        now = datetime.datetime.now()
        
        if self.radio_today.isChecked():
            if now.hour < 5:
                start_dt = (now - datetime.timedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0)
            else:
                start_dt = now.replace(hour=5, minute=0, second=0, microsecond=0)
            end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
            
        elif self.radio_week.isChecked():
            start_dt = (now - datetime.timedelta(days=now.weekday())).replace(hour=5, minute=0, second=0, microsecond=0)
            end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
            
        elif self.radio_month.isChecked():
            # Midnight, not 05:00. The 05:00 boundary is a working-day convention
            # that belongs to "today" and "this week"; applied to a calendar month
            # it silently dropped anything booked between 00:00 and 05:00 on the
            # 1st -- a real charge, absent from the month's total with no trace.
            start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
            
        elif self.radio_custom.isChecked():
            date_from = self.date_from_edit.date().toPython()
            date_to = self.date_to_edit.date().toPython()
            start_dt = datetime.datetime.combine(date_from, datetime.time(0, 0, 0))
            end_dt = datetime.datetime.combine(date_to, datetime.time(23, 59, 59))
            
        else: # Tout le Temps
            start_dt = datetime.datetime(2000, 1, 1, 0, 0, 0)
            end_dt = datetime.datetime(2099, 12, 31, 23, 59, 59)

        return start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")

    def _set_table_model(self, view, model):
        """
        Swaps a table's model without leaking the old one.

        Models used to be constructed with the page as Qt parent, so Qt owned every
        model ever created and freed none of them. They are now unparented and held
        in self._models, which keeps exactly one alive per view.
        """
        if not hasattr(self, "_models"):
            self._models = {}
        key = id(view)
        previous = self._models.get(key)
        self._models[key] = model
        view.setModel(model)
        if previous is not None and previous is not model:
            previous.deleteLater()

    def load_data(self):
        # The page is unreachable for a role without VIEW_FINANCE - the sidebar
        # entry is hidden, switch_page refuses, the warm-up skips it - but the
        # underlying data functions raise rather than return, so a route that
        # somehow got here must be turned away, not allowed to crash.
        if not permissions.has(Cap.VIEW_FINANCE):
            self._render_access_denied()
            return

        start_str, end_str = self.get_period_dates()
        is_fr = self.lang == "fr"

        # 1. Client names/phones only — get_all_clients() also deserializes 10,000
        # face embeddings this page never uses.
        # Client name/phone now arrive joined with each row. Building a 10,000-entry
        # map to look up the ~2,300 clients that actually appear was the last large
        # per-refresh allocation on this page.

        # 2. Inflows — selected by date in SQL rather than by scanning all 20,000
        # dossiers in Python and discarding those outside the period.
        self.inflows_list = []
        self.total_inflows = 0.0

        for cs in reception.get_case_inflows_between(start_str, end_str):
            created_at = cs.get("created_at") or ""
            av = float(cs.get("avance_amount") or 0.0)
            tot = float(cs.get("total_amount") or 0.0)
            self.total_inflows += av
            cid = cs.get("client_id") or ""
            self.inflows_list.append({
                "Source": "Contrat" if is_fr else "عقد توثيقي",
                "Dossier": cs.get("case_id", ""),
                "Client": cs.get("client_name") or ("Client inconnu" if is_fr else "حريف غير معروف"),
                "Acompte": av,
                "Total": tot,
                "Date": created_at.split()[0] if created_at else "",
                "Notes": cs.get("payment_notes") or "-"
            })

        # Check-in guichet inflows.
        # Queried by date range in SQL: the old "most recent 500, then filter by date"
        # under-reported income for any period older than those 500 check-ins.
        try:
            df_checkins = reception.get_check_in_inflows_between(start_str, end_str)
            if not df_checkins.empty:
                for _, row in df_checkins.iterrows():
                    av = float(row.get("avance_amount") or 0.0)
                    if av <= 0:
                        continue
                    dt_str = str(row.get("timestamp", ""))
                    self.total_inflows += av
                    self.inflows_list.append({
                        "Source": "Réception" if is_fr else "استقبال الشباك",
                        "Dossier": "Guichet",
                        "Client": row.get("client_name") or ("Visiteur" if is_fr else "زائر"),
                        "Acompte": av,
                        "Total": float(row.get("total_amount") or av),
                        "Date": dt_str.split()[0] if dt_str else "",
                        "Notes": "Versement guichet" if is_fr else "دفعة بالشباك"
                    })
        except Exception as e:
            print(f"[Accounting] check-in inflows failed: {e}")

        # 3. Expenses
        all_expenses = reception.get_expenses()
        self.filtered_expenses = [e for e in all_expenses if start_str <= (e.get("created_at") or "") <= end_str]
        self.total_expenses = sum(float(e.get("amount") or 0.0) for e in self.filtered_expenses)

        # 4. Salaries
        all_salaries = reception.get_salaries()
        self.filtered_salaries = [s for s in all_salaries if start_str <= (s.get("payment_date") or "") <= end_str]
        self.total_salaries = sum(float(s.get("amount") or 0.0) for s in self.filtered_salaries)

        # 5. Receivables (Debts)
        # One dict per receivable, carrying both the display fields and the detail
        # fields. This used to be two parallel lists of ~15,000 dicts each — the same
        # rows stored twice, which was the largest single allocation site in the app.
        self.receivables_list = []
        # Rows, true total and true count all come from SQL. The total is a SUM over
        # every dossier, so capping the displayed rows cannot understate what is owed.
        rec_rows, self.total_receivables, self.receivables_total_count = reception.get_receivables(
            limit=self.REC_ROW_LIMIT)
        for cs in rec_rows:
                tot = float(cs.get("total_amount") or 0.0)
                av = float(cs.get("avance_amount") or 0.0)
                rem = float(cs.get("reste") or 0.0)
                cid = cs.get("client_id") or ""
                client_name_r = cs.get("client_name") or ("Client inconnu" if is_fr else "حريف غير معروف")
                phone_r = cs.get("client_phone") or "—"
                case_id_r = cs.get("case_id", "")
                self.receivables_list.append({
                    "Dossier": case_id_r,
                    "Client": client_name_r,
                    "Téléphone": phone_r,
                    "Total": tot,
                    "Payé": av,
                    "Reste": rem,
                    # detail-panel fields (not shown as columns — see REC_COLUMNS)
                    "case_id": case_id_r,
                    "client_id": cid,
                    "client_name": client_name_r,
                    "phone": phone_r,
                    "service_type": cs.get("service_type", "—"),
                    "title": cs.get("title", "—"),
                    "total": tot,
                    "avance": av,
                    "reste": rem,
                    "status": cs.get("payment_status", "—"),
                    "created_at": cs.get("created_at", "—"),
                })
        # The detail panel indexes the same rows; no second copy.
        self._rec_raw_data = self.receivables_list

        # Net Profit
        self.net_profit = self.total_inflows - self.total_expenses - self.total_salaries

        # Reset detail panel when data refreshes
        if hasattr(self, 'receivables_detail_frame'):
            self.receivables_detail_frame.setVisible(False)

        # 6. Update UI Components
        self.update_kpi_cards()
        self.update_tables()

    def update_kpi_cards(self):
        # Update values
        self.kpi_widgets["recettes"][1].setText(f"{self.total_inflows:.3f} DT")
        self.kpi_widgets["depenses"][1].setText(f"{self.total_expenses:.3f} DT")
        self.kpi_widgets["salaires"][1].setText(f"{self.total_salaries:.3f} DT")
        self.kpi_widgets["net"][1].setText(f"{self.net_profit:.3f} DT")
        self.kpi_widgets["creances"][1].setText(f"{self.total_receivables:.3f} DT")

    def update_tables(self):
        is_fr = self.lang == "fr"

        # 1. Inflows Table Model
        inflow_headers = [
            "Source", "N° Dossier", "Client", "Acompte (DT)", "Total (DT)", "Date", "Notes"
        ] if is_fr else [
            "المصدر", "رقم الملف", "الحريف", "المبلغ التسبقة", "الإجمالي", "التاريخ", "ملاحظات"
        ]
        self._set_table_model(self.inflows_table, FinanceTableModel(self.inflows_list, inflow_headers, self.lang))

        # 2. Expenses Table Model
        expense_headers = [
            "ID", "Description", "Montant (DT)", "Catégorie", "Date", "Justificatif"
        ] if is_fr else [
            "رمز المصروف", "وصف المصروف", "المبلغ", "الصنف", "التاريخ", "الوصل"
        ]
        # The receipt photo was written to the database and then never displayed:
        # there was no column for it and formatted_expenses did not carry the path.
        # The notary attached a justificatif and had no way to see it had worked.
        formatted_expenses = []
        for e in self.filtered_expenses:
            ph = (e.get("photo_path") or "").strip()
            has = bool(ph) and os.path.exists(ph)
            formatted_expenses.append({
                "id": e.get("id", ""),
                "description": e.get("description", ""),
                "amount": float(e.get("amount") or 0.0),
                "category": self.clean_cat_lang(e.get("category", ""), is_fr),
                "created_at": str(e.get("created_at", "")).split()[0],
                "receipt": (("📎 " + ("Voir" if is_fr else "عرض")) if has
                            else ("— manquant" if is_fr else "— مفقود") if ph
                            else ("—" if is_fr else "—")),
                "_photo_path": ph,
            })
        self._set_table_model(self.expenses_table, FinanceTableModel(formatted_expenses, expense_headers, self.lang))

        # 3. Salaries Table Model
        salary_headers = [
            "ID", "Employé", "Montant (DT)", "Notes / Mois", "Date", "Justificatif"
        ] if is_fr else [
            "رمز الدفعة", "اسم الموظف", "المبلغ", "ملاحظات", "التاريخ", "الوصل"
        ]
        formatted_salaries = []
        for sal in self.filtered_salaries:
            ph = (sal.get("photo_path") or "").strip()
            has = bool(ph) and os.path.exists(ph)
            formatted_salaries.append({
                "id": sal.get("id", ""),
                "employee_name": sal.get("employee_name", ""),
                "amount": float(sal.get("amount") or 0.0),
                "notes": sal.get("notes", ""),
                "payment_date": str(sal.get("payment_date", "")).split()[0],
                "receipt": (("📎 " + ("Voir" if is_fr else "عرض")) if has
                            else ("— manquant" if is_fr else "— مفقود") if ph
                            else "—"),
                "_photo_path": ph,
            })
        self._set_table_model(self.salaries_table, FinanceTableModel(formatted_salaries, salary_headers, self.lang))

        # 4. Receivables Table Model
        receivable_headers = [
            "N° Dossier", "Client", "Téléphone", "Total (DT)", "Payé (DT)", "Reste à payer (DT)"
        ] if is_fr else [
            "رقم الملف", "اسم الحريف", "الهاتف", "الإجمالي", "المدفوع", "المتبقي للدفع"
        ]
        # Explicit keys: the receivable rows carry detail fields too, so column order
        # must not be inferred from dict order.
        self._set_table_model(self.receivables_table, FinanceTableModel(
            self.receivables_list, receivable_headers, self.lang,
            keys=self.REC_COLUMNS))

        # Say plainly when the list is capped. The total above it is a SQL SUM over
        # every dossier, so the figure is complete even when the listing is not.
        shown = len(self.receivables_list)
        total_rows = getattr(self, "receivables_total_count", shown)
        if hasattr(self, "rec_scope_lbl"):
            if shown < total_rows:
                self.rec_scope_lbl.setText(
                    f"عرض {shown:,} من {total_rows:,} ملف — المبلغ الإجمالي أعلاه محسوب على كامل الملفات"
                    if not is_fr else
                    f"Affichage de {shown:,} sur {total_rows:,} dossiers — le total ci-dessus couvre l'ensemble")
                self.rec_scope_lbl.setStyleSheet("color: #b45309; font-size: 11px; font-weight: bold;")
            else:
                self.rec_scope_lbl.setText(f"{total_rows:,} " + ("dossiers" if is_fr else "ملف"))
                self.rec_scope_lbl.setStyleSheet("color: #475569; font-size: 11px;")

    def save_expense(self):
        desc = self.exp_desc_input.text().strip()
        amt = self.exp_amt_spin.value()
        cat = self.exp_cat_combo.currentText()
        is_fr = self.lang == "fr"

        if not desc or amt <= 0:
            QMessageBox.warning(self, "Erreur" if is_fr else "خطأ", "La description et le montant sont requis." if is_fr else "وصف المصروف والمبلغ ضروريين.")
            return

        # Save photo proof if selected
        p_path = ""
        if self.exp_photo_path:
            try:
                from config import DOCUMENTS_DIR
                import time
                cdir = DOCUMENTS_DIR / "expenses"
                cdir.mkdir(parents=True, exist_ok=True)
                pf = cdir / f"Exp_{reception.unique_file_stamp()}_{Path(self.exp_photo_path).name}"
                import shutil
                shutil.copy(self.exp_photo_path, pf)
                p_path = str(pf)
            except Exception as copy_err:
                # (a) The notary picked a receipt for this expense. Swallowing the
                # failure recorded the expense with NO proof attached and said
                # nothing, which is exactly the evidence an audit would ask for.
                QMessageBox.warning(
                    self, "Justificatif" if self.lang == "fr" else "الوصل",
                    (f"La dépense sera enregistrée, mais le justificatif n'a PAS "
                     f"pu être copié.\n\n{copy_err}" if self.lang == "fr" else
                     f"سيتم تسجيل المصروف، لكن لم يتم نسخ الوصل!\n\n{copy_err}"))

        try:
            import licensing
            success = reception.add_expense(desc, cat, amt, photo_path=p_path)
        except (licensing.LicenceRequired, Exception) as exp_err:
            if "LicenceRequired" in type(exp_err).__name__ or "licence" in str(exp_err).lower():
                QMessageBox.warning(
                    self, "Licence requise" if is_fr else "ترخيص مطلوب",
                    "Cette fonctionnalité nécessite une licence active.\nVeuillez تفعيل الترخيص من الإعدادات." if is_fr else
                    "يتطلب هذا الإجراء ترخيصاً نَشِطاً. يرجى تفعيل الترخيص من الإعدادات.")
            else:
                QMessageBox.critical(self, "Erreur" if is_fr else "خطأ", f"{exp_err}")
            return

        if success:
            QMessageBox.information(self, "Succès" if is_fr else "نجاح", "Dépense enregistrée !" if is_fr else "تم تسجيل المصروف بنجاح!")
            self.exp_desc_input.clear()
            self.exp_amt_spin.setValue(0.0)
            self.exp_photo_path = ""
            if hasattr(self, 'exp_photo_display'):
                self.exp_photo_display.setText("لم يُختَر وصل بعد" if self.lang != "fr" else "Aucun justificatif")
            self.load_data()

    # -- correcting a recorded row ------------------------------------------
    # A right-click menu is not somewhere a notary looks for a button, so each
    # correctable table carries a visible bar underneath it. The buttons act on
    # the selected row; the same actions are on the context menu for anyone who
    # right-clicks first.

    def _retitle_row_action_bars(self):
        """Relabels the Modifier / Justificatif / Supprimer bars.

        These buttons are built once, so without this they keep the language
        the page happened to open in and end up sitting in an Arabic screen
        with French captions.
        """
        is_fr = self.lang == "fr"
        for kind in ("expenses", "salaries"):
            b = getattr(self, "btn_%s_open" % kind, None)
            if b is not None:
                b.setText("📎 " + ("Ouvrir le justificatif" if is_fr else "فتح الوصل"))
            b = getattr(self, "btn_%s_edit" % kind, None)
            if b is not None:
                b.setText("✏️ " + ("Modifier la ligne" if is_fr else "تعديل السطر"))
            b = getattr(self, "btn_%s_delete" % kind, None)
            if b is not None:
                b.setText("🗑 " + ("Supprimer" if is_fr else "حذف"))
            l = getattr(self, "lbl_%s_bar_hint" % kind, None)
            if l is not None:
                l.setText("Sélectionnez une ligne, puis :" if is_fr
                          else "اختر سطرا ثم :")

    def build_row_action_bar(self, kind, on_edit, on_open, on_delete):
        """The Modifier / Justificatif / Supprimer bar under a finance table."""
        is_fr = self.lang == "fr"
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.setContentsMargins(0, 6, 0, 0)

        hint = QLabel("Sélectionnez une ligne, puis :" if is_fr
                      else "اختر سطرا ثم :", self)
        hint.setStyleSheet("color:#64748b; font-size:12px;")
        bar.addWidget(hint)
        bar.addStretch(1)

        btn_open = QPushButton("📎 " + ("Ouvrir le justificatif" if is_fr
                                        else "فتح الوصل"), self)
        btn_open.setMinimumHeight(34)
        btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open.clicked.connect(on_open)
        bar.addWidget(btn_open)

        btn_edit = QPushButton("✏️ " + ("Modifier la ligne" if is_fr
                                        else "تعديل السطر"), self)
        btn_edit.setMinimumHeight(34)
        btn_edit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_edit.setStyleSheet(
            "QPushButton { background-color:#2563eb; color:white; font-weight:700;"
            " border:none; border-radius:6px; padding:5px 14px; }"
            "QPushButton:hover { background-color:#1d4ed8; }"
            "QPushButton:disabled { background-color:#cbd5e1; color:#f8fafc; }")
        btn_edit.clicked.connect(on_edit)
        # Correcting a figure already in the books is the notary's act, not the
        # secretary's. The button is hidden rather than greyed out for a role
        # that will never have it, and reception refuses the call regardless.
        allowed = permissions.has(Cap.EDIT_FINANCE_ENTRY)
        btn_edit.setEnabled(allowed)
        btn_edit.setVisible(allowed)
        bar.addWidget(btn_edit)

        btn_del = QPushButton("🗑 " + ("Supprimer" if is_fr else "حذف"), self)
        btn_del.setMinimumHeight(34)
        btn_del.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_del.clicked.connect(on_delete)
        bar.addWidget(btn_del)

        setattr(self, "btn_%s_open" % kind, btn_open)
        setattr(self, "btn_%s_edit" % kind, btn_edit)
        setattr(self, "btn_%s_delete" % kind, btn_del)
        setattr(self, "lbl_%s_bar_hint" % kind, hint)
        return bar

    def _selected_row(self, table):
        """The selected row index, or -1 with a prompt if there is none."""
        idx = table.currentIndex()
        if idx is not None and idx.isValid():
            return idx.row()
        is_fr = self.lang == "fr"
        QMessageBox.information(
            self, "Aucune ligne" if is_fr else "لم يقع اختيار سطر",
            "Sélectionnez d'abord une ligne dans le tableau."
            if is_fr else "اختر أولا سطرا من الجدول.")
        return -1

    def on_row_activated(self, table, index):
        """
        Double-click: the Justificatif column opens the receipt, anywhere else
        opens the correction form. Opening a receipt is the one action every
        role may take, so it is not gated.
        """
        if not index.isValid():
            return
        model = table.model()
        last = (model.columnCount() - 1) if model else -1
        if index.column() == last:
            self.open_receipt(table, index.row())
            return
        if not permissions.has(Cap.EDIT_FINANCE_ENTRY):
            self.open_receipt(table, index.row())
            return
        if table is self.expenses_table:
            self.edit_expense_row(index.row())
        elif table is self.salaries_table:
            self.edit_salary_row(index.row())

    def open_selected_receipt(self, table):
        row = self._selected_row(table)
        if row >= 0:
            self.open_receipt(table, row)

    def _row_dict(self, table, row):
        model = table.model()
        data = getattr(model, "_data", None) or getattr(model, "data_rows", None)
        try:
            return dict(data[row])
        except Exception:
            return {}

    def _refuse_edit(self):
        is_fr = self.lang == "fr"
        QMessageBox.warning(
            self, "Accès refusé" if is_fr else "الدخول مرفوض",
            "La correction d'une écriture est réservée au notaire."
            if is_fr else "تصحيح القيود مخصص للأستاذ فقط.")

    def edit_selected_expense(self):
        row = self._selected_row(self.expenses_table)
        if row >= 0:
            self.edit_expense_row(row)

    def edit_expense_row(self, row):
        if not permissions.has(Cap.EDIT_FINANCE_ENTRY):
            self._refuse_edit()
            return
        from ui.dialogs.edit_entry_dialog import EditEntryDialog
        rec = self._row_dict(self.expenses_table, row)
        if not rec:
            return
        exp_id = rec.get("id")
        raw = next((e for e in self.filtered_expenses
                    if str(e.get("id")) == str(exp_id)), {})
        fields = [
            ("description", "Description", "وصف المصروف", "text",
             raw.get("description", "")),
            ("amount", "Montant (DT)", "المبلغ", "amount", raw.get("amount", 0.0)),
            ("category", "Catégorie", "الصنف", "text", raw.get("category", "")),
        ]
        dlg = EditEntryDialog(self, "Corriger la dépense", "تصحيح المصروف",
                              fields, self.lang, receipt=(raw.get("photo_path") or ""))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        try:
            ok = reception.update_expense(
                int(exp_id), v["description"], v["category"],
                float(v["amount"]), v.get("_receipt"))
        except PermissionError:
            self._refuse_edit()
            return
        self._report_edit(ok)

    def edit_selected_salary(self):
        row = self._selected_row(self.salaries_table)
        if row >= 0:
            self.edit_salary_row(row)

    def edit_salary_row(self, row):
        if not permissions.has(Cap.EDIT_FINANCE_ENTRY):
            self._refuse_edit()
            return
        from ui.dialogs.edit_entry_dialog import EditEntryDialog
        rec = self._row_dict(self.salaries_table, row)
        if not rec:
            return
        sal_id = rec.get("id")
        raw = next((x for x in self.filtered_salaries
                    if str(x.get("id")) == str(sal_id)), {})
        fields = [
            ("employee_name", "Employé", "اسم الموظف", "text",
             raw.get("employee_name", "")),
            ("amount", "Montant (DT)", "المبلغ", "amount", raw.get("amount", 0.0)),
            ("notes", "Notes / Mois", "ملاحظات", "text", raw.get("notes", "")),
        ]
        dlg = EditEntryDialog(self, "Corriger le salaire", "تصحيح الأجر",
                              fields, self.lang, receipt=(raw.get("photo_path") or ""))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        try:
            ok = reception.update_salary(
                int(sal_id), v["employee_name"], float(v["amount"]),
                v["notes"], v.get("_receipt"))
        except PermissionError:
            self._refuse_edit()
            return
        self._report_edit(ok)

    def _report_edit(self, ok):
        is_fr = self.lang == "fr"
        if ok:
            QMessageBox.information(
                self, "Corrigé" if is_fr else "تم التصحيح",
                "La ligne a été corrigée et la modification enregistrée au journal."
                if is_fr else "تم تصحيح السطر وتسجيل التعديل بالسجل.")
            self.load_data()
        else:
            QMessageBox.warning(
                self, "Échec" if is_fr else "فشل",
                "La correction n'a pas pu être enregistrée."
                if is_fr else "لم يقع تسجيل التصحيح.")

    def delete_selected_expense(self):
        row = self._selected_row(self.expenses_table)
        if row >= 0:
            rec = self._row_dict(self.expenses_table, row)
            if rec.get("id") not in (None, ""):
                self.delete_expense_action(int(rec["id"]))

    def delete_selected_salary(self):
        row = self._selected_row(self.salaries_table)
        if row >= 0:
            rec = self._row_dict(self.salaries_table, row)
            if rec.get("id") not in (None, ""):
                self.delete_salary_action(int(rec["id"]))

    def _row_photo_path(self, table, row) -> str:
        """The receipt path stored alongside a row, if any."""
        model = table.model()
        data = getattr(model, "_data", None) or getattr(model, "data_rows", None)
        try:
            return (data[row].get("_photo_path") or "").strip()
        except Exception:
            return ""

    def open_receipt(self, table, row):
        """
        Opens the attached receipt in the system viewer.

        The photo was being written to the database and to disk and then never
        surfaced anywhere, so the notary had no way to tell an attached
        justificatif from a missing one.
        """
        is_fr = self.lang == "fr"
        path = self._row_photo_path(table, row)
        if not path:
            QMessageBox.information(
                self, "Justificatif" if is_fr else "الوصل",
                "Aucun justificatif n'est attaché à cette ligne."
                if is_fr else "لا يوجد وصل مرفق بهذا السطر.")
            return
        if not os.path.exists(path):
            QMessageBox.warning(
                self, "Justificatif" if is_fr else "الوصل",
                (f"Le justificatif est introuvable sur le disque :\n{path}"
                 if is_fr else f"الوصل غير موجود على القرص :\n{path}"))
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def show_expenses_context_menu(self, point):
        index = self.expenses_table.indexAt(point)
        if not index.isValid():
            return
        
        is_fr = self.lang == "fr"
        menu = QMenu(self)

        # Get exp ID
        row = index.row()
        model = self.expenses_table.model()
        exp_id = int(model.index(row, 0).data())

        view_action = QAction("Ouvrir le justificatif" if is_fr else "فتح الوصل", menu)
        view_action.setEnabled(bool(self._row_photo_path(self.expenses_table, row)))
        view_action.triggered.connect(
            lambda: self.open_receipt(self.expenses_table, row))
        menu.addAction(view_action)

        edit_action = QAction("Modifier cette dépense" if is_fr else "تعديل هذا المصروف", menu)
        edit_action.setEnabled(permissions.has(Cap.EDIT_FINANCE_ENTRY))
        edit_action.triggered.connect(lambda: self.edit_expense_row(row))
        menu.addAction(edit_action)
        menu.addSeparator()

        delete_action = QAction("Supprimer la dépense" if is_fr else "حذف المصروف", menu)
        delete_action.triggered.connect(lambda: self.delete_expense_action(exp_id))
        menu.addAction(delete_action)
        menu.exec(QCursor.pos() if hasattr(self, "cursor") else QCursor.pos())

    def delete_expense_action(self, exp_id):
        is_fr = self.lang == "fr"
        reply = QMessageBox.question(
            self, "Confirmation",
            f"Voulez-vous supprimer la dépense ID: {exp_id} ?" if is_fr else f"هل تريد بالتأكيد حذف هذا المصروف؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if reception.delete_expense(exp_id):
                self.load_data()

    def save_salary(self):
        name = self.sal_name_input.text().strip()
        amt = self.sal_amt_spin.value()
        notes = self.sal_note_input.text().strip()
        is_fr = self.lang == "fr"

        if not name or amt <= 0:
            QMessageBox.warning(self, "Erreur" if is_fr else "خطأ", "Le nom et le montant sont requis." if is_fr else "اسم العون والمبلغ ضروريين.")
            return

        # Save salary photo proof if selected
        sp_path = ""
        if self.sal_photo_path:
            try:
                from config import DOCUMENTS_DIR
                import time
                cdir = DOCUMENTS_DIR / "salaries"
                cdir.mkdir(parents=True, exist_ok=True)
                spf = cdir / f"Sal_{reception.unique_file_stamp()}_{Path(self.sal_photo_path).name}"
                import shutil
                shutil.copy(self.sal_photo_path, spf)
                sp_path = str(spf)
            except Exception as copy_err:
                # (a) Same as the expense proof above.
                QMessageBox.warning(
                    self, "Justificatif" if self.lang == "fr" else "الوصل",
                    (f"Le salaire sera enregistré, mais le justificatif n'a PAS "
                     f"pu être copié.\n\n{copy_err}" if self.lang == "fr" else
                     f"سيتم تسجيل الأجر، لكن لم يتم نسخ الوصل!\n\n{copy_err}"))

        success = reception.add_salary(name, "Personnel", amt, notes, photo_path=sp_path)
        if success:
            QMessageBox.information(self, "Succès" if is_fr else "نجاح", "Salaire enregistré !" if is_fr else "تم تسجيل الراتب بنجاح!")
            self.sal_name_input.clear()
            self.sal_amt_spin.setValue(0.0)
            self.sal_note_input.clear()
            self.sal_photo_path = ""
            if hasattr(self, 'sal_photo_display'):
                self.sal_photo_display.setText("لم يُختَر وصل بعد" if self.lang != "fr" else "Aucun justificatif")
            self.load_data()

    def show_salaries_context_menu(self, point):
        index = self.salaries_table.indexAt(point)
        if not index.isValid():
            return
        
        is_fr = self.lang == "fr"
        menu = QMenu(self)

        # Get salary ID
        row = index.row()
        model = self.salaries_table.model()
        sal_id = int(model.index(row, 0).data())

        view_action = QAction("Ouvrir le justificatif" if is_fr else "فتح الوصل", menu)
        view_action.setEnabled(bool(self._row_photo_path(self.salaries_table, row)))
        view_action.triggered.connect(
            lambda: self.open_receipt(self.salaries_table, row))
        menu.addAction(view_action)

        edit_action = QAction("Modifier ce salaire" if is_fr else "تعديل هذا الأجر", menu)
        edit_action.setEnabled(permissions.has(Cap.EDIT_FINANCE_ENTRY))
        edit_action.triggered.connect(lambda: self.edit_salary_row(row))
        menu.addAction(edit_action)
        menu.addSeparator()

        delete_action = QAction("Supprimer le salaire" if is_fr else "حذف الراتب", menu)
        delete_action.triggered.connect(lambda: self.delete_salary_action(sal_id))
        menu.addAction(delete_action)
        menu.exec(QCursor.pos())

    def delete_salary_action(self, sal_id):
        is_fr = self.lang == "fr"
        reply = QMessageBox.question(
            self, "Confirmation",
            f"Voulez-vous supprimer le salaire ID: {sal_id} ?" if is_fr else f"هل تريد بالتأكيد حذف هذا الراتب؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if reception.delete_salary(sal_id):
                self.load_data()

    def _render_access_denied(self):
        """Blanks every figure this page holds and says why."""
        is_fr = self.lang == "fr"
        self.inflows_list = []
        self.total_inflows = 0.0
        self.total_receivables = 0.0
        self.receivables_total_count = 0
        for attr in ("total_expenses", "total_salaries", "net_profit"):
            if hasattr(self, attr):
                setattr(self, attr, 0.0)
        msg = ("Section réservée au notaire." if is_fr
               else "هذا القسم مخصص للأستاذ فقط.")
        for name in ("summary_label", "status_label", "period_label"):
            w = getattr(self, name, None)
            if w is not None:
                try:
                    w.setText(msg)
                except (AttributeError, RuntimeError):
                    # (c) Safe. The label may not exist on this build of the
                    # page, or may already be destroyed; the figures above have
                    # been blanked either way, which is the part that matters.
                    pass

    def _refuse_export(self) -> bool:
        """True when the export must not proceed."""
        if permissions.has(Cap.EXPORT_FINANCE):
            return False
        is_fr = self.lang == "fr"
        QMessageBox.warning(
            self, "Accès refusé" if is_fr else "الدخول مرفوض",
            ("L'export du rapport financier est réservé au notaire."
             if is_fr else "تصدير التقرير المالي مخصص للأستاذ فقط."))
        return True

    def export_excel(self):
        if self._refuse_export():
            return
        # Convert inflows to DataFrame and trigger save dialog
        if not self.inflows_list:
            QMessageBox.warning(self, "Export", "Aucune donnée à exporter." if self.lang == "fr" else "لا توجد مداخيل لتصديرها.")
            return

        # pandas costs ~3.5 s to import and is needed by this one line, so it loads
        # here rather than the first time the page is opened.
        import pandas as pd
        df = pd.DataFrame(self.inflows_list)
        excel_bytes = create_executive_excel(df, sheet_name='Comptabilite')

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer sous / تصدير",
            f"Rapport_Financier_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx",
            "Fichiers Excel (*.xlsx)"
        )
        if file_path:
            try:
                with open(file_path, "wb") as f:
                    f.write(excel_bytes)
                QMessageBox.information(self, "Export", "Fichier exporté avec succès !" if self.lang == "fr" else "تم تصدير الملف بنجاح!")
            except Exception as e:
                QMessageBox.critical(self, "Export", f"Erreur lors de l'enregistrement: {e}")

    def export_pdf(self):
        if self._refuse_export():
            return
        # Generate real PDF using core/pdf_generator.py (Requirement 1)
        is_fr = self.lang == "fr"
        start_str, end_str = self.get_period_dates()
        
        try:
            start_date_fmt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y")
            end_date_fmt = datetime.datetime.now().strftime("%d/%m/%Y")
            
            pdf_bytes = pdf_generator.generate_pdf_bilan(
                start_date_str=start_date_fmt,
                end_date_str=end_date_fmt,
                tot_inflows=self.total_inflows,
                tot_expenses=self.total_expenses,
                tot_salaries=self.total_salaries,
                net_result=self.net_profit,
                tot_receivables=self.total_receivables,
                inflows_list=self.inflows_list,
                expenses_list=self.filtered_expenses,
                salaries_list=self.filtered_salaries,
                receivables_list=self.receivables_list
            )
            
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Enregistrer sous / تصدير",
                f"Bilan_Financier_Notarial_{datetime.datetime.now().strftime('%Y%m%d')}.pdf",
                "Fichiers PDF (*.pdf)"
            )
            if file_path:
                with open(file_path, "wb") as f:
                    f.write(pdf_bytes)
                QMessageBox.information(self, "Export PDF", "Bilan PDF généré et enregistré !" if is_fr else "تم توليد وتنزيل ملف التقرير PDF بنجاح!")
        except Exception as e:
            QMessageBox.critical(self, "Export PDF", f"Échec de génération PDF: {e}" if is_fr else f"خطأ في توليد PDF: {e}")

    # ── New methods added in audit pass ─────────────────────────────────────

    def filter_inflows(self, query=""):
        """Filter the inflows table based on the search field."""
        q = query.strip().lower()
        filtered = self.inflows_list if not q else [
            row for row in self.inflows_list
            if any(q in str(v).lower() for v in row.values())
        ]
        is_fr = self.lang == "fr"
        headers = [
            "Source", "N° Dossier", "Client", "Acompte (DT)", "Total (DT)", "Date", "Notes"
        ] if is_fr else [
            "المصدر", "رقم الملف", "الحريف", "المبلغ التسبقة", "الإجمالي", "التاريخ", "ملاحظات"
        ]
        self._set_table_model(self.inflows_table, FinanceTableModel(filtered, headers, self.lang))

    def browse_expense_photo(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Photo / Justificatif", "", "Fichiers (*.jpg *.jpeg *.png *.pdf)"
        )
        if fp:
            self.exp_photo_path = fp
            name = Path(fp).name
            self.exp_photo_display.setText(name[:40] + "..." if len(name) > 40 else name)

    def browse_salary_photo(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Photo / Justificatif", "", "Fichiers (*.jpg *.jpeg *.png *.pdf)"
        )
        if fp:
            self.sal_photo_path = fp
            name = Path(fp).name
            self.sal_photo_display.setText(name[:40] + "..." if len(name) > 40 else name)

    def on_receivable_clicked(self, index):
        """Shows the detail panel when a receivables row is clicked."""
        if not index.isValid() or index.row() >= len(self._rec_raw_data):
            return

        rec = self._rec_raw_data[index.row()]
        is_fr = self.lang == "fr"

        self._selected_rec_client_id = rec.get("client_id", "")
        self._selected_rec_case_id = str(rec.get("case_id", ""))

        self.rec_det_title.setText(
            f" {'Dossier N°' if is_fr else 'ملف رقم'} {self._selected_rec_case_id}"
        )

        self.rec_col1.setText(
            f" {'Client' if is_fr else 'الحريف'} : {rec.get('client_name', '—')}\n"
            f" {'Tél' if is_fr else 'الهاتف'} : {rec.get('phone', '—')}"
        )
        self.rec_col2.setText(
            f" {'Type' if is_fr else 'نوع العقد'} : {rec.get('service_type', '—')}\n"
            f" {'Objet' if is_fr else 'الموضوع'} : {rec.get('title', '—')}\n"
            f" {'Date' if is_fr else 'التاريخ'} : {str(rec.get('created_at', '—')).split()[0]}"
        )

        tot = rec.get("total", 0.0)
        av = rec.get("avance", 0.0)
        rem = rec.get("reste", 0.0)
        self.rec_col3.setText(
            f" {'Total' if is_fr else 'الإجمالي'} : {tot:.3f} DT\n"
            f" {'Payé' if is_fr else 'المدفوع'} : {av:.3f} DT\n"
            f" {'Reste' if is_fr else 'المتبقي'} : {rem:.3f} DT"
        )

        self.receivables_detail_frame.setVisible(True)

    def _open_fiche_from_receivables(self):
        if self._selected_rec_client_id:
            self.open_client_fiche.emit(self._selected_rec_client_id)
        else:
            QMessageBox.information(
                self, "Navigation",
                "Impossible de trouver l'ID client pour la navigation." if self.lang == "fr"
                else "لم يُعثَر على معرف الحريف للتنقل."
            )

    def clean_cat_lang(self, val, is_fr):
        if not val or not isinstance(val, str):
            return val
        if is_fr:
            if "مستلزمات" in val: return "Fournitures"
            if "كراء" in val: return "Loyer & Charges"
            if "تجهيزات" in val: return "Matériel"
            if "أداءات" in val: return "Taxes & Impôts"
            if "مصاريف أخرى" in val: return "Autre"
        return val

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "tabs") and self.tabs is not None:
            self.tabs.setCurrentIndex(0)

    # Slot for language update from parent
    def update_language(self, lang_code):
        self.lang = lang_code
        self.update_translations()
        self.load_data()

