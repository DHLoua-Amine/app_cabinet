"""
edit_entry_dialog.py — correcting a row that is already recorded.

Every table in the app was write-once from the notary's point of view. A name
typed with one letter wrong, an amount entered as 1500 instead of 150, a
justificatif attached to the wrong charge: the only remedy was to delete the row
and type it again, which loses the original date and leaves nothing to show a
figure was ever different.

This is the one dialog used for all of those corrections. It is deliberately
plain: the fields the row actually has, the receipt it is carrying, and nothing
that could be mistaken for creating a new entry.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLabel, QLineEdit, QDoubleSpinBox, QPushButton,
                               QFileDialog, QFrame, QMessageBox)


class EditEntryDialog(QDialog):
    """
    A small form built from a field spec.

    fields: a list of (key, label_fr, label_ar, kind, value) where kind is
            "text" or "amount".
    receipt: the current justificatif path, or None to hide the receipt row
             entirely (for records that never carry one).

    values() returns {key: value} plus "_receipt" when a receipt row was shown:
    the unchanged path, a new path, or "" if the notary detached it.
    """

    def __init__(self, parent, title_fr, title_ar, fields, lang="ar", receipt=None):
        super().__init__(parent)
        self.lang = lang
        self.is_fr = lang == "fr"
        self._fields = fields
        self._widgets = {}
        self._receipt = receipt
        self._receipt_shown = receipt is not None

        self.setWindowTitle(title_fr if self.is_fr else title_ar)
        self.setMinimumWidth(520)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight if self.is_fr
                                else Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        head = QLabel(title_fr if self.is_fr else title_ar, self)
        head.setStyleSheet("font-size:16px; font-weight:800; color:#1e3a8a;")
        root.addWidget(head)

        note = QLabel(
            "La correction est enregistrée dans le journal des modifications."
            if self.is_fr else
            "يُسجَّل هذا التصحيح في سجل التعديلات.", self)
        note.setWordWrap(True)
        note.setStyleSheet("color:#64748b; font-size:12px;")
        root.addWidget(note)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight
                               if not self.is_fr else Qt.AlignmentFlag.AlignLeft)
        for key, lab_fr, lab_ar, kind, value in fields:
            if kind == "amount":
                w = QDoubleSpinBox(self)
                w.setRange(0.0, 99_999_999.0)
                w.setDecimals(3)
                w.setSingleStep(10.0)
                w.setValue(float(value or 0.0))
                w.setMinimumHeight(34)
            else:
                w = QLineEdit(str(value or ""), self)
                w.setMinimumHeight(34)
            self._widgets[key] = w
            form.addRow(QLabel((lab_fr if self.is_fr else lab_ar) + " :", self), w)
        root.addLayout(form)

        if self._receipt_shown:
            line = QFrame(self)
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet("color:#e2e8f0;")
            root.addWidget(line)

            rec_row = QHBoxLayout()
            rec_row.setSpacing(8)
            rec_row.addWidget(QLabel("Justificatif :" if self.is_fr else "الوصل :", self))
            self.rec_label = QLabel(self)
            self.rec_label.setStyleSheet("color:#334155; font-size:12px;")
            self._refresh_receipt_label()
            rec_row.addWidget(self.rec_label, stretch=1)

            btn_pick = QPushButton("Changer…" if self.is_fr else "تغيير…", self)
            btn_pick.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_pick.clicked.connect(self._pick_receipt)
            rec_row.addWidget(btn_pick)

            btn_clear = QPushButton("Retirer" if self.is_fr else "إزالة", self)
            btn_clear.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_clear.clicked.connect(self._clear_receipt)
            rec_row.addWidget(btn_clear)
            root.addLayout(rec_row)

        root.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Annuler" if self.is_fr else "إلغاء", self)
        cancel.setMinimumHeight(36)
        cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        save = QPushButton("Enregistrer la correction" if self.is_fr
                           else "حفظ التصحيح", self)
        save.setMinimumHeight(36)
        save.setDefault(True)
        save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save.setStyleSheet(
            "QPushButton { background-color:#2563eb; color:white; font-weight:700;"
            " border:none; border-radius:6px; padding:6px 18px; }"
            "QPushButton:hover { background-color:#1d4ed8; }")
        save.clicked.connect(self._accept_if_valid)
        buttons.addWidget(save)
        root.addLayout(buttons)

    # -- receipt ------------------------------------------------------------
    def _refresh_receipt_label(self):
        path = self._receipt or ""
        if not path:
            self.rec_label.setText("Aucun" if self.is_fr else "لا يوجد")
        elif not os.path.exists(path):
            self.rec_label.setText(("introuvable : " if self.is_fr else "غير موجود : ")
                                   + os.path.basename(path))
        else:
            self.rec_label.setText(os.path.basename(path))

    def _pick_receipt(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un justificatif" if self.is_fr else "اختيار وصل", "",
            "Images / PDF (*.png *.jpg *.jpeg *.bmp *.pdf);;All files (*.*)")
        if path:
            self._receipt = path
            self._refresh_receipt_label()

    def _clear_receipt(self):
        self._receipt = ""
        self._refresh_receipt_label()

    # -- validation ---------------------------------------------------------
    def _accept_if_valid(self):
        """
        A correction that empties a required field is a worse record than the
        typo it was meant to fix, so it is refused here rather than written.
        """
        for key, lab_fr, lab_ar, kind, _value in self._fields:
            w = self._widgets[key]
            if kind == "amount":
                continue
            if not w.text().strip():
                QMessageBox.warning(
                    self, "Champ requis" if self.is_fr else "حقل ضروري",
                    (f"« {lab_fr} » ne peut pas être vide." if self.is_fr
                     else f"«{lab_ar}» لا يمكن أن يكون فارغا."))
                w.setFocus()
                return
        self.accept()

    def values(self) -> dict:
        out = {}
        for key, _lf, _la, kind, _v in self._fields:
            w = self._widgets[key]
            out[key] = w.value() if kind == "amount" else w.text().strip()
        if self._receipt_shown:
            out["_receipt"] = self._receipt
        return out
