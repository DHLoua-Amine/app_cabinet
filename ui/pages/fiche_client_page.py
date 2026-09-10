import os
import re
import time
import datetime
from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QTabWidget, QTableView, QHeaderView, QFrame, QFileDialog, QMessageBox, QDoubleSpinBox, QProgressBar, QTextEdit, QScrollArea, QListWidget, QListWidgetItem, QGridLayout, QMenu, QDialog, QDialogButtonBox
from PySide6.QtCore import Qt, QSize, Signal, QThread, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QIcon, QAction, QCursor, QImageReader, QValidator

class MoneySpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0.0, 99999999.0)
        self.setDecimals(3)
        self.setSingleStep(1.0)
        self.setSuffix(" DT")
        self.setGroupSeparatorShown(False)

    def validate(self, text, pos):
        clean_text = text.replace(" DT", "").replace(" ", "").strip()
        if not clean_text or clean_text == ".":
            return (QValidator.State.Acceptable, text, pos)
        try:
            val = float(clean_text)
            return (QValidator.State.Acceptable, text, pos)
        except ValueError:
            return (QValidator.State.Invalid, text, pos)

    def valueFromText(self, text):
        clean_text = text.replace(" DT", "").replace(" ", "").strip()
        try:
            return float(clean_text)
        except ValueError:
            return 0.0

# Import business logic
import reception
from ui.components import pixmap_cache
import auth
import cin_extractor
import config
from config import PROFILES_DIR, DOCUMENTS_DIR

# Global cache for profile photos

def safe_profile_path(base_dir: Path, client_id: str) -> Path | None:
    """
    Safely resolve a photo path from a client_id.
    Prevents path traversal: if the resolved path escapes base_dir, returns None.
    """
    # Strip any path separators and dangerous characters from the client_id
    safe_id = re.sub(r'[^\w\-]', '_', str(client_id))
    candidate = (base_dir / f"{safe_id}.jpg").resolve()
    try:
        candidate.relative_to(base_dir.resolve())
        return candidate
    except ValueError:
        # Path escapes the base directory — BLOCK IT
        return None

class OCRThread(QThread):
    # Signals to communicate back to the UI
    finished = Signal(dict)

    def __init__(self, front_bytes, back_bytes=None, api_key=""):
        super().__init__()
        self.front_bytes = front_bytes
        self.back_bytes = back_bytes
        self.api_key = api_key

    def run(self):
        try:
            result = cin_extractor.extract_cin_dual_faces(
                self.front_bytes,
                self.back_bytes,
                api_key=self.api_key
            )
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({"success": False, "error": str(e)})


class SimpleTableModel(QAbstractTableModel):
    """Lightweight read-only model over a list of dict rows."""

    def __init__(self, rows, headers, parent=None):
        super().__init__(parent)
        self.rows = rows or []
        self.headers = headers or []

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.rows)):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            value = self.rows[index.row()].get(self.headers[index.column()], "")
            return "" if value is None else str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return str(self.headers[section])
        return None


class FicheClientPage(QWidget):
    # Signal emitted when returning back to the client list
    back_to_list = Signal()
    # Face enrolment finishes on a worker thread, and Qt widgets may only be
    # touched from the UI thread. The worker emits this; the queued connection
    # delivers it here, on the right thread.
    face_enrolment_done = Signal(bool, str, str)   # ok, reason, client_id

    def __init__(self, client_id=None, parent=None):
        super().__init__(parent)
        self.lang = auth.session_state.lang
        self.client_id = client_id
        self.client_data = {}
        self.is_new = (client_id is None or client_id == "" or client_id == "NEW")
        
        if self.is_new:
            # Must not collide with an existing client: update_client_civil_status
            # UPDATEs when the id already exists, so a collision used to overwrite a
            # real client's identity while leaving their dossiers attached.
            self.client_id = reception.generate_client_id()
            self.init_empty_client()
        
        self.init_ui()
        self.update_translations()
        self.face_enrolment_done.connect(self._on_face_enrolment_done)
        self.load_client_data()

    def init_empty_client(self):
        if not getattr(self, "client_id", None) or self.client_id == "NEW":
            self.client_id = reception.generate_client_id()
        self.client_data = {
            "client_id": self.client_id,
            "nom": "", "prenom": "", "full_name": "",
            "father_name": "", "grandfather_name": "",
            "phone": "", "maiden_name": "", "birth_date": "01/01/1990", "birth_place": "",
            "cin_number": "", "cin_date_place": "", "cin_issue_date": "", "cin_issue_place": "",
            "marital_status": "Célibataire / أعزب",
            "matrimonial_regime": "", "profession": "", "address": "", "legal_role": "مشتري",
            "company_name": "", "company_rc": "", "titre_foncier": "", "wilaya": "", "profile_pic_path": ""
        }

    def init_ui(self):
        is_fr = getattr(self, 'lang', 'fr') == 'fr'
        # Base Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 30, 30, 30)
        self.main_layout.setSpacing(15)

        # ── 1. Page Header Toolbar ───────────────────────────────────────────
        toolbar = QHBoxLayout()

        self.back_btn = QPushButton(self); self._tr_btn(self.back_btn, "◀ Retour", "◀ رجوع")
        self.back_btn.setProperty("class", "SecondaryButton")
        self.back_btn.clicked.connect(lambda: self.back_to_list.emit())
        
        
        self.print_btn = QPushButton(self); self._tr_btn(self.print_btn, "Imprimer", "طباعة")
        self.print_btn.setProperty("class", "SecondaryButton")
        self.print_btn.clicked.connect(self.print_fiche)

        self.farida_btn = QPushButton("حاسبة الفريضة" if self.lang == "ar" else "Calculateur الفريضة", self)
        self.farida_btn.setProperty("class", "SecondaryButton")
        self.farida_btn.clicked.connect(self.open_farida_dialog)

        self.delete_client_btn = QPushButton(self)
        self._tr_btn(self.delete_client_btn, "Supprimer le client", "حذف الحريف")
        self.delete_client_btn.setProperty("class", "SecondaryButton")
        self.delete_client_btn.setStyleSheet("color: #dc2626; border-color: #dc2626;")
        self.delete_client_btn.clicked.connect(self.delete_client_action)

        if self.lang == "fr":
            toolbar.addWidget(self.back_btn)
            toolbar.addStretch()
            toolbar.addWidget(self.farida_btn)
            toolbar.addWidget(self.delete_client_btn)
            toolbar.addWidget(self.print_btn)
        else:
            toolbar.addWidget(self.print_btn)
            toolbar.addWidget(self.delete_client_btn)
            toolbar.addWidget(self.farida_btn)
            toolbar.addStretch()
            toolbar.addWidget(self.back_btn)
            
        self.main_layout.addLayout(toolbar)

        # ── 2. Top Header Banner (Avatar + Client Info) ──────────────────────
        self.banner_card = QFrame(self)
        self.banner_card.setObjectName("HeaderBanner")
        self.banner_card.setStyleSheet("""
            QFrame#HeaderBanner {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e0f2fe, stop:1 #bae6fd);
                border: 1px solid #cbd5e1;
                border-radius: 12px;
            }
        """)
        banner_layout = QHBoxLayout(self.banner_card)
        banner_layout.setContentsMargins(20, 15, 20, 15)
        banner_layout.setSpacing(15)

        self.banner_avatar = QLabel(self.banner_card)
        self.banner_avatar.setFixedSize(60, 60)
        self.banner_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.banner_name = QLabel("Nouveau Client / حريف جديد", self.banner_card)
        self.banner_name.setStyleSheet("font-size: 20px; font-weight: 800; color: #0369a1;")
        
        self.banner_badges_layout = QHBoxLayout()
        self.banner_badges_layout.setSpacing(8)

        if self.lang == "fr":
            banner_layout.addWidget(self.banner_avatar)
            banner_layout.addWidget(self.banner_name)
            banner_layout.addStretch()
            banner_layout.addLayout(self.banner_badges_layout)
        else:
            banner_layout.addLayout(self.banner_badges_layout)
            banner_layout.addStretch()
            banner_layout.addWidget(self.banner_name)
            banner_layout.addWidget(self.banner_avatar)

        self.main_layout.addWidget(self.banner_card)

        # ── 3. QTabWidget Container ──────────────────────────────────────────
        self.tabs = QTabWidget(self)

        # ── TAB 1: État Civil & CIN ──────────────────────────────────────────
        self.tab_civil = QWidget()
        tab_civil_outer = QVBoxLayout(self.tab_civil)
        tab_civil_outer.setContentsMargins(0, 0, 0, 0)
        tab_civil_outer.setSpacing(0)

        civil_scroll = QScrollArea(self.tab_civil)
        civil_scroll.setWidgetResizable(True)
        civil_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        civil_scroll_widget = QWidget()
        # Scoped to this widget by name. Written bare ("background: transparent;")
        # Qt applies it to every descendant, and a widget stylesheet outranks the
        # application one — so every button inside lost its fill and painted the
        # default #f0f0f0 instead of its QSS colour.
        civil_scroll_widget.setObjectName("CivilScrollBody")
        civil_scroll_widget.setStyleSheet("QWidget#CivilScrollBody { background: transparent; }")
        civil_layout = QVBoxLayout(civil_scroll_widget)
        civil_layout.setContentsMargins(10, 10, 10, 10)
        civil_layout.setSpacing(15)
        civil_scroll.setWidget(civil_scroll_widget)
        tab_civil_outer.addWidget(civil_scroll)

        # A. Premium OCR Import Bar
        ocr_frame = QFrame(self.tab_civil)
        ocr_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f8fafc, stop:1 #f1f5f9);
                border-radius: 12px;
                border: 1px solid #cbd5e1;
            }
        """)
        ocr_layout = QHBoxLayout(ocr_frame)
        ocr_layout.setContentsMargins(16, 12, 16, 12)
        ocr_layout.setSpacing(14)

        # Left Info Block
        ocr_info_lay = QVBoxLayout()
        ocr_info_lay.setSpacing(2)

        ocr_header = self._tr_label("🪪 Scanner & Extraction Automatique CIN", "الماسح الآلي واستخراج بيانات بطاقة التعريف 🪪")
        ocr_header.setParent(ocr_frame)
        ocr_header.setStyleSheet("font-weight: 800; color: #0f172a; font-size: 14px; border: none;")
        ocr_info_lay.addWidget(ocr_header)

        ocr_subtitle = self._tr_label(
            "Téléversez 1 ou 2 images de la CIN (Face 1 + Face 2) pour pré-remplir automatiquement tous les champs par l'IA.",
            "قم بتحميل صورة أو صورتين لبطاقة التعريف الوطنية (الوجه 1 + الوجه 2) لملء كافة البيانات بالذكاء الاصطناعي."
        )
        ocr_subtitle.setParent(ocr_frame)
        ocr_subtitle.setStyleSheet("color: #64748b; font-size: 11px; border: none;")
        ocr_info_lay.addWidget(ocr_subtitle)

        ocr_layout.addLayout(ocr_info_lay, 1)

        # Right Action Button (Primary Dual CIN Upload Button)
        self.ocr_btn = QPushButton(ocr_frame)
        self._tr_btn(self.ocr_btn, "📤 Charger photo(s) CIN (Face 1 + Face 2)", "📤 تحميل صورة/صورتين لبطاقة التعريف (الوجه 1 + 2)")
        self.ocr_btn.setMinimumHeight(42)
        self.ocr_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.ocr_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.ocr_btn.setToolTip("إختيار صورة أو صورتين لبطاقة التعريف (الوجه الأول والوجه الثاني) وقراءتها بواسطة الذكاء الاصطناعي")
        self.ocr_btn.clicked.connect(self.run_ocr)

        self.ocr_progress = QProgressBar(ocr_frame)
        self.ocr_progress.setRange(0, 0) # Infinite spinner
        self.ocr_progress.setVisible(False)
        self.ocr_progress.setStyleSheet("QProgressBar { max-height: 12px; min-width: 120px; }")

        ocr_layout.addWidget(self.ocr_btn)
        ocr_layout.addWidget(self.ocr_progress)
        civil_layout.addWidget(ocr_frame)

        # B. Fields Layout
        fields_container = QHBoxLayout()
        fields_container.setSpacing(20)

        # Photo column
        photo_col = QVBoxLayout()
        photo_col.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.photo_preview = QLabel(self.tab_civil)
        self.photo_preview.setFixedSize(150, 150)
        self.photo_preview.setStyleSheet("border: 2px dashed #475569; border-radius: 10px; background-color: #ffffff;")
        self.photo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.change_pic_btn = QPushButton(self.tab_civil); self._tr_btn(self.change_pic_btn, "Changer la photo", "تغيير الصورة")
        self.change_pic_btn.setProperty("class", "SecondaryButton")
        self.change_pic_btn.clicked.connect(self.change_photo)

        photo_col.addWidget(self.photo_preview)
        photo_col.addWidget(self.change_pic_btn)
        fields_container.addLayout(photo_col, stretch=1)

        # Form fields column
        form_grid = QGridLayout()
        form_grid.setSpacing(10)

        # Create LineEdits and error labels
        self.prenom_input = QLineEdit(self.tab_civil)
        self.prenom_err = QLabel("", self.tab_civil)
        self.prenom_err.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        self.prenom_err.setVisible(False)

        self.nom_input = QLineEdit(self.tab_civil)
        self.nom_err = QLabel("", self.tab_civil)
        self.nom_err.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        self.nom_err.setVisible(False)

        self.cin_input = QLineEdit(self.tab_civil)
        self.cin_err = QLabel("", self.tab_civil)
        self.cin_err.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        self.cin_err.setVisible(False)

        self.phone_input = QLineEdit(self.tab_civil)
        self.phone_err = QLabel("", self.tab_civil)
        self.phone_err.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        self.phone_err.setVisible(False)

        self.maiden_input = QLineEdit(self.tab_civil)
        self.profession_input = QLineEdit(self.tab_civil)
        self.cin_date_place_input = QLineEdit(self.tab_civil)
        self.tf_input = QLineEdit(self.tab_civil)

        self.father_name_input = QLineEdit(self.tab_civil)
        self.grandfather_name_input = QLineEdit(self.tab_civil)
        self.cin_issue_date_input = QLineEdit(self.tab_civil)
        self.cin_issue_place_input = QLineEdit(self.tab_civil)
        
        self.wilaya_combo = QComboBox(self.tab_civil)
        self.wilayas_list = [
            "", "أريانة", "باجة", "بن عروس", "بنزرت", "قابس", "قفصة", "جندوبة", "القيروان",
            "القصرين", "قبلي", "الكاف", "المهدية", "منوبة", "مدنين", "المنستير", "نابل",
            "صفاقس", "سيدي بوزيد", "سليانة", "سوسة", "تطاوين", "توزر", "تونس", "زغوان"
        ]
        self.wilaya_combo.addItems(self.wilayas_list)

        # Date of birth
        dob_layout = QHBoxLayout()
        self.dob_day = QComboBox(self.tab_civil)
        self.dob_month = QComboBox(self.tab_civil)
        self.dob_year = QComboBox(self.tab_civil)
        self.dob_day.addItems([f"{d:02d}" for d in range(1, 32)])
        self.dob_month.addItems([f"{m:02d}" for m in range(1, 13)])
        self.dob_year.addItems([str(y) for y in range(2026, 1920, -1)])
        dob_layout.addWidget(self.dob_day)
        dob_layout.addWidget(self.dob_month)
        dob_layout.addWidget(self.dob_year)

        self.birth_place_input = QLineEdit(self.tab_civil)

        self.marital_combo = QComboBox(self.tab_civil)
        self.combo_options = [
            "أعزب / عازبة",
            "متزوج(ة) بنظام التفرقة في الأملاك",
            "متزوج(ة) بنظام الاشتراك في الأملاك",
            "مطلق / مطلقة",
            "أرمل / أرملة"
        ]
        self.marital_combo.addItems(self.combo_options)

        self.role_combo = QComboBox(self.tab_civil)
        self.role_options = ["مشتري", "بائع", "وارث", "واهب", "موهوب له", "مؤجر", "مستأجر", "وكيل"]
        self.role_combo.addItems(self.role_options)

        self.address_input = QTextEdit(self.tab_civil)
        self.address_input.setMaximumHeight(60)

        self.company_name_input = QLineEdit(self.tab_civil)
        self.company_rc_input = QLineEdit(self.tab_civil)

        # Row 0
        form_grid.addWidget(self._tr_label("Prénom :", "الاسم :"), 0, 0)
        form_grid.addWidget(self.prenom_input, 0, 1)
        form_grid.addWidget(self._tr_label("Nom :", "اللقب :"), 0, 2)
        form_grid.addWidget(self.nom_input, 0, 3)

        # Row 1 (Errors)
        form_grid.addWidget(self.prenom_err, 1, 1)
        form_grid.addWidget(self.nom_err, 1, 3)

        # Row 2
        form_grid.addWidget(self._tr_label("CIN :", "بطاقة التعريف :"), 2, 0)
        form_grid.addWidget(self.cin_input, 2, 1)
        form_grid.addWidget(self._tr_label("Téléphone :", "الهاتف :"), 2, 2)
        form_grid.addWidget(self.phone_input, 2, 3)

        # Row 3 (Errors)
        form_grid.addWidget(self.cin_err, 3, 1)
        form_grid.addWidget(self.phone_err, 3, 3)

        # Row 4
        form_grid.addWidget(self._tr_label("Nom de la mère :", "لقب الأم :"), 4, 0)
        form_grid.addWidget(self.maiden_input, 4, 1)
        form_grid.addWidget(self._tr_label("Délivrance CIN :", "تاريخ ومكان إصدار بطاقة التعريف :"), 4, 2)
        form_grid.addWidget(self.cin_date_place_input, 4, 3)

        # Row 5
        form_grid.addWidget(self._tr_label("Titre Foncier :", "الرسم العقاري :"), 5, 0)
        form_grid.addWidget(self.tf_input, 5, 1)
        form_grid.addWidget(self._tr_label("Gouvernorat :", "ولاية الرسم :"), 5, 2)
        form_grid.addWidget(self.wilaya_combo, 5, 3)

        # Row 6
        form_grid.addWidget(self._tr_label("Date de naissance :", "تاريخ الولادة :"), 6, 0)
        form_grid.addWidget(self._tr_label("Date de naissance :", "تاريخ الولادة :"), 6, 0)
        form_grid.addLayout(dob_layout, 6, 1)
        form_grid.addWidget(self._tr_label("Lieu de naissance :", "مكان الولادة :"), 6, 2)
        form_grid.addWidget(self.birth_place_input, 6, 3)

        # Row 7
        form_grid.addWidget(self._tr_label("État Civil :", "الحالة الزوجية :"), 7, 0)
        form_grid.addWidget(self.marital_combo, 7, 1)
        form_grid.addWidget(self._tr_label("Profession :", "المهنة :"), 7, 2)
        form_grid.addWidget(self.profession_input, 7, 3)

        # Row 8
        form_grid.addWidget(self._tr_label("Qualité :", "الصفة القانونية :"), 8, 0)
        form_grid.addWidget(self.role_combo, 8, 1)
        form_grid.addWidget(self._tr_label("Adresse :", "العنوان :"), 8, 2)
        form_grid.addWidget(self.address_input, 8, 3)

        # Row 9
        form_grid.addWidget(self._tr_label("Société :", "الشركة :"), 9, 0)
        form_grid.addWidget(self.company_name_input, 9, 1)
        form_grid.addWidget(self._tr_label("Identifiant RNE :", "المعرّف الوحيد :"), 9, 2)
        form_grid.addWidget(self.company_rc_input, 9, 3)

        # Row 10 (Parentage)
        form_grid.addWidget(self._tr_label("Prénom du père :", "اسم الأب :"), 10, 0)
        form_grid.addWidget(self.father_name_input, 10, 1)
        form_grid.addWidget(self._tr_label("Prénom du grand-père :", "اسم الجد :"), 10, 2)
        form_grid.addWidget(self.grandfather_name_input, 10, 3)

        # Row 11 (CIN Issue details)
        form_grid.addWidget(self._tr_label("Date d'émission CIN :", "تاريخ إصدار البطاقة :"), 11, 0)
        form_grid.addWidget(self.cin_issue_date_input, 11, 1)
        form_grid.addWidget(self._tr_label("Lieu d'émission CIN :", "مكان إصدار البطاقة :"), 11, 2)
        form_grid.addWidget(self.cin_issue_place_input, 11, 3)

        fields_container.addLayout(form_grid, stretch=3)
        civil_layout.addLayout(fields_container)

        # Save Button
        self.save_btn = QPushButton(civil_scroll_widget); self._tr_btn(self.save_btn, "Enregistrer les données client", "حفظ معطيات الحريف")
        self.save_btn.setProperty("class", "PrimaryButton")
        self.save_btn.clicked.connect(self.save_client)
        civil_layout.addWidget(self.save_btn)
        civil_layout.addStretch()

        self.tabs.addTab(self.tab_civil, "État Civil && CIN" if self.lang == "fr" else "الحالة المدنية والتعريف")

        # ── TAB 2: Dossiers & Finances ───────────────────────────────────────
        self.tab_cases = QWidget()
        cases_lay = QVBoxLayout(self.tab_cases)
        
        # Upper form action
        cases_top = QHBoxLayout()
        self.new_case_btn = QPushButton(self.tab_cases); self._tr_btn(self.new_case_btn, "Nouveau dossier", "فتح ملف إشهاد جديد")
        self.new_case_btn.setProperty("class", "PrimaryButton")
        self.new_case_btn.clicked.connect(self.create_new_case_dialog)
        cases_top.addWidget(self.new_case_btn)
        cases_top.addStretch()
        cases_lay.addLayout(cases_top)

        # Scroll area containing dynamic case expandable frame list
        self.cases_scroll = QScrollArea(self.tab_cases)
        self.cases_scroll.setWidgetResizable(True)
        self.cases_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        self.cases_container = QWidget()
        self.cases_container_layout = QVBoxLayout(self.cases_container)
        self.cases_container_layout.setSpacing(10)
        self.cases_container_layout.setContentsMargins(0, 0, 0, 0)
        self.cases_container_layout.addStretch() # Bottom spacer
        
        self.cases_scroll.setWidget(self.cases_container)
        cases_lay.addWidget(self.cases_scroll)

        self.tabs.addTab(self.tab_cases, "Dossiers && Paiements" if self.lang == "fr" else "الملفات والتسبيقات")

        # ── TAB 3: Documents joints ──────────────────────────────────────────
        self.tab_docs = QWidget()
        docs_lay = QVBoxLayout(self.tab_docs)
        docs_lay.setSpacing(15)

        # Upload header
        upload_bar = QHBoxLayout()
        self.add_doc_btn = QPushButton(self.tab_docs)
        self._tr_btn(self.add_doc_btn, "📤 Ajouter / Importer un document", "📤 إضافة / تحميل وثيقة جديدة")
        self.add_doc_btn.setProperty("class", "PrimaryButton")
        self.add_doc_btn.setMinimumHeight(38)
        self.add_doc_btn.clicked.connect(self.upload_general_document)
        upload_bar.addWidget(self.add_doc_btn)
        upload_bar.addStretch()
        docs_lay.addLayout(upload_bar)

        # Documents Grid (using QListWidget styled)
        self.docs_list = QListWidget(self.tab_docs)
        self.docs_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.docs_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.docs_list.setSpacing(15)
        self.docs_list.setMovement(QListWidget.Movement.Static)
        self.docs_list.setStyleSheet("""
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #1e293b;
                padding: 10px;
            }
            QListWidget::item {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px;
                margin: 5px;
            }
            QListWidget::item:hover {
                border-color: #2563eb;
                background-color: #243249;
            }
        """)
        # Large enough that a scanned page is actually recognisable, with a grid cell
        # sized to fit the thumbnail plus two lines of filename.
        self.docs_list.setIconSize(QSize(128, 128))
        self.docs_list.setGridSize(QSize(168, 190))
        self.docs_list.setWordWrap(True)
        self.docs_list.setUniformItemSizes(True)
        self.docs_list.itemDoubleClicked.connect(self.open_selected_document)
        
        # Context menu for documents (delete, open)
        self.docs_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.docs_list.customContextMenuRequested.connect(self.show_docs_context_menu)

        docs_lay.addWidget(self.docs_list)

        self.tabs.addTab(self.tab_docs, "Documents joints" if self.lang == "fr" else "الوثائق المرفقة")

        # ── TAB 4: Registre des Visites ──────────────────────────────────────────
        self.tab_visits = QWidget()
        visits_outer = QVBoxLayout(self.tab_visits)
        visits_outer.setSpacing(8)

        # Search + export bar
        vis_bar = QHBoxLayout()
        self.visits_search_input = QLineEdit(self.tab_visits)
        self.visits_search_input.textChanged.connect(self.filter_visits)
        vis_bar.addWidget(self.visits_search_input, stretch=1)
        export_vis_btn = QPushButton("تصدير CSV" if self.lang != "fr" else "Exporter CSV", self.tab_visits)
        export_vis_btn.setProperty("class", "SecondaryButton")
        export_vis_btn.clicked.connect(self.export_visits_csv)
        vis_bar.addWidget(export_vis_btn)
        visits_outer.addLayout(vis_bar)

        self.visits_table = QTableView(self.tab_visits)
        self.visits_table.setAlternatingRowColors(True)
        self.visits_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.visits_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.visits_table.verticalHeader().setVisible(False)
        self.visits_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        visits_outer.addWidget(self.visits_table)

        self.visits_data = []  # Populated by load_visits_tab
        self.tabs.addTab(self.tab_visits, "Registre des Visites" if self.lang == "fr" else "سجل الحضور والزيارات")

        self.main_layout.addWidget(self.tabs)

    # ── Translation ──────────────────────────────────────────────────────────
    # This page used to have no update_translations() at all — the only page of the
    # eight without one — and never called setLayoutDirection, so it stayed
    # left-to-right even in Arabic and its labels were hardcoded as
    # "Français / عربي" jammed together. Widgets register their two labels here at
    # construction time and are re-labelled whenever the language changes.

    def _register_tr(self, widget, fr, ar):
        if not hasattr(self, "_tr_registry"):
            self._tr_registry = []
        self._tr_registry.append((widget, fr, ar))
        widget.setText(fr if self.lang == "fr" else ar)
        return widget

    def _tr_label(self, fr, ar):
        """Creates a QLabel that re-translates itself on a language change."""
        return self._register_tr(QLabel(""), fr, ar)

    def _tr_btn(self, button, fr, ar):
        """Registers an existing button so it re-translates on a language change."""
        return self._register_tr(button, fr, ar)

    # Nothing capped the identity fields before: a 500-character paste went
    # straight into the database, and from there into full_name, every client
    # list, every dossier header and every generated PDF.  A Tunisian civil
    # name never approaches this, so 80 is a ceiling, not a constraint.
    NAME_MAX_LEN = 80

    TAB_TITLES = [
        ("État Civil && CIN", "الحالة المدنية والتعريف"),
        ("Dossiers && Paiements", "الملفات والتسبيقات"),
        ("Documents joints", "الوثائق المرفقة"),
        ("Registre des Visites", "سجل الحضور والزيارات"),
    ]

    def update_translations(self):
        """Re-labels every registered widget and flips the layout for Arabic."""
        is_fr = self.lang == "fr"
        for widget, fr, ar in getattr(self, "_tr_registry", []):
            try:
                widget.setText(fr if is_fr else ar)
            except RuntimeError:
                pass        # the widget was destroyed with its tab; skip it

        for i, (fr, ar) in enumerate(self.TAB_TITLES):
            if i < self.tabs.count():
                self.tabs.setTabText(i, fr if is_fr else ar)

        self.setLayoutDirection(
            Qt.LayoutDirection.LeftToRight if is_fr else Qt.LayoutDirection.RightToLeft)

    def load_client_data(self):
        self.client_not_found = False
        if not self.is_new:
            # Load real client data
            db_data = reception.get_client_by_id(self.client_id)
            if db_data:
                self.client_data = db_data
            else:
                # The lookup found nothing — a client deleted on the other networked
                # machine, or a stale link. This used to leave self.client_data holding
                # the LAST client, so their name, CIN and phone were shown under a
                # different id: the notary could edit or delete against the wrong person.
                self.client_not_found = True
                self.init_empty_client()
        else:
            self.init_empty_client()

        # Clean None values to prevent QLineEdit.setText(None) TypeErrors
        for k, v in self.client_data.items():
            if v is None:
                self.client_data[k] = ""

        # Populate state civil fields
        self.prenom_input.setText(self.client_data.get("prenom") or "")
        self.nom_input.setText(self.client_data.get("nom") or "")
        self.father_name_input.setText(self.client_data.get("father_name") or "")
        self.grandfather_name_input.setText(self.client_data.get("grandfather_name") or "")
        self.maiden_input.setText(self.client_data.get("maiden_name") or "")
        self.profession_input.setText(self.client_data.get("profession") or "")
        self.cin_input.setText(self.client_data.get("cin_number") or "")
        self.cin_date_place_input.setText(self.client_data.get("cin_date_place") or "")
        self.cin_issue_date_input.setText(self.client_data.get("cin_issue_date") or "")
        self.cin_issue_place_input.setText(self.client_data.get("cin_issue_place") or "")
        self.phone_input.setText(self.client_data.get("phone") or "")
        self.tf_input.setText(self.client_data.get("titre_foncier") or "")
        
        # Wilaya combo
        w_val = self.client_data.get("wilaya") or ""
        w_idx = self.wilayas_list.index(w_val) if w_val in self.wilayas_list else 0
        self.wilaya_combo.setCurrentIndex(w_idx)

        # Date of birth combo values
        dob = self.client_data.get("birth_date") or "01/01/1990"
        try:
            # Parse DD/MM/YYYY or YYYY-MM-DD
            if "-" in dob:
                dt = datetime.datetime.strptime(dob.split()[0], "%Y-%m-%d").date()
            else:
                dt = datetime.datetime.strptime(dob.split()[0], "%d/%m/%Y").date()
        except Exception:
            dt = datetime.date(1990, 1, 1)
        
        # Set combos
        self.dob_day.setCurrentText(f"{dt.day:02d}")
        self.dob_month.setCurrentText(f"{dt.month:02d}")
        self.dob_year.setCurrentText(str(dt.year))

        self.birth_place_input.setText(self.client_data.get("birth_place") or "")

        # Marital combo
        m_status = self.client_data.get("marital_status") or ""
        m_regime = self.client_data.get("matrimonial_regime") or ""
        
        m_idx = 0
        if "الاشتراك" in m_regime:
            m_idx = 2
        elif "التفرقة" in m_regime:
            m_idx = 1
        elif "مطلق" in m_status or "Divorcé" in m_status:
            m_idx = 3
        elif "أرمل" in m_status or "Veuf" in m_status:
            m_idx = 4
        else:
            m_idx = 0
        self.marital_combo.setCurrentIndex(m_idx)

        # Role
        role = self.client_data.get("legal_role") or "مشتري"
        if role in self.role_options:
            self.role_combo.setCurrentIndex(self.role_options.index(role))

        self.address_input.setPlainText(self.client_data.get("address") or "")
        self.company_name_input.setText(self.client_data.get("company_name") or "")
        self.company_rc_input.setText(self.client_data.get("company_rc") or "")

        # Update headers and visuals
        self.update_header_visuals()
        self.load_client_cases()
        self.load_client_documents()
        self.load_visits_tab()

    def update_header_visuals(self):
        is_fr = self.lang == "fr"
        if getattr(self, "client_not_found", False):
            # Say plainly that this client does not exist, rather than showing blank
            # fields that look like a real but empty record.
            self.banner_name.setText(
                f"Client introuvable ({self.client_id})" if is_fr
                else f"الحريف غير موجود ({self.client_id})")
            self.banner_name.setStyleSheet("font-size: 20px; font-weight: 800; color: #dc2626;")
            self.load_profile_photo()
            while self.banner_badges_layout.count():
                item = self.banner_badges_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            return

        self.banner_name.setStyleSheet("font-size: 20px; font-weight: 800; color: #0369a1;")
        full_name = self.client_data.get("full_name", "").strip()
        if not full_name:
            full_name = "Nouveau client" if is_fr else "حريف جديد"
        self.banner_name.setText(full_name)

        # Profile Picture circular crop
        self.load_profile_photo()

        # Update banner case badges
        # Clear existing badges
        while self.banner_badges_layout.count():
            item = self.banner_badges_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cases = reception.get_client_cases(self.client_id)
        for cs in cases[:4]: # Limit to first 4 badges
            cid = cs.get("case_id", "")
            raw_stat = cs.get("status", "جديد")
            c_stat = raw_stat.split(' / ')[-1] if ' / ' in raw_stat else raw_stat
            
            badge = QLabel(f" {cid} ({c_stat})")
            
            # Badges styles
            b_bg = "#e0f2fe"; b_fg = "#0369a1"; b_border = "#0369a1"
            if "تام" in c_stat or "Finalisé" in c_stat:
                b_bg = "#dcfce7"; b_fg = "#15803d"; b_border = "#15803d"
            elif "إنجاز" in c_stat or "cours" in c_stat:
                b_bg = "#fef3c7"; b_fg = "#b45309"; b_border = "#b45309"
            elif "توقيع" in c_stat or "attente" in c_stat:
                b_bg = "#fae8ff"; b_fg = "#86198f"; b_border = "#86198f"

            badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {b_bg};
                    color: {b_fg};
                    border: 1px solid {b_border};
                    padding: 3px 8px;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """)
            self.banner_badges_layout.addWidget(badge)

    def load_profile_photo(self):
        # Header avatar
        raw_pic = self.client_data.get("profile_pic_path") or self.client_data.get("profile_pic") or ""
        if not raw_pic and not self.is_new:
            prof_file = safe_profile_path(PROFILES_DIR, self.client_id)
            if prof_file and prof_file.exists():
                raw_pic = str(prof_file)

        pic_path = reception.resolve_photo_path(raw_pic) if raw_pic else ""

        if pic_path and os.path.exists(pic_path):
            # Check cache
            # Cached at display size, LRU-bounded. Caching the full-resolution
            # QPixmap held ~195 KB per client forever (~1.9 GB at 10,000 clients).
            rounded_banner = pixmap_cache.circular_avatar(pic_path, 60)
            preview = pixmap_cache.scaled_preview(pic_path, 150, 150)
            if not rounded_banner.isNull():
                self.banner_avatar.setPixmap(rounded_banner)
                self.photo_preview.setPixmap(preview)
                return

        # Fallback avatar representation: MUST clear any previous QPixmap explicitly in Qt
        from PySide6.QtGui import QPixmap
        self.banner_avatar.clear()
        self.banner_avatar.setPixmap(QPixmap())
        self.banner_avatar.setText("👤")
        self.banner_avatar.setStyleSheet("font-size: 32px; color: #64748b; background-color: #ffffff; border-radius: 30px;")
        
        self.photo_preview.clear()
        self.photo_preview.setPixmap(QPixmap())
        self.photo_preview.setText("\nSans photo" if self.lang == "fr" else "\nبدون صورة")
        self.photo_preview.setStyleSheet("color: #64748b; font-size: 13px; font-weight: bold; text-align: center; border: 2px dashed #475569; border-radius: 10px; background-color: #ffffff;")

    # A profile photo used to be accepted on the strength of its file extension
    # alone.  A text file renamed to .jpg was copied into the profiles folder, the
    # database was pointed at it, face enrolment was fired on it and the notary was
    # told "photo and face print updated successfully" — for a file that is not an
    # image.  The header then rendered blank and the client was never recognised.
    MAX_PHOTO_BYTES = 20 * 1024 * 1024
    MIN_PHOTO_PIXELS = 32

    def _validate_image(self, file_path):
        """Returns (ok, message) after actually decoding the file, not trusting its name."""
        is_fr = self.lang == "fr"
        try:
            size = os.path.getsize(file_path)
        except OSError as e:
            return False, (f"Fichier illisible : {e}" if is_fr
                           else f"تعذّرت قراءة الملف : {e}")
        if size == 0:
            return False, ("Le fichier est vide." if is_fr else "الملف فارغ.")
        if size > self.MAX_PHOTO_BYTES:
            mb = size / (1024 * 1024)
            return False, (f"Image trop volumineuse ({mb:.1f} Mo, maximum "
                           f"{self.MAX_PHOTO_BYTES // (1024 * 1024)} Mo)." if is_fr
                           else f"الصورة كبيرة جدا ({mb:.1f} ميغا، الحد الأقصى "
                                f"{self.MAX_PHOTO_BYTES // (1024 * 1024)} ميغا).")

        reader = QImageReader(file_path)
        reader.setDecideFormatFromContent(True)      # sniff the bytes, ignore the name
        if not reader.canRead():
            return False, ("Ce fichier n'est pas une image valide."
                           if is_fr else "هذا الملف ليس صورة صالحة.")
        image = reader.read()
        if image.isNull():
            return False, (f"Image illisible ou corrompue : {reader.errorString()}"
                           if is_fr else "الصورة تالفة أو غير قابلة للقراءة.")
        if image.width() < self.MIN_PHOTO_PIXELS or image.height() < self.MIN_PHOTO_PIXELS:
            return False, (f"Image trop petite ({image.width()}x{image.height()} px, "
                           f"minimum {self.MIN_PHOTO_PIXELS}x{self.MIN_PHOTO_PIXELS})."
                           if is_fr else
                           f"الصورة صغيرة جدا ({image.width()}x{image.height()} بيكسل).")
        return True, ""

    # What each failure code means to the person looking at the screen.
    ENROL_MESSAGES = {
        "no_file": ("Le fichier photo est introuvable.",
                    "\u0645\u0644\u0641 \u0627\u0644\u0635\u0648\u0631\u0629 \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f."),
        "unreadable": ("Cette image n'a pas pu \u00eatre lue.",
                       "\u062a\u0639\u0630\u0651\u0631\u062a \u0642\u0631\u0627\u0621\u0629 \u0647\u0630\u0647 \u0627\u0644\u0635\u0648\u0631\u0629."),
        "no_face": ("Aucun visage n'a \u00e9t\u00e9 d\u00e9tect\u00e9 sur cette photo.",
                    "\u0644\u0645 \u064a\u062a\u0645 \u0627\u0644\u0639\u062b\u0648\u0631 \u0639\u0644\u0649 \u0648\u062c\u0647 \u0641\u064a \u0647\u0630\u0647 \u0627\u0644\u0635\u0648\u0631\u0629."),
        "not_saved": ("L'empreinte n'a pas pu \u00eatre enregistr\u00e9e dans la fiche.",
                      "\u062a\u0639\u0630\u0651\u0631 \u062d\u0641\u0638 \u0628\u0635\u0645\u0629 \u0627\u0644\u0648\u062c\u0647 \u0641\u064a \u0627\u0644\u0628\u0637\u0627\u0642\u0629."),
        "error": ("Une erreur est survenue pendant l'analyse du visage.",
                  "\u062d\u062f\u062b \u062e\u0637\u0623 \u0623\u062b\u0646\u0627\u0621 \u062a\u062d\u0644\u064a\u0644 \u0627\u0644\u0648\u062c\u0647."),
    }

    def _enrol_face(self, client_id, photo_path):
        """Starts enrolment and routes the real outcome back to this page."""
        reception.update_client_facial_embedding_from_photo_async(
            client_id, photo_path,
            on_done=lambda ok, reason: self.face_enrolment_done.emit(
                bool(ok), str(reason), str(client_id)))

    def _on_face_enrolment_done(self, ok, reason, client_id):
        """
        Says what actually happened, once it has actually happened.

        The page used to announce "Photo et empreinte faciale mises a jour avec
        succes !" the instant the worker was dispatched, so a photo with no face
        in it - or a path that did not exist - produced a success message and a
        client the camera would never recognise.
        """
        is_fr = self.lang == "fr"
        # The notary may have moved to another client while the worker ran.
        if str(client_id) != str(getattr(self, "client_id", "")):
            return
        if ok:
            QMessageBox.information(
                self, "Photo",
                "Photo et empreinte faciale mises \u00e0 jour avec succ\u00e8s !" if is_fr
                else "\u062a\u0645 \u062a\u062d\u062f\u064a\u062b \u0627\u0644\u0635\u0648\u0631\u0629 \u0648\u0628\u0635\u0645\u0629 \u0627\u0644\u0648\u062c\u0647 \u0628\u0646\u062c\u0627\u062d!")
            return
        fr_msg, ar_msg = self.ENROL_MESSAGES.get(
            reason, self.ENROL_MESSAGES["error"])
        QMessageBox.warning(
            self, "Empreinte faciale" if is_fr else "\u0628\u0635\u0645\u0629 \u0627\u0644\u0648\u062c\u0647",
            ((fr_msg + "\n\nLa photo est enregistr\u00e9e, mais ce client ne sera pas "
              "reconnu par la cam\u00e9ra. Choisissez une photo de face, bien \u00e9clair\u00e9e.")
             if is_fr else
             (ar_msg + "\n\n\u062a\u0645 \u062d\u0641\u0638 \u0627\u0644\u0635\u0648\u0631\u0629\u060c \u0644\u0643\u0646 \u0644\u0646 \u062a\u062a\u0639\u0631\u0651\u0641 \u0627\u0644\u0643\u0627\u0645\u064a\u0631\u0627 \u0639\u0644\u0649 "
              "\u0647\u0630\u0627 \u0627\u0644\u062d\u0631\u064a\u0641. \u0627\u062e\u062a\u0631 \u0635\u0648\u0631\u0629 \u0623\u0645\u0627\u0645\u064a\u0629 \u0648\u0648\u0627\u0636\u062d\u0629.")))

    def change_photo(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choisir une photo" if self.lang == "fr" else "اختيار صورة",
            "", "Images (*.png *.jpg *.jpeg)"
        )
        if file_path:
            ok, why = self._validate_image(file_path)
            if not ok:
                QMessageBox.warning(
                    self, "Photo refusée" if self.lang == "fr" else "تم رفض الصورة",
                    (why + "\n\nAucune modification n'a été apportée à la fiche."
                     if self.lang == "fr"
                     else why + "\n\nلم يتم تغيير أي شيء في بطاقة الحريف.")
                )
                return

            PROFILES_DIR.mkdir(parents=True, exist_ok=True)
            target_path = safe_profile_path(PROFILES_DIR, self.client_id)
            if target_path is None:
                QMessageBox.critical(self, "Erreur", "Identifiant client invalide — opération annulée.")
                return
            
            try:
                # Copy file to profiles folder
                import shutil
                shutil.copy(file_path, target_path)
                
                # Update database
                if not reception.update_client_profile_pic(self.client_id, str(target_path)):
                    QMessageBox.warning(
                        self, "Erreur" if self.lang == "fr" else "خطأ",
                        "La photo n'a PAS été enregistrée dans la fiche."
                        if self.lang == "fr" else "لم يتم حفظ الصورة في بطاقة الحريف!"
                    )
                    return
                
                self.client_data["profile_pic_path"] = str(target_path)
                self.load_profile_photo()
                self.update_header_visuals()

                # The photo IS saved at this point, so say that much now, and let
                # _on_face_enrolment_done() report the enrolment when it is real.
                QMessageBox.information(
                    self, "Photo",
                    "Photo enregistrée. Analyse du visage en cours…"
                    if self.lang == "fr"
                    else "تم حفظ الصورة. جاري تحليل الوجه…")
                self._enrol_face(self.client_id, str(target_path))
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur de copie: {e}")

    def save_client(self):
        # 1. Clear previous errors
        self.prenom_err.setVisible(False)
        self.nom_err.setVisible(False)
        self.cin_err.setVisible(False)
        self.phone_err.setVisible(False)

        # 2. Extract inputs
        prenom = self.prenom_input.text().strip()
        nom = self.nom_input.text().strip()
        cin = self.cin_input.text().strip()
        phone = self.phone_input.text().strip()
        
        # Matrimonial combos
        sel_marital = self.marital_combo.currentText()
        if "الاشتراك" in sel_marital:
            marital = "متزوج"
            regime = "متزوج بنظام الاشتراك في الأملاك (قانون 1998)"
        elif "التفرقة" in sel_marital:
            marital = "متزوج"
            regime = "متزوج بنظام التفرقة في الأملاك"
        elif "مطلق" in sel_marital:
            marital = "مطلق"
            regime = "غير مطبق"
        elif "أرمل" in sel_marital:
            marital = "أرمل(ة)"
            regime = "غير مطبق"
        else:
            marital = "أعزب"
            regime = "غير مطبق"

        # Validations
        valid = True
        
        # Nom et prenom obligatoire
        if not nom and not prenom:
            self.prenom_err.setText(("Le nom et le prénom sont obligatoires !" if self.lang == "fr" else "الاسم واللقب إجباريان !"))
            self.prenom_err.setVisible(True)
            self.nom_err.setText(("Le nom et le prénom sont obligatoires !" if self.lang == "fr" else "الاسم واللقب إجباريان !"))
            self.nom_err.setVisible(True)
            valid = False
        elif not prenom:
            self.prenom_err.setText(("Le prénom est obligatoire !" if self.lang == "fr" else "الاسم إجباري !"))
            self.prenom_err.setVisible(True)
            valid = False
        elif not nom:
            self.nom_err.setText(("Le nom est obligatoire !" if self.lang == "fr" else "اللقب إجباري !"))
            self.nom_err.setVisible(True)
            valid = False

        # Length cap.  The field keeps what was typed so the notary can shorten
        # it, rather than silently losing the characters past the limit.
        for value, err_label, fr_field, ar_field in (
                (prenom, self.prenom_err, "Le prénom", "الاسم"),
                (nom, self.nom_err, "Le nom", "اللقب")):
            if len(value) > self.NAME_MAX_LEN:
                err_label.setText(
                    f"{fr_field} est trop long : {len(value)} caractères "
                    f"(maximum {self.NAME_MAX_LEN}) !" if self.lang == "fr"
                    else f"{ar_field} طويل جدا : {len(value)} حرفا "
                         f"(الحد الأقصى {self.NAME_MAX_LEN}) !")
                err_label.setVisible(True)
                valid = False

        # CIN exactly 8 digits (Requirement 4)
        if cin and not re.match(r"^\d{8}$", cin):
            self.cin_err.setText(("Le CIN doit faire 8 chiffres !" if self.lang == "fr" else "يجب أن يتكون رقم البطاقة من 8 أرقام !"))
            self.cin_err.setVisible(True)
            valid = False

        # Phone exactly 8 digits (Requirement 4)
        if phone and not re.match(r"^\d{8}$", phone):
            self.phone_err.setText(("Le téléphone doit faire 8 chiffres !" if self.lang == "fr" else "يجب أن يتكون رقم الهاتف من 8 أرقام !"))
            self.phone_err.setVisible(True)
            valid = False

        if not valid:
            QMessageBox.warning(self, "Erreur de validation", "Veuillez corriger les erreurs de saisie." if self.lang == "fr" else "يرجى إصلاح أخطاء الإدخال.")
            return

        # Prepare date string
        bdate = f"{self.dob_day.currentText()}/{self.dob_month.currentText()}/{self.dob_year.currentText()}"

        # A client was found in a real office database carrying the literal id
        # "NEW" — the placeholder, saved as though it were an identifier. Its
        # card then opened a blank form instead of that person's file, because
        # "NEW" is exactly what the New-client button emits. Whatever let the
        # placeholder through has been closed upstream; this is the last line of
        # defence, so it can never reach the clients table again.
        if not self.client_id or str(self.client_id).strip().upper() == "NEW":
            self.client_id = reception.generate_client_id()
            self.client_data["client_id"] = self.client_id

        # Write to DB using core module (Requirement 4 check)
        try:
            father_name = self.father_name_input.text().strip()
            grandfather_name = self.grandfather_name_input.text().strip()
            cin_issue_date = self.cin_issue_date_input.text().strip()
            cin_issue_place = self.cin_issue_place_input.text().strip()

            success = reception.update_client_civil_status(
                client_id=self.client_id,
                nom=nom,
                prenom=prenom,
                father_name=father_name,
                grandfather_name=grandfather_name,
                phone=phone,
                maiden_name=self.maiden_input.text().strip(),
                birth_date=bdate,
                birth_place=self.birth_place_input.text().strip(),
                cin_number=cin,
                cin_date_place=self.cin_date_place_input.text().strip(),
                cin_issue_date=cin_issue_date,
                cin_issue_place=cin_issue_place,
                marital_status=marital,
                matrimonial_regime=regime,
                profession=self.profession_input.text().strip(),
                address=self.address_input.toPlainText().strip(),
                legal_role=self.role_combo.currentText(),
                company_name=self.company_name_input.text().strip(),
                company_rc=self.company_rc_input.text().strip(),
                titre_foncier=self.tf_input.text().strip(),
                wilaya=self.wilaya_combo.currentText(),
                is_new=self.is_new
            )
        except reception.ClientIdConflict as e:
            # The generated id already belongs to a real client. Refusing is the whole
            # point: overwriting used to replace their identity and leave their dossiers
            # attached to the wrong person.
            QMessageBox.critical(
                self, "Conflit d'identifiant" if self.lang == "fr" else "تعارض في المعرّف",
                ("Ce dossier client n'a PAS été créé : l'identifiant est déjà "
                 "utilisé par un autre client." + "\n\n" + str(e))
                if self.lang == "fr" else
                ("لم يتم إنشاء بطاقة الحريف: المعرّف مستعمل من طرف حريف آخر."
                 + "\n\n" + str(e)))
            return

        if success:
            self.is_new = False
            self.client_data["full_name"] = f"{prenom} {nom}".strip()
            self.client_data["prenom"] = prenom
            self.client_data["nom"] = nom
            self.client_data["father_name"] = father_name
            self.client_data["grandfather_name"] = grandfather_name
            self.client_data["cin_number"] = cin
            self.client_data["cin_issue_date"] = cin_issue_date
            self.client_data["cin_issue_place"] = cin_issue_place
            self.client_data["phone"] = phone
            
            # Check facial trigger
            if self.client_data.get("profile_pic_path"):
                self._enrol_face(self.client_id, self.client_data["profile_pic_path"])

            self.update_header_visuals()
            QMessageBox.information(self, "Sauvegarde", "Fiche client enregistrée avec succès !" if self.lang == "fr" else "تم حفظ معطيات الزبون بنجاح!")
        else:
            # A failed save used to produce nothing at all — no dialog, no error label,
            # no exception — so the notary believed the edit had been recorded.
            QMessageBox.critical(
                self, "Erreur d'enregistrement" if self.lang == "fr" else "خطأ في الحفظ",
                ("Les modifications n'ont PAS été enregistrées. Aucune donnée n'a été "
                 "changée — consultez le journal des erreurs dans Paramètres.")
                if self.lang == "fr" else
                ("لم يتم حفظ التعديلات! لم يطرأ أي تغيير على البيانات — "
                 "راجع سجل الأخطاء في صفحة الإعدادات."))

    def run_ocr(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Sélectionner les photos CIN (Face 1 et/ou Face 2) / إختر صور بطاقة التعريف (الوجه الأول والوجه الثاني)",
            "",
            "Images / Documents (*.png *.jpg *.jpeg *.webp *.bmp *.pdf)"
        )
        if file_paths:
            self.ocr_btn.setEnabled(False)
            self.ocr_progress.setVisible(True)

            try:
                front_bytes = None
                back_bytes = None
                with open(file_paths[0], "rb") as f:
                    front_bytes = f.read()
                if len(file_paths) > 1:
                    with open(file_paths[1], "rb") as f:
                        back_bytes = f.read()

                api_key = config.load_saved_api_keys("gemini") or os.environ.get("GEMINI_API_KEY", "")
                self.ocr_thread = OCRThread(front_bytes, back_bytes, api_key)
                self.ocr_thread.finished.connect(self.on_ocr_finished)
                self.ocr_thread.start()
            except Exception as e:
                self.on_ocr_finished({"success": False, "error": str(e)})

    def on_ocr_finished(self, result):
        self.ocr_btn.setEnabled(True)
        self.ocr_progress.setVisible(False)

        if result.get("success"):
            data = result.get("data", {})
            
            # Prefill fields
            if data.get("cin_number"):
                self.cin_input.setText(str(data["cin_number"]).strip())
            if data.get("first_name"):
                self.prenom_input.setText(str(data["first_name"]).strip())
            if data.get("last_name"):
                self.nom_input.setText(str(data["last_name"]).strip())
            elif data.get("full_name"):
                names = str(data["full_name"]).strip().split(" ")
                self.prenom_input.setText(names[0])
                self.nom_input.setText(" ".join(names[1:]) if len(names) > 1 else "")
            if data.get("birth_date"):
                dob_val = str(data["birth_date"]).strip() # Expected YYYY/MM/DD or DD/MM/YYYY
                parts = re.split(r"[/\-\.]", dob_val)
                if len(parts) == 3:
                    if len(parts[0]) == 4: # YYYY/MM/DD
                        self.dob_year.setCurrentText(parts[0])
                        self.dob_month.setCurrentText(parts[1])
                        self.dob_day.setCurrentText(parts[2])
                    else: # DD/MM/YYYY
                        self.dob_day.setCurrentText(parts[0])
                        self.dob_month.setCurrentText(parts[1])
                        self.dob_year.setCurrentText(parts[2])
            if data.get("birth_place"):
                self.birth_place_input.setText(str(data["birth_place"]).strip())
            if data.get("father_name"):
                self.father_name_input.setText(str(data["father_name"]).strip())
            if data.get("grandfather_name"):
                self.grandfather_name_input.setText(str(data["grandfather_name"]).strip())
            if data.get("issue_date"):
                self.cin_date_place_input.setText(str(data["issue_date"]).strip())
                self.cin_issue_date_input.setText(str(data["issue_date"]).strip())
            if data.get("job"):
                self.profession_input.setText(str(data["job"]).strip())
            if data.get("address"):
                self.address_input.setPlainText(str(data["address"]).strip())

            QMessageBox.information(self, "OCR CIN", "Données de la CIN lues et appliquées aux champs avec succès !" if self.lang == "fr" else "تم استخراج وتطبيق بيانات بطاقة التعريف الوطنية بنجاح!")
        else:
            QMessageBox.warning(self, "OCR CIN", f"Échec de l'OCR: {result.get('error')}" if self.lang == "fr" else f"فشل استخراج المعطيات: {result.get('error')}")

    def load_client_cases(self):
        # Clean existing case widgets
        for i in reversed(range(self.cases_container_layout.count())):
            item = self.cases_container_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()

        cases = reception.get_client_cases(self.client_id)
        is_fr = self.lang == "fr"

        if not cases:
            no_case = self._tr_label("Aucun dossier enregistré pour ce client.", "لا توجد ملفات مسجلة لهذا الحريف.")
            no_case.setStyleSheet("color: #64748b; font-style: italic; padding: 15px;")
            self.cases_container_layout.addWidget(no_case)
        else:
            for cs in cases:
                case_widget = self.build_case_card_widget(cs)
                self.cases_container_layout.addWidget(case_widget)

        self.cases_container_layout.addStretch() # Reposition spacer

    def build_case_card_widget(self, cs):
        cid = cs.get("case_id")
        title = cs.get("title", "")
        service_type = cs.get("service_type", "")
        status = cs.get("status", "جديد")
        total_amount = float(cs.get("total_amount") or 0.0)
        avance_amount = float(cs.get("avance_amount") or 0.0)
        remaining = round(total_amount - avance_amount, 3)
        payment_notes = cs.get("payment_notes", "")
        created_at = cs.get("created_at", "")

        is_fr = self.lang == "fr"

        card = QFrame(self.cases_container)
        card.setObjectName("CaseDetailCard")
        card.setStyleSheet("""
            QFrame#CaseDetailCard {
                background-color: #ffffff;
                border: 1px solid #334155;
                border-radius: 8px;
                margin-bottom: 5px;
            }
        """)

        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(15, 12, 15, 12)
        card_lay.setSpacing(8)

        # ── Header row: title + status ────────────────────────────────────
        title_row = QHBoxLayout()
        title_lbl = QLabel(f" {'Dossier N°' if is_fr else 'ملف رقم'} {cid} — {title}", card)
        title_lbl.setStyleSheet("font-weight: 800; font-size: 14px; color: #ffffff;")

        status_lbl = QLabel(f"● {status}", card)
        if "جديد" in status or "Nouveau" in status:
            status_lbl.setStyleSheet("color: #38bdf8; font-weight: bold;")
        elif "إنجاز" in status or "cours" in status:
            status_lbl.setStyleSheet("color: #fbbf24; font-weight: bold;")
        elif "توقيع" in status or "attente" in status:
            status_lbl.setStyleSheet("color: #c084fc; font-weight: bold;")
        else:
            status_lbl.setStyleSheet("color: #34d399; font-weight: bold;")

        title_row.addWidget(title_lbl, stretch=1)
        title_row.addWidget(status_lbl)
        card_lay.addLayout(title_row)

        # ── Meta row & Notes/Remarques ────────────────────────────────────
        meta_lbl = QLabel(f"{'Type' if is_fr else 'نوع العقد'}: {service_type}  |  {'Création' if is_fr else 'التاريخ'}: {str(created_at).split()[0]}", card)
        meta_lbl.setStyleSheet("color: #64748b; font-size: 12px;")
        card_lay.addWidget(meta_lbl)

        # ── Notes / Remarques section ──────────────────────────────────────────
        notes_text = (cs.get("payment_notes") or cs.get("notes") or "").strip()
        if notes_text:
            notes_lbl = QLabel(f"<b>{'Remarques' if is_fr else 'ملاحظات'}:</b> {notes_text}", card)
            notes_lbl.setWordWrap(True)
            notes_lbl.setStyleSheet("""
                QLabel {
                    background-color: #f8fafc;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 8px 12px;
                    color: #1e293b;
                    font-size: 12px;
                    margin-top: 4px;
                    margin-bottom: 4px;
                }
            """)
            card_lay.addWidget(notes_lbl)

        # ── Actions row ───────────────────────────────────────────────────
        actions_row = QHBoxLayout()

        status_combo = QComboBox(card)
        status_options = [
            "Nouveau" if is_fr else "جديد",
            "En cours" if is_fr else "قيد الإنجاز",
            "En attente de signature" if is_fr else "في انتظار التوقيع",
            "Finalisé & Archivé" if is_fr else "تام ومسجل"
        ]
        status_combo.addItems(status_options)
        idx = 0
        for i, opt in enumerate(status_options):
            if opt.lower() in status.lower() or ("جديد" in status and i == 0):
                idx = i
                break
        status_combo.setCurrentIndex(idx)
        status_combo.currentIndexChanged.connect(lambda index, cid=cid, sc=status_combo: self.change_case_status(cid, sc.currentText()))

        pay_btn = QPushButton("Finances" if self.lang == "fr" else "الخلاص", card)
        pay_btn.setProperty("class", "SecondaryButton")
        pay_btn.clicked.connect(lambda checked=False, cid=cid, tot=total_amount, av=avance_amount, notes=payment_notes: self.open_payment_dialog_full(cid, tot, av, notes))

        attach_btn = QPushButton("📤 Ajouter un document" if is_fr else "📤 إضافة وثيقة للملف", card)
        attach_btn.setProperty("class", "PrimaryButton")
        attach_btn.clicked.connect(lambda checked=False, cid=cid: self.attach_case_document(cid))

        actions_row.addWidget(status_combo)
        actions_row.addWidget(pay_btn)
        actions_row.addWidget(attach_btn)
        card_lay.addLayout(actions_row)

        # ── Documents linked to this case ──────────────────────────────
        try:
            all_docs = reception.get_client_documents_list(self.client_id)
            case_docs = [d for d in all_docs
                         if f"Dossier_{cid}_" in d["name"] or f"Reçu_Paiement_{cid}_" in d["name"]
                         or f"Paiement_{cid}_" in d["name"]]
        except Exception:
            case_docs = []

        if case_docs:
            docs_sep = QLabel(f" {'Documents' if is_fr else 'وثائق الملف'} ({len(case_docs)}) :", card)
            docs_sep.setStyleSheet("font-size:11px; color:#64748b; font-weight:bold; margin-top:4px;")
            card_lay.addWidget(docs_sep)

            IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

            # Every document is listed. This used to be case_docs[:5], which hid the
            # rest of a case's paperwork with nothing on screen to say so.
            for doc in case_docs:
                dpath = doc["path"]
                dname = doc["name"]
                clean_name = dname.replace(f"Dossier_{cid}_", "").replace(f"Reçu_Paiement_{cid}_", "")
                is_image = Path(dname).suffix.lower() in IMAGE_EXTS

                doc_row = QHBoxLayout()
                doc_row.setSpacing(8)

                # Thumbnail for image attachments, so a scanned receipt or ID is
                # visible at a glance instead of being just a filename.
                thumb_lbl = QLabel(card)
                thumb_lbl.setFixedSize(56, 56)
                thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb_lbl.setStyleSheet(
                    "border:1px solid #334155; border-radius:6px; background:#0f172a;")
                if is_image and os.path.exists(dpath):
                    # Cached at display size (bounded LRU) — never the full-resolution image.
                    pm = pixmap_cache.scaled_preview(dpath, 54, 54)
                    if not pm.isNull():
                        thumb_lbl.setPixmap(pm)
                        thumb_lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        thumb_lbl.setToolTip(f"{dname}\n{'Cliquer pour ouvrir' if is_fr else 'اضغط للفتح والمعاينة'}")
                        thumb_lbl.mousePressEvent = (
                            lambda ev, d=doc, c_docs=case_docs: self._open_gallery_dialog(d, c_docs))
                    else:
                        thumb_lbl.setText("🖼️")
                else:
                    thumb_lbl.setText("📄" if Path(dname).suffix.lower() != ".pdf" else "📕")
                    thumb_lbl.setStyleSheet(
                        "border:1px solid #334155; border-radius:6px; background:#0f172a; font-size:22px;")

                doc_lbl = QLabel(f"{clean_name}\n{doc['size_kb']} KB", card)
                doc_lbl.setStyleSheet("font-size:11px; color:#cbd5e1;")
                doc_lbl.setWordWrap(True)
                doc_lbl.setToolTip(dname)

                dl_btn = QPushButton("👁️", card)
                dl_btn.setFixedSize(32, 28)
                dl_btn.setStyleSheet("font-size:13px; padding:0px; background:#1e293b; color:#38bdf8; border:1px solid #334155; border-radius:4px;")
                dl_btn.setToolTip("معاينة الوثيقة / Ouvrir la galerie")
                dl_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                dl_btn.clicked.connect(lambda chk=False, d=doc, c_docs=case_docs: self._open_gallery_dialog(d, c_docs))

                del_btn = QPushButton("🗑️", card)
                del_btn.setFixedSize(32, 28)
                del_btn.setStyleSheet("font-size:13px; padding:0px; background:#1e293b; color:#ef4444; border:1px solid #334155; border-radius:4px;")
                del_btn.setToolTip("حذف الوثيقة / Supprimer")
                del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                del_btn.clicked.connect(lambda chk=False, n=dname: self._delete_case_doc(n))
                del_btn.clicked.connect(lambda chk=False, n=dname: self._delete_case_doc(n))

                doc_row.addWidget(thumb_lbl)
                doc_row.addWidget(doc_lbl, stretch=1)
                doc_row.addWidget(dl_btn)
                doc_row.addWidget(del_btn)
                card_lay.addLayout(doc_row)

        return card

    def change_case_status(self, case_id, new_stat):
        # Remove prefix formatting if any
        clean_stat = new_stat.replace("", "").replace("", "").replace("", "").replace("", "")
        
        # Store in Arabic primarily to match database rules
        db_stat = clean_stat
        if "Nouveau" in clean_stat: db_stat = "جديد"
        elif "En cours" in clean_stat: db_stat = "قيد الإنجاز"
        elif "En attente" in clean_stat: db_stat = "في انتظار التوقيع"
        elif "Finalisé" in clean_stat: db_stat = "تام ومسجل"

        success = reception.update_case_status(case_id, db_stat)
        if success:
            reception.clear_db_caches()
            self.load_client_cases()
            self.update_header_visuals()

    def open_payment_dialog_full(self, case_id, total, avance, payment_notes):
        is_fr = self.lang == "fr"

        dialog = QDialog(self)
        dialog.setWindowTitle("الوضعية المالية للملف" if not is_fr else "Situation Financière du Dossier")
        dialog.setMinimumWidth(430)
        dialog.setModal(True)
        lay = QVBoxLayout(dialog)
        lay.setSpacing(10)

        # Current state display
        rem = round(total - avance, 3)
        state_frame = QFrame()
        state_frame.setStyleSheet("background:#f0f9ff; border-radius:8px; border:1px solid #bae6fd;")
        state_lay = QHBoxLayout(state_frame)
        for lbl_txt, val, col in [
            ("إجمالي" if not is_fr else "Total", total, "#1e293b"),
            ("مدفوع" if not is_fr else "Payé", avance, "#16a34a"),
            ("متبقي" if not is_fr else "Reste", rem, "#ef4444" if rem > 0 else "#16a34a")
        ]:
            w = QLabel(f"<center><b style='color:#64748b;font-size:11px'>{lbl_txt}</b><br><span style='color:{col};font-size:15px;font-weight:900'>{val:.3f} DT</span></center>")
            w.setTextFormat(Qt.TextFormat.RichText)
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            state_lay.addWidget(w)
        lay.addWidget(state_frame)

        # New versement
        sep1 = QLabel("─── " + ("دفعة جديدة" if not is_fr else "Nouveau versement") + " ───")
        sep1.setStyleSheet("color:#0284c7; font-weight:bold;")
        lay.addWidget(sep1)
        add_pay_row = QHBoxLayout()
        add_pay_row.addWidget(QLabel("مبلغ الدفعة :" if not is_fr else "Montant :"))
        add_pay_spin = MoneySpinBox(dialog)
        add_pay_row.addWidget(add_pay_spin)
        lay.addLayout(add_pay_row)

        # Global modification
        sep2 = QLabel("─── " + ("التعديل الجملي" if not is_fr else "Modification globale") + " ───")
        sep2.setStyleSheet("color:#64748b; font-weight:bold;")
        lay.addWidget(sep2)
        glob_row = QHBoxLayout()
        glob_row.addWidget(QLabel("إجمالي جملي :" if not is_fr else "Total global :"))
        new_tot_spin = MoneySpinBox(dialog)
        new_tot_spin.setValue(total)
        glob_row.addWidget(new_tot_spin)
        glob_row.addWidget(QLabel("تسبقة جملية :" if not is_fr else "Acompte cumulé :"))
        new_av_spin = MoneySpinBox(dialog)
        new_av_spin.setValue(avance)
        glob_row.addWidget(new_av_spin)
        lay.addLayout(glob_row)

        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel("ملاحظات :" if not is_fr else "Notes :"))
        notes_edit = QLineEdit()
        notes_edit.setText(payment_notes or "")
        notes_row.addWidget(notes_edit, stretch=1)
        lay.addLayout(notes_row)

        # Proof file
        proof_path = [""]
        proof_display = QLabel("لا يوجد وصل" if not is_fr else "Aucun fichier")
        proof_display.setStyleSheet("color:#64748b; font-style:italic; font-size:11px;")

        def browse_proof():
            fp, _ = QFileDialog.getOpenFileName(dialog, "وصل الدفع", "", "Fichiers (*.pdf *.jpg *.jpeg *.png)")
            if fp:
                proof_path[0] = fp
                proof_display.setText(Path(fp).name)

        proof_row = QHBoxLayout()
        proof_btn = QPushButton("وصل دفع" if not is_fr else "Justificatif")
        proof_btn.clicked.connect(browse_proof)
        proof_row.addWidget(proof_btn)
        proof_row.addWidget(proof_display, stretch=1)
        lay.addLayout(proof_row)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        lay.addWidget(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            add_pay = add_pay_spin.value()
            final_tot = new_tot_spin.value()
            final_av = new_av_spin.value() + add_pay
            final_notes = notes_edit.text().strip()

            if final_av >= final_tot and final_tot > 0:
                p_status = "خالص بالكامل"
            elif final_av > 0:
                p_status = "تسبقة"
            else:
                p_status = "غير خالص"

            if proof_path[0]:
                try:
                    with open(proof_path[0], 'rb') as f:
                        proof_bytes = f.read()
                    pname = f"Reçu_Paiement_{case_id}_{Path(proof_path[0]).name}"
                    saved = reception.save_client_document(self.client_id, proof_bytes, pname)
                    # Overwriting a file reuses its path, so drop any cached thumbnail.
                    if saved:
                        pixmap_cache.invalidate(saved)
                    final_notes += f" [وصل مرفق: {Path(proof_path[0]).name}]"
                except Exception as attach_err:
                    # (a) The receipt for a PAYMENT. Losing it silently while the
                    # payment itself is recorded is the worst version of this bug:
                    # the money is in the books with no document behind it.
                    QMessageBox.warning(
                        self, "Reçu" if is_fr else "الوصل",
                        (f"Le paiement sera enregistré, mais le reçu n'a PAS pu "
                         f"être joint.\n\n{attach_err}" if is_fr else
                         f"سيتم تسجيل الدفعة، لكن لم يتم إرفاق الوصل!\n\n{attach_err}"))

            # The confirmation used to be shown unconditionally, so a payment that never
            # reached the database was still reported to the client as recorded.
            try:
                saved_ok = reception.update_case_payment(
                    case_id, final_tot, final_av, p_status, final_notes)
            except Exception as e:
                QMessageBox.critical(
                    self, "Erreur" if is_fr else "خطأ",
                    f"La modification financière n'a PAS été enregistrée.\n\n{e}" if is_fr
                    else f"لم يتم تسجيل الدفعة!\n\nالسبب: {e}"
                )
                return

            if not saved_ok:
                QMessageBox.critical(
                    self, "Erreur" if is_fr else "خطأ",
                    f"La modification financière n'a PAS été enregistrée : "
                    f"dossier {case_id} introuvable." if is_fr
                    else f"لم يتم تسجيل الدفعة! الملف {case_id} غير موجود."
                )
                return

            QMessageBox.information(
                self, "Finances",
                "تم تسجيل الدفعة والتعديلات بنجاح!" if not is_fr
                else "Modifications financières enregistrées !"
            )
            self.load_client_cases()

    def attach_case_document(self, case_id):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un document pour le dossier / إرفاق ملف", "", "Fichiers (*.pdf *.docx *.doc *.jpg *.jpeg *.png *.webp)"
        )
        if file_path:
            try:
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                filename = Path(file_path).name
                saved = reception.save_client_document(
                    self.client_id, file_bytes, f"Dossier_{case_id}_{filename}")
                if saved:
                    pixmap_cache.invalidate(saved)
                
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur de sauvegarde: {e}")

    def scan_cin_with_camera(self):
        from ui.dialogs.document_scan_dialog import DocumentScanDialog
        w = self.window()
        svc = getattr(w, "camera_service", None)
        dlg = DocumentScanDialog(self, client_id=self.client_id, mode="cin", camera_service=svc, lang=self.lang)
        dlg.scanned_successfully.connect(self._on_cin_camera_scanned)
        dlg.exec()

    def _on_cin_camera_scanned(self, res: dict):
        if res and res.get("extracted"):
            ext = res["extracted"]
            if ext.get("cin_number"): self.cin_input.setText(ext["cin_number"])
            if ext.get("full_name"):
                names = ext["full_name"].strip().split(" ")
                self.prenom_input.setText(names[0])
                self.nom_input.setText(" ".join(names[1:]) if len(names) > 1 else "")
            if ext.get("birth_date"):
                parts = ext["birth_date"].split("/")
                if len(parts) == 3:
                    self.dob_day.setCurrentText(parts[0])
                    self.dob_month.setCurrentText(parts[1])
                    self.dob_year.setCurrentText(parts[2])
            if ext.get("birth_place"): self.birth_place_input.setText(ext["birth_place"])
            if ext.get("father_name"): self.father_name_input.setText(ext["father_name"])
            if ext.get("grandfather_name"): self.grandfather_name_input.setText(ext["grandfather_name"])
            if ext.get("address"): self.address_input.setPlainText(ext["address"])

    def scan_document_with_camera(self):
        from ui.dialogs.document_scan_dialog import DocumentScanDialog
        w = self.window()
        svc = getattr(w, "camera_service", None)
        dlg = DocumentScanDialog(self, client_id=self.client_id, mode="document", camera_service=svc, lang=self.lang)
        dlg.scanned_successfully.connect(lambda res: self.load_client_documents())
        dlg.exec()

    def create_new_case_dialog(self):
        is_fr = self.lang == "fr"

        dialog = QDialog(self)
        dialog.setWindowTitle("Nouveau Dossier Notarié" if is_fr else "فتح ملف إشهاد جديد")
        dialog.setMinimumWidth(560)
        dialog.setModal(True)
        lay = QVBoxLayout(dialog)
        lay.setSpacing(10)

        # N° dossier custom
        row_num = QHBoxLayout()
        row_num.addWidget(QLabel("رقم الملف (اختياري) :" if not is_fr else "N° Dossier (optionnel) :"))
        num_input = QLineEdit()
        row_num.addWidget(num_input, stretch=1)
        lay.addLayout(row_num)

        # Contract type (Pure Arabic Options)
        type_lbl = QLabel("نوع العقد :" if not is_fr else "Type de contrat :")
        type_combo = QComboBox()
        type_combo.addItems([
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
        ])
        lay.addWidget(type_lbl)
        lay.addWidget(type_combo)

        # Title
        title_lbl = QLabel("عنوان العقد التفصيلي :" if not is_fr else "Objet détaillé du contrat :")
        title_input = QLineEdit()
        lay.addWidget(title_lbl)
        lay.addWidget(title_input)

        # Notes / Description
        desc_lbl = QLabel("ملاحظات العقد :" if not is_fr else "Notes du contrat :")
        desc_input = QTextEdit()
        desc_input.setMaximumHeight(70)
        lay.addWidget(desc_lbl)
        lay.addWidget(desc_input)

        # Financial section
        fin_sep = QLabel("" + ("معطيات الخلاص والمالية" if not is_fr else "Informations Financières"))
        fin_sep.setStyleSheet("font-weight:bold; color:#0284c7; margin-top:6px;")
        lay.addWidget(fin_sep)

        fin_row = QHBoxLayout()
        fin_row.addWidget(QLabel("الإجمالي :" if not is_fr else "Total :"))
        tot_spin = MoneySpinBox(dialog)
        fin_row.addWidget(tot_spin)
        fin_row.addWidget(QLabel("التسبقة :" if not is_fr else "Acompte :"))
        av_spin = MoneySpinBox(dialog)
        fin_row.addWidget(av_spin)
        lay.addLayout(fin_row)

        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel("طريقة الخلاص :" if not is_fr else "Mode de règlement :"))
        notes_input = QLineEdit()
        notes_row.addWidget(notes_input, stretch=1)
        lay.addLayout(notes_row)

        # File attachments
        files_sep = QLabel("" + ("وثائق الملف" if not is_fr else "Documents du dossier"))
        files_sep.setStyleSheet("font-weight:bold; margin-top:6px;")
        lay.addWidget(files_sep)

        self._new_case_files = []
        files_count_lbl = QLabel("لا يوجد ملف محدد" if not is_fr else "Aucun fichier")
        files_count_lbl.setStyleSheet("color:#64748b; font-style:italic; font-size:11px;")

        def browse_attach():
            paths, _ = QFileDialog.getOpenFileNames(
                dialog, "اختيار ملفات / Fichiers", "",
                "Fichiers (*.pdf *.docx *.doc *.jpg *.jpeg *.png)"
            )
            if paths:
                self._new_case_files = paths
                files_count_lbl.setText(f"{len(paths)} ملف / fichier(s) sélectionné(s)")

        files_row = QHBoxLayout()
        browse_f_btn = QPushButton("استعراض" if not is_fr else "Parcourir")
        browse_f_btn.clicked.connect(browse_attach)
        files_row.addWidget(browse_f_btn)
        files_row.addWidget(files_count_lbl, stretch=1)
        lay.addLayout(files_row)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        lay.addWidget(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            if not title_input.text().strip():
                QMessageBox.warning(self, "خطأ", "عنوان العقد إجباري." if not is_fr else "L'objet du contrat est obligatoire.")
                return

            tot_v = tot_spin.value()
            av_v = av_spin.value()
            if av_v >= tot_v and tot_v > 0:
                p_status = "خالص بالكامل"
            elif av_v > 0:
                p_status = "تسبقة"
            else:
                p_status = "غير خالص"

            custom_id = num_input.text().strip() or None
            new_id = reception.create_case(
                client_id=self.client_id,
                service_type=type_combo.currentText(),
                title=title_input.text().strip(),
                description=desc_input.toPlainText().strip(),
                total_amount=tot_v,
                avance_amount=av_v,
                payment_status=p_status,
                payment_notes=notes_input.text().strip(),
                custom_case_id=custom_id
            )

            if new_id:
                for fpath in getattr(self, '_new_case_files', []):
                    try:
                        with open(fpath, 'rb') as f:
                            fbytes = f.read()
                        if not reception.save_client_document(
                                self.client_id, fbytes,
                                f"Dossier_{new_id}_{Path(fpath).name}"):
                            raise OSError("écriture refusée")
                    except Exception as attach_err:
                        # (a) A document the notary attached while creating the
                        # dossier. The dossier was created and the file was not,
                        # with no indication which ones made it.
                        QMessageBox.warning(
                            self, "Document" if is_fr else "الوثيقة",
                            (f"Le dossier est créé, mais le document "
                             f"{Path(fpath).name} n'a PAS pu être joint."
                             f"\n\n{attach_err}" if is_fr else
                             f"تم إنشاء الملف، لكن لم يتم إرفاق الوثيقة "
                             f"{Path(fpath).name}!\n\n{attach_err}"))

                reception.clear_db_caches()
                self.load_client_cases()
                self.update_header_visuals()
                QMessageBox.information(
                    self, "Dossier",
                    f"تم فتح الملف رقم {new_id} بنجاح!" if not is_fr
                    else f"Dossier N° {new_id} créé avec succès !"
                )

    def load_client_documents(self):
        self.docs_list.clear()
        
        # Read from core logic
        docs = reception.get_client_documents_list(self.client_id)
        for d in docs:
            dname = d["name"]
            dpath = d["path"]
            dsize = d["size_kb"]
            
            item = QListWidgetItem(self.docs_list)
            # Shorten name for display icon mode
            clean_name = dname
            if "Dossier_" in dname:
                clean_name = dname.split("_", 2)[-1]
                
            item.setText(f"{clean_name}\n({dsize} KB)")
            item.setData(Qt.ItemDataRole.UserRole, dpath)
            item.setData(Qt.ItemDataRole.ToolTipRole, dname)
            
            # Custom icons based on extensions
            ext = Path(dname).suffix.lower()
            if ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
                # Real preview of the attachment, scaled to the list's icon size and
                # cached. QIcon(dpath) decoded the full-resolution image every time the
                # list was rebuilt — a 600 KB scan costs far more than the 96px shown.
                pm = pixmap_cache.scaled_preview(dpath, 128, 128) if os.path.exists(dpath) else None
                if pm is not None and not pm.isNull():
                    item.setIcon(QIcon(pm))
                else:
                    item.setIcon(QIcon.fromTheme("image-x-generic"))
            elif ext == ".pdf":
                item.setIcon(QIcon.fromTheme("document-pdf"))
            else:
                item.setIcon(QIcon.fromTheme("text-x-generic"))
                
            self.docs_list.addItem(item)

    def upload_general_document(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Ajouter une pièce / إضافة وثيقة للملف", "", "Tous les fichiers (*.pdf *.docx *.doc *.jpg *.jpeg *.png *.webp)"
        )
        if file_path:
            try:
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                filename = Path(file_path).name
                
                saved = reception.save_client_document(self.client_id, file_bytes, filename)
                if saved:
                    pixmap_cache.invalidate(saved)
                self.load_client_documents()
                QMessageBox.information(self, "Document", "Document téléversé avec succès !" if self.lang == "fr" else "تم حفظ الوثيقة المرفقة بنجاح!")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur d'écriture: {e}")

    def _open_gallery_dialog(self, doc_obj, case_docs=None):
        """Opens interactive document gallery dialog with left/right carousel."""
        docs_to_show = case_docs if case_docs else reception.get_client_documents_list(self.client_id)
        start_idx = 0
        if docs_to_show and doc_obj in docs_to_show:
            start_idx = docs_to_show.index(doc_obj)
        elif docs_to_show and isinstance(doc_obj, str):
            for i, d in enumerate(docs_to_show):
                if d.get("path") == doc_obj or d.get("name") == doc_obj:
                    start_idx = i
                    break

        from ui.dialogs.document_gallery_dialog import DocumentGalleryDialog
        dlg = DocumentGalleryDialog(documents=docs_to_show, start_index=start_idx, parent=self, lang=self.lang)
        dlg.doc_deleted.connect(lambda n: self._delete_case_doc(n))
        dlg.exec()

    def open_selected_document(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            self._open_gallery_dialog(path)

    def show_docs_context_menu(self, point):
        item = self.docs_list.itemAt(point)
        if not item:
            return
            
        is_fr = self.lang == "fr"
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #ffffff; color: #1e293b; border: 1px solid #cbd5e1; }
            QMenu::item:selected { background-color: #e2e8f0; color: #1e293b; }
        """)

        path = item.data(Qt.ItemDataRole.UserRole)
        filename = item.data(Qt.ItemDataRole.ToolTipRole)

        open_action = QAction("Ouvrir le document" if is_fr else "فتح الوثيقة", menu)
        open_action.triggered.connect(lambda: self.open_selected_document(item))
        menu.addAction(open_action)

        delete_action = QAction("Supprimer le document" if is_fr else "حذف الوthيقة", menu)
        delete_action.triggered.connect(lambda: self.delete_document_action(filename))
        menu.addAction(delete_action)

        from PySide6.QtGui import QCursor
        menu.exec(QCursor.pos())

    def delete_document_action(self, filename):
        is_fr = self.lang == "fr"
        reply = QMessageBox.question(
            self, "Confirmation",
            f"Voulez-vous supprimer définitivement la pièce : {filename} ?" if is_fr else f"هل تريد بالتأكيد حذف هذه الوثيقة نهائياً؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Refreshing the list used to be the only feedback: if the delete failed the
            # file simply reappeared, with no explanation.
            try:
                removed = reception.delete_client_document(self.client_id, filename)
            except Exception as e:
                removed, err = False, e
            else:
                err = None
            if not removed:
                QMessageBox.critical(
                    self, "Erreur" if is_fr else "خطأ",
                    (f"La pièce « {filename} » n'a PAS été supprimée."
                     + (f"\n\n{err}" if err else "")) if is_fr
                    else (f"لم يتم حذف الوثيقة «{filename}»."
                          + (f"\n\nالسبب: {err}" if err else ""))
                )
            self.load_client_documents()

    def print_fiche(self):
        """Generates and opens the real PDF summary for this client."""
        is_fr = self.lang == "fr"
        if not getattr(self, "client_id", None):
            QMessageBox.warning(
                self, "Impression" if is_fr else "الطباعة",
                "Aucun client sélectionné." if is_fr else "لم يقع اختيار حريف."
            )
            return

        try:
            import pdf_generator
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl

            client_info = reception.get_client_by_id(self.client_id) or {"full_name": "Client", "client_id": self.client_id}
            cases = getattr(self, "cases_data", []) or reception.get_client_cases(self.client_id)

            pdf_bytes = pdf_generator.generate_client_fiche_pdf(client_info, cases)
            out_dir = DOCUMENTS_DIR / "PDF_Exports"
            out_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = out_dir / f"Fiche_Client_{self.client_id}.pdf"
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path)))
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur PDF" if is_fr else "خطأ في طباعة PDF",
                f"Impossible de générer la fiche PDF : {e}" if is_fr else f"تعذر إنشاء ملف PDF: {e}"
            )

    def update_language(self, lang_code):
        self.lang = lang_code
        self.update_translations()
        self.load_client_data()

    # ── New methods added in audit pass ─────────────────────────────────────

    def load_visits_tab(self):
        """Load check-in visits for this client into the visits table."""
        try:
            df = reception.get_check_ins_for_client(self.client_id)
            if df is None or df.empty:
                self.visits_data = []
            else:
                self.visits_data = df.to_dict('records')
        except Exception:
            self.visits_data = []
        self.filter_visits()


    def _set_visits_model(self, model):
        """Swaps the visits model without leaking the previous one (see accounting_page)."""
        previous = getattr(self, "_visits_model", None)
        self._visits_model = model
        self.visits_table.setModel(model)
        if previous is not None and previous is not model:
            previous.deleteLater()

    def filter_visits(self):
        """Filter the visits table based on search input."""
        q = ""
        if hasattr(self, 'visits_search_input'):
            q = self.visits_search_input.text().strip().lower()

        filtered = self.visits_data if not q else [
            r for r in self.visits_data
            if any(q in str(v).lower() for v in r.values())
        ]

        if not filtered:
            headers = ["لا توجد زيارات مسجلة" if self.lang != "fr" else "Aucune visite enregistrée"]
            self._set_visits_model(SimpleTableModel([], headers))
        else:
            headers = list(filtered[0].keys())
            self._set_visits_model(SimpleTableModel(filtered, headers))
            self.visits_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            self.visits_table.horizontalHeader().setStretchLastSection(True)

    def export_visits_csv(self):
        """Export the visits register to a CSV file."""
        if not self.visits_data:
            QMessageBox.information(
                self, "Export",
                "Aucune visite à exporter." if self.lang == "fr" else "لا توجد زيارات لتصديرها."
            )
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter",
            f"Visites_{self.client_id}.csv",
            "CSV (*.csv)"
        )
        if file_path:
            try:
                import csv
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=list(self.visits_data[0].keys()))
                    writer.writeheader()
                    writer.writerows(self.visits_data)
                QMessageBox.information(self, "Export", "تم تصدير السجل بنجاح!" if self.lang != "fr" else "Registre exporté avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", str(e))

    def delete_client_action(self):
        """Delete the current client after confirmation."""
        is_fr = self.lang == "fr"
        if self.is_new:
            QMessageBox.information(
                self, "Info",
                "Aucun client à supprimer (non encore enregistré)." if is_fr
                else "لا يوجد حريف لحذفه (لم يُحفظ بعد)."
            )
            return
        reply = QMessageBox.warning(
            self,
            "Confirmation de suppression" if is_fr else "تأكيد الحذف",
            ("Voulez-vous supprimer définitivement ce client et toutes ses données ?\n\n"
             "Cette action est IRRÉVERSIBLE.") if is_fr else
            ("هل أنت متأكد من حذف هذا الحريف وجميع بياناته نهائياً؟\n\n"
             "هذا الإجراء لا يمكن التراجع عنه."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # delete_client() catches everything internally and returns False, so it never
            # raises — which made this except arm unreachable and the success message and
            # navigation unconditional. The returned flag is what actually has to be read.
            try:
                deleted = reception.delete_client(self.client_id)
            except Exception as e:
                QMessageBox.critical(
                    self, "Erreur" if is_fr else "خطأ",
                    f"Impossible de supprimer : {e}" if is_fr
                    else f"تعذّر حذف الحريف!\n\nالسبب: {e}"
                )
                return

            if not deleted:
                QMessageBox.critical(
                    self, "Erreur" if is_fr else "خطأ",
                    ("Le client n'a PAS été supprimé. Aucune donnée n'a été modifiée — "
                     "consultez le journal des erreurs.") if is_fr
                    else ("لم يتم حذف الحريف! لم يطرأ أي تغيير على البيانات — "
                          "راجع سجل الأخطاء.")
                )
                return

            QMessageBox.information(
                self, "حذف" if not is_fr else "Suppression",
                "تم حذف الحريف بنجاح!" if not is_fr else "Client supprimé avec succès !"
            )
            self.back_to_list.emit()

    def _open_or_save_doc(self, doc_path):
        """Open a document with the OS default viewer, or let user save a copy."""
        if not os.path.exists(doc_path):
            QMessageBox.warning(self, "Erreur", "الملف غير موجود." if self.lang != "fr" else "Fichier introuvable.")
            return
        try:
            os.startfile(doc_path)
        except Exception:
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Enregistrer sous", Path(doc_path).name, "Tous (*.*)"
            )
            if save_path:
                import shutil
                shutil.copy(doc_path, save_path)

    def _delete_case_doc(self, filename):
        """Delete a document linked to a case after confirmation."""
        is_fr = self.lang == "fr"
        reply = QMessageBox.question(
            self, "Confirmation",
            f"Supprimer ce document définitivement ?\n{filename}" if is_fr
            else f"حذف هذه الوثيقة نهائياً؟\n{filename}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Drop any cached thumbnail first: entries are keyed by path, so a file
            # later re-added under the same name would still show the old image.
            try:
                from config import DOCUMENTS_DIR
                pixmap_cache.invalidate(str(DOCUMENTS_DIR / self.client_id / filename))
            except Exception:
                # (c) Safe. A cache eviction; a stale thumbnail is cosmetic and
                # the deletion below is the operation that matters.
                pass

            ok = reception.delete_client_document(self.client_id, filename)
            if not ok:
                QMessageBox.warning(
                    self, "Erreur" if is_fr else "خطأ",
                    f"Impossible de supprimer ce document.\n{filename}" if is_fr
                    else f"تعذّر حذف هذه الوثيقة.\n{filename}")
            self.load_client_cases()
            self.load_client_documents()

    def scan_cin_with_camera(self):
        """Scans CIN front/back directly from scanner/camera into civil status fields."""
        from ui.dialogs.document_scan_dialog import DocumentScanDialog
        dlg = DocumentScanDialog(parent=self, client_id=self.client_id, mode="cin", lang=self.lang)
        dlg.scanned_successfully.connect(self._on_cin_scanned)
        dlg.exec()

    def _on_cin_scanned(self, cin_data):
        if not cin_data or not isinstance(cin_data, dict):
            return
        if "cin_number" in cin_data and hasattr(self, "cin_input"):
            self.cin_input.setText(str(cin_data["cin_number"]))
        if "first_name" in cin_data and hasattr(self, "prenom_input"):
            self.prenom_input.setText(str(cin_data["first_name"]))
        if "last_name" in cin_data and hasattr(self, "nom_input"):
            self.nom_input.setText(str(cin_data["last_name"]))
        if "issue_date" in cin_data and hasattr(self, "cin_issue_date_input"):
            self.cin_issue_date_input.setText(str(cin_data["issue_date"]))
        if "issue_place" in cin_data and hasattr(self, "cin_issue_place_input"):
            self.cin_issue_place_input.setText(str(cin_data["issue_place"]))

    def scan_document_with_camera(self):
        """Scans general paper directly from scanner/camera into client documents."""
        from ui.dialogs.document_scan_dialog import DocumentScanDialog
        dlg = DocumentScanDialog(parent=self, client_id=self.client_id, mode="document", lang=self.lang)
        dlg.scanned_successfully.connect(lambda d: (self.load_client_documents(), self.load_client_cases()))
        dlg.exec()

    def scan_case_document(self, case_id):
        """Scans paper directly from scanner/camera into a specific case dossier."""
        from ui.dialogs.document_scan_dialog import DocumentScanDialog
        dlg = DocumentScanDialog(parent=self, client_id=self.client_id, mode="document", lang=self.lang)
        def _on_case_doc_scanned(doc_info):
            file_path = doc_info.get("file_path") if isinstance(doc_info, dict) else None
            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()
                    fname = f"Dossier_{case_id}_{Path(file_path).name}"
                    reception.save_client_document(self.client_id, file_bytes, fname)
                except Exception as e:
                    print("Error saving scanned case doc:", e)
            self.load_client_cases()
            self.load_client_documents()

        dlg.scanned_successfully.connect(_on_case_doc_scanned)
        dlg.exec()

    def open_farida_dialog(self):
        from ui.components.farida_dialog import TunisianFaridaDialog
        dlg = TunisianFaridaDialog(self, lang=self.lang, client_id=self.client_id)
        dlg.exec()

