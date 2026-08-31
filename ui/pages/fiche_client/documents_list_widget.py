"""
ui/pages/fiche_client/documents_list_widget.py — Modular UI Component for Client Attached Documents.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from pathlib import Path
import shutil


class DocumentsListWidget(QWidget):
    """Encapsulates the Attached Documents tab for a client."""

    document_added = Signal(str)

    def __init__(self, client_id: str = "", lang="ar", parent=None):
        super().__init__(parent)
        self.client_id = client_id
        self.lang = lang
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Action bar
        top_bar = QHBoxLayout()
        self.add_doc_btn = QPushButton(
            "Joindre un document" if self.lang == "fr" else "إضافة وثيقة للملف", self
        )
        self.add_doc_btn.setProperty("class", "PrimaryButton")
        self.add_doc_btn.clicked.connect(self.add_document)
        top_bar.addWidget(self.add_doc_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # Documents list
        self.docs_list = QListWidget(self)
        self.docs_list.setStyleSheet("""
            QListWidget {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f1f5f9;
            }
        """)
        layout.addWidget(self.docs_list)

        self.empty_lbl = QLabel(
            "Aucun document joint pour le moment." if self.lang == "fr" else "لا توجد وثائق مرفقة لهذا الحريف حالياً.", self
        )
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setStyleSheet("color: #94a3b8; font-size: 13px;")
        layout.addWidget(self.empty_lbl)

    def set_client_id(self, client_id: str):
        self.client_id = client_id
        self.load_documents()

    def load_documents(self):
        self.docs_list.clear()
        if not self.client_id:
            self.empty_lbl.setVisible(True)
            return

        try:
            from config import DOCUMENTS_DIR
            client_docs_dir = DOCUMENTS_DIR / self.client_id
            if client_docs_dir.exists():
                files = list(client_docs_dir.glob("*.*"))
                if files:
                    self.empty_lbl.setVisible(False)
                    for f in files:
                        item = QListWidgetItem(f.name)
                        item.setData(Qt.ItemDataRole.UserRole, str(f))
                        self.docs_list.addItem(item)
                else:
                    self.empty_lbl.setVisible(True)
            else:
                self.empty_lbl.setVisible(True)
        except Exception:
            self.empty_lbl.setVisible(True)

    def add_document(self):
        if not self.client_id:
            msg = "Veuillez sauvegarder le client avant d'ajouter des documents." if self.lang == "fr" else "الرجاء حفظ الحريف أولاً قبل إضافة الوثائق."
            QMessageBox.warning(self, "Attention", msg)
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un document" if self.lang == "fr" else "اختر وثيقة",
            "",
            "Documents (*.pdf *.docx *.png *.jpg *.jpeg)"
        )
        if file_path:
            try:
                from config import DOCUMENTS_DIR
                client_docs_dir = DOCUMENTS_DIR / self.client_id
                client_docs_dir.mkdir(parents=True, exist_ok=True)
                dest = client_docs_dir / Path(file_path).name
                shutil.copy2(file_path, dest)
                self.load_documents()
                self.document_added.emit(str(dest))
            except Exception as e:
                QMessageBox.critical(self, "Erreur", str(e))
