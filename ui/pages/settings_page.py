import os
from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QFrame, QGridLayout, QScrollArea, QTextEdit, QFileDialog, QProgressBar, QStyledItemDelegate, QCheckBox, QMessageBox, QApplication
from PySide6.QtCore import Qt, Signal, QThread

# Import core business logic
from ui.components.collapsible_box import CollapsibleSection

import auth
import office_profile
import permissions
from permissions import Cap
import config
import camera
import reception
import system_guardian
import updater

# Import modular QThread workers
from ui.pages.settings.workers import (
    CamConnectThread, BackupThread, UpdateCheckThread, ArchiveImportThread
)


class SettingsPage(QWidget):
    # Signal emitted when language is changed
    language_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_lang = getattr(auth.session_state, "lang", "ar")
        self.last_created_backup = None
        self.init_ui()
        self.apply_role_restrictions()

    def init_ui(self):
        # Base Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # Title Label

        # Scroll area for multi-section content
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_widget = QWidget()
        # Scoped to this widget by name. Written bare ("background: transparent;")
        # Qt applies it to every descendant, and a widget stylesheet outranks the
        # application one — so every button inside lost its fill and painted the
        # default #f0f0f0 instead of its QSS colour.
        scroll_widget.setObjectName("SettingsScrollBody")
        scroll_widget.setStyleSheet("QWidget#SettingsScrollBody { background: transparent; }")
        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setSpacing(15)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)

        # ── 1. Langue de l'Application ─────────────────────────────────────────
        # ── 0. Office identity ───────────────────────────────────────────────
        # Everything that identifies the OFFICE rather than a client: the notary's
        # name, the court, the office number and address, the tax office. These used
        # to be written into sixteen contract templates and five other files, so
        # selling the app to a second notary meant editing source. They live in the
        # database now and every generated deed reads them from here.
        self.office_card = QFrame(scroll_widget)
        self.office_card.setProperty("class", "Card")
        office_lay = QVBoxLayout(self.office_card)
        self.office_title_lbl = QLabel("0. بيانات المكتب وعدل الإشهاد", self.office_card)
        self.office_title_lbl.setProperty("class", "CardTitle")
        office_lay.addWidget(self.office_title_lbl)

        self.office_hint = QLabel("", self.office_card)
        self.office_hint.setWordWrap(True)
        self.office_hint.setStyleSheet("color:#475569; font-size:12px;")
        office_lay.addWidget(self.office_hint)

        office_grid = QGridLayout()
        office_grid.setSpacing(10)
        self.office_inputs = {}
        self.office_labels = {}
        for row, (key, _default, label_ar, label_fr) in enumerate(office_profile.FIELDS):
            lbl = QLabel("", self.office_card)
            edit = QLineEdit(self.office_card)
            edit.setPlaceholderText(label_ar)
            self.office_labels[key] = lbl
            self.office_inputs[key] = edit
            office_grid.addWidget(lbl, row // 2, (row % 2) * 2)
            office_grid.addWidget(edit, row // 2, (row % 2) * 2 + 1)
        office_lay.addLayout(office_grid)

        self.office_preview = QLabel("", self.office_card)
        # The heading follows the interface language; the sample below it is the
        # deed's own Arabic preamble and stays Arabic in either mode. Named so
        # the bilingual-label check knows this pairing is deliberate.
        self.office_preview.setObjectName("ArabicSamplePreview")
        self.office_preview.setWordWrap(True)
        self.office_preview.setStyleSheet(
            "background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; "
            "padding:10px; color:#0f172a; font-size:12px;")
        office_lay.addWidget(self.office_preview)

        office_btn_row = QHBoxLayout()
        self.save_office_btn = QPushButton("", self.office_card)
        self.save_office_btn.setObjectName("PrimaryButton")
        self.save_office_btn.clicked.connect(self.save_office_profile)
        self.office_status = QLabel("", self.office_card)
        office_btn_row.addWidget(self.save_office_btn)
        office_btn_row.addWidget(self.office_status, 1)
        office_lay.addLayout(office_btn_row)

        self.load_office_profile()
        self._add_section(self.office_card, self.office_title_lbl)

        self.lang_card = QFrame(scroll_widget)
        self.lang_card.setProperty("class", "Card")
        lang_lay = QVBoxLayout(self.lang_card)
        self.lang_title = QLabel("1. Langue de l'Application / لغة التطبيق والنظام", self.lang_card)
        self.lang_title.setProperty("class", "CardTitle")
        lang_lay.addWidget(self.lang_title)

        lang_form = QHBoxLayout()
        self.lang_lbl = QLabel("Sélectionnez la langue active :", self.lang_card)
        
        self.lang_combo = QComboBox(self.lang_card)
        self.lang_combo.setItemDelegate(QStyledItemDelegate())
        self.lang_combo.addItems(["العربية (ar)", "Français (fr)"])
        
        # We block signals while setting the initial index so it doesn't trigger immediately
        self.lang_combo.blockSignals(True)
        self.lang_combo.setCurrentIndex(0 if self.current_lang == "ar" else 1)
        self.lang_combo.blockSignals(False)
        
        self.lang_combo.currentIndexChanged.connect(self.save_language)
        
        lang_form.addWidget(self.lang_lbl)
        lang_form.addWidget(self.lang_combo)
        
        lang_lay.addLayout(lang_form)
        self.lang_status = QLabel("", self.lang_card)
        lang_lay.addWidget(self.lang_status)
        self._add_section(self.lang_card, self.lang_title)

        # ── 1b. Moteur d'Intelligence Artificielle ────────────────────────────
        # Moved here from the Scanner page: this is configuration, not part of
        # drafting a contract. The Scanner reads the saved provider/model/keys.
        is_fr = self.current_lang == "fr"
        self.ai_card = QFrame(scroll_widget)
        self.ai_card.setProperty("class", "Card")
        ai_lay = QVBoxLayout(self.ai_card)
        ai_lay.setSpacing(10)

        self.ai_title = QLabel(
            "2. Moteur d'Intelligence Artificielle" if is_fr
            else "2. محرك الذكاء الاصطناعي", self.ai_card)
        self.ai_title.setProperty("class", "CardTitle")
        ai_lay.addWidget(self.ai_title)

        # Gemini is the only engine this office uses, so there is no provider to pick.
        # An install that previously saved "openai" is migrated back on load.
        saved_provider, saved_model = config.load_ai_engine()
        self.ai_provider = self.PROVIDER
        if saved_provider != self.PROVIDER:
            saved_model = self.MODEL_CHOICES[self.PROVIDER][0]
            config.save_ai_engine(self.PROVIDER, saved_model)
        self.ai_model = saved_model

        prov_row = QHBoxLayout()
        self.ai_provider_lbl = QLabel("Fournisseur :" if is_fr else "المزوّد :", self.ai_card)
        self.ai_provider_value = QLabel("Google Gemini", self.ai_card)
        self.ai_provider_value.setStyleSheet("font-weight: 600; color: #1e3a8a;")

        self.ai_model_lbl = QLabel("Modèle :" if is_fr else "النموذج :", self.ai_card)
        self.ai_model_combo = QComboBox(self.ai_card)
        self.ai_model_combo.setItemDelegate(QStyledItemDelegate())
        self.ai_model_combo.currentTextChanged.connect(self.on_ai_model_changed)
        self.ai_model_combo.setFixedHeight(36)
        self.ai_model_combo.setMinimumWidth(220)

        prov_row.addWidget(self.ai_provider_lbl)
        prov_row.addWidget(self.ai_provider_value)
        prov_row.addWidget(self.ai_model_lbl)
        prov_row.addWidget(self.ai_model_combo)
        prov_row.addStretch()
        ai_lay.addLayout(prov_row)

        self.ai_keys_lbl = QLabel("", self.ai_card)
        ai_lay.addWidget(self.ai_keys_lbl)
        self.ai_keys_input = QTextEdit(self.ai_card)
        self.ai_keys_input.setFixedHeight(80)
        self.ai_keys_input.textChanged.connect(self.on_ai_keys_changed)
        ai_lay.addWidget(self.ai_keys_input)

        self.ai_status = QLabel("", self.ai_card)
        self.ai_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ai_status.setWordWrap(True)
        ai_lay.addWidget(self.ai_status)

        # ── Certificate-verification warning ─────────────────────────────────
        # The office can opt out of TLS verification (a marker file or an
        # environment variable) when antivirus or a proxy re-signs HTTPS. That
        # switch is off by default, but once thrown it was invisible: scans of
        # clients' identity cards would go out over an unverified connection
        # with nothing on screen to say so. This banner appears only while the
        # opt-out is actually active, and offers to turn it back off.
        self.tls_warning = QFrame(self.ai_card)
        self.tls_warning.setStyleSheet(
            "QFrame { background-color: #fef2f2; border: 2px solid #dc2626;"
            " border-radius: 8px; }")
        tls_lay = QVBoxLayout(self.tls_warning)
        tls_lay.setContentsMargins(12, 10, 12, 10)
        self.tls_warning_lbl = QLabel("", self.tls_warning)
        self.tls_warning_lbl.setWordWrap(True)
        self.tls_warning_lbl.setStyleSheet(
            "color: #b91c1c; font-weight: 800; font-size: 12px; border: none;")
        tls_lay.addWidget(self.tls_warning_lbl)
        self.tls_disable_btn = QPushButton("", self.tls_warning)
        self.tls_disable_btn.setObjectName("SecondaryButton")
        self.tls_disable_btn.setMinimumHeight(32)
        self.tls_disable_btn.clicked.connect(self.disable_insecure_tls)
        tls_lay.addWidget(self.tls_disable_btn)
        ai_lay.addWidget(self.tls_warning)

        # The recommended alternative, stated whether or not the opt-out is on.
        self.tls_hint_lbl = QLabel("", self.ai_card)
        self.tls_hint_lbl.setWordWrap(True)
        self.tls_hint_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        ai_lay.addWidget(self.tls_hint_lbl)

        self._add_section(self.ai_card, self.ai_title)
        self._refresh_ai_fields(initial=True)
        self.refresh_tls_warning()

        # ── 2. Source Vidéo de la Caméra ───────────────────────────────────────
        self.cam_card = QFrame(scroll_widget)
        self.cam_card.setProperty("class", "Card")
        cam_lay = QVBoxLayout(self.cam_card)
        self.cam_title = QLabel("3. Source Vidéo de la Caméra / مصدر الكاميرا", self.cam_card)
        self.cam_title.setProperty("class", "CardTitle")
        cam_lay.addWidget(self.cam_title)

        cam_form = QGridLayout()
        cam_form.setSpacing(10)
        self.cam_lbl = QLabel("Sélectionnez le périphérique vidéo :", self.cam_card)
        self.cam_combo = QComboBox(self.cam_card)
        self.cam_combo.setItemDelegate(QStyledItemDelegate())
        self.cam_combo.addItems(self._camera_choices())
        saved_cam = camera.get_saved_camera_source()
        if isinstance(saved_cam, int) and 0 <= saved_cam <= 2:
            self.cam_combo.setCurrentIndex(saved_cam)
        else:
            self.cam_combo.setCurrentIndex(3)
        self.cam_combo.currentIndexChanged.connect(self.on_camera_combo_changed)

        self.rtsp_lbl = QLabel(
            "URL du flux RTSP / IP Camera (format http://ADRESSE:PORT/video) :"
            if self.current_lang == "fr"
            else "عنوان بث الكاميرا (بالشكل http://ADRESSE:PORT/video) :", self.cam_card)
        self.rtsp_input = QLineEdit(self.cam_card)
        if isinstance(saved_cam, str):
            self.rtsp_input.setText(saved_cam)
        else:
            self.rtsp_input.setText("")

        self.save_cam_btn = QPushButton("Sauvegarder Source / حفظ المصدر", self.cam_card)
        self.save_cam_btn.setObjectName("PrimaryButton")
        self.save_cam_btn.clicked.connect(self.save_camera_source)

        cam_form.addWidget(self.cam_lbl, 0, 0)
        cam_form.addWidget(self.cam_combo, 0, 1)
        cam_form.addWidget(self.rtsp_lbl, 1, 0)
        cam_form.addWidget(self.rtsp_input, 1, 1)
        cam_form.addWidget(self.save_cam_btn, 2, 0, 1, 2)
        cam_lay.addLayout(cam_form)

        # The camera now runs for the whole session rather than only while Accueil is
        # open, so whether it starts by itself at launch is a real preference.
        self.cam_autostart_chk = QCheckBox(
            "Démarrer la caméra automatiquement au lancement" if is_fr
            else "تشغيل الكاميرا تلقائياً عند فتح البرنامج", self.cam_card)
        self.cam_autostart_chk.setChecked(camera.get_camera_autostart())
        self.cam_autostart_chk.toggled.connect(self.on_camera_autostart_toggled)
        cam_lay.addWidget(self.cam_autostart_chk)

        self.cam_status = QLabel("", self.cam_card)
        cam_lay.addWidget(self.cam_status)
        self._add_section(self.cam_card, self.cam_title)
        self.on_camera_combo_changed(self.cam_combo.currentIndex()) # apply initial show/hide for rtsp input

        # ── 3. Sécurité & Modification du Mot de Passe ─────────────────────────
        self.pass_card = QFrame(scroll_widget)
        self.pass_card.setProperty("class", "Card")
        pass_lay = QVBoxLayout(self.pass_card)
        self.pass_title = QLabel("4. Sécurité & Mots de Passe / كلمة المرور", self.pass_card)
        self.pass_title.setProperty("class", "CardTitle")
        pass_lay.addWidget(self.pass_title)

        pass_grid = QGridLayout()
        pass_grid.setSpacing(10)
        self.user_lbl = QLabel("Compte à modifier :", self.pass_card)
        self.user_combo = QComboBox(self.pass_card)
        self.user_combo.setItemDelegate(QStyledItemDelegate())
        self.user_combo.addItems([
            f"patron ({office_profile.display_name()})",
            "secretaire (كاتبة المكتب)"
        ])

        self.curr_pw_lbl = QLabel("Mot de passe actuel :", self.pass_card)
        self.curr_pw_input = QLineEdit(self.pass_card)
        self.curr_pw_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.new_pw_lbl = QLabel("Nouveau mot de passe :", self.pass_card)
        self.new_pw_input = QLineEdit(self.pass_card)
        self.new_pw_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.conf_pw_lbl = QLabel("Confirmer nouveau mot de passe :", self.pass_card)
        self.conf_pw_input = QLineEdit(self.pass_card)
        self.conf_pw_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.save_pass_btn = QPushButton("Mettre à jour / تحديث كلمة المرور", self.pass_card)
        self.save_pass_btn.setObjectName("PrimaryButton")
        self.save_pass_btn.clicked.connect(self.save_password)

        pass_grid.addWidget(self.user_lbl, 0, 0)
        pass_grid.addWidget(self.user_combo, 0, 1)
        pass_grid.addWidget(self.curr_pw_lbl, 1, 0)
        pass_grid.addWidget(self.curr_pw_input, 1, 1)
        pass_grid.addWidget(self.new_pw_lbl, 2, 0)
        pass_grid.addWidget(self.new_pw_input, 2, 1)
        pass_grid.addWidget(self.conf_pw_lbl, 3, 0)
        pass_grid.addWidget(self.conf_pw_input, 3, 1)
        pass_grid.addWidget(self.save_pass_btn, 4, 0, 1, 2)
        pass_lay.addLayout(pass_grid)
        self.pass_status = QLabel("", self.pass_card)
        pass_lay.addWidget(self.pass_status)
        self._add_section(self.pass_card, self.pass_title)

        # ── 4. Sauvegarde & Protection des Données ─────────────────────────────
        self.backup_card = QFrame(scroll_widget)
        self.backup_card.setProperty("class", "Card")
        backup_lay = QVBoxLayout(self.backup_card)
        self.backup_title = QLabel("5. Sauvegarde & Protection 30 Ans / النسخ الاحتياطي", self.backup_card)
        self.backup_title.setProperty("class", "CardTitle")
        backup_lay.addWidget(self.backup_title)

        backup_splits = QHBoxLayout()
        
        # Left side of splits: Actions and Drive Sync
        backup_left = QVBoxLayout()
        self.backup_manual_lbl = QLabel("<b>إنشاء نسخة احتياطية كاملة (ZIP) :</b>", self.backup_card)
        self.backup_manual_btn = QPushButton("Créer sauvegarde complète maintenant / إنشاء نسخة", self.backup_card)
        self.backup_manual_btn.setObjectName("PrimaryButton")
        self.backup_manual_btn.clicked.connect(self.run_manual_backup)
        self.backup_dl_btn = QPushButton("Télécharger / تنزيل النسخة", self.backup_card)
        self.backup_dl_btn.setObjectName("SecondaryButton")
        self.backup_dl_btn.setVisible(False)
        self.backup_dl_btn.clicked.connect(self.download_backup_zip)
        
        backup_left.addWidget(self.backup_manual_lbl)
        backup_left.addWidget(self.backup_manual_btn)
        backup_left.addWidget(self.backup_dl_btn)
        
        # External USB sync config
        backup_left.addWidget(QLabel(("<b>Disque dur externe (USB) :</b>" if self.current_lang == "fr" else "<b>ربط ومزامنة القرص الصلب الخارجي (USB) :</b>"), self.backup_card))
        self.usb_path_lbl = QLabel("مسار القرص الصلب الخارجي المربوط بالكمبيوتر:", self.backup_card)
        usb_input_lay = QHBoxLayout()
        self.usb_input = QLineEdit(self.backup_card)
        
        ext_dir = system_guardian.get_external_backup_dir()
        self.usb_input.setText(str(ext_dir) if ext_dir else "E:\\Sauvegardes_Notaire_Zarai")
        
        self.save_usb_btn = QPushButton("Enregistrer / حفظ", self.backup_card)
        self.save_usb_btn.setObjectName("SecondaryButton")
        self.save_usb_btn.clicked.connect(self.save_usb_path)
        usb_input_lay.addWidget(self.usb_input)
        usb_input_lay.addWidget(self.save_usb_btn)
        backup_left.addLayout(usb_input_lay)
        
        self.usb_status_lbl = QLabel("", self.backup_card)
        self.check_usb_status()
        backup_left.addWidget(self.usb_status_lbl)
        
        # Right side of splits: Diagnostics
        backup_right = QVBoxLayout()
        self.diag_status_lbl = QLabel("<b>حالة حماية البيانات وحارس النظام (System Guardian) :</b>", self.backup_card)
        
        # Check SQLite DB integrity
        db_ok = system_guardian.verify_database_integrity()
        self._db_ok = db_ok
        self.db_status_lbl = QLabel(self.backup_card)
        if db_ok:
            self.db_status_lbl.setText("حالة قاعدة البيانات: سليمة (تم فحص PRAGMA)")
            self.db_status_lbl.setStyleSheet("color: #059669; font-weight: bold; padding: 5px; background: #ecfdf5; border-radius: 6px;")
        else:
            self.db_status_lbl.setText("جاري إعادة المزامنة والإصلاح التلقائي لقاعدة البيانات...")
            self.db_status_lbl.setStyleSheet("color: #d97706; font-weight: bold; padding: 5px; background: #fffbeb; border-radius: 6px;")
            
        self.backup_count_lbl = QLabel(
            f"عدد النسخ الاحتياطية المحفوظة آلياً: {self._backup_count()}", self.backup_card)
        self.backup_count_lbl.setStyleSheet("color: #2563eb; font-weight: bold; padding: 5px; background: #eff6ff; border-radius: 6px;")
        
        self.backup_hint_lbl = QLabel("يتم حظر حذف البيانات وتوليد نسخة يومية تلقائياً لضمان استقرار العمل لـ30 سنة قادمة.", self.backup_card)
        self.backup_hint_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        self.backup_hint_lbl.setWordWrap(True)
        
        backup_right.addWidget(self.diag_status_lbl)
        backup_right.addWidget(self.db_status_lbl)
        backup_right.addWidget(self.backup_count_lbl)
        backup_right.addWidget(self.backup_hint_lbl)
        
        backup_splits.addLayout(backup_left, 6)
        backup_splits.addLayout(backup_right, 4)
        backup_lay.addLayout(backup_splits)
        
        self.backup_status = QLabel("", self.backup_card)
        backup_lay.addWidget(self.backup_status)
        self._add_section(self.backup_card, self.backup_title)

        # ── 5. Diagnostic Log & Maintenance ───────────────────────────────────
        self.diag_card = QFrame(scroll_widget)
        self.diag_card.setProperty("class", "Card")
        diag_lay = QVBoxLayout(self.diag_card)
        self.diag_title = QLabel("6. سجل الصيانة والأخطاء / Diagnostic Logs", self.diag_card)
        self.diag_title.setProperty("class", "CardTitle")
        diag_lay.addWidget(self.diag_title)

        self.diag_hint_lbl = QLabel("إذا حدث أي إشكال مستقبلي، يمكنك معاينة وتصدير سجل الصيانة والأخطاء لإرساله لخدمة الصيانة فورياً:", self.diag_card)
        diag_lay.addWidget(self.diag_hint_lbl)

        self.log_viewer = QTextEdit(self.diag_card)
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setMaximumHeight(150)
        self.log_viewer.setStyleSheet("""
            QTextEdit {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #334155;
                font-family: 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        self.load_diagnostic_logs()
        diag_lay.addWidget(self.log_viewer)

        self.export_diag_btn = QPushButton("تنزيل تقرير الصيانة / Exporter le Diagnostic (.log)", self.diag_card)
        self.export_diag_btn.setObjectName("PrimaryButton")
        self.export_diag_btn.clicked.connect(self.export_diagnostic_log)

        self.clear_log_btn = QPushButton("🗑 Vider le journal / مسح السجل", self.diag_card)
        self.clear_log_btn.setObjectName("DangerButton")
        self.clear_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #dc2626; }
            QPushButton:pressed { background-color: #b91c1c; }
        """)
        self.clear_log_btn.clicked.connect(self.clear_diagnostic_log)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.export_diag_btn)
        btn_row.addWidget(self.clear_log_btn)
        diag_lay.addLayout(btn_row)

        self.diag_status = QLabel("", self.diag_card)
        diag_lay.addWidget(self.diag_status)
        self._add_section(self.diag_card, self.diag_title)

        # ── 6. Mises à Jour Automatiques & Version ──────────────────────────────
        self.update_card = QFrame(scroll_widget)
        self.update_card.setProperty("class", "Card")
        update_lay = QVBoxLayout(self.update_card)
        self.update_title = QLabel("7. التحديثات وإصدار النظام / Software Version & Updates", self.update_card)
        self.update_title.setProperty("class", "CardTitle")
        update_lay.addWidget(self.update_title)

        update_content = QHBoxLayout()
        # The repository line is only shown when there is a real one. With the
        # placeholder still in version.py it printed "github.com/OWNER/mon-app-releases"
        # to the notary, next to a button that could never find anything.
        self._update_channel_ready = updater.is_update_channel_configured()
        self.version_lbl = QLabel(
            self._version_label_text(self.current_lang == "fr"), self.update_card)
        self.version_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.check_update_btn = QPushButton(("Vérifier les mises à jour" if self.current_lang == "fr" else "فحص التحديثات الآلية"), self.update_card)
        self.check_update_btn.setObjectName("PrimaryButton")
        self.check_update_btn.clicked.connect(self.check_app_updates)

        self.download_update_btn = QPushButton(("Télécharger et installer" if self.current_lang == "fr" else "تنزيل وتثبيت التحديث"), self.update_card)
        self.download_update_btn.setObjectName("SuccessButton")
        self.download_update_btn.setVisible(False)
        self.download_update_btn.clicked.connect(self.start_update_download)

        update_content.addWidget(self.version_lbl, 5)
        update_content.addWidget(self.check_update_btn, 2)
        update_content.addWidget(self.download_update_btn, 3)
        update_lay.addLayout(update_content)

        self.update_progress = QProgressBar(self.update_card)
        self.update_progress.setVisible(False)
        update_lay.addWidget(self.update_progress)

        self.update_status = QLabel("", self.update_card)
        update_lay.addWidget(self.update_status)

        # No update channel configured yet: hide the button rather than offer an
        # action that silently does nothing, and say plainly that updates are
        # installed by hand for now.
        self._apply_update_channel_state()
        self.refresh_office_labels()
        self.refresh_office_preview()
        self._sync_section_titles()

        self._add_section(self.update_card, self.update_title)

        # ── 7. Bulk Legacy Archive Folder Importer ─────────────────────────────
        self.import_card = QFrame(scroll_widget)
        self.import_card.setProperty("class", "Card")
        import_lay = QVBoxLayout(self.import_card)
        self.import_title = QLabel("8. استيراد أرشيف الملفات القديمة / Bulk Archive Importer", self.import_card)
        self.import_title.setProperty("class", "CardTitle")
        import_lay.addWidget(self.import_title)

        self.import_hint_lbl = QLabel("يتيح هذا الخيار استيراد جميع المجلدات والعقود المكتوبة سابقاً (.docx, .pdf, images) وإدراجها تلقائياً بالذكاء الاصطناعي دون كتابة يدوية :", self.import_card)
        self.import_hint_lbl.setWordWrap(True)
        import_lay.addWidget(self.import_hint_lbl)

        import_form = QHBoxLayout()
        self.import_path_input = QLineEdit(self.import_card)
        self.browse_import_btn = QPushButton("تصفح / Choisir", self.import_card)
        self.browse_import_btn.setObjectName("SecondaryButton")
        self.browse_import_btn.clicked.connect(self.browse_import_directory)
        self.run_import_btn = QPushButton("بدء الاستيراد / Lancer", self.import_card)
        self.run_import_btn.setObjectName("PrimaryButton")
        self.run_import_btn.clicked.connect(self.run_bulk_import)

        import_form.addWidget(self.import_path_input, 6)
        import_form.addWidget(self.browse_import_btn, 2)
        import_form.addWidget(self.run_import_btn, 2)
        import_lay.addLayout(import_form)

        # Progress bar for imports
        self.import_progress = QProgressBar(self.import_card)
        self.import_progress.setVisible(False)
        self.import_progress.setStyleSheet("QProgressBar { max-height: 14px; }")
        import_lay.addWidget(self.import_progress)

        self.import_status = QLabel("", self.import_card)
        self.import_status.setWordWrap(True)
        import_lay.addWidget(self.import_status)

        # ── The assisted migration tool ──────────────────────────────────────
        # Its review screen existed but nothing anywhere opened it, so the whole
        # assisted-migration feature was unreachable from the running app. It
        # belongs beside the bulk importer: the same job, done carefully.
        _mig_line = QFrame(self.import_card)
        _mig_line.setFrameShape(QFrame.Shape.HLine)
        _mig_line.setStyleSheet("color:#e2e8f0;")
        import_lay.addWidget(_mig_line)

        self.migration_hint_lbl = QLabel("", self.import_card)
        self.migration_hint_lbl.setWordWrap(True)
        self.migration_hint_lbl.setStyleSheet("color:#475569; font-size:12px;")
        import_lay.addWidget(self.migration_hint_lbl)

        self.open_migration_btn = QPushButton("", self.import_card)
        self.open_migration_btn.setObjectName("PrimaryButton")
        self.open_migration_btn.setMinimumHeight(36)
        self.open_migration_btn.clicked.connect(self.open_migration_review)
        import_lay.addWidget(self.open_migration_btn)

        self._add_section(self.import_card, self.import_title)

        # ── 9. Le réseau du cabinet ──────────────────────────────────────────
        # Without this screen the multi-machine mode existed only as a json file
        # nobody would ever write by hand, which is the same as not existing.
        self.net_card = QFrame(scroll_widget)
        self.net_card.setProperty("class", "Card")
        net_lay = QVBoxLayout(self.net_card)
        self.net_title = QLabel("", self.net_card)
        self.net_title.setProperty("class", "CardTitle")
        net_lay.addWidget(self.net_title)

        self.net_hint = QLabel("", self.net_card)
        self.net_hint.setWordWrap(True)
        self.net_hint.setStyleSheet("color:#475569; font-size:12px;")
        net_lay.addWidget(self.net_hint)

        mode_row = QHBoxLayout()
        self.net_mode_lbl = QLabel("", self.net_card)
        self.net_mode_combo = QComboBox(self.net_card)
        self.net_mode_combo.setItemDelegate(QStyledItemDelegate())
        self.net_mode_combo.setFixedHeight(36)
        self.net_mode_combo.setMinimumWidth(300)
        self.net_mode_combo.currentIndexChanged.connect(self.on_network_mode_changed)
        mode_row.addWidget(self.net_mode_lbl)
        mode_row.addWidget(self.net_mode_combo)
        mode_row.addStretch()
        net_lay.addLayout(mode_row)

        # -- shown when this machine SERVES --
        self.net_server_box = QFrame(self.net_card)
        srv_lay = QVBoxLayout(self.net_server_box)
        srv_lay.setContentsMargins(0, 6, 0, 0)
        self.net_server_status = QLabel("", self.net_server_box)
        self.net_server_status.setWordWrap(True)
        self.net_server_status.setStyleSheet(
            "background-color:#ecfdf5; border:1px solid #10b981; border-radius:6px;"
            " padding:8px; color:#065f46; font-weight:700; font-size:12px;")
        srv_lay.addWidget(self.net_server_status)
        self.net_server_help = QLabel("", self.net_server_box)
        self.net_server_help.setWordWrap(True)
        self.net_server_help.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.net_server_help.setStyleSheet("color:#334155; font-size:12px;")
        srv_lay.addWidget(self.net_server_help)
        net_lay.addWidget(self.net_server_box)

        # -- shown when this machine is a WORKSTATION --
        self.net_client_box = QFrame(self.net_card)
        cli_lay = QVBoxLayout(self.net_client_box)
        cli_lay.setContentsMargins(0, 6, 0, 0)
        addr_row = QHBoxLayout()
        self.net_host_lbl = QLabel("", self.net_client_box)
        self.net_host_input = QLineEdit(self.net_client_box)
        self.net_host_input.setFixedHeight(34)
        self.net_port_lbl = QLabel("", self.net_client_box)
        self.net_port_input = QLineEdit(self.net_client_box)
        self.net_port_input.setFixedHeight(34)
        self.net_port_input.setFixedWidth(90)
        addr_row.addWidget(self.net_host_lbl)
        addr_row.addWidget(self.net_host_input, 3)
        addr_row.addWidget(self.net_port_lbl)
        addr_row.addWidget(self.net_port_input)
        cli_lay.addLayout(addr_row)
        net_lay.addWidget(self.net_client_box)

        tok_row = QHBoxLayout()
        self.net_token_lbl = QLabel("", self.net_card)
        self.net_token_input = QLineEdit(self.net_card)
        self.net_token_input.setFixedHeight(34)
        self.net_token_gen_btn = QPushButton("", self.net_card)
        self.net_token_gen_btn.setObjectName("SecondaryButton")
        self.net_token_gen_btn.clicked.connect(self.generate_network_token)
        tok_row.addWidget(self.net_token_lbl)
        tok_row.addWidget(self.net_token_input, 3)
        tok_row.addWidget(self.net_token_gen_btn)
        net_lay.addLayout(tok_row)

        btn_row = QHBoxLayout()
        self.net_test_btn = QPushButton("", self.net_card)
        self.net_test_btn.setObjectName("SecondaryButton")
        self.net_test_btn.setMinimumHeight(36)
        self.net_test_btn.clicked.connect(self.test_network_connection)
        self.net_save_btn = QPushButton("", self.net_card)
        self.net_save_btn.setObjectName("PrimaryButton")
        self.net_save_btn.setMinimumHeight(36)
        self.net_save_btn.clicked.connect(self.save_network_settings)
        btn_row.addStretch()
        btn_row.addWidget(self.net_test_btn)
        btn_row.addWidget(self.net_save_btn)
        net_lay.addLayout(btn_row)

        self.net_status = QLabel("", self.net_card)
        self.net_status.setWordWrap(True)
        net_lay.addWidget(self.net_status)

        self._add_section(self.net_card, self.net_title)
        self.load_network_settings()

        # ── 10. Licence ──────────────────────────────────────────────────────
        self.lic_card = QFrame(scroll_widget)
        self.lic_card.setProperty("class", "Card")
        lic_lay = QVBoxLayout(self.lic_card)
        self.lic_title = QLabel("", self.lic_card)
        self.lic_title.setProperty("class", "CardTitle")
        lic_lay.addWidget(self.lic_title)

        self.lic_status_lbl = QLabel("", self.lic_card)
        self.lic_status_lbl.setWordWrap(True)
        lic_lay.addWidget(self.lic_status_lbl)

        mid_row = QHBoxLayout()
        self.lic_machine_lbl = QLabel("", self.lic_card)
        self.lic_machine_value = QLineEdit(self.lic_card)
        self.lic_machine_value.setReadOnly(True)
        self.lic_machine_value.setFixedHeight(34)
        self.lic_machine_value.setStyleSheet(
            "font-family:Consolas,monospace; font-weight:800; color:#1e3a8a;")
        self.lic_copy_btn = QPushButton("", self.lic_card)
        self.lic_copy_btn.setObjectName("SecondaryButton")
        self.lic_copy_btn.clicked.connect(self.copy_machine_id)
        mid_row.addWidget(self.lic_machine_lbl)
        mid_row.addWidget(self.lic_machine_value, 3)
        mid_row.addWidget(self.lic_copy_btn)
        lic_lay.addLayout(mid_row)

        self.lic_help = QLabel("", self.lic_card)
        self.lic_help.setWordWrap(True)
        self.lic_help.setStyleSheet("color:#475569; font-size:12px;")
        lic_lay.addWidget(self.lic_help)

        self.lic_key_lbl = QLabel("", self.lic_card)
        lic_lay.addWidget(self.lic_key_lbl)
        self.lic_key_input = QTextEdit(self.lic_card)
        self.lic_key_input.setFixedHeight(70)
        lic_lay.addWidget(self.lic_key_input)

        lic_btns = QHBoxLayout()
        lic_btns.addStretch()
        self.lic_activate_btn = QPushButton("", self.lic_card)
        self.lic_activate_btn.setObjectName("PrimaryButton")
        self.lic_activate_btn.setMinimumHeight(36)
        self.lic_activate_btn.clicked.connect(self.activate_licence)
        lic_btns.addWidget(self.lic_activate_btn)
        lic_lay.addLayout(lic_btns)

        self._add_section(self.lic_card, self.lic_title)
        self._retitle_licence()
        self.refresh_licence_status()

        # Add everything to layout
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        # Apply translations
        self.update_translation(self.current_lang)

    # ── Language Actions ──
    # ── AI engine configuration ───────────────────────────────────────────────
    # Gemini only. OpenAI is deliberately not offered.
    PROVIDER = "gemini"
    MODEL_CHOICES = {
        "gemini": ["gemini-3.6-flash", "gemini-2.5-flash"],
    }

    def _refresh_ai_fields(self, initial=False):
        """Repopulates the model list and key box for the selected provider."""
        is_fr = self.current_lang == "fr"
        provider = self.ai_provider

        self.ai_model_combo.blockSignals(True)
        self.ai_model_combo.clear()
        self.ai_model_combo.addItems(self.MODEL_CHOICES[provider])
        idx = self.ai_model_combo.findText(self.ai_model)
        self.ai_model_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.ai_model = self.ai_model_combo.currentText()
        self.ai_model_combo.blockSignals(False)

        keys = config.load_saved_api_keys(provider)
        self.ai_keys_input.blockSignals(True)
        self.ai_keys_input.setPlainText(keys.replace(",", "\n"))
        self.ai_keys_input.blockSignals(False)

        self.ai_keys_lbl.setText("Clés API Gemini (une par ligne) :" if is_fr
                                 else "مفاتيح Gemini (مفتاح في كل سطر) :")
        self._refresh_ai_status()

    def apply_role_restrictions(self):
        """Hides administrative settings sections for the Secretary role, keeping only Language & Password."""
        is_admin = permissions.has(Cap.MANAGE_USERS) or permissions.has(Cap.MANAGE_BACKUP)
        
        # 1. Hide/show collapsible section cards based on role
        for sec, lbl, card in getattr(self, "_sections", []):
            allowed_cards = (
                getattr(self, "lang_card", None),
                getattr(self, "pass_card", None),
                getattr(self, "update_card", None),
                getattr(self, "net_card", None)
            )
            if not is_admin and card not in allowed_cards:
                sec.setVisible(False)
            else:
                sec.setVisible(True)

        # 2. In Password section, hide user management / recovery controls for Secretary
        if not is_admin:
            for name in ("target_user_combo", "recovery_code_btn", "user_manage_box"):
                w = getattr(self, name, None)
                if w is not None:
                    try:
                        w.setVisible(False)
                    except Exception:
                        pass
        
        may_keys = permissions.has(Cap.MANAGE_API_KEYS)
        for name in ("ai_keys_input", "ai_model_combo", "ai_provider_combo"):
            w = getattr(self, name, None)
            if w is not None:
                try:
                    w.setEnabled(may_keys)
                except (AttributeError, RuntimeError):
                    pass
        may_backup = permissions.has(Cap.MANAGE_BACKUP)
        for name in ("backup_manual_btn", "usb_path_input", "usb_save_btn",
                     "diagnostic_export_btn", "restore_btn"):
            w = getattr(self, name, None)
            if w is not None:
                try:
                    w.setEnabled(may_backup)
                except (AttributeError, RuntimeError):
                    pass

    def refresh_tls_warning(self):
        """
        Shows the certificate warning only while the opt-out is actually on.

        The banner is not decoration: while this is active, a scan of a client's
        identity card leaves the office over a connection whose certificate was
        not checked. The office should be able to see that at a glance and undo
        it without editing files.
        """
        is_fr = self.current_lang == "fr"
        active = False
        try:
            active = config.insecure_tls_allowed()
        except Exception:
            # (c) Safe: if the check itself fails, the banner stays hidden and
            # the request path keeps verifying, which is the secure default.
            active = False

        self.tls_warning.setVisible(active)
        if active:
            self.tls_warning_lbl.setText(
                "⚠ VÉRIFICATION DES CERTIFICATS DÉSACTIVÉE\n\n"
                "Les documents envoyés à l'IA — y compris les scans de cartes "
                "d'identité de vos clients — partent sur une connexion dont le "
                "certificat n'est PAS vérifié. À n'utiliser que temporairement."
                if is_fr else
                "⚠ التحقّق من شهادات الأمان مُعطَّل\n\n"
                "الوثائق المُرسَلة إلى الذكاء الاصطناعي — بما فيها صور بطاقات "
                "تعريف حرفائك — تُرسَل عبر اتصال لم يقع التحقّق من شهادته. "
                "لا تستعمل هذا إلا مؤقّتا.")
            self.tls_disable_btn.setText(
                "Réactiver la vérification des certificats" if is_fr
                else "إعادة تفعيل التحقّق من الشهادات")

        # Stated in both states: this is the route that keeps verification on.
        self.tls_hint_lbl.setText(
            "Antivirus ou proxy qui bloque l'IA ? La solution recommandée n'est "
            "pas de désactiver la vérification, mais d'installer le certificat "
            "racine de votre antivirus dans :\n"
            f"{config.DATA_DIR}\\ca_bundle.pem\n"
            "La vérification reste alors active."
            if is_fr else
            "هل يمنع برنامج الحماية أو الوسيط عمل الذكاء الاصطناعي؟ الحل الموصى به "
            "ليس تعطيل التحقّق، بل إضافة الشهادة الجذرية لبرنامج الحماية إلى :\n"
            f"{config.DATA_DIR}\\ca_bundle.pem\n"
            "وبذلك يبقى التحقّق مفعّلا.")

    def disable_insecure_tls(self):
        """Turns certificate verification back on."""
        is_fr = self.current_lang == "fr"
        try:
            ok, note = config.disable_insecure_tls()
        except Exception as e:
            QMessageBox.critical(self, "Erreur" if is_fr else "خطأ", str(e))
            return
        if ok:
            QMessageBox.information(
                self, "Sécurité" if is_fr else "الأمان",
                "La vérification des certificats est réactivée."
                if is_fr else "تم إعادة تفعيل التحقّق من الشهادات.")
        elif note == "env":
            QMessageBox.warning(
                self, "Sécurité" if is_fr else "الأمان",
                "Le fichier a été retiré, mais la variable d'environnement "
                "ZARAI_ALLOW_INSECURE_TLS est encore définie sur cette machine. "
                "Retirez-la puis redémarrez l'application."
                if is_fr else
                "تم حذف الملف، لكن متغيّر البيئة ZARAI_ALLOW_INSECURE_TLS "
                "ما زال مضبوطا على هذا الجهاز. احذفه ثم أعد تشغيل التطبيق.")
        else:
            QMessageBox.warning(self, "Sécurité" if is_fr else "الأمان", str(note))
        self.refresh_tls_warning()

    def _refresh_ai_status(self):
        """States what the engine can actually do, rather than asserting it is ready."""
        is_fr = self.current_lang == "fr"
        name = "Google Gemini"
        keys = [k for k in config.load_saved_api_keys(self.ai_provider).replace("\n", ",").split(",")
                if k.strip()]
        if not keys:
            txt = (f" Aucune clé API pour {name}." if is_fr
                   else f" لا يوجد مفتاح API لـ {name}.")
            grad = "stop:0 #7f1d1d, stop:1 #991b1b"
        else:
            extra = f" ({len(keys)})" if len(keys) > 1 else ""
            txt = (f" {name} — {self.ai_model}{extra}" if is_fr
                   else f" {name} — {self.ai_model}{extra}")
            grad = "stop:0 #065f46, stop:1 #047857"
        self.ai_status.setText(txt)
        self.ai_status.setStyleSheet(
            "QLabel { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, %s);"
            " color:#ffffff; padding:8px; border-radius:8px;"
            " font-size:11px; font-weight:bold; }" % grad)

    def on_ai_model_changed(self, text):
        # Silent, not a dialog: this is a signal handler that also fires while the
        # combo is being populated, and a refusal popup on page load would be
        # noise rather than information. The section is disabled for this role
        # anyway; this stops a stray signal writing to the config.
        if not permissions.has(Cap.MANAGE_API_KEYS):
            return
        if text:
            self.ai_model = text
            config.save_ai_engine(self.ai_provider, self.ai_model)
            self._refresh_ai_status()

    def on_ai_keys_changed(self):
        if self._refuse(Cap.MANAGE_API_KEYS, 'La gestion des clés API', 'إدارة مفاتيح API'):
            return
        raw = self.ai_keys_input.toPlainText().strip()
        keys = [k.strip() for k in raw.replace(",", "\n").split("\n") if k.strip()]
        # save_api_keys() used to swallow its own failure, so a key file that could
        # not be written left the notary believing the keys were stored until the
        # next launch found none.
        if not config.save_api_keys(",".join(keys), self.ai_provider):
            QMessageBox.warning(
                self, "Erreur" if self.current_lang == "fr" else "خطأ",
                "Les clés API n'ont PAS pu être enregistrées."
                if self.current_lang == "fr"
                else "لم يتم حفظ مفاتيح API!")
        self._refresh_ai_status()

    def save_language(self):
        choice = self.lang_combo.currentIndex()
        lang_code = "ar" if choice == 0 else "fr"
        auth.update_language(lang_code)
        
        # We don't update translation here, we emit to MainWindow to restart the UI
        self.language_changed.emit(lang_code)

    def update_translation(self, lang_code):
        self.current_lang = lang_code
        is_fr = lang_code == "fr"
        
        if is_fr:
            self.office_title_lbl.setText("0. Identité de l'étude et du notaire")
            self.lang_title.setText("1. Langue de l'Application")
            self.lang_lbl.setText("Sélectionnez la langue par défaut :")
            
            self.cam_title.setText("3. Source Vidéo de la Caméra")
            self.cam_autostart_chk.setText(
                "Démarrer la caméra automatiquement au lancement")
            self.cam_lbl.setText("Sélectionnez le périphérique vidéo :")
            self.rtsp_lbl.setText("URL du flux RTSP / IP Camera :")
            self.save_cam_btn.setText("Enregistrer la source caméra")
            
            self.pass_title.setText("4. Sécurité & Modification du Mot de Passe")
            self.user_lbl.setText("Compte à modifier :")
            self.curr_pw_lbl.setText("Mot de passe actuel :")
            self.new_pw_lbl.setText("Nouveau mot de passe :")
            self.conf_pw_lbl.setText("Confirmer le nouveau mot de passe :")
            self.save_pass_btn.setText("Mettre à jour le mot de passe")
            
            self.backup_title.setText("5. Sauvegarde & Protection des Données (30 Ans)")
            self.backup_manual_lbl.setText("<b>Créer une sauvegarde complète (ZIP) :</b>")
            self.backup_manual_btn.setText("Créer une sauvegarde complète maintenant")
            self.backup_dl_btn.setText("Télécharger le fichier ZIP")
            self.usb_path_lbl.setText("Répertoire de sauvegarde externe USB :")
            self.save_usb_btn.setText("Enregistrer")
            self.diag_status_lbl.setText("<b>Protection des Données & Guardian :</b>")
            self.backup_hint_lbl.setText("Les sauvegardes sont automatiques. La suppression manuelle des données est interdite pour garantir la traçabilité notariale sur 30 ans.")
            
            self.diag_title.setText("6. Journal de Diagnostic & Maintenance Future")
            self.diag_hint_lbl.setText("En cas d'incident, vous pouvez consulter le journal et exporter un rapport technique :")
            self.export_diag_btn.setText("Exporter le rapport de Diagnostic (.log)")
            self.clear_log_btn.setText("🗑 Vider le journal")

            self.update_title.setText("7. Mises à Jour Automatiques & Version")
            self.check_update_btn.setText("Vérifier les mises à jour")
            
            self.import_title.setText("8. Importateur Automatique de Dossiers & Archives")
            self.import_hint_lbl.setText("Importez en bloc vos dossiers physiques et anciens contrats (.docx, .pdf, images) pour indexation automatique IA :")
            self.browse_import_btn.setText("Parcourir")
            self.run_import_btn.setText("Démarrer l'Importation")
            
            # These used to keep their Arabic construction text in French mode.
            self.ai_title.setText("2. Moteur d'Intelligence Artificielle")
            self.ai_provider_lbl.setText("Fournisseur :")
            self.ai_provider_value.setText("Google Gemini")
            self.ai_model_lbl.setText("Modèle :")
            self.cam_combo.blockSignals(True)
            _idx = self.cam_combo.currentIndex()
            self.cam_combo.clear(); self.cam_combo.addItems(self._camera_choices())
            self.cam_combo.setCurrentIndex(_idx); self.cam_combo.blockSignals(False)
            self.rtsp_lbl.setText(
                "Adresse de la caméra IP / de surveillance (ex. http://192.168.1.20:8080/video) :")
            self.usb_status_lbl.setText(
                "Les sauvegardes restent en local. Dès qu'un disque externe est branché, "
                "elles y sont recopiées automatiquement.")
            self.backup_count_lbl.setText(
                f"Sauvegardes automatiques conservées : {self._backup_count()}")
            self.db_status_lbl.setText(
                "État de la base de données : intacte (PRAGMA vérifié)" if self._db_ok
                else "Resynchronisation et réparation automatique de la base en cours...")
            self.version_lbl.setText(self._version_label_text(is_fr=True))
            self._refresh_ai_fields()
            self._apply_update_channel_state()

            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        else:
            self.office_title_lbl.setText("0. بيانات المكتب وعدل الإشهاد")
            self.lang_title.setText("1. لغة التطبيق والنظام")
            self.lang_lbl.setText("اختر لغة واجهة ورسائل النظام:")
            
            self.cam_title.setText("3. مصدر الكاميرا والمراقبة الحية")
            self.cam_autostart_chk.setText(
                "تشغيل الكاميرا تلقائياً عند فتح البرنامج")
            self.cam_lbl.setText("اختر جهاز الكاميرا أو رابط البث:")
            self.rtsp_lbl.setText("رابط بث الكاميرا IP / RTSP:")
            self.save_cam_btn.setText("حفظ مصدر الكاميرا")
            
            self.pass_title.setText("4. الأمان وتغيير كلمة المرور")
            self.user_lbl.setText("حساب المستخدم المراد تعديله:")
            self.curr_pw_lbl.setText("كلمة المرور الحالية:")
            self.new_pw_lbl.setText("كلمة المرور الجديدة:")
            self.conf_pw_lbl.setText("تأكيد كلمة المرور الجديدة:")
            self.save_pass_btn.setText("تحديث كلمة المرور")
            
            self.backup_title.setText("5. النسخ الاحتياطي وحماية البيانات (حماية 30 سنة)")
            self.backup_manual_lbl.setText(("<b>Créer une sauvegarde complète (ZIP) :</b>" if self.current_lang == "fr" else "<b>إنشاء نسخة احتياطية كاملة (ZIP) :</b>"))
            self.backup_manual_btn.setText("إنشاء نسخة احتياطية كاملة الآن")
            self.backup_dl_btn.setText("تنزيل ملف النسخة الاحتياطية")
            self.usb_path_lbl.setText("مسار القرص الصلب الخارجي المربوط بالكمبيوتر:")
            self.save_usb_btn.setText("حفظ المسار")
            self.diag_status_lbl.setText("<b>حالة حماية البيانات وحارس النظام (System Guardian) :</b>")
            self.backup_hint_lbl.setText("يتم حظر حذف البيانات وتوليد نسخة يومية تلقائياً لضمان استقرار العمل لـ30 سنة قادمة.")
            
            self.diag_title.setText("6. سجل تشخيص الصيانة والأخطاء المستقبلية")
            self.diag_hint_lbl.setText("إذا حدث أي إشكال مستقبلي، يمكنك تنزيل تقرير التشخيص بنقرة واحدة وإرساله للصيانة:")
            self.export_diag_btn.setText("تنزيل تقرير تشخيص النظام (system_errors.log)")
            self.clear_log_btn.setText("🗑 مسح السجل")

            self.update_title.setText("7. التحديثات الآلية وإصدار المنظومة")
            self.check_update_btn.setText(("Vérifier les mises à jour" if self.current_lang == "fr" else "فحص التحديثات"))
            
            self.import_title.setText("8. أداة الاستيراد التلقائي لأرشيف المجلدات والملفات القديمة")
            self.import_hint_lbl.setText("يتيح هذا الخيار استيراد جميع المجلدات والعقود المكتوبة سابقاً وصور بطاقات التعريف وإدراجها تلقائياً:")
            self.browse_import_btn.setText("تصفح")
            self.run_import_btn.setText("بدء الاستيراد التلقائي")
            
            self.ai_title.setText("2. محرك الذكاء الاصطناعي")
            self.ai_provider_lbl.setText("المزوّد :")
            self.ai_provider_value.setText("Google Gemini")
            self.ai_model_lbl.setText("النموذج :")
            self.cam_combo.blockSignals(True)
            _idx = self.cam_combo.currentIndex()
            self.cam_combo.clear(); self.cam_combo.addItems(self._camera_choices())
            self.cam_combo.setCurrentIndex(_idx); self.cam_combo.blockSignals(False)
            self.rtsp_lbl.setText(
                "عنوان كاميرا IP أو كاميرا المراقبة (مثال http://192.168.1.20:8080/video) :")
            self.usb_status_lbl.setText(
                "يتم حفظ النسخ محلياً. فور ربط القرص الخارجي سيتم نقل النسخ إليه آلياً.")
            self.backup_count_lbl.setText(
                f"عدد النسخ الاحتياطية المحفوظة آلياً: {self._backup_count()}")
            self.db_status_lbl.setText(
                "حالة قاعدة البيانات: سليمة (تم فحص PRAGMA)" if self._db_ok
                else "جاري إعادة المزامنة والإصلاح التلقائي لقاعدة البيانات...")
            self.version_lbl.setText(self._version_label_text(is_fr=False))
            self._refresh_ai_fields()
            self._apply_update_channel_state()

            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # Clear active status messages to avoid mismatching language status
        self.lang_status.setText("")
        self.cam_status.setText("")
        self.pass_status.setText("")
        self.backup_status.setText("")
        self.diag_status.setText("")
        self.update_status.setText("")
        self.import_status.setText("")

        # This block wipes every status line, so the standing "updates are
        # installed manually" notice has to be restored after it rather than
        # before, or a language switch leaves the panel blank.
        self._apply_update_channel_state()
        # The section headers mirror the card titles set above, so they are
        # re-synced here, at the end of the language switch.
        # The office form's labels and its preamble preview follow the language too.
        self.refresh_office_labels()
        self.refresh_office_preview()

        # The licence card follows the language as well.
        self._retitle_licence()
        self.refresh_licence_status()

        # The office-network card follows the language as well.
        self._retitle_network()
        self.on_network_mode_changed()

        # The certificate warning and its guidance are language-dependent too.
        self.refresh_tls_warning()

        # The assisted-migration entry point, in the language of the page.
        self.open_migration_btn.setText(
            "📁 Migration assistée d'un ancien dossier client" if is_fr
            else "📁 استيراد مُساعَد لأرشيف قديم")
        self.migration_hint_lbl.setText(
            "Analyse un dossier d'archives et propose des fiches clients ; "
            "rien n'est enregistré avant votre confirmation."
            if is_fr else
            "يحلّل مجلّد أرشيف ويقترح بطاقات حرفاء ؛ "
            "لا يقع تسجيل أي شيء قبل مصادقتك.")

        self._sync_section_titles()

    # ── Camera Source Actions ──
    # Index 3 is the URL entry: an IP webcam (phone app) or a network/security camera
    # reached over http/rtsp. The office uses both, so it is a normal choice, not a
    # fallback.
    URL_CHOICE_INDEX = 3

    def _camera_choices(self):
        is_fr = self.current_lang == "fr"
        if is_fr:
            return ["Caméra USB 0 (par défaut)",
                    "Caméra USB 1 (externe)",
                    "Caméra USB 2 (secondaire)",
                    "Caméra IP / de surveillance (adresse réseau)"]
        return ["كاميرا USB رقم 0 (الافتراضية)",
                "كاميرا USB رقم 1 (خارجية)",
                "كاميرا USB رقم 2 (ثانوية)",
                "كاميرا IP أو كاميرا مراقبة (عنوان الشبكة)"]

    def on_camera_combo_changed(self, index):
        show_url = index == self.URL_CHOICE_INDEX
        self.rtsp_lbl.setVisible(show_url)
        self.rtsp_input.setVisible(show_url)

    def camera_service(self):
        """The one CameraService owned by MainWindow, or None when running standalone."""
        w = self.window()
        # A widget with no parent is its own window, so `w` can be this page. The
        # lookup would then find this very method and hand it back as though it
        # were the service, and the caller's `svc.restart(...)` would raise
        # AttributeError instead of taking the "no service" branch.
        if w is None or w is self:
            return None
        svc = getattr(w, "camera_service", None)
        return svc if hasattr(svc, "restart") else None

    def on_camera_autostart_toggled(self, enabled: bool):
        """Persists whether the camera should come up on its own at launch."""
        camera.set_camera_autostart(bool(enabled))
        is_fr = self.current_lang == "fr"
        if enabled:
            msg = ("La caméra démarrera automatiquement au lancement."
                   if is_fr else "ستشتغل الكاميرا تلقائياً عند فتح البرنامج.")
        else:
            msg = ("La caméra ne démarrera plus toute seule."
                   if is_fr else "لن تشتغل الكاميرا تلقائياً.")
        self.cam_status.setText(msg)
        self.cam_status.setStyleSheet("color: #059669; font-weight: bold;")

    def save_camera_source(self):
        choice = self.cam_combo.currentIndex()
        is_fr = self.current_lang == "fr"

        if choice == self.URL_CHOICE_INDEX:
            new_source = self.rtsp_input.text().strip()
            # An empty URL used to be saved as "" and reported as a success, after which
            # CameraService refused to start and the camera silently never came up.
            if not new_source:
                self.cam_status.setText(
                    "Saisissez l'adresse de la caméra IP avant d'enregistrer." if is_fr
                    else "أدخل عنوان كاميرا المراقبة قبل الحفظ.")
                self.cam_status.setStyleSheet("color: #dc2626; font-weight: bold;")
                return
        else:
            new_source = choice

        self.cam_status.setText(
            "Vérification de la connexion à la caméra..." if is_fr
            else "جاري فحص الاتصال وتواجد الكاميرا...")
        self.cam_status.setStyleSheet("color: #2563eb;")
        self.save_cam_btn.setEnabled(False)

        # Asynchronously check IP reachability to avoid freezing UI
        self.cam_thread = CamConnectThread(new_source)
        self.cam_thread.finished.connect(lambda reached: self.on_camera_connection_tested(reached, new_source))
        self.cam_thread.start()

    def on_camera_connection_tested(self, reached, new_source):
        self.save_cam_btn.setEnabled(True)
        is_fr = self.current_lang == "fr"

        unreachable = not reached and isinstance(new_source, str) and bool(new_source)

        # An unreachable address used to be refused outright, so a security camera that
        # was merely switched off — or not yet on the network — could never be recorded.
        # It is saved and applied; CameraService reports it as disconnected and keeps
        # retrying with backoff, which is exactly what that state is for.
        if not camera.set_saved_camera_source(new_source):
            # Same shape as the USB backup path bug: the write failed and the page
            # used to carry on and report the source as applied.
            self.cam_status.setText(
                "La source caméra n'a PAS pu être enregistrée." if is_fr
                else "لم يتم حفظ مصدر الكاميرا!")
            self.cam_status.setStyleSheet("color: #dc2626; font-weight: bold;")
            return

        # Saving to disk is not enough: the camera runs for the whole session inside
        # CameraService, so it has to be told. Without this the page reported success
        # while the running camera stayed on the previous device until the next launch.
        svc = self.camera_service()
        if svc is None:
            self.cam_status.setText(
                "Source enregistrée. Elle sera utilisée au prochain démarrage." if is_fr
                else "تم حفظ المصدر. سيُستعمل عند التشغيل القادم.")
            self.cam_status.setStyleSheet("color: #059669; font-weight: bold;")
            return

        svc.restart(new_source)
        if unreachable:
            self.cam_status.setText(
                "Adresse enregistrée, mais la caméra ne répond pas pour l'instant. "
                "La connexion sera retentée automatiquement." if is_fr
                else "تم حفظ العنوان، لكن الكاميرا لا تستجيب حالياً. "
                     "ستتم إعادة المحاولة تلقائياً.")
            self.cam_status.setStyleSheet("color: #d97706; font-weight: bold;")
        else:
            self.cam_status.setText(
                "Source caméra mise à jour et appliquée immédiatement." if is_fr
                else "تم تحديث مصدر الكاميرا وتطبيقه فوراً.")
            self.cam_status.setStyleSheet("color: #059669; font-weight: bold;")

    # A single character used to be accepted. These accounts will gate the notaire and
    # secrétaire builds across the office network, so a real minimum applies.
    MIN_PASSWORD_LEN = 8

    def _password_problem(self, pw: str):
        """Returns a message describing why the password is too weak, or None."""
        is_fr = self.current_lang == "fr"
        if len(pw) < self.MIN_PASSWORD_LEN:
            return (f"Le mot de passe doit contenir au moins {self.MIN_PASSWORD_LEN} caractères."
                    if is_fr else
                    f"يجب أن تحتوي كلمة المرور على {self.MIN_PASSWORD_LEN} خانات على الأقل.")
        if pw.isdigit() or pw.isalpha():
            return ("Mélangez lettres et chiffres." if is_fr
                    else "اخلط بين الحروف والأرقام.")
        if pw.lower() in ("zarai2024", "password", "motdepasse", "12345678"):
            return ("Ce mot de passe est trop courant." if is_fr
                    else "كلمة المرور هذه شائعة جداً.")
        return None

    # ── Password Safety Flow (High Priority) ──
    def save_password(self):
        """
        Two different operations behind one button, decided by who is signed in.

        The notary changing his own password, or the secretary changing hers,
        must present the current one. The notary resetting the SECRETARY's
        password must not - that is the whole point of the reset, since a
        forgotten password cannot be presented. The old build read the stored
        password back in clear text to compare it; that is no longer possible,
        and no longer necessary.
        """
        is_fr = self.current_lang == "fr"
        target_username = ("patron" if self.user_combo.currentIndex() == 0
                           else "secretaire")
        me = permissions.session.username
        curr_pw = self.curr_pw_input.text()
        new_pw = self.new_pw_input.text().strip()
        conf_pw = self.conf_pw_input.text()

        def fail(msg):
            self.pass_status.setText(msg)
            self.pass_status.setStyleSheet("color: #dc2626; font-weight: bold;")

        def ok(msg):
            self.pass_status.setText(msg)
            self.pass_status.setStyleSheet("color: #059669; font-weight: bold;")
            self.curr_pw_input.clear()
            self.new_pw_input.clear()
            self.conf_pw_input.clear()

        changing_own = (target_username == me)
        if not changing_own and not permissions.has(Cap.MANAGE_USERS):
            fail("Vous ne pouvez modifier que votre propre mot de passe."
                 if is_fr else "لا يمكنك تغيير إلا كلمة المرور الخاصة بك.")
            return

        if not new_pw:
            fail("Le nouveau mot de passe ne peut pas être vide !" if is_fr
                 else "لا يمكن أن تكون كلمة المرور الجديدة فارغة!")
            return
        if new_pw != conf_pw:
            fail("Les deux mots de passe ne correspondent pas !" if is_fr
                 else "كلمتا المرور الجديدتان غير متطابقتان!")
            return
        problem = self._password_problem(new_pw)
        if problem:
            fail(problem)
            return

        try:
            if changing_own:
                success = auth.change_own_password(target_username, curr_pw, new_pw)
                if not success:
                    fail("Mot de passe actuel incorrect !" if is_fr
                         else "كلمة المرور الحالية غير صحيحة!")
                    return
            else:
                success = auth.admin_reset_password(target_username, new_pw)
                if not success:
                    fail("Réinitialisation refusée." if is_fr
                         else "تم رفض إعادة التعيين.")
                    return
        except permissions.PermissionDenied:
            fail("Action réservée au notaire." if is_fr
                 else "هذا الإجراء مخصص للأستاذ فقط.")
            return
        except Exception as e:
            fail((f"Erreur de modification : {e}" if is_fr
                  else f"فشل تعديل كلمة المرور : {e}"))
            return

        if changing_own:
            ok("Votre mot de passe a été mis à jour." if is_fr
               else "تم تحديث كلمة المرور الخاصة بك.")
        else:
            ok(f"Mot de passe de '{target_username}' réinitialisé." if is_fr
               else f"تمت إعادة تعيين كلمة مرور الحساب '{target_username}'.")

    def _refuse(self, cap, fr_what, ar_what) -> bool:
        """
        True when this role may not perform the action, having said so.

        Every administrative action on this page routes through here rather than
        relying on its button being hidden, so a keyboard shortcut or a future
        caller meets the same wall.
        """
        if permissions.has(cap):
            return False
        is_fr = self.current_lang == "fr"
        QMessageBox.warning(
            self, "Accès refusé" if is_fr else "الدخول مرفوض",
            (f"{fr_what} est réservé au notaire." if is_fr
             else f"{ar_what} مخصص للأستاذ فقط."))
        return True

    def regenerate_recovery_code(self):
        """Issues a fresh recovery code for the notary and shows it once."""
        is_fr = self.current_lang == "fr"
        if not permissions.has(Cap.MANAGE_USERS):
            QMessageBox.warning(
                self, "Accès refusé" if is_fr else "الدخول مرفوض",
                "Action réservée au notaire." if is_fr
                else "هذا الإجراء مخصص للأستاذ فقط.")
            return
        code = auth.issue_recovery_code(permissions.session.username)
        if not code:
            QMessageBox.warning(self, "Erreur" if is_fr else "خطأ",
                                "Compte introuvable." if is_fr else "الحساب غير موجود.")
            return
        QMessageBox.information(
            self, "Code de récupération" if is_fr else "رمز الاسترجاع",
            (f"Votre nouveau code est :\n\n{code}\n\n"
             "L'ancien code ne fonctionne plus. Notez celui-ci et rangez-le "
             "en lieu sûr — c'est le seul moyen de rouvrir votre compte si "
             "vous perdez votre mot de passe."
             if is_fr else
             f"رمزك الجديد هو :\n\n{code}\n\n"
             "الرمز القديم لم يعد صالحاً. دوّن هذا الرمز واحتفظ به في مكان آمن "
             "— هو الوسيلة الوحيدة لاسترجاع حسابك إذا ضاعت كلمة المرور."))

    # ── Sauvegarde & Protection 30 Ans ──
    def run_manual_backup(self):
        if self._refuse(Cap.MANAGE_BACKUP, 'La sauvegarde', 'النسخ الاحتياطي'):
            return
        self.backup_status.setText("Archivage et compression de la base de données..." if self.current_lang == "fr" else "جاري ضغط قاعدة المعطيات ومجلدات الأرشيف وحفظهم...")
        self.backup_status.setStyleSheet("color: #2563eb;")
        self.backup_manual_btn.setEnabled(False)
        self.backup_dl_btn.setVisible(False)

        self.backup_thread = BackupThread()
        self.backup_thread.finished.connect(self.on_backup_completed)
        self.backup_thread.start()

    def on_backup_completed(self, zip_path_str):
        self.backup_manual_btn.setEnabled(True)
        if zip_path_str:
            self.last_created_backup = Path(zip_path_str)
            self.backup_status.setText(
                f"Sauvegarde créée : {self.last_created_backup.name}" if self.current_lang == "fr"
                else f"تم إنشاء النسخة الاحتياطية بنجاح: {self.last_created_backup.name}")
            self.backup_status.setStyleSheet("color: #059669; font-weight: bold;")
            self.backup_dl_btn.setVisible(True)
            
            # Recalculate backup count
            self.backup_count_lbl.setText(
                f"عدد النسخ الاحتياطية المحفوظة آلياً: {self._backup_count()}"
                if self.current_lang != "fr"
                else f"Sauvegardes archivées : {self._backup_count()}")
            
            # Check USB sync status
            self.check_usb_status()
        else:
            self.backup_status.setText("Échec de la création de la sauvegarde." if self.current_lang == "fr" else "فشل إنشاء نسخة احتياطية كاملة للمنظومة.")
            self.backup_status.setStyleSheet("color: #dc2626; font-weight: bold;")

    def download_backup_zip(self):
        if not self.last_created_backup or not self.last_created_backup.exists():
            return
            
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter la Sauvegarde / حفظ النسخة الاحتياطية", 
            self.last_created_backup.name, "Archives ZIP (*.zip)"
        )
        if save_path:
            import shutil
            try:
                shutil.copy2(self.last_created_backup, save_path)
                self.backup_status.setText(f"Sauvegarde exportée vers : {Path(save_path).name}" if self.current_lang == "fr" else f" تم تصدير وتحميل النسخة الاحتياطية بنجاح إلى: {Path(save_path).name}")
                self.backup_status.setStyleSheet("color: #059669; font-weight: bold;")
            except Exception as e:
                self.backup_status.setText(f"Échec de l'export : {str(e)}" if self.current_lang == "fr" else f" فشل تصدير الملف: {str(e)}")
                self.backup_status.setStyleSheet("color: #dc2626; font-weight: bold;")

    def save_usb_path(self):
        if self._refuse(Cap.MANAGE_BACKUP, 'Le réglage du chemin USB', 'ضبط مسار USB'):
            return
        path_str = self.usb_input.text().strip()
        is_fr = self.current_lang == "fr"

        # An empty box used to do nothing at all, with no message; a path that does not
        # exist was reported as saved successfully.
        if not path_str:
            self.backup_status.setText(
                "Indiquez le dossier du disque externe." if is_fr
                else "أدخل مسار القرص الخارجي.")
            self.backup_status.setStyleSheet("color: #dc2626; font-weight: bold;")
            return

        from pathlib import Path as _P
        _target = _P(path_str)
        if not _target.exists():
            self.backup_status.setText(
                f"Ce dossier est introuvable : {path_str}" if is_fr
                else f"المسار غير موجود : {path_str}")
            self.backup_status.setStyleSheet("color: #dc2626; font-weight: bold;")
            return
        # .exists() is true for a file as well, and a file was being accepted as
        # the backup folder - reported as saved, then failing on every mirror.
        if not _target.is_dir():
            self.backup_status.setText(
                f"Ce chemin est un fichier, pas un dossier : {path_str}" if is_fr
                else f"هذا المسار ملف وليس مجلداً : {path_str}")
            self.backup_status.setStyleSheet("color: #dc2626; font-weight: bold;")
            return

        if path_str:
            if not system_guardian.set_external_backup_dir(path_str):
                self.backup_status.setText(
                    "Chemin USB non enregistré — vérifiez qu'il est accessible."
                    if self.current_lang == "fr"
                    else "لم يتم حفظ مسار القرص الخارجي! تأكد من أن المسار موجود.")
                self.backup_status.setStyleSheet("color: #dc2626; font-weight: bold;")
                return
            self.check_usb_status()
            self.backup_status.setText("Chemin de sauvegarde externe enregistré." if self.current_lang == "fr" else "تم حفظ مسار القرص الصلب الخارجي بنجاح!")
            self.backup_status.setStyleSheet("color: #059669; font-weight: bold;")

    def _backup_count(self) -> int:
        """How many automatic backups are on disk right now."""
        try:
            return len(list(system_guardian.BACKUPS_DIR.glob("*.zip")))
        except Exception as e:
            system_guardian.log_system_error("could not count backups", e)
            return 0

    def check_usb_status(self):
        ext_dir = system_guardian.get_external_backup_dir()
        is_connected = False
        if ext_dir:
            try:
                is_connected = ext_dir.exists()
            except Exception as e:
                # Swallowing this made an unreachable drive look like "not connected yet".
                system_guardian.log_system_error(
                    f"external backup path unreachable: {ext_dir}", e)
                
        if is_connected:
            self.usb_status_lbl.setText(f"القرص الصلب الخارجي متصل ومربوط بنجاح: {ext_dir} (تتم المزامنة التلقائية فورياً)" if self.current_lang != "fr" else f" Disque USB connecté : {ext_dir}")
            self.usb_status_lbl.setStyleSheet("color: #059669; font-weight: bold; font-size: 11px;")
        else:
            self.usb_status_lbl.setText(
                "يتم حفظ النسخ محلياً. فور ربط القرص الخارجي سيتم نقل النسخ إليه آلياً."
                if self.current_lang != "fr"
                else "Sauvegardes locales. Connectez le disque externe pour la synchronisation.")
            self.usb_status_lbl.setStyleSheet("color: #4b5563; font-style: italic; font-size: 11px;")

    # ── Diagnostic & Logs Actions ──
    def load_diagnostic_logs(self):
        from system_guardian import ERROR_LOG_PATH
        if ERROR_LOG_PATH.exists() and ERROR_LOG_PATH.stat().st_size > 0:
            try:
                log_content = ERROR_LOG_PATH.read_text(encoding="utf-8")
                self.log_viewer.setPlainText(log_content[-3000:])
            except Exception:
                self.log_viewer.setPlainText("Aucun log d'erreur enregistré. Le système est propre." if self.current_lang == "fr" else "سجل النظام نظيف 100%! لم يتم تسجيل أي أخطاء.")
        else:
            self.log_viewer.setPlainText("Aucun log d'erreur enregistré. Le système est propre." if self.current_lang == "fr" else "سجل النظام نظيف 100%! لم يتم تسجيل أي أخطاء أو أعطال في المنظومة.")

    def clear_diagnostic_log(self):
        """Wipe system_errors.log after user confirmation."""
        from system_guardian import ERROR_LOG_PATH
        is_fr = self.current_lang == "fr"
        title = "Vider le journal de diagnostic" if is_fr else "مسح سجل الأخطاء"
        msg   = ("Voulez-vous effacer tout le journal d'erreurs ?\n"
                 "Cette action est irréversible.") if is_fr else (
                "هل تريد مسح سجل الأخطاء بالكامل؟\nلا يمكن التراجع عن هذا الإجراء.")
        reply = QMessageBox.question(
            self, title, msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if ERROR_LOG_PATH.exists():
                ERROR_LOG_PATH.write_text("", encoding="utf-8")
            ok_msg = "Journal vidé avec succès. Le système est propre." if is_fr else "تم مسح السجل بنجاح. المنظومة نظيفة الآن."
            self.log_viewer.setPlainText(ok_msg)
            self.diag_status.setText(ok_msg)
        except Exception as e:
            err_msg = f"Erreur lors de la suppression : {e}" if is_fr else f"خطأ أثناء المسح: {e}"
            QMessageBox.warning(self, "Erreur" if is_fr else "خطأ", err_msg)

    def _diagnostic_header(self) -> str:
        """
        The environment facts a maintainer needs before the error lines mean anything.

        The export used to be a byte-for-byte copy of system_errors.log: no version, no
        operating system, no database state. Whoever received it could not tell which
        build produced it, or whether the database was even healthy.
        """
        import platform
        import shutil as _sh
        import datetime as _dt
        from system_guardian import BACKUPS_DIR

        def safe(fn, default="?"):
            try:
                return fn()
            except Exception:
                return default

        counts = {}
        for table in ("clients", "cases", "check_ins", "expenses", "salaries"):
            counts[table] = safe(lambda t=table: reception.get_connection()
                                 .execute("SELECT COUNT(*) FROM " + t).fetchone()[0])
        free_mb = safe(lambda: round(_sh.disk_usage(str(config.DATA_DIR)).free / 1e6, 1))
        backups = safe(lambda: len(list(BACKUPS_DIR.glob("*.zip"))), 0)
        newest = safe(lambda: max((b.name for b in BACKUPS_DIR.glob("*.zip")),
                                  default="aucune"), "?")
        provider, model = safe(config.load_ai_engine, ("?", "?"))
        nkeys = safe(lambda: len([k for k in config.load_saved_api_keys("gemini").split(",")
                                  if k.strip()]), 0)
        ext = safe(lambda: system_guardian.get_external_backup_dir() or "non configure", "?")

        L = [
            "=" * 72,
            "RAPPORT DE DIAGNOSTIC - Cabinet Notarial Zarai",
            "تقرير تشخيص المنظومة",
            "=" * 72,
            f"Genere le           : {_dt.datetime.now():%Y-%m-%d %H:%M:%S}",
            f"Version             : v{updater.__version__}",
            f"Systeme             : {platform.platform()}",
            f"Python              : {platform.python_version()}",
            f"Dossier de donnees  : {config.DATA_DIR}",
            f"Espace disque libre : {free_mb} Mo",
            "",
            "--- Base de donnees ---",
            f"Integrite (PRAGMA)  : {'OK' if getattr(self, '_db_ok', False) else 'ECHEC'}",
        ]
        for t, n in counts.items():
            L.append(f"  {t:<12s}: {n}")
        L += [
            "",
            "--- Sauvegardes ---",
            f"Nombre d'archives   : {backups}",
            f"Plus recente        : {newest}",
            f"Disque externe      : {ext}",
            "",
            "--- Camera ---",
            f"Source enregistree  : {safe(camera.get_saved_camera_source)}",
            f"Demarrage auto      : {safe(camera.get_camera_autostart)}",
            "",
            "--- Moteur IA ---",
            f"Fournisseur/modele  : {provider} / {model}",
            f"Cles API presentes  : {nkeys}",
            "",
            "=" * 72,
            "JOURNAL DES ERREURS",
            "=" * 72,
            "",
        ]
        return "\n".join(L)

    def export_diagnostic_log(self):
        if self._refuse(Cap.MANAGE_BACKUP, "L'export du diagnostic", 'تصدير تقرير التشخيص'):
            return
        from system_guardian import ERROR_LOG_PATH
        is_fr = self.current_lang == "fr"

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le rapport de diagnostic / تصدير تقرير التشخيص",
            "rapport_diagnostic_zarai.log", "Logs Files (*.log *.txt)"
        )
        if not save_path:
            return

        try:
            body = ""
            if ERROR_LOG_PATH.exists():
                body = ERROR_LOG_PATH.read_text(encoding="utf-8", errors="replace")
            if not body.strip():
                body = "(aucune erreur enregistree / لا توجد أخطاء مسجلة)\n"
            with open(save_path, "w", encoding="utf-8") as fh:
                fh.write(self._diagnostic_header())
                fh.write(body)
            self.diag_status.setText(
                "Rapport de diagnostic exporte." if is_fr
                else "تم تصدير تقرير التشخيص بنجاح!")
            self.diag_status.setStyleSheet("color: #059669; font-weight: bold;")
        except Exception as e:
            self.diag_status.setText(
                f"Echec de l'export : {str(e)}" if is_fr
                else f"فشل تصدير التقرير : {str(e)}")
            self.diag_status.setStyleSheet("color: #dc2626; font-weight: bold;")

    # ── Mises à Jour Automatiques ──
    def _add_section(self, card, title_label, expanded=False):
        sec = CollapsibleSection(title_label.text(), expanded=expanded, parent=self)
        title_label.setVisible(False)
        card.setProperty("class", "")
        card.setStyleSheet("QFrame { background: transparent; border: none; }")
        sec.add_widget(card)
        if not hasattr(self, "_sections"):
            self._sections = []
        self._sections.append((sec, title_label, card))
        self.scroll_layout.addWidget(sec)
        return sec

    def _sync_section_titles(self):
        """Copies each card's (hidden) title into its section header after a language switch."""
        for item in getattr(self, "_sections", []):
            try:
                sec, lbl = item[0], item[1]
                sec.set_title(lbl.text())
            except (RuntimeError, IndexError, ValueError):
                pass

    def load_office_profile(self):
        """Fills the form from the stored office profile."""
        prof = office_profile.load()
        for key, edit in getattr(self, "office_inputs", {}).items():
            edit.setText(prof.get(key, "") or "")
        self.refresh_office_labels()
        self.refresh_office_preview()

    def refresh_office_labels(self):
        is_fr = self.current_lang == "fr"
        for key, _d, label_ar, label_fr in office_profile.FIELDS:
            lbl = self.office_labels.get(key)
            if lbl is not None:
                lbl.setText((label_fr if is_fr else label_ar) + " :")
            edit = self.office_inputs.get(key)
            if edit is not None:
                edit.setPlaceholderText(label_fr if is_fr else label_ar)
        self.office_hint.setText(
            "Ces informations identifient VOTRE étude. Elles remplacent "
            "automatiquement l'en-tête, la signature et le préambule de chaque "
            "acte généré." if is_fr else
            "\u0647\u0630\u0647 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a \u062a\u062e\u0635 \u0645\u0643\u062a\u0628\u0643 \u0623\u0646\u062a. \u062a\u064f\u0633\u062a\u0639\u0645\u0644 \u0622\u0644\u064a\u0627\u064b \u0641\u064a \u062a\u0631\u0648\u064a\u0633\u0629 \u0648\u062f\u064a\u0628\u0627\u062c\u0629 "
            "\u0648\u0625\u0645\u0636\u0627\u0621 \u0643\u0644 \u0639\u0642\u062f \u064a\u062a\u0645 \u062a\u0648\u0644\u064a\u062f\u0647.")
        self.save_office_btn.setText(
            "Enregistrer les données du bureau" if is_fr
            else "\u062d\u0641\u0638 \u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u0645\u0643\u062a\u0628")

    def refresh_office_preview(self):
        """Shows the exact sentence that will open every generated deed."""
        prof = {k: e.text() for k, e in getattr(self, "office_inputs", {}).items()}
        is_fr = self.current_lang == "fr"
        head = ("Aperçu du préambule :" if is_fr
                else "\u0645\u0639\u0627\u064a\u0646\u0629 \u062f\u064a\u0628\u0627\u062c\u0629 \u0627\u0644\u0639\u0642\u062f :")
        self.office_preview.setText(
            f"<b>{head}</b><br>\u0627\u0644\u062d\u0645\u062f \u0644\u0644\u0647 \u0641\u064a \u064a\u0648\u0645 ... "
            f"{office_profile.notary_block(prof)}")

    def save_office_profile(self):
        """
        Stores the office identity. Every deed generated afterwards uses it.

        A blank required field is refused rather than silently producing a deed
        with dotted placeholders where the notary's name should be.
        """
        is_fr = self.current_lang == "fr"
        values = {k: e.text().strip() for k, e in self.office_inputs.items()}
        missing = office_profile.missing_fields(values)
        if missing:
            names = []
            for key, _d, lab_ar, lab_fr in office_profile.FIELDS:
                if key in missing:
                    names.append(lab_fr if is_fr else lab_ar)
            self.office_status.setText(
                ("Champs obligatoires manquants : " + "\u060c ".join(names))
                if is_fr else
                ("\u062e\u0627\u0646\u0627\u062a \u0625\u062c\u0628\u0627\u0631\u064a\u0629 \u0646\u0627\u0642\u0635\u0629 : " + "\u060c ".join(names)))
            self.office_status.setStyleSheet("color:#dc2626; font-weight:bold;")
            return
        if not office_profile.save(values):
            self.office_status.setText(
                "Les données du bureau n'ont PAS pu être enregistrées." if is_fr
                else "\u0644\u0645 \u064a\u062a\u0645 \u062d\u0641\u0638 \u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u0645\u0643\u062a\u0628!")
            self.office_status.setStyleSheet("color:#dc2626; font-weight:bold;")
            return
        self.office_status.setText(
            "Données du bureau enregistrées. Elles seront utilisées dans tous "
            "les actes." if is_fr else
            "\u062a\u0645 \u062d\u0641\u0638 \u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u0645\u0643\u062a\u0628. \u0633\u062a\u064f\u0633\u062a\u0639\u0645\u0644 \u0641\u064a \u062c\u0645\u064a\u0639 \u0627\u0644\u0639\u0642\u0648\u062f.")
        self.office_status.setStyleSheet("color:#059669; font-weight:bold;")
        self.refresh_office_preview()
        # The account label and the window title carry the notary's name.
        try:
            self.user_combo.setItemText(0, f"patron ({office_profile.display_name()})")
        except Exception:
            # (c) Safe: the combo may not exist yet during construction.
            pass

    def _version_label_text(self, is_fr: bool) -> str:
        """
        The version line, with the repository shown only when there is a real one.

        This lived in three places - the constructor and both branches of
        update_translation - and all three printed the placeholder
        "github.com/OWNER/mon-app-releases". Fixing one of them left the other two
        to put it back on the next language switch.
        """
        ready = updater.is_update_channel_configured()
        head = (f"<b>Version installée : v{updater.__version__}</b>" if is_fr
                else f"<b>إصدار المنظومة الحالي : v{updater.__version__}</b>")
        if not ready:
            return head
        repo = updater.GITHUB_REPO_RELEASES
        return head + ((f"<br>Dépôt officiel des mises à jour : github.com/{repo}")
                       if is_fr else
                       (f"<br>مستودع التحديثات الرسمي: github.com/{repo}"))

    def _apply_update_channel_state(self):
        """Shows or hides the update control to match whether a channel exists."""
        ready = updater.is_update_channel_configured()
        self._update_channel_ready = ready
        is_fr = self.current_lang == "fr"
        self.version_lbl.setText(self._version_label_text(is_fr))
        self.check_update_btn.setVisible(ready)
        if not ready:
            self.update_status.setText(
                "Les mises à jour sont installées manuellement pour le moment."
                if is_fr else "يتم تثبيت التحديثات يدوياً في الوقت الحالي.")
            self.update_status.setStyleSheet("color: #64748b; font-size: 12px;")

    def check_app_updates(self):
        if not getattr(self, "_update_channel_ready", False):
            self.update_status.setText(
                "Aucun canal de mise à jour n'est configuré."
                if self.current_lang == "fr"
                else "لا يوجد مصدر تحديثات مضبوط.")
            self.update_status.setStyleSheet("color: #b45309; font-weight: bold;")
            return
        self.update_status.setText("Connexion au serveur de mises à jour..." if self.current_lang == "fr" else "جاري الاتصال بالخادم والبحث عن تحديثات...")
        self.update_status.setStyleSheet("color: #2563eb;")
        self.check_update_btn.setEnabled(False)

        self.update_thread = UpdateCheckThread()
        self.update_thread.finished.connect(self.on_update_checked)
        self.update_thread.start()

    def on_update_checked(self, up_info):
        self.check_update_btn.setEnabled(True)
        if up_info:
            self._current_update_info = up_info
            ver = up_info.get("version", "")
            asset_name = up_info.get("asset_name", "")
            self.update_status.setText(
                f"Nouvelle version disponible : {ver} ({asset_name}) !"
                if self.current_lang == "fr" else
                f"توجد نسخة جديدة متاحة للمنظومة: {ver} ({asset_name}) !"
            )
            self.update_status.setStyleSheet("color: #059669; font-weight: bold;")
            self.download_update_btn.setVisible(True)
            self.download_update_btn.setEnabled(True)
        elif updater.is_update_channel_configured():
            self._current_update_info = None
            self.download_update_btn.setVisible(False)
            self.update_status.setText(
                f"Aucune nouvelle version trouvée (v{updater.__version__}). "
                f"Si vous n'avez pas de connexion Internet, ce résultat n'est pas fiable."
                if self.current_lang == "fr" else
                f"لم يتم العثور على نسخة أحدث (v{updater.__version__}). "
                f"إذا لم يكن هناك اتصال بالأنترنت فهذه النتيجة غير مؤكدة.")
            self.update_status.setStyleSheet("color: #059669; font-weight: bold;")
        else:
            self._current_update_info = None
            self.download_update_btn.setVisible(False)
            self.update_status.setText(
                "Aucun canal de mise à jour n'est configuré."
                if self.current_lang == "fr"
                else "لا يوجد مصدر تحديثات مضبوط.")
            self.update_status.setStyleSheet("color: #b45309; font-weight: bold;")

    def start_update_download(self):
        if not hasattr(self, "_current_update_info") or not self._current_update_info:
            return
        
        up_info = self._current_update_info
        is_fr = self.current_lang == "fr"

        self.check_update_btn.setEnabled(False)
        self.download_update_btn.setEnabled(False)
        self.update_progress.setValue(0)
        self.update_progress.setVisible(True)
        self.update_status.setText("Téléchargement de la mise à jour en cours..." if is_fr else "جاري تنزيل التحديث...")
        self.update_status.setStyleSheet("color: #2563eb;")

        from ui.pages.settings.workers import UpdateDownloadThread
        self.download_thread = UpdateDownloadThread(up_info)
        self.download_thread.progress.connect(self.update_progress.setValue)
        self.download_thread.finished.connect(self.on_update_downloaded)
        self.download_thread.start()

    def on_update_downloaded(self, success: bool, zip_or_err: str, err_type: str):
        is_fr = self.current_lang == "fr"
        self.check_update_btn.setEnabled(True)
        self.download_update_btn.setEnabled(True)
        self.update_progress.setVisible(False)

        if success:
            self.update_status.setText(
                "Téléchargement et vérification SHA-256 réussis ! Redémarrage de l'application..."
                if is_fr else
                "تم التنزيل والتحقق من التشفير بنجاح! جاري إعادة تشغيل المنظومة..."
            )
            self.update_status.setStyleSheet("color: #059669; font-weight: bold;")
            
            # Launch smooth restart helper bat
            from updater import apply_update_and_restart
            apply_update_and_restart(zip_or_err)
        else:
            if err_type == "sha256_mismatch":
                err_msg = ("Erreur de sécurité : L'empreinte SHA-256 ne correspond pas. L'archive a été supprimée par sécurité."
                           if is_fr else "خطأ أمني: بصمة التشفير غير مطابقة. تم إلغاء التحديث لحماية بياناتك.")
            elif err_type == "network_error":
                err_msg = ("Erreur réseau : La connexion a été interrompue pendant le téléchargement. Votre version actuelle est intacte. Vous pouvez réessayer."
                           if is_fr else "خطأ في الشبكة: انقطع الاتصال أثناء التنزيل. نسختك الحالية سليمة 100%. يمكنك إعادة المحاولة.")
            else:
                err_msg = (f"Échec de la mise à jour : {zip_or_err}" if is_fr else f"فشل التحديث: {zip_or_err}")

            self.update_status.setText(err_msg)
            self.update_status.setStyleSheet("color: #dc2626; font-weight: bold;")
            QMessageBox.critical(self, "Mise à jour" if is_fr else "التحديث", err_msg)


    # ── Bulk Archive Importer ──
    # ── Licence ─────────────────────────────────────────────────────────────
    def refresh_licence_status(self):
        """Shows what this installation is entitled to, and what to do about it."""
        import licensing
        is_fr = self.current_lang == "fr"
        st = licensing.status()
        kind = st.get("status")
        self.lic_machine_value.setText(st.get("machine") or
                                       licensing.machine_fingerprint())

        if kind == licensing.ACTIVE:
            office = st.get("office") or ""
            exp = st.get("expires") or ""
            txt = ("✓ Licence active" if is_fr else "✓ الرخصة مفعّلة")
            if office:
                txt += f" — {office}"
            txt += ((f"  (expire le {exp})" if is_fr else f"  (تنتهي في {exp})")
                    if exp else (" — perpétuelle" if is_fr else " — دائمة"))
            style = ("background-color:#ecfdf5; border:1px solid #10b981;")
            colour = "#065f46"
        elif getattr(licensing, "TRIAL", None) and kind == licensing.TRIAL:
            # Kept behind a getattr so this screen survives the trial period
            # being removed from licensing.py — which it did not, previously:
            # the reference to a deleted constant crashed Paramètres on
            # construction, taking the whole settings screen with it.
            d = st.get("days_left", 0)
            txt = (f"Période d'essai — {d} jour(s) restant(s)" if is_fr
                   else f"فترة تجريبية — بقي {d} يوم")
            style = "background-color:#fef3c7; border:1px solid #f59e0b;"
            colour = "#92400e"
        else:
            reasons = {
                licensing.WRONG_MACHINE: (
                    "Cette licence appartient à une AUTRE machine.",
                    "هذه الرخصة تخصّ جهازا آخر."),
                licensing.EXPIRED: ("La licence a expiré.", "انتهت صلاحية الرخصة."),
                licensing.INVALID: ("Licence invalide.", "رخصة غير صالحة."),
                licensing.UNLICENSED: ("Application non activée.",
                                       "التطبيق غير مفعّل."),
            }
            fr, ar = reasons.get(kind, ("Non activé.", "غير مفعّل."))
            txt = ("⚠ " + fr + " Vos dossiers restent consultables et "
                   "exportables ; la création de NOUVEAUX dossiers est bloquée."
                   if is_fr else
                   "⚠ " + ar + " ملفاتك تبقى قابلة للاطّلاع والتصدير ؛ "
                   "إنشاء ملفات جديدة متوقّف.")
            style = "background-color:#fef2f2; border:1px solid #dc2626;"
            colour = "#b91c1c"

        self.lic_status_lbl.setText(txt)
        self.lic_status_lbl.setStyleSheet(
            style + f" border-radius:6px; padding:9px; color:{colour};"
                    " font-weight:800; font-size:12px;")

    def copy_machine_id(self):
        QApplication.clipboard().setText(self.lic_machine_value.text())
        is_fr = self.current_lang == "fr"
        self.lic_status_lbl.setText(self.lic_status_lbl.text())
        QMessageBox.information(
            self, "Licence",
            "Identifiant machine copié. Envoyez-le à votre fournisseur."
            if is_fr else "تم نسخ معرّف الجهاز. أرسله إلى مزوّدك.")

    def activate_licence(self):
        import licensing
        is_fr = self.current_lang == "fr"
        text = self.lic_key_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(
                self, "Licence",
                "Collez la clé de licence reçue." if is_fr
                else "الصق مفتاح الرخصة الذي تلقّيته.")
            return
        ok, msg = licensing.activate(text)
        if ok:
            QMessageBox.information(
                self, "Licence",
                (f"Licence activée pour :\n{msg}" if is_fr
                 else f"تم تفعيل الرخصة لـ :\n{msg}"))
            self.lic_key_input.clear()
        else:
            QMessageBox.critical(
                self, "Licence",
                (f"La licence a été refusée.\n\n{msg}\n\n"
                 "Vérifiez que l'identifiant machine communiqué est bien celui "
                 "affiché ci-dessus."
                 if is_fr else
                 f"تم رفض الرخصة.\n\n{msg}\n\n"
                 "تأكّد أن معرّف الجهاز الذي أرسلته هو المعروض أعلاه."))
        self.refresh_licence_status()

    def _retitle_licence(self):
        is_fr = self.current_lang == "fr"
        self.lic_title.setText("10. Licence" if is_fr else "10. الرخصة")
        self.lic_machine_lbl.setText("Identifiant machine :" if is_fr
                                     else "معرّف الجهاز :")
        self.lic_copy_btn.setText("Copier" if is_fr else "نسخ")
        self.lic_key_lbl.setText("Clé de licence :" if is_fr else "مفتاح الرخصة :")
        self.lic_activate_btn.setText("Activer" if is_fr else "تفعيل")
        self.lic_help.setText(
            "Cette licence est liée à cette machine. Communiquez l'identifiant "
            "ci-dessus à votre fournisseur pour recevoir votre clé. Copier "
            "l'application sur un autre ordinateur ne fonctionnera pas."
            if is_fr else
            "هذه الرخصة مرتبطة بهذا الجهاز. أرسل المعرّف أعلاه إلى مزوّدك "
            "للحصول على مفتاحك. نسخ التطبيق إلى حاسوب آخر لن يعمل.")

    # ── Le réseau du cabinet ────────────────────────────────────────────────
    NET_MODES = ("standalone", "server", "workstation")

    def load_network_settings(self):
        """Fills the form from network.json and paints the right half of it."""
        cfg = config.load_network_config()
        self._retitle_network()
        idx = self.NET_MODES.index(cfg.get("mode", "standalone")) \
            if cfg.get("mode") in self.NET_MODES else 0
        self.net_mode_combo.blockSignals(True)
        self.net_mode_combo.setCurrentIndex(idx)
        self.net_mode_combo.blockSignals(False)
        self.net_host_input.setText(cfg.get("host") or "")
        self.net_port_input.setText(str(cfg.get("port") or config.DEFAULT_DB_PORT))
        self.net_token_input.setText(cfg.get("token") or "")
        self.on_network_mode_changed()

    def _selected_net_mode(self) -> str:
        i = self.net_mode_combo.currentIndex()
        return self.NET_MODES[i] if 0 <= i < len(self.NET_MODES) else "standalone"

    def on_network_mode_changed(self):
        mode = self._selected_net_mode()
        self.net_server_box.setVisible(mode == "server")
        self.net_client_box.setVisible(mode == "workstation")
        # Standalone needs no token at all; showing the field would only invite
        # someone to fill it in and expect something to happen.
        show_token = mode in ("server", "workstation")
        self.net_token_lbl.setVisible(show_token)
        self.net_token_input.setVisible(show_token)
        self.net_token_gen_btn.setVisible(mode == "server")
        self.net_test_btn.setVisible(mode == "workstation")
        self.refresh_network_status()

    def refresh_network_status(self):
        """What this machine is actually doing right now, not what is configured."""
        is_fr = self.current_lang == "fr"
        if self._selected_net_mode() != "server":
            return
        try:
            import db_service
            running = db_service.is_running()
            n = db_service.client_count()
        except Exception:
            running, n = False, 0
        if running:
            try:
                import db_service as _svc
                bound = _svc.bound_address()
                blocked = _svc.blocked_addresses()
                refused = _svc.refused_count()
            except Exception:
                bound, blocked, refused = "", [], 0
            extra_fr = f"  ·  écoute sur {bound}" if bound else ""
            extra_ar = f"  ·  يستمع على {bound}" if bound else ""
            if blocked:
                extra_fr += f"  ·  ⚠ {len(blocked)} machine(s) bloquée(s)"
                extra_ar += f"  ·  ⚠ {len(blocked)} جهاز محظور"
            elif refused:
                extra_fr += f"  ·  {refused} connexion(s) refusée(s)"
                extra_ar += f"  ·  {refused} اتصال مرفوض"
            self.net_server_status.setText(
                f"● Serveur actif — {n} poste(s) connecté(s){extra_fr}" if is_fr
                else f"● الخادم يعمل — {n} جهاز متّصل{extra_ar}")
            self.net_server_status.setStyleSheet(
                "background-color:#ecfdf5; border:1px solid #10b981; border-radius:6px;"
                " padding:8px; color:#065f46; font-weight:700; font-size:12px;")
        else:
            self.net_server_status.setText(
                "○ Serveur à l'arrêt — redémarrez l'application pour l'activer"
                if is_fr else "○ الخادم متوقّف — أعد تشغيل التطبيق لتفعيله")
            self.net_server_status.setStyleSheet(
                "background-color:#fef3c7; border:1px solid #f59e0b; border-radius:6px;"
                " padding:8px; color:#92400e; font-weight:700; font-size:12px;")

        addrs = config.local_ip_addresses()
        port = self.net_port_input.text().strip() or str(config.DEFAULT_DB_PORT)
        addr_txt = ", ".join(addrs) if addrs else ("adresse introuvable" if is_fr
                                                   else "تعذّر تحديد العنوان")
        self.net_server_help.setText(
            f"Sur l'autre poste, choisissez « Poste de travail » et saisissez :\n"
            f"    Adresse : {addr_txt}      Port : {port}\n"
            f"    Clé     : celle affichée ci-dessous\n\n"
            f"Cette machine doit rester allumée et l'application ouverte pendant "
            f"les heures de bureau — c'est elle qui détient la base."
            if is_fr else
            f"على الجهاز الآخر اختر «جهاز عمل» وأدخل :\n"
            f"    العنوان : {addr_txt}      المنفذ : {port}\n"
            f"    المفتاح : المعروض أسفله\n\n"
            f"يجب أن يبقى هذا الجهاز مشتغلا والتطبيق مفتوحا خلال أوقات العمل — "
            f"فهو الذي يحتوي قاعدة البيانات.")

    def generate_network_token(self):
        if self._refuse(Cap.MANAGE_USERS, "le réseau du cabinet", "شبكة المكتب"):
            return
        self.net_token_input.setText(config.generate_db_token())
        is_fr = self.current_lang == "fr"
        self.net_status.setText(
            "Nouvelle clé générée. Enregistrez, puis saisissez-la sur chaque poste."
            if is_fr else "تم توليد مفتاح جديد. احفظ ثم أدخله في كل جهاز.")
        self.net_status.setStyleSheet("color:#1e3a8a; font-weight:600;")

    def test_network_connection(self):
        """Tries the address now, so a typo is found here and not tomorrow."""
        is_fr = self.current_lang == "fr"
        host = self.net_host_input.text().strip()
        token = self.net_token_input.text().strip()
        try:
            port = int(self.net_port_input.text().strip() or config.DEFAULT_DB_PORT)
        except ValueError:
            self.net_status.setText("Port invalide." if is_fr else "المنفذ غير صالح.")
            self.net_status.setStyleSheet("color:#b91c1c; font-weight:700;")
            return
        if not host:
            self.net_status.setText(
                "Saisissez l'adresse du serveur du cabinet."
                if is_fr else "أدخل عنوان خادم المكتب.")
            self.net_status.setStyleSheet("color:#b91c1c; font-weight:700;")
            return
        self.net_status.setText("Test en cours…" if is_fr else "جاري الاختبار…")
        self.net_status.setStyleSheet("color:#475569;")
        QApplication.processEvents()
        from db_client import probe
        ok, msg = probe(host, port, token)
        self.net_status.setText(("✓ " if ok else "✗ ") + str(msg))
        self.net_status.setStyleSheet(
            "color:#065f46; font-weight:700;" if ok else "color:#b91c1c; font-weight:700;")

    def save_network_settings(self):
        is_fr = self.current_lang == "fr"
        mode = self._selected_net_mode()
        host = self.net_host_input.text().strip()
        token = self.net_token_input.text().strip()
        try:
            port = int(self.net_port_input.text().strip() or config.DEFAULT_DB_PORT)
        except ValueError:
            self.net_status.setText("Port invalide." if is_fr else "المنفذ غير صالح.")
            self.net_status.setStyleSheet("color:#b91c1c; font-weight:700;")
            return

        # Saving a half-configured workstation would leave the office unable to
        # start: it would look for a server it has no address for.
        if mode == "workstation":
            if not host or not token:
                self.net_status.setText(
                    "Adresse et clé sont requises pour un poste de travail."
                    if is_fr else "العنوان والمفتاح ضروريان لجهاز العمل.")
                self.net_status.setStyleSheet("color:#b91c1c; font-weight:700;")
                return
            from db_client import probe
            ok, msg = probe(host, port, token)
            if not ok:
                QMessageBox.warning(
                    self, "Réseau du cabinet" if is_fr else "شبكة المكتب",
                    (f"Le serveur n'a pas répondu :\n\n{msg}\n\n"
                     "Rien n'a été enregistré. Corrigez l'adresse ou la clé."
                     if is_fr else
                     f"لم يستجب الخادم :\n\n{msg}\n\n"
                     "لم يقع حفظ أي شيء. صحّح العنوان أو المفتاح."))
                self.net_status.setText("✗ " + str(msg))
                self.net_status.setStyleSheet("color:#b91c1c; font-weight:700;")
                return
        if mode == "server" and not token:
            self.net_status.setText(
                "Générez une clé avant d'activer le serveur."
                if is_fr else "ولّد مفتاحا قبل تفعيل الخادم.")
            self.net_status.setStyleSheet("color:#b91c1c; font-weight:700;")
            return

        if not config.save_network_config({"mode": mode, "host": host,
                                           "port": port, "token": token}):
            self.net_status.setText(
                "Échec de l'enregistrement." if is_fr else "فشل الحفظ.")
            self.net_status.setStyleSheet("color:#b91c1c; font-weight:700;")
            return

        QMessageBox.information(
            self, "Réseau du cabinet" if is_fr else "شبكة المكتب",
            ("Enregistré. Redémarrez l'application pour appliquer ce mode.\n\n"
             "Les connexions à la base sont établies au démarrage."
             if is_fr else
             "تم الحفظ. أعد تشغيل التطبيق لتطبيق هذا الوضع.\n\n"
             "يقع الاتصال بقاعدة البيانات عند بدء التشغيل."))
        self.net_status.setText(
            "✓ Enregistré — redémarrage requis" if is_fr
            else "✓ تم الحفظ — يلزم إعادة التشغيل")
        self.net_status.setStyleSheet("color:#065f46; font-weight:700;")
        self.refresh_network_status()

    def _retitle_network(self):
        is_fr = self.current_lang == "fr"
        self.net_title.setText("9. Réseau du Cabinet (plusieurs postes)" if is_fr
                               else "9. شبكة المكتب (عدّة أجهزة)")
        self.net_hint.setText(
            "Un cabinet avec deux postes doit partager UNE base de données. "
            "Désignez une machine comme serveur ; les autres s'y connectent. "
            "Sans cela, chaque poste garde ses propres dossiers et les deux ne se "
            "voient jamais."
            if is_fr else
            "المكتب الذي به جهازان يجب أن يتقاسم قاعدة بيانات واحدة. "
            "اختر جهازا كخادم وليتّصل به الباقي. "
            "بدون ذلك يحتفظ كل جهاز بملفاته ولا يرى أحدهما الآخر أبدا.")
        self.net_mode_lbl.setText("Rôle de cette machine :" if is_fr
                                  else "دور هذا الجهاز :")
        cur = self.net_mode_combo.currentIndex()
        self.net_mode_combo.blockSignals(True)
        self.net_mode_combo.clear()
        self.net_mode_combo.addItems(
            ["Autonome — un seul poste", "Serveur — détient la base du cabinet",
             "Poste de travail — se connecte au serveur"] if is_fr else
            ["مستقلّ — جهاز واحد", "خادم — يحتوي قاعدة المكتب",
             "جهاز عمل — يتّصل بالخادم"])
        self.net_mode_combo.setCurrentIndex(max(0, cur))
        self.net_mode_combo.blockSignals(False)
        self.net_host_lbl.setText("Adresse du serveur :" if is_fr else "عنوان الخادم :")
        self.net_port_lbl.setText("Port :" if is_fr else "المنفذ :")
        self.net_token_lbl.setText("Clé d'accès :" if is_fr else "مفتاح الدخول :")
        self.net_token_gen_btn.setText("Générer" if is_fr else "توليد")
        self.net_test_btn.setText("Tester la connexion" if is_fr else "اختبار الاتصال")
        self.net_save_btn.setText("Enregistrer" if is_fr else "حفظ")

    def open_migration_review(self):
        """Opens the assisted migration review screen.

        Scanning proposes; nothing reaches the client tables until the notary
        confirms each identity in that screen.
        """
        is_fr = self.current_lang == "fr"
        if not permissions.has(Cap.EDIT_CLIENTS):
            QMessageBox.warning(
                self, "Accès refusé" if is_fr else "الدخول مرفوض",
                "Vous n'êtes pas autorisé à importer des dossiers."
                if is_fr else "لا تملك صلاحية استيراد الملفات.")
            return
        try:
            from ui.dialogs.migration_review_dialog import MigrationReviewDialog
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur" if is_fr else "خطأ",
                f"L'outil de migration n'a pas pu être ouvert.\n\n"
                f"{type(e).__name__}: {e}")
            return
        dlg = MigrationReviewDialog(self, lang=self.current_lang)
        dlg.exec()

    def browse_import_directory(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Choisir le dossier d'archive / اختر مجلد الأرشيف")
        if folder_path:
            self.import_path_input.setText(folder_path)

    def run_bulk_import(self):
        path_str = self.import_path_input.text().strip()
        if not path_str:
            self.import_status.setText("Veuillez entrer ou sélectionner un chemin valide." if self.current_lang == "fr" else "يرجى إدخال أو تحديد مسار مجلد الأرشيف القديم أولاً.")
            self.import_status.setStyleSheet("color: #dc2626; font-weight: bold;")
            return

        if not os.path.exists(path_str) or not os.path.isdir(path_str):
            self.import_status.setText("Dossier introuvable." if self.current_lang == "fr" else "المجلد المحدد غير موجود أو غير صالح.")
            self.import_status.setStyleSheet("color: #dc2626; font-weight: bold;")
            return

        self.import_status.setText("Analyse et importation des archives..." if self.current_lang == "fr" else "جاري فحص مجلدات الأرشيف القديم واستخراج العقود والزبائن وبصمات الوجوه للذكاء الاصطناعي...")
        self.import_status.setStyleSheet("color: #2563eb;")
        self.run_import_btn.setEnabled(False)
        self.import_progress.setRange(0, 0)
        self.import_progress.setVisible(True)

        self.import_thread = ArchiveImportThread(path_str)
        self.import_thread.finished.connect(self.on_bulk_import_finished)
        self.import_thread.start()

    def on_bulk_import_finished(self, res):
        """
        Reports what the import actually did.

        The importer now distinguishes four outcomes, and the difference matters
        to the notary: 'success' means every folder went in, 'partial' means some
        folders could not be read and are listed, 'empty' means the chosen folder
        held no clients at all — which the old build reported as success — and
        'error' means nothing was imported.
        """
        self.run_import_btn.setEnabled(True)
        self.import_progress.setVisible(False)
        is_fr = self.current_lang == "fr"
        status = res.get("status")

        created = res.get("clients_created", 0)
        updated = res.get("clients_updated", 0)
        docs = res.get("documents_imported", 0)
        faces = res.get("faces_extracted", 0)
        scanned = res.get("folders_scanned", 0)
        failed = res.get("failed", []) or []
        skipped = res.get("skipped", []) or []

        if status in ("success", "partial"):
            if is_fr:
                msg = (f"Importation terminée.\n"
                       f"- Dossiers parcourus : {scanned}\n"
                       f"- Clients créés : {created}\n"
                       f"- Fiches complétées : {updated}\n"
                       f"- Documents copiés : {docs}\n"
                       f"- Visages enregistrés : {faces}\n"
                       f"- Dossiers ignorés (classement, années) : {len(skipped)}")
            else:
                msg = (f"تم الاستيراد.\n"
                       f"- المجلدات التي تم فحصها : {scanned}\n"
                       f"- حرفاء تم إنشاؤهم : {created}\n"
                       f"- بطاقات تم تكميلها : {updated}\n"
                       f"- وثائق تم نسخها : {docs}\n"
                       f"- بصمات وجوه : {faces}\n"
                       f"- مجلدات تم تجاوزها (تصنيف، سنوات) : {len(skipped)}")
            if status == "partial":
                msg += (f"\n\n{len(failed)} dossier(s) n'ont pas pu être importés — "
                        f"voir le journal ci-dessous."
                        if is_fr else
                        f"\n\n{len(failed)} مجلد(ات) تعذّر استيرادها — انظر السجل أسفله.")
            self.import_status.setText(msg)
            self.import_status.setStyleSheet(
                "color: %s; font-weight: bold;"
                % ("#b45309" if status == "partial" else "#059669"))

        elif status == "empty":
            self.import_status.setText(
                "Aucun client trouvé dans ce dossier. Rien n'a été importé.\n"
                "Vérifiez que les sous-dossiers portent le nom du client "
                "et/ou son numéro de CIN."
                if is_fr else
                "لم يتم العثور على أي حريف في هذا المجلد. لم يتم استيراد أي شيء.\n"
                "تأكّد أن المجلدات الفرعية تحمل اسم الحريف و/أو رقم بطاقة تعريفه.")
            self.import_status.setStyleSheet("color: #b45309; font-weight: bold;")

        elif status == "cancelled":
            self.import_status.setText("Importation annulée." if is_fr
                                       else "تم إلغاء الاستيراد.")
            self.import_status.setStyleSheet("color: #64748b; font-weight: bold;")

        else:
            error_msg = "\n".join(res.get("logs", []) or
                                  ["Erreur d'importation." if is_fr else "خطأ في الاستيراد."])
            self.import_status.setText(
                (f"Erreur pendant l'importation :\n{error_msg}" if is_fr
                 else f"حدث خطأ أثناء عملية الاستيراد:\n{error_msg}"))
            self.import_status.setStyleSheet("color: #dc2626; font-weight: bold;")

        lines = list(res.get("logs", []) or [])
        if failed:
            lines.append("")
            lines.append("--- NON IMPORTES / لم يتم استيرادها ---")
            for f in failed[:100]:
                lines.append(f"  {f.get('folder', '')} {f.get('file', '')}: "
                             f"{f.get('error', '')}")
        if skipped:
            lines.append("")
            lines.append("--- IGNORES / تم تجاوزها ---")
            for sk in skipped[:100]:
                lines.append(f"  {sk.get('folder', '')}: {sk.get('reason', '')}")
        self.log_viewer.setPlainText(
            self.log_viewer.toPlainText()
            + "\n\n=== ARCHIVE IMPORT ===\n" + "\n".join(lines))
