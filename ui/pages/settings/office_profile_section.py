"""
ui/pages/settings/office_profile_section.py — Modular UI section for Notary Office Profile.
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt
import office_profile


class OfficeProfileSection(QFrame):
    """Encapsulates Section 0: Notary Office Profile & Identity Configuration."""

    def __init__(self, current_lang="ar", parent=None):
        super().__init__(parent)
        self.current_lang = current_lang
        self.setProperty("class", "Card")
        self.office_inputs = {}
        self.office_labels = {}
        self.init_ui()

    def init_ui(self):
        office_lay = QVBoxLayout(self)

        self.office_title_lbl = QLabel("0. بيانات المكتب وعدل الإشهاد", self)
        self.office_title_lbl.setProperty("class", "CardTitle")
        office_lay.addWidget(self.office_title_lbl)

        self.office_hint = QLabel("", self)
        self.office_hint.setWordWrap(True)
        self.office_hint.setStyleSheet("color:#475569; font-size:12px;")
        office_lay.addWidget(self.office_hint)

        office_grid = QGridLayout()
        office_grid.setSpacing(10)

        for row, (key, _default, label_ar, label_fr) in enumerate(office_profile.FIELDS):
            lbl = QLabel("", self)
            edit = QLineEdit(self)
            edit.setPlaceholderText(label_ar)
            self.office_labels[key] = (lbl, label_ar, label_fr)
            self.office_inputs[key] = edit
            office_grid.addWidget(lbl, row, 0)
            office_grid.addWidget(edit, row, 1)

        office_lay.addLayout(office_grid)

        self.save_office_btn = QPushButton("حفظ بيانات المكتب", self)
        self.save_office_btn.setObjectName("PrimaryButton")
        self.save_office_btn.clicked.connect(self.save_profile)
        office_lay.addWidget(self.save_office_btn)

        self.load_profile()
        self.update_translations(self.current_lang)

    def load_profile(self):
        p = office_profile.load()
        for key, edit in self.office_inputs.items():
            edit.setText(p.get(key, ""))

    def save_profile(self):
        data = {k: v.text().strip() for k, v in self.office_inputs.items()}
        try:
            office_profile.save(data)
            win = self.window()
            if win:
                if hasattr(win, "update_sidebar_brand"):
                    win.update_sidebar_brand()
                if hasattr(win, "_pages") and "scanner" in win._pages:
                    scanner = win._pages["scanner"]
                    if scanner and hasattr(scanner, "update_office_header"):
                        scanner.update_office_header()
                        scanner.refresh_contract_preview_text()
            is_fr = self.current_lang == "fr"
            msg = "Données du cabinet enregistrées." if is_fr else "تم حفظ بيانات المكتب بنجاح."
            QMessageBox.information(self, "Cabinet" if is_fr else "المكتب", msg)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    def update_translations(self, lang: str):
        self.current_lang = lang
        is_fr = lang == "fr"
        if is_fr:
            self.office_title_lbl.setText("0. Identité de l'étude et du notaire")
            self.office_hint.setText("Ces informations apparaissent sur tous les actes, reçus et impressions officiels générés par l'application :")
            self.save_office_btn.setText("Enregistrer les coordonnées du cabinet")
        else:
            self.office_title_lbl.setText("0. بيانات المكتب وعدل الإشهاد")
            self.office_hint.setText("تظهر هذه البيانات على جميع العقود والمحاضر والوصولات الصادرة عن المكتب :")
            self.save_office_btn.setText("حفظ بيانات المكتب")

        for key, (lbl, label_ar, label_fr) in self.office_labels.items():
            lbl.setText(label_fr if is_fr else label_ar)
            self.office_inputs[key].setPlaceholderText(label_fr if is_fr else label_ar)
