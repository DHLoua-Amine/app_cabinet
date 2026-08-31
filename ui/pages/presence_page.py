import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableView, QHeaderView, QFileDialog, QMessageBox, QFrame,
    QScrollArea, QComboBox, QSpinBox, QDateEdit, QMenu
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QDate, Signal
from PySide6.QtGui import QColor, QFont

# Import business logic
import auth
import reception
from ui.components import pixmap_cache
from ui.components.export_thread import run_export_with_progress
from config import PROFILES_DIR
from core.style_utils import create_executive_excel


# ── Payment status helpers ─────────────────────────────────────────────────────

def _parse_payment(row) -> tuple:
    """
    Returns (status_key, restant_amount).
    status_key is one of: 'paye', 'non_paye', 'acompte', 'unknown'
    """
    raw = str(row.get("الخلاص / Règlement", "") or "").lower()
    restant = float(row.get("Restant_Raw", 0) or 0)

    if "غير" in raw or "non pay" in raw:
        return "non_paye", restant
    if "تسبقة" in raw or "acompte" in raw:
        return "acompte", restant
    if "خالص" in raw or "pay" in raw:
        return "paye", 0.0
    return "unknown", restant


def _payment_display(status_key, restant, is_fr):
    """Build the combined payment label shown in the single Statut column."""
    if status_key == "paye":
        return "✓ Payé" if is_fr else "✓ خالص بالكامل"
    if status_key == "non_paye":
        amt = f"{restant:,.3f} DT"
        return f"✗ Non Payé — {amt}" if is_fr else f"✗ غير خالص — {amt}"
    if status_key == "acompte":
        amt = f"{restant:,.3f} DT"
        return f"⚡ Acompte — {amt} restant" if is_fr else f"⚡ تسبقة — {amt} متبقية"
    return "—"


_STATUS_COLORS = {
    "paye":     QColor("#10b981"),
    "non_paye": QColor("#ef4444"),
    "acompte":  QColor("#f59e0b"),
    "unknown":  QColor("#94a3b8"),
}


# ── Table Model ────────────────────────────────────────────────────────────────

class PresenceTableModel(QAbstractTableModel):
    COL_PHOTO  = 0
    COL_DATE   = 1
    COL_CLIENT = 2
    COL_CIN    = 3
    COL_PHONE  = 4
    COL_CONF   = 5
    COL_STATUT = 6
    COL_NOTES  = 7

    def __init__(self, df, lang="ar"):
        super().__init__()
        self.df = df
        self.lang = lang
        self.headers = []
        self.update_headers()

    def update_headers(self):
        is_fr = self.lang == "fr"
        self.headers = [
            "Photo"             if is_fr else "الصورة",
            "Date & Heure"      if is_fr else "التاريخ والوقت",
            "Client"            if is_fr else "الحريف",
            "CIN"               if is_fr else "ب.ت.و",
            "Téléphone"         if is_fr else "الهاتف",
            "Confiance"         if is_fr else "نسبة التعرف",
            "Statut Paiement"   if is_fr else "وضعية الدفع",
            "Notes"             if is_fr else "ملاحظات",
        ]

    def rowCount(self, parent=QModelIndex()):
        return len(self.df)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.df)):
            return None

        row_idx = index.row()
        col     = index.column()
        is_fr   = self.lang == "fr"
        row     = self.df.iloc[row_idx]

        # ── Decoration: avatar photo ──
        if role == Qt.ItemDataRole.DecorationRole and col == self.COL_PHOTO:
            client_id  = str(row.get("ID Client", "")).strip()
            photo_path = str(row.get("PhotoPath", "")).strip()
            img_src = None
            if photo_path and os.path.exists(photo_path):
                img_src = photo_path
            else:
                cf = PROFILES_DIR / f"{client_id}.jpg"
                if cf.exists():
                    img_src = str(cf)
            if img_src:
                thumb = pixmap_cache.circular_avatar(img_src, 36)
                if not thumb.isNull():
                    return thumb
            return pixmap_cache.placeholder_avatar(36)

        # ── Display text ──
        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.COL_PHOTO:
                return ""
            if col == self.COL_DATE:
                return str(row.get("Date & Heure", "") or "")
            if col == self.COL_CLIENT:
                return str(row.get("Client", "") or "")
            if col == self.COL_CIN:
                return str(row.get("CIN", "") or "")
            if col == self.COL_PHONE:
                return str(row.get("Téléphone", "") or "")
            if col == self.COL_CONF:
                return str(row.get("Confiance", "") or "")
            if col == self.COL_STATUT:
                status_key, restant = _parse_payment(row)
                return _payment_display(status_key, restant, is_fr)
            if col == self.COL_NOTES:
                return str(row.get("ملاحظات / Notes", "") or "")

        # ── Foreground color for payment status ──
        if role == Qt.ItemDataRole.ForegroundRole and col == self.COL_STATUT:
            status_key, _ = _parse_payment(row)
            return _STATUS_COLORS.get(status_key, _STATUS_COLORS["unknown"])

        # ── Bold font for payment status ──
        if role == Qt.ItemDataRole.FontRole and col == self.COL_STATUT:
            f = QFont()
            f.setBold(True)
            return f

        # ── Text alignment ──
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == self.COL_PHOTO:
                return Qt.AlignmentFlag.AlignCenter
            if self.lang == "ar":
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return None


# ── Page ──────────────────────────────────────────────────────────────────────

class PresencePage(QWidget):
    client_selected = Signal(str)

    # Sentinel: "no start-date filter selected" — year 2000 is far enough in the past
    # that it effectively means no filter. The user sees it as blank/default.
    _DATE_FROM_SENTINEL = QDate(2000, 1, 1)

    @staticmethod
    def _default_date_from() -> QDate:
        """3 days ago — a sensible recent window when the page first opens."""
        return QDate.currentDate().addDays(-3)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang = auth.session_state.lang
        self.df_logs = None
        self._dates_touched = False
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

        # ── 1. Page Header & Export ──────────────────────────────────────────
        header_layout = QHBoxLayout()

        self.export_btn = QPushButton("Exporter le Journal (Excel)", self)
        self.export_btn.setProperty("class", "SecondaryButton")
        self.export_btn.clicked.connect(self.export_to_excel)

        self.refresh_btn = QPushButton("Rafraîchir", self)
        self.refresh_btn.setProperty("class", "SecondaryButton")
        self.refresh_btn.clicked.connect(self.load_data)

        if self.lang == "fr":
            header_layout.addStretch()
            header_layout.addWidget(self.refresh_btn)
            header_layout.addWidget(self.export_btn)
        else:
            header_layout.addWidget(self.export_btn)
            header_layout.addWidget(self.refresh_btn)
            header_layout.addStretch()
        self.main_layout.addLayout(header_layout)

        # ── 1.5 Summary KPI Cards ─────────────────────────────────────────────
        self.kpi_layout = QHBoxLayout()
        self.kpi_layout.setSpacing(20)

        self.card_total = QFrame(self)
        self.card_total.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #cbd5e1; border-left: 5px solid #3b82f6; border-radius: 8px; }")
        total_lay = QVBoxLayout(self.card_total)
        total_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_total_title = QLabel("Total des Visites", self.card_total)
        self.lbl_total_title.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 700; border: none;")
        self.lbl_total_val = QLabel("0", self.card_total)
        self.lbl_total_val.setStyleSheet("font-size: 28px; font-weight: 800; color: #0f172a; border: none;")
        total_lay.addWidget(self.lbl_total_title)
        total_lay.addWidget(self.lbl_total_val)
        self.kpi_layout.addWidget(self.card_total)

        self.card_today = QFrame(self)
        self.card_today.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #cbd5e1; border-left: 5px solid #10b981; border-radius: 8px; }")
        today_lay = QVBoxLayout(self.card_today)
        today_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_today_title = QLabel("Visites Aujourd'hui", self.card_today)
        self.lbl_today_title.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 700; border: none;")
        self.lbl_today_val = QLabel("0", self.card_today)
        self.lbl_today_val.setStyleSheet("font-size: 28px; font-weight: 800; color: #10b981; border: none;")
        today_lay.addWidget(self.lbl_today_title)
        today_lay.addWidget(self.lbl_today_val)
        self.kpi_layout.addWidget(self.card_today)

        self.main_layout.addLayout(self.kpi_layout)

        # ── 2. Search Bar Card ──────────────────────────────────────────────
        search_card = QFrame(self)
        search_card.setProperty("class", "Card")
        search_card_layout = QHBoxLayout(search_card)
        search_card_layout.setContentsMargins(12, 10, 12, 10)
        self.search_input = QLineEdit(search_card)
        self.search_input.textChanged.connect(self.apply_filter)
        search_card_layout.addWidget(self.search_input)
        self.main_layout.addWidget(search_card)

        # ── 3. Advanced Filter Bar ───────────────────────────────────────────
        filter_card = QFrame(self)
        filter_card.setStyleSheet(
            "QFrame { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; }"
            "QLabel { color: #475569; font-size: 11px; font-weight: 600; border: none; background: transparent; }"
            "QDateEdit, QComboBox, QSpinBox {"
            "  border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 8px;"
            "  background: #ffffff; color: #0f172a; font-size: 12px; min-height: 28px; }"
            "QDateEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #3b82f6; }"
        )
        filter_outer = QVBoxLayout(filter_card)
        filter_outer.setContentsMargins(14, 10, 14, 10)
        filter_outer.setSpacing(8)

        self.filter_title = QLabel("🔍  Filtres avancés", filter_card)
        self.filter_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none; background: transparent;")
        filter_outer.addWidget(self.filter_title)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(14)

        # Date De
        self.lbl_date_from = QLabel("📅 Du", filter_card)
        filter_row.addWidget(self.lbl_date_from)
        self.date_from = QDateEdit(filter_card)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(self._default_date_from())
        self.date_from.dateChanged.connect(self._on_date_changed)
        filter_row.addWidget(self.date_from)

        # Date À
        self.lbl_date_to = QLabel("📅 Au", filter_card)
        filter_row.addWidget(self.lbl_date_to)
        self.date_to = QDateEdit(filter_card)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self._on_date_changed)
        filter_row.addWidget(self.date_to)

        # Payment status
        self.lbl_status = QLabel("💰 Paiement", filter_card)
        filter_row.addWidget(self.lbl_status)
        self.status_combo = QComboBox(filter_card)
        self.status_combo.addItems(["Tous", "Payé", "Non Payé", "Acompte"])
        self.status_combo.currentIndexChanged.connect(self.apply_filter)
        filter_row.addWidget(self.status_combo)

        # Min confidence
        self.lbl_conf = QLabel("🎯 Confiance ≥", filter_card)
        filter_row.addWidget(self.lbl_conf)
        self.conf_spin = QSpinBox(filter_card)
        self.conf_spin.setRange(0, 100)
        self.conf_spin.setSuffix(" %")
        self.conf_spin.setValue(0)
        self.conf_spin.valueChanged.connect(self.apply_filter)
        filter_row.addWidget(self.conf_spin)

        filter_row.addStretch()

        # Reset button
        self.reset_btn = QPushButton("🔄 Réinitialiser", filter_card)
        self.reset_btn.setStyleSheet(
            "QPushButton { background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px;"
            "  color: #475569; font-size: 12px; padding: 4px 14px; min-height: 28px; }"
            "QPushButton:hover { background: #e2e8f0; }")
        self.reset_btn.clicked.connect(self.reset_filters)
        filter_row.addWidget(self.reset_btn)

        filter_outer.addLayout(filter_row)
        self.main_layout.addWidget(filter_card)

        # ── 4. Scope label ────────────────────────────────────────────────────
        self.scope_lbl = QLabel("", self)
        self.scope_lbl.setWordWrap(True)
        self.scope_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        self.main_layout.addWidget(self.scope_lbl)

        # ── 5. Table View for Presence History ───────────────────────────────
        self.table_view = QTableView(self)
        self.table_view.setMinimumHeight(400)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.verticalHeader().setDefaultSectionSize(42)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_view.setColumnWidth(0, 50)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_context_menu)
        self.table_view.doubleClicked.connect(self.on_row_double_clicked)
        self.main_layout.addWidget(self.table_view)

        self.update_translations()

    def show_context_menu(self, pos):
        index = self.table_view.indexAt(pos)
        if not index.isValid():
            return

        row_idx = index.row()
        if not hasattr(self, 'model') or self.model is None or row_idx >= len(self.model.df):
            return

        row = self.model.df.iloc[row_idx]
        client_id = str(row.get("ID Client", "")).strip()
        if not client_id:
            return

        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft if self.lang == "ar" else Qt.LayoutDirection.LeftToRight)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #e0f2fe;
                color: #0369a1;
            }
        """)

        is_fr = self.lang == "fr"
        action_open = menu.addAction("👁 Ouvrir la fiche client" if is_fr else "👁 فتح بطاقة الحريف")

        action_selected = menu.exec(self.table_view.viewport().mapToGlobal(pos))
        if action_selected == action_open and client_id:
            self.client_selected.emit(client_id)

    def on_row_double_clicked(self, index):
        if not index.isValid():
            return
        row_idx = index.row()
        if hasattr(self, 'model') and self.model and row_idx < len(self.model.df):
            row = self.model.df.iloc[row_idx]
            client_id = str(row.get("ID Client", "")).strip()
            if client_id:
                self.client_selected.emit(client_id)

    RECENT_PAGE = 200

    def reset_filters(self):
        """Clear all filters back to defaults without triggering multiple reloads."""
        for w in (self.search_input, self.date_from, self.date_to,
                  self.status_combo, self.conf_spin):
            w.blockSignals(True)
        self.search_input.clear()
        self.date_from.setDate(self._default_date_from())
        self.date_to.setDate(QDate.currentDate())
        self.status_combo.setCurrentIndex(0)
        self.conf_spin.setValue(0)
        for w in (self.search_input, self.date_from, self.date_to,
                  self.status_combo, self.conf_spin):
            w.blockSignals(False)
        self.apply_filter()

    def _on_date_changed(self, *_):
        """A date box only becomes a filter once someone actually sets it."""
        self._dates_touched = True
        self.apply_filter()

    def _active_filters(self):
        """Collect all current filter values into a dict."""
        query     = self.search_input.text().strip()
        df        = self.date_from.date()
        dt        = self.date_to.date()
        # The boxes open on a 3-day window, but that window is a DISPLAY default,
        # not a filter. Applying it silently meant a search for a CIN returned
        # nothing unless the visit happened in the last three days, while the
        # label underneath still said "0 of 3005 matching". The range only
        # filters once someone has actually picked a date.
        if not getattr(self, "_dates_touched", False):
            date_from = ""
            date_to = ""
        else:
            date_from = df.toString("yyyy-MM-dd") if df != self._DATE_FROM_SENTINEL else ""
            date_to   = dt.toString("yyyy-MM-dd") if (date_from or dt != QDate.currentDate()) else ""
        status    = self.status_combo.currentText()
        if status == "Tous":
            status = ""
        conf = self.conf_spin.value()
        return dict(query_str=query, date_from=date_from, date_to=date_to,
                    payment_status=status, min_confidence=float(conf))

    def load_data(self):
        # Most recent page by default; filtering reaches the full history.
        # A failure here is remembered rather than swallowed.
        import pandas as pd
        self.load_error = None
        try:
            self.df_logs = reception.get_recent_check_ins(limit=self.RECENT_PAGE)
        except reception.DataUnavailable as e:
            self.load_error = str(e)
            self.load_error_code = getattr(e, "code", "")
            self.df_logs = pd.DataFrame(
                columns=["ID Client", "Client", "PhotoPath", "Date & Heure"])
        self.apply_filter()
        self.update_stats()

    def apply_filter(self):
        import pandas as pd
        filters = self._active_filters()
        has_any = any([
            filters["query_str"],
            filters["date_from"],
            filters["date_to"],
            filters["payment_status"],
            filters["min_confidence"] > 0,
        ])

        if has_any:
            try:
                df_filtered = reception.get_check_ins_filtered(**filters)
                self.load_error = None
            except reception.DataUnavailable as e:
                self.load_error = str(e)
                self.load_error_code = getattr(e, "code", "")
                df_filtered = None
        else:
            df_filtered = self.df_logs

        if df_filtered is None or df_filtered.empty:
            df_filtered = pd.DataFrame(columns=["ID Client", "Client", "PhotoPath", "Date & Heure"])

        self.model = PresenceTableModel(df_filtered, lang=self.lang)
        self.table_view.setModel(self.model)
        self._update_scope_label(len(df_filtered), has_any, filters["query_str"])

    def _update_scope_label(self, shown: int, filtering: bool, query: str = ""):
        """
        States what the table is showing, without conflating three cases.
        """
        if getattr(self, "load_error", None):
            self._show_error_scope()
            return
        try:
            total = reception.count_check_ins()
            if filtering and query:
                matching = reception.count_check_ins_matching(query)
                capped = shown < matching
            else:
                matching = shown
                capped = False
        except reception.DataUnavailable as e:
            self.load_error = str(e)
            self.load_error_code = getattr(e, "code", "")
            self._show_error_scope()
            return
        self.scope_lbl.setText(self._scope_text(shown, matching, total, filtering, capped))
        self.scope_lbl.setStyleSheet(
            "color: #b45309; font-size: 11px; font-weight: bold;"
            if (capped or (not filtering and shown < total))
            else "color: #475569; font-size: 11px;")

    # What went wrong, in the reader's own language.
    ERROR_REASONS = {
        "journal":  ("le journal n'a pas pu être lu", "تعذّرت قراءة السجل"),
        "search":   ("la recherche a échoué", "فشل البحث"),
        "total":    ("le total est illisible", "تعذّر احتساب المجموع"),
        "today":    ("le total du jour est illisible", "تعذّر احتساب زيارات اليوم"),
        "matching": ("le comptage des résultats a échoué", "تعذّر احتساب النتائج"),
    }

    def _show_error_scope(self):
        """Says the journal could not be read, instead of reporting zero visits."""
        is_fr = self.lang == "fr"
        fr, ar = self.ERROR_REASONS.get(
            getattr(self, "load_error_code", ""),
            ("cause inconnue", "سبب غير معروف"))
        reason = fr if is_fr else ar
        msg = (f"⚠ Le journal de présence n'a pas pu être affiché ({reason}). "
               f"Les chiffres ci-dessus sont indisponibles — ce n'est PAS un jour "
               f"sans visite. Vérifiez la base de données."
               if is_fr else
               f"⚠ تعذّر عرض سجل الحضور ({reason}). "
               f"الأرقام أعلاه غير متوفّرة — وهذا ليس يوما بدون زيارات. "
               f"تحقّق من قاعدة البيانات.")
        self.scope_lbl.setText(msg)
        self.scope_lbl.setStyleSheet(
            "color: #b91c1c; font-size: 12px; font-weight: bold; "
            "background-color: #fef2f2; border: 1px solid #fecaca; "
            "border-radius: 6px; padding: 8px;")

    def _scope_text(self, shown, matching, total, filtering, capped):
        """The wording for each case, in both languages."""
        is_fr = self.lang == "fr"
        if filtering:
            if capped:
                return (f"Affichage des {shown} premiers résultats sur {matching} "
                        f"correspondants — affinez vos filtres pour voir les autres."
                        if is_fr else
                        f"عرض أول {shown} نتيجة من {matching} نتيجة مطابقة — "
                        f"ضيّق الفلتر للاطّلاع على البقية.")
            return (f"{shown} résultat(s) trouvé(s) sur {total} enregistrement(s)."
                    if is_fr else
                    f"تم العثور على {shown} نتيجة من جملة {total} تسجيل.")
        if shown < total:
            return (f"Affichage des {shown} visites les plus récentes sur {total}. "
                    f"Utilisez les filtres pour atteindre les {total - shown} plus anciennes."
                    if is_fr else
                    f"عرض آخر {shown} زيارة من جملة {total}. "
                    f"استعمل الفلاتر للوصول إلى {total - shown} زيارة أقدم.")
        return (f"Affichage de la totalité du journal ({total} visites)."
                if is_fr else
                f"عرض كامل السجل ({total} زيارة).")

    def update_language(self, lang_code):
        self.lang = lang_code
        if hasattr(self, "model") and self.model:
            self.model.lang = lang_code
            self.model.update_headers()
        self.retitle_ui()
        self.load_data()

    def retitle_ui(self):
        is_fr = self.lang == "fr"
        if hasattr(self, "export_btn"):
            self.export_btn.setText("Exporter le Journal (Excel)" if is_fr else "تصدير السجل إلى (Excel)")
        if hasattr(self, "refresh_btn"):
            self.refresh_btn.setText("Rafraîchir" if is_fr else "تحديث")
        if hasattr(self, "lbl_total_title"):
            self.lbl_total_title.setText("Total des Visites" if is_fr else "مجموع الزيارات")
        if hasattr(self, "lbl_today_title"):
            self.lbl_today_title.setText("Visites Aujourd'hui" if is_fr else "زيارات اليوم")
        if hasattr(self, "search_input"):
            self.search_input.setPlaceholderText("🔍 Rechercher un client, CIN, téléphone..." if is_fr else "🔍 بحث عن حريف، رقم بطاقة التعريف، هاتف...")
        if hasattr(self, "filter_title"):
            self.filter_title.setText("🔍  Filtres avancés" if is_fr else "🔍  بحث وتصفية متقدمة")
        if hasattr(self, "lbl_date_from"):
            self.lbl_date_from.setText("📅 Du" if is_fr else "📅 من")
        if hasattr(self, "lbl_date_to"):
            self.lbl_date_to.setText("📅 Au" if is_fr else "📅 إلى")
        if hasattr(self, "lbl_status"):
            self.lbl_status.setText("💰 Paiement" if is_fr else "💰 حالة الدفع")
        if hasattr(self, "lbl_conf"):
            self.lbl_conf.setText("🎯 Confiance ≥" if is_fr else "🎯 نسبة الدقة ≥")
        if hasattr(self, "status_combo"):
            curr = self.status_combo.currentIndex()
            self.status_combo.blockSignals(True)
            self.status_combo.clear()
            self.status_combo.addItems(["Tous" if is_fr else "الكل", "Payé" if is_fr else "خالص", "Non Payé" if is_fr else "غير خالص", "Acompte" if is_fr else "تسبقة"])
            self.status_combo.setCurrentIndex(curr)
            self.status_combo.blockSignals(False)

    def update_stats(self):
        """Both cards count the DATABASE, not the loaded page."""
        if getattr(self, "load_error", None):
            self.lbl_total_val.setText("—")
            self.lbl_today_val.setText("—")
            return
        try:
            self.lbl_total_val.setText(str(reception.count_check_ins()))
            self.lbl_today_val.setText(str(reception.count_check_ins_today()))
        except reception.DataUnavailable as e:
            self.load_error = str(e)
            self.load_error_code = getattr(e, "code", "")
            self.lbl_total_val.setText("—")
            self.lbl_today_val.setText("—")
            self._show_error_scope()

    def rows_for_export(self):
        """Return the correct DataFrame for export: filtered if filters are active, else full history."""
        filters = self._active_filters()
        has_any = any([
            filters["query_str"],
            filters["date_from"],
            filters["date_to"],
            filters["payment_status"],
            filters["min_confidence"] > 0,
        ])
        if has_any:
            return reception.get_check_ins_filtered(**filters, limit=20000), filters["query_str"]
        total = reception.count_check_ins() or self.RECENT_PAGE
        return reception.get_recent_check_ins(limit=max(total, self.RECENT_PAGE)), ""

    def export_to_excel(self):
        try:
            df_export, active_query = self.rows_for_export()
        except reception.DataUnavailable as e:
            QMessageBox.critical(
                self, "Export" if self.lang == "fr" else "تصدير",
                (f"Le journal n'a pas pu être lu, rien n'a été exporté.\n\n{e}"
                 if self.lang == "fr" else
                 f"تعذّرت قراءة السجل، لم يقع تصدير أي شيء.\n\n{e}"))
            return
        if df_export is None or df_export.empty:
            QMessageBox.warning(self, "Export", "Aucun enregistrement à exporter." if self.lang == "fr" else "لا توجد سجلات لتصديرها.")
            return

        is_fr = self.lang == "fr"
        suggested = "Journal_Presence_filtre.xlsx" if active_query else "Journal_Presence.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter le journal" if is_fr else "تصدير السجل",
            suggested, "Fichiers Excel (*.xlsx)"
        )
        if file_path:
            try:
                want = ["Date & Heure", "Client", "CIN", "Téléphone",
                        "Confiance", "الخلاص / Règlement", "Restant_Raw", "ملاحظات / Notes"]
                available = [c for c in want if c in df_export.columns]
                df_save = df_export[available].copy()

                if is_fr:
                    df_save = df_save.rename(columns={
                        "الخلاص / Règlement": "Statut Paiement",
                        "Restant_Raw": "Restant (DT)",
                        "ملاحظات / Notes": "Notes",
                    })
                else:
                    df_save = df_save.rename(columns={
                        "Date & Heure": "التاريخ والوقت",
                        "Client": "الحريف",
                        "CIN": "ب.ت.و",
                        "Téléphone": "الهاتف",
                        "Confiance": "نسبة التعرف",
                        "الخلاص / Règlement": "وضعية الدفع",
                        "Restant_Raw": "المتبقي (DT)",
                        "ملاحظات / Notes": "الملاحظات",
                    })

                n = len(df_save)

                def build(report):
                    report(0, n)
                    data = create_executive_excel(df_save, sheet_name='Visites')
                    report(n, n)
                    return data

                self.export_thread = run_export_with_progress(
                    self, build, file_path,
                    "Export" if is_fr else "تصدير",
                    (f"Export de {n} visites en cours…" if is_fr else f"جاري تصدير {n} زيارة…"))
                done_msg = (
                    (f"{n} visites exportées"
                     + (f" (filtre actif)." if active_query else " (journal complet).")
                     ) if is_fr else
                    (f"تم تصدير {n} زيارة"
                     + (f" (نتائج الفلتر)." if active_query else " (كامل السجل).")))
                self.export_thread.finished_ok.connect(lambda _p: QMessageBox.information(
                    self, "Export" if is_fr else "تصدير", done_msg))
                self.export_thread.failed.connect(lambda m: QMessageBox.critical(
                    self, "Erreur", f"Erreur d'écriture: {m}"))
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur d'écriture: {e}")

    def update_translations(self):
        is_fr = self.lang == "fr"
        if hasattr(self, "scope_lbl") and getattr(self, "load_error", None):
            self._show_error_scope()
        if hasattr(self, "search_input"):
            # Blanking this wiped the search hint on every language switch, so
            # the box gave no clue that a CIN or a phone number is accepted.
            self.search_input.setPlaceholderText(
                "🔍 Rechercher un client, CIN, téléphone..." if is_fr
                else "🔍 بحث عن حريف، رقم بطاقة التعريف، هاتف...")
        self.export_btn.setText("Exporter (Excel)" if is_fr else "تصدير السجل (Excel)")
        self.refresh_btn.setText("Rafraîchir" if is_fr else "تحديث البيانات")
        self.lbl_total_title.setText("Total des Visites" if is_fr else "إجمالي الزيارات")
        self.lbl_today_title.setText("Visites Aujourd'hui" if is_fr else "زيارات اليوم")
        
        if is_fr:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    def update_language(self, lang_code):
        self.lang = lang_code
        self.update_translations()
        self.apply_filter()      # rebuilds the model and the scope sentence
