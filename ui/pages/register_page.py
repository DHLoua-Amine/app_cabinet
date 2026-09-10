from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDateEdit,
    QComboBox, QPushButton, QTableView, QHeaderView, QMenu, QMessageBox, QFrame, QScrollArea, QFileDialog
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QDate
from PySide6.QtGui import QCursor, QAction

# Import business logic
import reception
import permissions
from permissions import Cap
import auth
from ui.components.calendar_utils import configure_calendar
from ui.components.export_thread import run_export_with_progress

class CaseTableModel(QAbstractTableModel):
    def __init__(self, data=None, lang="ar", parent=None):
        super().__init__(parent)
        self._data = data or []
        self.lang = lang
        self.update_headers()

    def update_headers(self):
        is_fr = self.lang == "fr"
        if is_fr:
            self.headers = [
                "N° Dossier", "Nom du Client", "Type de Contrat",
                "Objet du Contrat", "Statut du Dossier", "Date de Création"
            ]
        else:
            self.headers = [
                "رقم الملف", "اسم الحريف", "نوع العقد",
                "موضوع العقد", "مآل الملف", "تاريخ الإنجاز"
            ]

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._data)):
            return None

        row_data = self._data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            is_fr = self.lang == "fr"
            if col == 0:
                return str(row_data.get("case_id", ""))
            elif col == 1:
                return str(row_data.get("client_name", "Inconnu / غير معروف"))
            elif col == 2:
                # Clean service type language based on selection
                val = row_data.get("service_type", "")
                return self.clean_service_type_lang(val, is_fr)
            elif col == 3:
                val = row_data.get("title", "")
                return self.clean_val_lang(val, is_fr)
            elif col == 4:
                val = row_data.get("status", "")
                return self.clean_val_lang(val, is_fr)
            elif col == 5:
                raw_date = row_data.get("created_at", "")
                if raw_date:
                    return str(raw_date).split()[0]
                return ""
                
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            # Align right for Arabic, left for French
            if self.lang == "ar":
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return None

    def clean_service_type_lang(self, val, is_fr):
        if not val or not isinstance(val, str):
            return val
        if "(" in val and ")" in val:
            ar_part = val.split("(")[0].strip()
            fr_part = val.split("(")[1].split(")")[0].strip()
            return fr_part if is_fr else ar_part
        if " / " in val:
            parts = val.split(" / ")
            return parts[0].strip() if is_fr else parts[-1].strip()
        return val

    def clean_val_lang(self, val, is_fr):
        if not val or not isinstance(val, str):
            return val
        if is_fr:
            if "جديد" in val: return "Nouveau"
            if "إنجاز" in val: return "En cours"
            if "توقيع" in val: return "En attente de signature"
            if "تام" in val: return "Finalisé & Archivé"
        else:
            if " / " in val:
                return val.split(" / ")[-1].strip()
        return val


class RegisterPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang = auth.session_state.lang
        self.all_cases = []
        self.filtered_cases = []
        self.page_size = 12
        self.current_page = 1
        
        self.init_ui()
        self.load_data()

    def init_ui(self):
        # Base layout wrapped in QScrollArea for web-like scrolling
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        self.scroll_content = QWidget()
        self.scroll_area.setWidget(self.scroll_content)
        
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setContentsMargins(30, 30, 30, 30)
        self.main_layout.setSpacing(15)
        
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.scroll_area)

        # ── 1. Page Header & Title ───────────────────────────────────────────

        # ── 2. Summary KPI Cards ─────────────────────────────────────────────
        self.kpi_layout = QHBoxLayout()
        self.kpi_layout.setSpacing(20)

        # Total Cards
        self.card_total = QFrame(self)
        self.card_total.setObjectName("CardTotal")
        self.card_total.setStyleSheet("QFrame#CardTotal { background-color: #ffffff; border: 1px solid #cbd5e1; border-left: 5px solid #3b82f6; border-radius: 8px; }")
        total_lay = QVBoxLayout(self.card_total)
        total_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_total_title = QLabel("Total des Dossiers", self.card_total)
        self.lbl_total_title.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 700;")
        self.lbl_total_val = QLabel("0", self.card_total)
        self.lbl_total_val.setStyleSheet("font-size: 28px; font-weight: 800; color: #0f172a;")
        total_lay.addWidget(self.lbl_total_title)
        total_lay.addWidget(self.lbl_total_val)
        self.kpi_layout.addWidget(self.card_total)

        # In progress Card
        self.card_progress = QFrame(self)
        self.card_progress.setObjectName("CardProgress")
        self.card_progress.setStyleSheet("QFrame#CardProgress { background-color: #ffffff; border: 1px solid #cbd5e1; border-left: 5px solid #f59e0b; border-radius: 8px; }")
        prog_lay = QVBoxLayout(self.card_progress)
        prog_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_prog_title = QLabel("Dossiers actifs (non archivés)", self.card_progress)
        self.lbl_prog_title.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 700;")
        self.lbl_prog_val = QLabel("0", self.card_progress)
        self.lbl_prog_val.setStyleSheet("font-size: 28px; font-weight: 800; color: #f59e0b;")
        prog_lay.addWidget(self.lbl_prog_title)
        prog_lay.addWidget(self.lbl_prog_val)
        self.kpi_layout.addWidget(self.card_progress)

        # Finalized Card
        self.card_final = QFrame(self)
        self.card_final.setObjectName("CardFinal")
        self.card_final.setStyleSheet("QFrame#CardFinal { background-color: #ffffff; border: 1px solid #cbd5e1; border-left: 5px solid #10b981; border-radius: 8px; }")
        final_lay = QVBoxLayout(self.card_final)
        final_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_final_title = QLabel("Dossiers Finalisés", self.card_final)
        self.lbl_final_title.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 700;")
        self.lbl_final_val = QLabel("0", self.card_final)
        self.lbl_final_val.setStyleSheet("font-size: 28px; font-weight: 800; color: #10b981;")
        final_lay.addWidget(self.lbl_final_title)
        final_lay.addWidget(self.lbl_final_val)
        self.kpi_layout.addWidget(self.card_final)

        self.main_layout.addLayout(self.kpi_layout)

        # How many rows the current filter shows. The KPI cards above always
        # describe the whole office; this is the only figure that moves with the
        # filter, and it says so.
        self.lbl_filtered_count = QLabel("", self)
        self.lbl_filtered_count.setStyleSheet("font-size: 12px; color: #64748b;")
        self.main_layout.addWidget(self.lbl_filtered_count)

        # ── 3. Filters Layout Card ───────────────────────────────────────────
        filter_card = QFrame(self)
        filter_card.setProperty("class", "Card")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(15, 10, 15, 10)
        filter_layout.setSpacing(15)

        # Search field
        search_sub_layout = QVBoxLayout()
        self.lbl_search = QLabel("Recherche :", filter_card)
        self.lbl_search.setProperty("class", "FieldLabel")
        self.search_input = QLineEdit(filter_card)
        self.search_input.textChanged.connect(self.apply_filters)
        search_sub_layout.addWidget(self.lbl_search)
        search_sub_layout.addWidget(self.search_input)
        filter_layout.addLayout(search_sub_layout, stretch=2)

        # Date From
        date_from_lay = QVBoxLayout()
        self.lbl_date_from = QLabel("Date Début :", filter_card)
        self.lbl_date_from.setProperty("class", "FieldLabel")
        self.date_from_edit = QDateEdit(filter_card)
        self.date_from_edit.setCalendarPopup(True)
        # Default to 90 days ago
        qdate_from = QDate.currentDate().addDays(-90)
        self.date_from_edit.setDate(qdate_from)
        self.date_from_edit.setDisplayFormat("dd/MM/yyyy")
        configure_calendar(self.date_from_edit)
        # dateChanged carries a QDate; apply_filters() takes none.
        self.date_from_edit.dateChanged.connect(self.on_filter_date_changed)
        date_from_lay.addWidget(self.lbl_date_from)
        date_from_lay.addWidget(self.date_from_edit)
        filter_layout.addLayout(date_from_lay)

        # Date To
        date_to_lay = QVBoxLayout()
        self.lbl_date_to = QLabel("Date Fin :", filter_card)
        self.lbl_date_to.setProperty("class", "FieldLabel")
        self.date_to_edit = QDateEdit(filter_card)
        self.date_to_edit.setCalendarPopup(True)
        self.date_to_edit.setDate(QDate.currentDate())
        self.date_to_edit.setDisplayFormat("dd/MM/yyyy")
        configure_calendar(self.date_to_edit)
        self.date_to_edit.dateChanged.connect(self.on_filter_date_changed)
        date_to_lay.addWidget(self.lbl_date_to)
        date_to_lay.addWidget(self.date_to_edit)
        filter_layout.addLayout(date_to_lay)

        # Type Filter
        type_lay = QVBoxLayout()
        self.lbl_type = QLabel("Type :", filter_card)
        self.lbl_type.setProperty("class", "FieldLabel")
        self.type_combo = QComboBox(filter_card)
        self.type_combo.currentIndexChanged.connect(self.apply_filters)
        type_lay.addWidget(self.lbl_type)
        type_lay.addWidget(self.type_combo)
        filter_layout.addLayout(type_lay)

        # Status Filter
        status_lay = QVBoxLayout()
        self.lbl_status = QLabel("Statut :", filter_card)
        self.lbl_status.setProperty("class", "FieldLabel")
        self.status_combo = QComboBox(filter_card)
        self.status_combo.currentIndexChanged.connect(self.apply_filters)
        status_lay.addWidget(self.lbl_status)
        status_lay.addWidget(self.status_combo)
        filter_layout.addLayout(status_lay)

        # Reset & Export buttons
        reset_lay = QVBoxLayout()
        reset_lay.addStretch()
        
        btn_hlay = QHBoxLayout()
        self.reset_btn = QPushButton("Réinitialiser", filter_card)
        self.reset_btn.setProperty("class", "SecondaryButton")
        self.reset_btn.clicked.connect(self.reset_filters)
        
        self.export_btn = QPushButton("Exporter (Excel)", filter_card)
        self.export_btn.setProperty("class", "SecondaryButton")
        self.export_btn.clicked.connect(self.export_to_excel)
        
        btn_hlay.addWidget(self.reset_btn)
        btn_hlay.addWidget(self.export_btn)
        
        reset_lay.addLayout(btn_hlay)
        filter_layout.addLayout(reset_lay)

        self.main_layout.addWidget(filter_card)

        # ── 4. Main QTableView ───────────────────────────────────────────────
        self.table_view = QTableView(self)
        self.table_view.setMinimumHeight(600)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_context_menu)
        self.table_view.doubleClicked.connect(self.on_table_double_clicked)
        
        # Header configurations
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setAlternatingRowColors(True)

        self.main_layout.addWidget(self.table_view)

        # A right-click menu is not where anyone looks for a button, so the two
        # actions that change a dossier get a visible bar under the table.
        self.row_bar = QHBoxLayout()
        self.row_bar.setSpacing(8)
        self.row_bar.setContentsMargins(0, 6, 0, 0)
        self.lbl_row_bar_hint = QLabel("", self)
        self.lbl_row_bar_hint.setStyleSheet("color:#64748b; font-size:12px;")
        self.row_bar.addWidget(self.lbl_row_bar_hint)
        self.row_bar.addStretch(1)
        self.btn_edit_case = QPushButton("", self)
        self.btn_edit_case.setMinimumHeight(34)
        self.btn_edit_case.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_edit_case.setStyleSheet(
            "QPushButton { background-color:#2563eb; color:white; font-weight:700;"
            " border:none; border-radius:6px; padding:5px 14px; }"
            "QPushButton:hover { background-color:#1d4ed8; }"
            "QPushButton:disabled { background-color:#cbd5e1; color:#f8fafc; }")
        self.btn_edit_case.clicked.connect(self.edit_selected_case)
        _may_edit = permissions.has(Cap.EDIT_DOSSIER)
        self.btn_edit_case.setEnabled(_may_edit)
        self.btn_edit_case.setVisible(_may_edit)
        self.row_bar.addWidget(self.btn_edit_case)

        # Supprimer Dossier button (Admin Only)
        self.btn_delete_case = QPushButton("", self)
        self.btn_delete_case.setMinimumHeight(34)
        self.btn_delete_case.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_delete_case.setStyleSheet(
            "QPushButton { background-color:#dc2626; color:white; font-weight:700;"
            " border:none; border-radius:6px; padding:5px 14px; }"
            "QPushButton:hover { background-color:#b91c1c; }"
            "QPushButton:disabled { background-color:#cbd5e1; color:#f8fafc; }")
        self.btn_delete_case.clicked.connect(self.delete_selected_case)
        _may_delete = permissions.has(Cap.DELETE_DOSSIER)
        self.btn_delete_case.setEnabled(_may_delete)
        self.btn_delete_case.setVisible(_may_delete)
        self.row_bar.addWidget(self.btn_delete_case)

        self.main_layout.addLayout(self.row_bar)
        self._retitle_row_bar()

        # ── 5. Pagination controls ───────────────────────────────────────────
        self.pag_layout = QHBoxLayout()
        self.pag_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.prev_btn = QPushButton("Page Précédente", self)
        self.prev_btn.setProperty("class", "SecondaryButton")
        self.prev_btn.clicked.connect(self.prev_page)

        self.page_label = QLabel("Page 1 sur 1", self)
        self.page_label.setStyleSheet("color: #94a3b8; font-weight: 700; font-size: 13px; margin: 0 20px;")

        self.next_btn = QPushButton("Page Suivante", self)
        self.next_btn.setProperty("class", "SecondaryButton")
        self.next_btn.clicked.connect(self.next_page)

        self.pag_layout.addWidget(self.prev_btn)
        self.pag_layout.addWidget(self.page_label)
        self.pag_layout.addWidget(self.next_btn)
        
        self.main_layout.addLayout(self.pag_layout)

        # Initialize ComboBox choices and translations
        self.update_translations()

    def export_to_excel(self):
        import pandas as pd
        from core.style_utils import create_executive_excel
        if not self.filtered_cases:
            QMessageBox.warning(self, "Export", "Aucun dossier à exporter.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Exporter le Registre", "Registre_Dossiers.xlsx", "Fichiers Excel (*.xlsx)")
        if not file_path:
            return

        rows = list(self.filtered_cases)   # snapshot: the worker must not read live state

        def build(report):
            report(0, len(rows))
            df = pd.DataFrame(rows)
            cols = ["case_id", "client_name", "service_type", "title", "status", "created_at"]
            df = df[[c for c in cols if c in df.columns]]
            report(len(rows) // 2, len(rows))
            data = create_executive_excel(df, sheet_name='Registre')
            report(len(rows), len(rows))
            return data

        # Built on a worker thread so the window keeps repainting during the export.
        self.export_thread = run_export_with_progress(
            self, build, file_path,
            "Export" if self.lang == "fr" else "تصدير",
            (f"Export de {len(rows)} dossiers en cours…" if self.lang == "fr"
             else f"جاري تصدير {len(rows)} ملف…"))
        self.export_thread.finished_ok.connect(
            lambda p: QMessageBox.information(self, "Export", "Registre exporté avec succès !"))
        self.export_thread.failed.connect(
            lambda m: QMessageBox.critical(self, "Erreur", f"Erreur d'exportation: {m}"))

    def update_translations(self):
        is_fr = self.lang == "fr"
        self._retitle_row_bar()
        
        # Stats labels
        # "Dossiers En Cours" counted new + in progress + awaiting signature, which
        # is every dossier that is not archived. The number was useful; the label
        # was not true. The label now matches what is counted.
        # ("الإنجaz" also had the Latin letters "az" typed into the middle of it.)
        self.lbl_total_title.setText("Total des Dossiers" if is_fr else "إجمالي الملفات")
        self.lbl_prog_title.setText("Dossiers actifs (non archivés)" if is_fr
                                    else "ملفات نشطة (غير مؤرشفة)")
        self.lbl_final_title.setText("Dossiers Finalisés" if is_fr else "ملفات تامة ومسجلة")
        self.update_filtered_count_label()

        # Filters labels
        self.lbl_search.setText("Recherche :" if is_fr else "البحث :")
        self.lbl_date_from.setText("Date Début :" if is_fr else "من تاريخ :")
        self.lbl_date_to.setText("Date Fin :" if is_fr else "إلى تاريخ :")
        self.lbl_status.setText("Statut :" if is_fr else "مآل الملف :")
        self.lbl_type.setText("Type :" if is_fr else "النوع :")
        self.reset_btn.setText("Réinitialiser" if is_fr else "إعادة تعيين")

        # Combobox Options (Disconnect signal temporarily to avoid infinite loops)
        self.status_combo.blockSignals(True)
        self.status_combo.clear()
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.status_options = ["Tous les statuts" if is_fr else "جميع مآلات الملفات", "جديد", "قيد الإنجاز", "في انتظار التوقيع", "تام ومسجل"]
        self.type_options = [
            "Tous les types" if is_fr else "جميع أنواع العقود",
            "عقد بيع عقار (دفتر خانة)",
            "عقد بيع عقار (غير مسجل)",
            "عقد وعد بيع",
            "عقد مقاسمة رضائية",
            "عقد مقاسمة قضائية",
            "عقد هبة",
            "حجة وفاة",
            "فريضة تريكة",
            "رفض ميراث",
            "عقد زواج",
            "عقد ترهين عقاري",
            "عقد تنازل",
            "محضر استجواب",
            "شهادة ملكية",
            "توكيل رسمي",
            "عقد كراء",
            "كتب تكميلي",
            "كتب توضيحي",
            "استشارة قانونية"
        ]
        self.status_combo.addItems(self.status_options)
        self.type_combo.addItems(self.type_options)
        self.status_combo.blockSignals(False)
        self.type_combo.blockSignals(False)

        # Pagination buttons
        self.prev_btn.setText("Page Précédente" if is_fr else "الصفحة السابقة")
        self.next_btn.setText("Page Suivante" if is_fr else "الصفحة التالية")

        # Layout direction
        if is_fr:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    def load_data(self):
        # Filtering happens in SQL now (see apply_filters), so the page no longer needs
        # to hold all 20,000 dossiers in Python just to search them.
        self.apply_filters()

    def on_filter_date_changed(self, _qdate=None):
        """Re-filters when a calendar date changes; accepts the QDate the signal sends."""
        self.apply_filters()

    def reset_filters(self):
        self.search_input.clear()
        self.date_from_edit.setDate(QDate.currentDate().addDays(-90))
        self.date_to_edit.setDate(QDate.currentDate())
        self.status_combo.setCurrentIndex(0)
        self.apply_filters()

    def apply_filters(self):
        """
        Filters in SQL rather than looping over every dossier on the UI thread.

        The old loop walked all 20,000 cases per filter change (measured 150–614 ms of
        frozen window each time). SQLite does the same selection against its indexes.
        """
        search_q = self.search_input.text().strip()
        date_from = self.date_from_edit.date().toPython().isoformat()
        date_to = self.date_to_edit.date().toPython().isoformat()

        status = ""
        if self.status_combo.currentIndex() > 0:
            status = self._status_filter_value(self.status_combo.currentText())

        service_type = ""
        if hasattr(self, 'type_combo') and self.type_combo.currentIndex() > 0:
            service_type = self.type_combo.currentText().strip()

        # A read that FAILED is reported; it is not an empty register.
        try:
            self.filtered_cases = reception.search_cases(
                search_text=search_q, status=status, service_type=service_type,
                date_from=date_from, date_to=date_to)
        except reception.DataUnavailable:
            self.filtered_cases = []
            QMessageBox.critical(
                self, "Erreur" if self.lang == "fr" else "خطأ",
                ("Le registre n'a pas pu être lu. Ce n'est PAS un registre "
                 "vide — vérifiez la base de données."
                 if self.lang == "fr" else
                 "تعذّرت قراءة السجل. هذا ليس سجلا فارغا — "
                 "تحقّق من قاعدة البيانات."))
        self.all_cases = self.filtered_cases   # kept for the export snapshot
        self.current_page = 1
        self.update_stats()
        self.update_table_view()

    def _status_filter_value(self, label):
        """
        Maps a translated status label back to what is stored in the database.

        Statuses are written in Arabic; the French labels are display-only, so matching
        the French text against the column would return nothing.
        """
        fr_to_ar = {
            "Nouveau": "جديد",
            "En cours": "قيد الإنجاز",
            "En attente de signature": "في انتظار التوقيع",
            "Finalisé & Archivé": "تام ومسجل",
            "Finalisé": "تام ومسجل",
        }
        return fr_to_ar.get(label.strip(), label.strip())
        self.update_table_view()

    def update_stats(self):
        """
        Fills the three dashboard cards with office-wide figures.

        Two things were wrong here. "Total des Dossiers" was len(filtered_cases),
        so leaving a search in the box silently turned the office total into a
        filtered count under a label that still said "Total" - measured at 2 when
        the office held 5. And "Dossiers En Cours" added new, in-progress and
        awaiting-signature together - measured at 3 when exactly 1 dossier was in
        progress - which is a "not yet archived" figure, not a workload one.

        The cards now describe the whole office and are labelled for what they
        actually count. How many rows the current filter shows is a separate,
        separately-labelled figure below the filters.
        """
        is_fr = self.lang == "fr"
        counts = reception.count_cases_by_status()

        self.lbl_total_val.setText(str(counts.get("total", 0)))
        self.lbl_prog_val.setText(str(counts.get("active", 0)))
        self.lbl_final_val.setText(str(counts.get("finalised", 0)))

        # The breakdown behind "actifs", so the number is not a black box.
        self.card_progress.setToolTip(
            ("Dossiers non archiv\u00e9s : {n} nouveaux, {p} en cours, "
             "{a} en attente de signature.").format(
                n=counts.get("new", 0), p=counts.get("in_progress", 0),
                a=counts.get("awaiting_signature", 0))
            if is_fr else
            ("\u0645\u0644\u0641\u0627\u062a \u063a\u064a\u0631 \u0645\u0624\u0631\u0634\u0641\u0629 : {n} \u062c\u062f\u064a\u062f\u060c {p} \u0642\u064a\u062f \u0627\u0644\u0625\u0646\u062c\u0627\u0632\u060c "
             "{a} \u0641\u064a \u0627\u0646\u062a\u0638\u0627\u0631 \u0627\u0644\u062a\u0648\u0642\u064a\u0639.").format(
                n=counts.get("new", 0), p=counts.get("in_progress", 0),
                a=counts.get("awaiting_signature", 0)))

        self.update_filtered_count_label(counts.get("total", 0))

    def update_filtered_count_label(self, office_total=None):
        """States how many dossiers the current filter shows, and out of how many."""
        lbl = getattr(self, "lbl_filtered_count", None)
        if lbl is None:
            return
        is_fr = self.lang == "fr"
        shown = len(self.filtered_cases)
        if office_total is None:
            office_total = reception.count_cases_by_status().get("total", 0)
        if shown == office_total:
            lbl.setText("Tous les dossiers sont affich\u00e9s." if is_fr
                        else "\u0643\u0644 \u0627\u0644\u0645\u0644\u0641\u0627\u062a \u0645\u0639\u0631\u0648\u0636\u0629.")
            lbl.setStyleSheet("font-size: 12px; color: #64748b;")
        else:
            lbl.setText(
                f"R\u00e9sultats du filtre : {shown} dossier(s) sur {office_total}."
                if is_fr else
                f"\u0646\u062a\u0627\u0626\u062c \u0627\u0644\u0628\u062d\u062b : {shown} \u0645\u0644\u0641 \u0645\u0646 \u0623\u0635\u0644 {office_total}.")
            lbl.setStyleSheet("font-size: 12px; color: #b45309; font-weight: 600;")

    def update_table_view(self):
        # 1. Slice data for current page pagination
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_data = self.filtered_cases[start_idx:end_idx]

        # 2. Update model.
        # No Qt parent: parenting to the page made Qt keep every model ever built,
        # which grew memory without bound. self.model holds the only reference, so the
        # previous one is released as soon as it is replaced.
        previous = getattr(self, "model", None)
        self.model = CaseTableModel(page_data, self.lang)
        self.table_view.setModel(self.model)
        if previous is not None:
            previous.deleteLater()

        # 3. Pagination controls state
        total_records = len(self.filtered_cases)
        total_pages = max(1, (total_records + self.page_size - 1) // self.page_size)
        
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < total_pages)

        # Translation of page text
        if self.lang == "fr":
            self.page_label.setText(f"Page {self.current_page} sur {total_pages} ({total_records} dossiers)")
        else:
            self.page_label.setText(f"صفحة {self.current_page} من {total_pages} ({total_records} ملفات)")

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.update_table_view()

    def next_page(self):
        total_records = len(self.filtered_cases)
        total_pages = (total_records + self.page_size - 1) // self.page_size
        if self.current_page < total_pages:
            self.current_page += 1
            self.update_table_view()

    # Context menu triggers
    def show_context_menu(self, point):
        index = self.table_view.indexAt(point)
        if not index.isValid():
            return

        is_fr = self.lang == "fr"
        menu = QMenu(self)

        # Get row item from model
        row = index.row()
        case_data = self.model._data[row]
        case_id = case_data.get("case_id", "")

        # Action: Change status (Submenu)
        status_menu = menu.addMenu("Modifier le statut" if is_fr else "تغيير حالة الملف")
        
        opt_list = [
            ("Nouveau", "جديد"),
            ("En cours", "قيد الإنجاز"),
            ("En attente de signature", "في انتظار التوقيع"),
            ("Finalisé & Archivé", "تام ومسجل")
        ]

        for fr_opt, ar_opt in opt_list:
            act_label = fr_opt if is_fr else ar_opt
            db_status = ar_opt # Database stores in Arabic primarily
            action = QAction(act_label, status_menu)
            action.triggered.connect(lambda checked=False, s=db_status, cid=case_id: self.change_status(cid, s))
            status_menu.addAction(action)

        # Action: correct the dossier's own wording. Until now a mistyped title
        # or the wrong service type could only be fixed by deleting the dossier
        # and creating it again, which loses its number, date and payments.
        edit_action = QAction("Ouvrir dans Fiche Client" if is_fr else "فتح في بطاقة الحريف", menu)
        edit_action.setEnabled(permissions.has(Cap.EDIT_DOSSIER))
        edit_action.triggered.connect(
            lambda checked=False, r=row: self.edit_selected_case_by_row(r))
        menu.addAction(edit_action)

        menu.addSeparator()

        # Action: Delete case (Admin Only)
        delete_action = QAction("Supprimer le dossier" if is_fr else "حذف الملف النهائي", menu)
        may_delete = permissions.has(Cap.DELETE_DOSSIER)
        delete_action.setEnabled(may_delete)
        delete_action.triggered.connect(lambda checked=False, cid=case_id: self.delete_case_action(cid))
        menu.addAction(delete_action)

        menu.exec(QCursor.pos())

    def _retitle_row_bar(self):
        """Labels the row-action bar in the current language."""
        is_fr = self.lang == "fr"
        if hasattr(self, "btn_edit_case"):
            self.btn_edit_case.setText(
                "📂 " + ("Ouvrir dans Fiche Client" if is_fr else "فتح في بطاقة الحريف"))
        if hasattr(self, "btn_delete_case"):
            self.btn_delete_case.setText(
                "🗑️ " + ("Supprimer le dossier" if is_fr else "حذف الملف النهائي"))
        if hasattr(self, "lbl_row_bar_hint"):
            self.lbl_row_bar_hint.setText(
                "Sélectionnez un dossier, puis :" if is_fr
                else "اختر ملفا ثم :")

    def edit_selected_case(self):
        """Opens the selected dossier's client directly inside Fiche Client."""
        idx = self.table_view.currentIndex()
        is_fr = self.lang == "fr"
        if idx is None or not idx.isValid():
            QMessageBox.information(
                self, "Aucune ligne" if is_fr else "لم يقع اختيار سطر",
                "Sélectionnez d'abord un dossier dans le tableau."
                if is_fr else "اختر أولا ملفا من الجدول.")
            return
        row = idx.row()
        self.edit_selected_case_by_row(row)

    def edit_selected_case_by_row(self, row: int):
        """Opens the client fiche for the dossier at specified row."""
        model_data = getattr(self.model, "_data", []) if hasattr(self, "model") and self.model else []
        if 0 <= row < len(model_data):
            case = model_data[row]
            client_id = case.get("client_id")
            if client_id:
                win = self.window()
                if win and hasattr(win, "open_fiche_client"):
                    win.open_fiche_client(client_id)
            else:
                is_fr = self.lang == "fr"
                QMessageBox.warning(
                    self, "Client introuvable" if is_fr else "تعذّر إيجاد الحريف",
                    "Ce dossier n'est associé à aucun client enregistré." if is_fr
                    else "هذا الملف غير مرتبط بحريف مسجل في المنظومة."
                )

    def open_in_fiche_client(self):
        """Alias for edit_selected_case."""
        self.edit_selected_case()

    def _on_open_in_fiche_client(self):
        """Alias slot for edit_selected_case."""
        self.edit_selected_case()

    def delete_selected_case(self):
        """Deletes the selected dossier (Admin Only)."""
        idx = self.table_view.currentIndex()
        is_fr = self.lang == "fr"
        if idx is None or not idx.isValid():
            QMessageBox.information(
                self, "Aucune ligne" if is_fr else "لم يقع اختيار سطر",
                "Sélectionnez d'abord un dossier dans le tableau."
                if is_fr else "اختر أولا ملفا من الجدول.")
            return
        row = idx.row()
        model_data = getattr(self.model, "_data", []) if hasattr(self, "model") and self.model else []
        if 0 <= row < len(model_data):
            case = model_data[row]
            case_id = case.get("case_id")
            if case_id:
                self.delete_case_action(case_id)

    def delete_case_action(self, case_id: str):
        """Performs complete permanent deletion of a dossier from SQLite (Admin Only)."""
        is_fr = self.lang == "fr"
        if not permissions.has(Cap.DELETE_DOSSIER):
            QMessageBox.warning(
                self, "Accès refusé" if is_fr else "الدخول مرفوض",
                "Seul l'administrateur (notaire) peut supprimer définitivement un dossier."
                if is_fr else "لا تملك صلاحية حذف الملفات. هذا الإجراء خاص بالأستاذ فقط.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirmation de suppression" if is_fr else "تأكيد الحذف النهائي",
            f"Voulez-vous vraiment supprimer DÉFINITIVEMENT le dossier {case_id} ?\nCette action est irréversible."
            if is_fr else
            f"هل أنت متأكد من حذف الملف {case_id} نهائياً؟\nهذا الإجراء لا يمكن التراجع عنه.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            ok = reception.delete_case(case_id)
            if ok:
                QMessageBox.information(
                    self, "Supprimé" if is_fr else "تم الحذف",
                    f"Le dossier {case_id} a été supprimé définitivement de l'application."
                    if is_fr else f"تم حذف الملف {case_id} نهائياً من المنظومة.")
                self.load_data()
            else:
                QMessageBox.warning(
                    self, "Échec" if is_fr else "فشل الحذف",
                    f"Le dossier {case_id} n'a pas pu être supprimé."
                    if is_fr else f"تعذر حذف الملف {case_id}.")
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur" if is_fr else "خطأ",
                f"Erreur lors de la suppression du dossier : {e}")
        is_fr = self.lang == "fr"
        if not permissions.has(Cap.EDIT_DOSSIER):
            QMessageBox.warning(
                self, "Accès refusé" if is_fr else "الدخول مرفوض",
                "Vous n'êtes pas autorisé à modifier un dossier."
                if is_fr else "لا تملك صلاحية تعديل الملفات.")
            return
        try:
            case_data = self.model._data[row]
        except Exception:
            return
        case_id = case_data.get("case_id", "")
        if not case_id:
            return

        from ui.dialogs.edit_entry_dialog import EditEntryDialog
        from PySide6.QtWidgets import QDialog
        fields = [
            ("title", "Objet du dossier", "موضوع الملف", "text",
             case_data.get("title", "")),
            ("service_type", "Type d'acte", "نوع العقد", "text",
             case_data.get("service_type", "")),
        ]
        dlg = EditEntryDialog(
            self,
            f"Corriger le dossier {case_id}",
            f"تصحيح الملف {case_id}",
            fields, self.lang, receipt=None)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        try:
            ok = reception.update_case_details(
                case_id, v["title"], v["service_type"])
        except PermissionError:
            QMessageBox.warning(
                self, "Accès refusé" if is_fr else "الدخول مرفوض",
                "Vous n'êtes pas autorisé à modifier un dossier."
                if is_fr else "لا تملك صلاحية تعديل الملفات.")
            return
        if ok:
            QMessageBox.information(
                self, "Corrigé" if is_fr else "تم التصحيح",
                "Le dossier a été corrigé et la modification enregistrée au journal."
                if is_fr else "تم تصحيح الملف وتسجيل التعديل بالسجل.")
            self.load_data()
        else:
            QMessageBox.warning(
                self, "Échec" if is_fr else "فشل",
                "La correction n'a pas pu être enregistrée."
                if is_fr else "لم يقع تسجيل التصحيح.")

    def on_table_double_clicked(self, index):
        """Double clicking any dossier row opens the client's full Fiche Client page."""
        if not index.isValid():
            return
        row = index.row()
        model_data = getattr(self.model, "_data", []) if hasattr(self, "model") and self.model else []
        if 0 <= row < len(model_data):
            case = model_data[row]
            client_id = case.get("client_id")
            if client_id:
                win = self.window()
                if win and hasattr(win, "open_fiche_client"):
                    win.open_fiche_client(client_id)

    def change_status(self, case_id, new_status):
        """
        Applies a status change, and says so when it does not apply.

        This used to be `if success:` with no else. update_case_status() returns
        False when it matches no row, so a failed change closed the menu with no
        dialog and no reload - the table kept showing the OLD status, which reads
        exactly like the click never registered. The notary clicks again, gets the
        same silence, and is left guessing.
        """
        is_fr = self.lang == "fr"
        try:
            success = reception.update_case_status(case_id, new_status)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erreur" if is_fr else "خطأ",
                (f"Le statut du dossier {case_id} n'a PAS été modifié.\n\n{e}"
                 if is_fr else
                 f"لم يتم تغيير حالة الملف {case_id}!\n\nالسبب: {e}"))
            return

        if not success:
            QMessageBox.critical(
                self,
                "Erreur" if is_fr else "خطأ",
                (f"Le statut du dossier {case_id} n'a PAS été modifié : "
                 f"dossier introuvable.\n\nActualisez la liste et réessayez."
                 if is_fr else
                 f"لم يتم تغيير حالة الملف {case_id}! الملف غير موجود.\n\n"
                 f"يرجى تحديث القائمة والمحاولة من جديد."))
            # Reload anyway: the dossier is not where the table thinks it is, so
            # what is on screen is already out of date.
            reception.clear_db_caches()
            self.load_data()
            return

        reception.clear_db_caches()
        self.load_data()

    def delete_case_action(self, case_id):
        is_fr = self.lang == "fr"
        title = "Confirmation de suppression" if is_fr else "تأكيد الحذف"
        msg = f"Êtes-vous sûr de vouloir supprimer définitivement le dossier {case_id} ?" if is_fr else f"هل أنت متأكد من حذف الملف {case_id} نهائياً؟"
        
        reply = QMessageBox.question(
            self, title, msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Same shape as change_status(): this used to be `if success:` with no
        # else, so the notary confirmed a deletion, the dialog closed, the dossier
        # was still in the list, and nothing explained why. In an office whose
        # reflex is "it did not work, try again", that is how someone ends up
        # deleting the wrong record instead.
        try:
            success = reception.delete_case(case_id)
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur" if is_fr else "خطأ",
                (f"Le dossier {case_id} n'a PAS été supprimé.\n\n{e}"
                 if is_fr else
                 f"لم يتم حذف الملف {case_id}!\n\nالسبب: {e}"))
            return

        if not success:
            QMessageBox.critical(
                self, "Erreur" if is_fr else "خطأ",
                (f"Le dossier {case_id} n'a PAS été supprimé : dossier "
                 f"introuvable.\n\nIl a peut-être déjà été supprimé ailleurs. "
                 f"La liste vient d'être actualisée."
                 if is_fr else
                 f"لم يتم حذف الملف {case_id}! الملف غير موجود.\n\n"
                 f"ربما تم حذفه من جهاز آخر. تم تحديث القائمة."))
            # Refresh regardless: what is on screen no longer matches the database.
            reception.clear_db_caches()
            self.load_data()
            return

        reception.clear_db_caches()
        self.load_data()

    def clean_val_lang(self, val, is_fr):
        if not val or not isinstance(val, str):
            return val
        if is_fr:
            if "جديد" in val: return "Nouveau"
            if "إنجاز" in val: return "En cours"
            if "توقيع" in val: return "En attente de signature"
            if "تام" in val: return "Finalisé & Archivé"
            if " / " in val:
                return val.split(" / ")[0].strip()
        else:
            if " / " in val:
                return val.split(" / ")[-1].strip()
        return val

    # Slot for language update from parent
    def update_language(self, lang_code):
        self.lang = lang_code
        self.update_translations()
        self.apply_filters()
