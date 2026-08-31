import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QFrame, QGridLayout, QMessageBox
from PySide6.QtCore import Qt, Signal

# Import business logic
import reception
from ui.components import pixmap_cache
import auth
from config import PROFILES_DIR

# Global QPixmap cache to avoid repeated disk reads (Requirement 2)

class ClientCard(QFrame):
    # Signal emitted when "Open Fiche" is clicked
    open_fiche = Signal(str)

    def __init__(self, client_data, case_count=0, lang="ar", parent=None):
        super().__init__(parent)
        self.client_data = client_data
        self.client_id = client_data.get("client_id", "")
        self.case_count = case_count
        self.lang = lang
        self.init_ui()

    def init_ui(self):
        self.setObjectName("ClientCard")
        self.setProperty("class", "Card")
        self.setStyleSheet("""
            QFrame#ClientCard {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
            }
            QFrame#ClientCard:hover {
                border-color: #3b82f6;
                background-color: #f8fafc;
            }
        """)

        # Layout inside card
        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(15, 15, 15, 15)
        card_layout.setSpacing(10)

        # Upper row: Avatar + Details
        upper_layout = QHBoxLayout()
        upper_layout.setSpacing(12)

        # 1. Profile image / Avatar
        self.avatar_label = QLabel(self)
        self.avatar_label.setFixedSize(70, 70)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.load_profile_pic()
        
        # 2. Text Details
        details_layout = QVBoxLayout()
        details_layout.setSpacing(3)
        details_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        fullname = self.client_data.get("full_name", "").strip()
        if not fullname:
            fullname = "Nouveau Client" if self.lang == "fr" else "حريف جديد"
        self.name_lbl = QLabel(fullname, self)
        self.name_lbl.setStyleSheet("font-weight: 800; font-size: 14px; color: #0f172a;")
        
        cin_val = self.client_data.get("cin_number", "—")
        phone_val = self.client_data.get("phone", "—")

        cin_prefix = "CIN:" if self.lang == "fr" else "ب.ت.و:"
        phone_prefix = "Tél:" if self.lang == "fr" else "الهاتف:"
        
        self.cin_lbl = QLabel(f"{cin_prefix} {cin_val}", self)
        self.cin_lbl.setStyleSheet("font-size: 12px; color: #475569; font-weight: 600;")
        
        self.phone_lbl = QLabel(f"{phone_prefix} {phone_val}", self)
        self.phone_lbl.setStyleSheet("font-size: 12px; color: #475569; font-weight: 600;")

        details_layout.addWidget(self.name_lbl)
        details_layout.addWidget(self.cin_lbl)
        details_layout.addWidget(self.phone_lbl)

        # Order layout based on language (Right-to-Left for Arabic)
        if self.lang == "ar":
            upper_layout.addLayout(details_layout, stretch=1)
            upper_layout.addWidget(self.avatar_label)
            self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.cin_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.phone_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            upper_layout.addWidget(self.avatar_label)
            upper_layout.addLayout(details_layout, stretch=1)
            self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.cin_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.phone_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)

        card_layout.addLayout(upper_layout)

        # Case count badge
        badge_layout = QHBoxLayout()
        dossiers_lbl = "dossier(s)" if self.lang == "fr" else "ملف(ات)"
        self.badge_lbl = QLabel(f" {self.case_count} {dossiers_lbl}", self)
        self.badge_lbl.setStyleSheet("""            QLabel {
                background-color: #e0f2fe;
                color: #0369a1;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        self.badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        if self.lang == "ar":
            badge_layout.addStretch()
            badge_layout.addWidget(self.badge_lbl)
        else:
            badge_layout.addWidget(self.badge_lbl)
            badge_layout.addStretch()
            
        card_layout.addLayout(badge_layout)

        # Open button
        btn_txt = "Ouvrir la Fiche Client" if self.lang == "fr" else "فتح بطاقة الحريف"
        self.open_btn = QPushButton(btn_txt, self)
        self.open_btn.setProperty("class", "PrimaryButton")
        self.open_btn.setStyleSheet("QPushButton { min-height: 32px; font-size: 12px; }")
        self.open_btn.clicked.connect(lambda: self.open_fiche.emit(self.client_id))
        card_layout.addWidget(self.open_btn)

    def load_profile_pic(self):
        # Resolve pic path
        pic_path = self.client_data.get("profile_pic_path", "") or self.client_data.get("profile_pic", "")
        img_src = None
        
        if pic_path and os.path.exists(pic_path):
            img_src = pic_path
        else:
            prof_file = PROFILES_DIR / f"{self.client_id}.jpg"
            if prof_file.exists():
                img_src = str(prof_file)

        # Render image
        if img_src:
            # Check Pixmap cache first (Requirement 2)
            # Cached at 70px, LRU-bounded (see ui/components/pixmap_cache.py).
            rounded = pixmap_cache.circular_avatar(img_src, 70)
            if not rounded.isNull():
                self.avatar_label.setPixmap(rounded)
                return

        # No photo: a drawn placeholder circle rather than a glyph.
        self.avatar_label.setPixmap(pixmap_cache.placeholder_avatar(70, "#f1f5f9", "#cbd5e1"))
        self.avatar_label.setStyleSheet("border-radius: 35px;")


class ClientsPage(QWidget):
    # Signal emitted when client profile needs to be opened
    client_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang = auth.session_state.lang
        self.clients_list = []
        self.case_counts = {}
        self.grid_widgets = []
        
        self.init_ui()
        self.load_data()

    def init_ui(self):
        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 30, 30, 30)
        self.main_layout.setSpacing(15)

        # ── 1. Page Header & Title ───────────────────────────────────────────
        header_layout = QHBoxLayout()
        
        self.new_client_btn = QPushButton("إضافة حريف جديد", self)
        self.new_client_btn.setProperty("class", "PrimaryButton")
        self.new_client_btn.setStyleSheet("QPushButton { min-width: 160px; }")
        self.new_client_btn.clicked.connect(self.add_new_client)

        if self.lang == "fr":
            header_layout.addStretch()
            header_layout.addWidget(self.new_client_btn)
        else:
            header_layout.addWidget(self.new_client_btn)
            header_layout.addStretch()
            
        self.main_layout.addLayout(header_layout)

        # ── 2. Filters Layout Card ───────────────────────────────────────────
        filter_card = QFrame(self)
        filter_card.setProperty("class", "Card")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(15, 10, 15, 10)
        filter_layout.setSpacing(15)

        # Global Search field
        search_lay = QVBoxLayout()
        self.lbl_search = QLabel("Recherche globale :", filter_card)
        self.lbl_search.setProperty("class", "FieldLabel")
        self.search_input = QLineEdit(filter_card)
        self.search_input.textChanged.connect(self.apply_search)
        search_lay.addWidget(self.lbl_search)
        search_lay.addWidget(self.search_input)
        filter_layout.addLayout(search_lay, stretch=2)

        # Land Title Search field
        title_lay = QVBoxLayout()
        self.lbl_title_search = QLabel("Titre foncier :", filter_card)
        self.lbl_title_search.setProperty("class", "FieldLabel")
        self.title_input = QLineEdit(filter_card)
        self.title_input.textChanged.connect(self.apply_search)
        title_lay.addWidget(self.lbl_title_search)
        title_lay.addWidget(self.title_input)
        filter_layout.addLayout(title_lay, stretch=1)

        self.main_layout.addWidget(filter_card)

        # ── 3. Scroll Area for Clients Grid ──────────────────────────────────
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #f1f5f9;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)

        # Container widget inside scroll area
        self.grid_container = QWidget()
        self.grid_container.setObjectName("GridContainer")
        self.grid_container.setStyleSheet("QWidget#GridContainer { background-color: transparent; }")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll_area.setWidget(self.grid_container)
        self.main_layout.addWidget(self.scroll_area)

        # ── 4. Floating-Style Count Badge ────────────────────────────────────
        self.footer_layout = QHBoxLayout()
        self.count_badge = QLabel("0 Clients", self)
        self.count_badge.setStyleSheet("""
            background-color: #fee2e2;
            color: #dc2626;
            border: 2px solid #ef4444;
            padding: 6px 16px;
            border-radius: 15px;
            font-size: 13px;
            font-weight: 800;
        """)
        
        if self.lang == "fr":
            self.footer_layout.addStretch()
            self.footer_layout.addWidget(self.count_badge)
        else:
            self.footer_layout.addWidget(self.count_badge)
            self.footer_layout.addStretch()
            
        self.main_layout.addLayout(self.footer_layout)

        # Apply translations
        self.update_translations()

    def update_translations(self):
        is_fr = self.lang == "fr"
        self.new_client_btn.setText("Nouveau Client" if is_fr else "إضافة حريف جديد")
        
        self.lbl_search.setText("Recherche globale :" if is_fr else "البحث العام في دليل الحرفاء :")
        
        self.lbl_title_search.setText("Titre foncier :" if is_fr else "البحث برقم الرسم العقاري :")

        if is_fr:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    # The default listing asks for one page. Search is uncapped and reaches every
    # client, so the page's job is to say so rather than to look complete.
    LISTING_PAGE = 100

    def load_data(self):
        """
        Loads one page of the directory, and says what it is showing.

        Two faults lived here. A read that FAILED came back as an empty list, so
        a corrupted database rendered as a directory with no clients in it --
        identical to a brand new office. And the listing silently asked for only
        100 clients: an office with 600 saw 100 and nothing said the other 500
        existed.
        """
        self.load_error = None
        try:
            self.case_counts = reception.get_client_case_counts()
            self.clients_list = reception.get_all_clients_summary(limit=self.LISTING_PAGE)
            self.total_clients = reception.count_clients()
        except reception.DataUnavailable as e:
            self.load_error = getattr(e, "code", "") or "clients"
            self.case_counts = {}
            self.clients_list = []
            self.total_clients = 0
            self.display_clients([])
            self._show_read_failure()
            return
        self.display_clients(self.clients_list)

    def apply_search(self):
        query = self.title_input.text().strip() or self.search_input.text().strip()
        if query:
            # Query backend with search term. This one is NOT capped.
            try:
                results = reception.search_clients_summary(query)
                self.load_error = None
            except reception.DataUnavailable as e:
                self.load_error = getattr(e, "code", "") or "clients_search"
                self.display_clients([])
                self._show_read_failure()
                return
            self._searching = True
            self.display_clients(results)
            self._searching = False
        else:
            self.display_clients(self.clients_list)

    def _badge_text(self, shown: int) -> str:
        """
        What the footer badge says.

        It used to read "100 Clients" whether the office had 100 or 10 000,
        because the listing quietly asked for a page and the badge counted the
        page. It now separates what is displayed from what exists.
        """
        is_fr = self.lang == "fr"
        self.count_badge.setStyleSheet(
            "background-color: #fee2e2; color: #dc2626; border: 2px solid #ef4444;"
            " padding: 6px 16px; border-radius: 15px; font-size: 13px; font-weight: 800;")
        total = getattr(self, "total_clients", None)
        if getattr(self, "_searching", False):
            return (f"{shown} résultat(s)" if is_fr else f"{shown} نتيجة")
        if total is None:
            return (f"{shown} Clients" if is_fr else f"{shown} حريف")
        if shown < total:
            return (f"{shown} sur {total} clients — recherchez pour atteindre les autres"
                    if is_fr else
                    f"{shown} من {total} حريف — استعمل البحث للوصول إلى البقية")
        return (f"{total} Clients" if is_fr else f"{total} حريف")

    def _show_read_failure(self):
        """Says the directory could not be READ, instead of showing zero clients."""
        is_fr = self.lang == "fr"
        msg = ("Le répertoire des clients n'a pas pu être lu. Ce n'est PAS un "
               "répertoire vide — vérifiez la base de données."
               if is_fr else
               "تعذّرت قراءة دليل الحرفاء. هذا ليس دليلا فارغا — "
               "تحقّق من قاعدة البيانات.")
        self.count_badge.setText(("⚠ Lecture impossible" if is_fr
                                  else "⚠ تعذّرت القراءة"))
        self.count_badge.setStyleSheet(
            "background-color: #fef2f2; color: #b91c1c; border: 2px solid #ef4444;"
            " padding: 6px 16px; border-radius: 15px; font-size: 13px; font-weight: 800;")
        QMessageBox.critical(self, "Erreur" if is_fr else "خطأ", msg)

    def display_clients(self, clients):
        # 1. Clean previous layout
        for w in self.grid_widgets:
            self.grid_layout.removeWidget(w)
            w.deleteLater()
        self.grid_widgets.clear()

        # 2. Re-populate grid
        is_fr = self.lang == "fr"
        columns_count = 3
        
        for idx, client in enumerate(clients):
            cid = client.get("client_id", "")
            cnt = self.case_counts.get(cid, 0)
            
            card = ClientCard(client, case_count=cnt, lang=self.lang, parent=self.grid_container)
            card.open_fiche.connect(self.on_client_clicked)
            
            row = idx // columns_count
            col = idx % columns_count
            self.grid_layout.addWidget(card, row, col)
            self.grid_widgets.append(card)

        # 3. Update count label
        count = len(clients)
        if is_fr:
            self.count_badge.setText(self._badge_text(count))
        else:
            self.count_badge.setText(self._badge_text(count))

    def add_new_client(self):
        self.client_selected.emit("NEW")

    def on_client_clicked(self, client_id):
        self.client_selected.emit(client_id)

    # Parent notifications
    def update_language(self, lang_code):
        self.lang = lang_code
        self.update_translations()
        self.apply_search()
