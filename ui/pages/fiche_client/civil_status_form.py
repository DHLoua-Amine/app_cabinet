"""
ui/pages/fiche_client/civil_status_form.py — Modular UI Component for Client Civil Status & Identity.
"""

import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QComboBox, QPushButton
)
from PySide6.QtCore import Qt, Signal


class CivilStatusForm(QWidget):
    """Encapsulates Client Civil Status, Identity Fields (Name, CIN, Phone), DOB, and Validation."""

    form_changed = Signal()

    WILAYAS_LIST = [
        "", "أريانة", "باجة", "بن عروس", "بنزرت", "قابس", "قفصة", "جندوبة", "القيروان",
        "القصرين", "قبلي", "الكاف", "المهدية", "منوبة", "مدنين", "المنستير", "نابل",
        "صفاقس", "سيدي بوزيد", "سليانة", "سوسة", "تطاوين", "توزر", "تونس", "زغوان"
    ]

    MARITAL_OPTIONS = [
        "أعزب / Célibataire",
        "متزوج(ة) / Marié(e)",
        "مطلق(ة) / Divorcé(e)",
        "أرمل(ة) / Veuf(ve)"
    ]

    REGIME_OPTIONS = [
        "اشتراك في الأملاك / Communauté de biens",
        "فصل الأملاك / Séparation de biens"
    ]

    def __init__(self, lang="ar", parent=None):
        super().__init__(parent)
        self.lang = lang
        self.init_ui()

    def init_ui(self):
        form_grid = QGridLayout(self)
        form_grid.setSpacing(10)

        # Input fields
        self.prenom_input = QLineEdit(self)
        self.prenom_err = QLabel("", self)
        self.prenom_err.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        self.prenom_err.setVisible(False)

        self.nom_input = QLineEdit(self)
        self.nom_err = QLabel("", self)
        self.nom_err.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        self.nom_err.setVisible(False)

        self.cin_input = QLineEdit(self)
        self.cin_err = QLabel("", self)
        self.cin_err.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        self.cin_err.setVisible(False)

        self.phone_input = QLineEdit(self)
        self.phone_err = QLabel("", self)
        self.phone_err.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        self.phone_err.setVisible(False)

        self.maiden_input = QLineEdit(self)
        self.profession_input = QLineEdit(self)
        self.cin_date_place_input = QLineEdit(self)
        self.tf_input = QLineEdit(self)
        self.birth_place_input = QLineEdit(self)
        self.address_input = QLineEdit(self)

        self.wilaya_combo = QComboBox(self)
        self.wilaya_combo.addItems(self.WILAYAS_LIST)

        # Date of birth selectors
        dob_layout = QHBoxLayout()
        self.dob_day = QComboBox(self)
        self.dob_month = QComboBox(self)
        self.dob_year = QComboBox(self)
        self.dob_day.addItems([f"{d:02d}" for d in range(1, 32)])
        self.dob_month.addItems([f"{m:02d}" for m in range(1, 13)])
        self.dob_year.addItems([str(y) for y in range(2026, 1920, -1)])
        dob_layout.addWidget(self.dob_day)
        dob_layout.addWidget(self.dob_month)
        dob_layout.addWidget(self.dob_year)

        self.marital_combo = QComboBox(self)
        self.marital_combo.addItems(self.MARITAL_OPTIONS)

        self.regime_combo = QComboBox(self)
        self.regime_combo.addItems(self.REGIME_OPTIONS)

        # Connect change signals
        for widget in [self.prenom_input, self.nom_input, self.cin_input, self.phone_input,
                       self.maiden_input, self.profession_input, self.address_input]:
            widget.textChanged.connect(self.form_changed.emit)

    def validate(self) -> tuple[bool, list[str]]:
        """Validates civil status inputs and returns (is_valid, list_of_error_messages)."""
        errors = []
        is_valid = True

        prenom = self.prenom_input.text().strip()
        nom = self.nom_input.text().strip()
        cin = self.cin_input.text().strip()
        phone = self.phone_input.text().strip()

        # Name validation
        if not nom and not prenom:
            self.prenom_err.setText("الاسم واللقب إجباريان")
            self.prenom_err.setVisible(True)
            self.nom_err.setText("الاسم واللقب إجباريان")
            self.nom_err.setVisible(True)
            errors.append("Le prénom et le nom sont obligatoires.")
            is_valid = False
        else:
            self.prenom_err.setVisible(False)
            self.nom_err.setVisible(False)

        # CIN validation (8 digits if specified)
        if cin and not re.match(r"^\d{8}$", cin):
            self.cin_err.setText("رقم بطاقة التعريف يجب أن يتكون من 8 أرقام")
            self.cin_err.setVisible(True)
            errors.append("Le numéro de CIN doit comporter exactement 8 chiffres.")
            is_valid = False
        else:
            self.cin_err.setVisible(False)

        # Phone validation (8 digits if specified)
        if phone and not re.match(r"^\d{8}$", phone):
            self.phone_err.setText("رقم الهاتف يجب أن يتكون من 8 أرقام")
            self.phone_err.setVisible(True)
            errors.append("Le numéro de téléphone doit comporter exactement 8 chiffres.")
            is_valid = False
        else:
            self.phone_err.setVisible(False)

        return is_valid, errors

    def get_data(self) -> dict:
        """Collects form inputs as a clean dictionary."""
        return {
            "prenom": self.prenom_input.text().strip(),
            "nom": self.nom_input.text().strip(),
            "cin_number": self.cin_input.text().strip(),
            "phone": self.phone_input.text().strip(),
            "maiden_name": self.maiden_input.text().strip(),
            "profession": self.profession_input.text().strip(),
            "cin_date_place": self.cin_date_place_input.text().strip(),
            "titre_foncier": self.tf_input.text().strip(),
            "birth_place": self.birth_place_input.text().strip(),
            "address": self.address_input.text().strip(),
            "wilaya": self.wilaya_combo.currentText(),
            "marital_status": self.marital_combo.currentText(),
            "matrimonial_regime": self.regime_combo.currentText(),
            "birth_date": f"{self.dob_year.currentText()}-{self.dob_month.currentText()}-{self.dob_day.currentText()}"
        }

    def set_data(self, data: dict):
        """Populates form inputs from database record."""
        self.prenom_input.setText(data.get("prenom", ""))
        self.nom_input.setText(data.get("nom", ""))
        self.cin_input.setText(data.get("cin_number", ""))
        self.phone_input.setText(data.get("phone", ""))
        self.maiden_input.setText(data.get("maiden_name", ""))
        self.profession_input.setText(data.get("profession", ""))
        self.cin_date_place_input.setText(data.get("cin_date_place", ""))
        self.tf_input.setText(data.get("titre_foncier", ""))
        self.birth_place_input.setText(data.get("birth_place", ""))
        self.address_input.setText(data.get("address", ""))
        
        idx = self.wilaya_combo.findText(data.get("wilaya", ""))
        if idx >= 0:
            self.wilaya_combo.setCurrentIndex(idx)
