"""
document_gallery_dialog.py — Interactive Document & Image Gallery Viewer with Next/Previous Carousel & Word/PDF Launcher.
"""

import os
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QFrame, QFileDialog, QScrollArea, QWidget, QApplication
)
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QPixmap, QImage, QKeySequence, QShortcut, QCursor

class DocumentGalleryDialog(QDialog):
    """
    Full-featured Document Viewer & Image Gallery.
    Allows scrolling left/right between image attachments, downloading copies,
    and opening Word / PDF files directly in native software (Word, PDF reader, etc.).
    """

    doc_deleted = Signal(str)

    def __init__(self, documents: list, start_index: int = 0, parent=None, lang: str = "ar"):
        super().__init__(parent)
        self.documents = documents  # List of dicts: [{"name":..., "path":..., "size_kb":...}]
        self.current_index = max(0, min(start_index, len(documents) - 1)) if documents else 0
        self.lang = lang

        # Filter image documents for carousel navigation
        IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
        self.images_list = [d for d in self.documents if Path(d.get("path", "")).suffix.lower() in IMAGE_EXTS]
        
        # Determine image index relative to images_list
        current_doc = self.documents[self.current_index] if self.documents else None
        if current_doc and Path(current_doc.get("path", "")).suffix.lower() in IMAGE_EXTS:
            try:
                self.img_index = self.images_list.index(current_doc)
            except ValueError:
                self.img_index = 0
        else:
            self.img_index = 0

        self.init_ui()

        # Keyboard shortcuts: Left/Right arrows for carousel
        self.shortcut_left = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.shortcut_left.activated.connect(self.prev_image)
        self.shortcut_right = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.shortcut_right.activated.connect(self.next_image)

    def init_ui(self):
        is_fr = self.lang == "fr"
        self.setWindowTitle("معاينة الوثائق والمستندات" if not is_fr else "Visualiseur de Documents")
        self.resize(850, 680)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if not is_fr else Qt.LayoutDirection.LeftToRight)

        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                font-family: 'Segoe UI', 'Tajawal', sans-serif;
            }
            QFrame.TopBar {
                background-color: #1e293b;
                border-bottom: 1px solid #334155;
                padding: 6px;
            }
            QLabel.HeaderTitle {
                color: #f8fafc;
                font-weight: bold;
                font-size: 14px;
            }
            QLabel.Counter {
                color: #38bdf8;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton.NavButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton.NavButton:hover {
                background-color: #334155;
                border-color: #38bdf8;
            }
            QPushButton.ActionButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton.ActionButton:hover {
                background-color: #0369a1;
            }
            QPushButton.DeleteButton {
                background-color: #dc2626;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton.DeleteButton:hover {
                background-color: #b91c1c;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top Action Toolbar ──
        top_bar = QFrame(self)
        top_bar.setProperty("class", "TopBar")
        top_lay = QHBoxLayout(top_bar)
        top_lay.setContentsMargins(12, 8, 12, 8)

        self.title_lbl = QLabel(top_bar)
        self.title_lbl.setProperty("class", "HeaderTitle")
        top_lay.addWidget(self.title_lbl)

        self.counter_lbl = QLabel(top_bar)
        self.counter_lbl.setProperty("class", "Counter")
        top_lay.addWidget(self.counter_lbl)

        top_lay.addStretch()

        # Action buttons
        self.btn_download = QPushButton("📥 تحميل / Télécharger" if is_fr else "📥 تحميل النسخة", top_bar)
        self.btn_download.setProperty("class", "ActionButton")
        self.btn_download.clicked.connect(self.download_current_doc)
        top_lay.addWidget(self.btn_download)

        self.btn_open_external = QPushButton("📂 فتح في Word/النظام" if not is_fr else "📂 Ouvrir dans Word/Système", top_bar)
        self.btn_open_external.setProperty("class", "ActionButton")
        self.btn_open_external.clicked.connect(self.open_current_external)
        top_lay.addWidget(self.btn_open_external)

        self.btn_delete = QPushButton("🗑️ حذف" if not is_fr else "🗑️ Supprimer", top_bar)
        self.btn_delete.setProperty("class", "DeleteButton")
        self.btn_delete.clicked.connect(self.delete_current_doc)
        top_lay.addWidget(self.btn_delete)

        layout.addWidget(top_bar)

        # ── Main Viewport with Left/Right Navigation ──
        view_container = QWidget(self)
        v_main_lay = QHBoxLayout(view_container)
        v_main_lay.setContentsMargins(15, 15, 15, 15)

        # Prev Button (◄)
        self.btn_prev = QPushButton("◀" if not is_fr else "◄ Précédent", view_container)
        self.btn_prev.setProperty("class", "NavButton")
        self.btn_prev.setFixedSize(44, 100)
        self.btn_prev.setToolTip("الصورة السابقة (مفتاح سهم اليسار)" if not is_fr else "Image précédente (Flèche Gauche)")
        self.btn_prev.clicked.connect(self.prev_image)
        v_main_lay.addWidget(self.btn_prev)

        # Center Scrollable Viewport
        self.scroll_area = QScrollArea(view_container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: #020617; }")

        self.img_lbl = QLabel(self.scroll_area)
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.img_lbl)

        v_main_lay.addWidget(self.scroll_area, stretch=1)

        # Next Button (►)
        self.btn_next = QPushButton("▶" if not is_fr else "Suivant ►", view_container)
        self.btn_next.setProperty("class", "NavButton")
        self.btn_next.setFixedSize(44, 100)
        self.btn_next.setToolTip("الصورة التالية (مفتاح سهم اليمين)" if not is_fr else "Image suivante (Flèche Droite)")
        self.btn_next.clicked.connect(self.next_image)
        v_main_lay.addWidget(self.btn_next)

        layout.addWidget(view_container, stretch=1)

        # Display current document
        self.update_display()

    def update_display(self):
        if not self.documents or self.current_index >= len(self.documents):
            self.img_lbl.setText("لا توجد وثائق للمعاينة")
            self.title_lbl.setText("")
            self.counter_lbl.setText("")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            return

        doc = self.documents[self.current_index]
        dpath = doc.get("path", "")
        dname = doc.get("name", "")
        size_kb = doc.get("size_kb", 0)
        ext = Path(dpath).suffix.lower()

        IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
        is_image = ext in IMAGE_EXTS

        # Update Toolbar info
        clean_name = dname.split("_", 2)[-1] if "Dossier_" in dname else dname
        self.title_lbl.setText(f"📄 {clean_name} ({size_kb} KB)")

        if is_image:
            if doc in self.images_list:
                self.img_index = self.images_list.index(doc)
            self.counter_lbl.setText(f" [{self.img_index + 1} / {len(self.images_list)}]")
            self.btn_prev.setEnabled(len(self.images_list) > 1)
            self.btn_next.setEnabled(len(self.images_list) > 1)

            if os.path.exists(dpath):
                pm = QPixmap(dpath)
                if not pm.isNull():
                    scaled_pm = pm.scaled(
                        720, 520, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                    self.img_lbl.setPixmap(scaled_pm)
                else:
                    self.img_lbl.setText("تعذر تحميل الصورة")
            else:
                self.img_lbl.setText("الملف غير موجود على القرص")

        elif ext in [".docx", ".doc"]:
            self.counter_lbl.setText(" [مستند Word]")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.img_lbl.setText(f"📘 مستند Microsoft Word:\n\n{clean_name}\n\nاضغط 'فتح في Word/النظام' لقراءة وتعديل المستند")
            self.img_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")

        elif ext == ".pdf":
            self.counter_lbl.setText(" [ملف PDF]")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.img_lbl.setText(f"📕 وثيقة PDF:\n\n{clean_name}\n\nاضغط 'فتح في Word/النظام' لفتح الوثيقة بقارئ PDF")
            self.img_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #f87171;")

        else:
            self.counter_lbl.setText(" [ملف مرفق]")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.img_lbl.setText(f"📁 ملف مرفق:\n\n{clean_name}\n\nاضغط 'فتح في Word/النظام' لفتحه بالتطبيق المناسب")
            self.img_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #cbd5e1;")

    def prev_image(self):
        if not self.images_list:
            return
        self.img_index = (self.img_index - 1) % len(self.images_list)
        target_doc = self.images_list[self.img_index]
        self.current_index = self.documents.index(target_doc)
        self.update_display()

    def next_image(self):
        if not self.images_list:
            return
        self.img_index = (self.img_index + 1) % len(self.images_list)
        target_doc = self.images_list[self.img_index]
        self.current_index = self.documents.index(target_doc)
        self.update_display()

    def download_current_doc(self):
        if not self.documents or self.current_index >= len(self.documents):
            return
        doc = self.documents[self.current_index]
        dpath = doc.get("path", "")
        dname = doc.get("name", "")
        if not os.path.exists(dpath):
            QMessageBox.warning(self, "خطأ", "الملف الأصلي غير موجود.")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "تحميل وثيقة / Enregistrer sous", dname, "Tous les fichiers (*.*)"
        )
        if save_path:
            try:
                shutil.copy(dpath, save_path)
                QMessageBox.information(self, "نجاح", "تم حفظ نسخة من الوثيقة بنجاح!")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"تعذر حفظ الوثيقة: {e}")

    def open_current_external(self):
        if not self.documents or self.current_index >= len(self.documents):
            return
        doc = self.documents[self.current_index]
        dpath = doc.get("path", "")
        if not os.path.exists(dpath):
            QMessageBox.warning(self, "خطأ", "الملف الأصلي غير موجود.")
            return
        try:
            os.startfile(dpath)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"تعذر فتح الملف عبر النظام: {e}")

    def delete_current_doc(self):
        if not self.documents or self.current_index >= len(self.documents):
            return
        doc = self.documents[self.current_index]
        dname = doc.get("name", "")
        is_fr = self.lang == "fr"

        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"هل أنت متأكد من حذف هذه الوثيقة نهائياً؟\n{dname}" if not is_fr else f"Supprimer ce document ?\n{dname}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.doc_deleted.emit(dname)
            del self.documents[self.current_index]
            IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
            self.images_list = [d for d in self.documents if Path(d.get("path", "")).suffix.lower() in IMAGE_EXTS]
            if self.current_index >= len(self.documents):
                self.current_index = max(0, len(self.documents) - 1)
            if not self.documents:
                self.accept()
            else:
                self.update_display()
