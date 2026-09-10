"""
document_scan_dialog.py — Direct 1-Click Scanner & Camera Document Capture Dialog.
Allows secretary to place a paper or CIN on the scanner/camera, click "Capture",
and automatically attach the document or populate CIN fields in the client's dossier.
"""

import io
import time
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QFrame, QFileDialog, QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage

try:
    import reception
    import cin_extractor
    from config import DOCUMENTS_DIR, PROFILES_DIR
except ImportError:
    import core.reception as reception
    import core.cin_extractor as cin_extractor
    from core.config import DOCUMENTS_DIR, PROFILES_DIR

class DocumentScanDialog(QDialog):
    """
    Direct hardware scan dialog for secretary workflow:
    1-Click scan of physical papers & CIN cards directly into client dossier.
    """

    scanned_successfully = Signal(dict)

    def __init__(self, parent=None, client_id=None, mode="document", camera_service=None, lang="ar"):
        super().__init__(parent)
        self.client_id = client_id
        self.mode = mode  # "document" or "cin"
        self.camera_service = camera_service
        self.lang = lang
        self.captured_qimg = None
        self.last_frame = None

        self.init_ui()

        self.fallback_cap = None
        self.fallback_timer = None

        # Connect camera service if available
        if self.camera_service and hasattr(self.camera_service, "frame_ready"):
            self.camera_service.frame_ready.connect(self._on_frame_received)
            self.camera_service.set_preview_enabled(True)
        else:
            self._init_fallback_camera()

    def init_ui(self):
        is_fr = self.lang == "fr"
        title_str = ("📷 المسح الضوئي المباشر للوثائق" if not is_fr else "📷 Scan Direct de Document")
        if self.mode == "cin":
            title_str = ("📷 مسح وقراءة بطاقة التعريف الوطنية" if not is_fr else "📷 Scan && Extraction CIN")

        self.setWindowTitle(title_str)
        self.resize(700, 560)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if not is_fr else Qt.LayoutDirection.LeftToRight)

        self.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
                font-family: 'Segoe UI', 'Tajawal', sans-serif;
            }
            QFrame.Card {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }
            QLabel {
                color: #0f172a;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QPushButton.Primary {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton.Primary:hover {
                background-color: #0369a1;
            }
            QPushButton.Success {
                background-color: #059669;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton.Success:hover {
                background-color: #047857;
            }
            QPushButton.Secondary {
                background-color: #475569;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton.Secondary:hover {
                background-color: #334155;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Title Label
        self.header_lbl = QLabel(title_str, self)
        self.header_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #1e293b;")
        layout.addWidget(self.header_lbl)

        # Document Title Input (only if mode == "document")
        if self.mode == "document":
            name_lay = QHBoxLayout()
            lbl_name = QLabel("عنوان أو اسم الوثيقة :" if not is_fr else "Titre du document :", self)
            lbl_name.setStyleSheet("font-weight: bold;")
            self.doc_name_input = QLineEdit(self)
            self.doc_name_input.setPlaceholderText("مثال: حجة وفاة / عقد ملكية / وصل خلاص" if not is_fr else "Ex: Titre de propriété / Facture")
            name_lay.addWidget(lbl_name)
            name_lay.addWidget(self.doc_name_input, 1)
            layout.addLayout(name_lay)

        # Viewport Card Frame
        viewport_card = QFrame(self)
        viewport_card.setProperty("class", "Card")
        v_lay = QVBoxLayout(viewport_card)
        v_lay.setContentsMargins(10, 10, 10, 10)

        self.viewport = QLabel(viewport_card)
        self.viewport.setFixedSize(640, 360)
        self.viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewport.setStyleSheet("""
            QLabel {
                background-color: #0f172a;
                border: 2px dashed #475569;
                border-radius: 6px;
                color: #94a3b8;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        self.viewport.setText("ضع الوثيقة تحت الماسح / الكاميرا واضغط التقاط\nPlacer le document sous le scanner et cliquer sur Capturer")
        v_lay.addWidget(self.viewport, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(viewport_card)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_capture = QPushButton("📷 التقاط بالماسح الضوئي" if not is_fr else "📷 Capturer via Scanner", self)
        self.btn_capture.setProperty("class", "Primary")
        self.btn_capture.clicked.connect(self.on_capture_clicked)
        btn_row.addWidget(self.btn_capture)

        self.btn_browse = QPushButton("📁 اختيار ملف من الجهاز" if not is_fr else "📁 Choisir un fichier", self)
        self.btn_browse.setProperty("class", "Secondary")
        self.btn_browse.clicked.connect(self.on_browse_clicked)
        btn_row.addWidget(self.btn_browse)

        btn_row.addStretch()

        self.btn_save = QPushButton("حفظ الوثيقة في ملف الحريف" if not is_fr else "Enregistrer dans le dossier", self)
        self.btn_save.setProperty("class", "Success")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self.on_save_clicked)
        btn_row.addWidget(self.btn_save)

        layout.addLayout(btn_row)

    def _on_frame_received(self, qimg, faces):
        if self.captured_qimg is None and qimg and not qimg.isNull():
            self.last_frame = qimg.copy()
            self.viewport.setPixmap(
                QPixmap.fromImage(qimg).scaled(
                    640, 360, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )

    def on_capture_clicked(self):
        is_fr = self.lang == "fr"
        if self.last_frame and not self.last_frame.isNull():
            self.captured_qimg = self.last_frame.copy()
            self.viewport.setPixmap(
                QPixmap.fromImage(self.captured_qimg).scaled(
                    640, 360, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
            self.btn_save.setEnabled(True)
            QMessageBox.information(
                self, "تم الالتقاط",
                "تم التقاط الوثيقة بنجاح! اضغط 'حفظ الوثيقة' للإدراج في الملف." if not is_fr
                else "Document capturé avec succès ! Cliquez sur Enregistrer."
            )
        else:
            QMessageBox.warning(
                self, "تنبيه",
                "الكاميرا لم ترسل أي صورة بعد. يمكنك استخدام خيار 'اختيار ملف من الجهاز'." if not is_fr
                else "Aucune image reçue de la caméra. Utilisez l'option Choisir un fichier."
            )

    def on_browse_clicked(self):
        is_fr = self.lang == "fr"
        fp, _ = QFileDialog.getOpenFileName(
            self, "اختر وثيقة الحريف", "", "Fichiers (*.jpg *.jpeg *.png *.pdf *.webp)"
        )
        if fp:
            try:
                img = QImage(fp)
                if not img.isNull():
                    self.captured_qimg = img
                    self.viewport.setPixmap(
                        QPixmap.fromImage(img).scaled(
                            640, 360, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                        )
                    )
                else:
                    self.viewport.setText(f"تم اختيار الملف:\n{Path(fp).name}")
                    self.captured_qimg = fp
                self.btn_save.setEnabled(True)
            except Exception as e:
                QMessageBox.warning(self, "خطأ", f"تعذر قراءة الملف: {e}")

    def on_save_clicked(self):
        is_fr = self.lang == "fr"
        if not self.captured_qimg and not hasattr(self, 'captured_qimg'):
            return

        if self.mode == "document":
            doc_name = (self.doc_name_input.text().strip() if hasattr(self, 'doc_name_input') else "").strip()
            if not doc_name:
                doc_name = f"وثيقة_{int(time.time())}"

            if isinstance(self.captured_qimg, QImage):
                buffer = io.BytesIO()
                self.captured_qimg.save(buffer, "JPEG", 90)
                img_bytes = buffer.getvalue()
                filename = f"{doc_name}.jpg"
            elif isinstance(self.captured_qimg, str) and Path(self.captured_qimg).exists():
                p = Path(self.captured_qimg)
                img_bytes = p.read_bytes()
                filename = f"{doc_name}{p.suffix}"
            else:
                return

            saved = reception.save_client_document(self.client_id, img_bytes, filename)
            if saved:
                QMessageBox.information(
                    self, "نجاح الإدراج",
                    f"تم إضافة الوثيقة '{doc_name}' إلى ملف الحريف بنجاح!" if not is_fr
                    else f"Document '{doc_name}' ajouté avec succès au dossier client !"
                )
                self.scanned_successfully.emit({"success": True, "path": saved, "name": filename, "file_path": saved})
                self.accept()
            else:
                QMessageBox.critical(self, "خطأ", "تعذر حفظ الوثيقة في الأرشيف.")

        elif self.mode == "cin":
            if isinstance(self.captured_qimg, QImage):
                buffer = io.BytesIO()
                self.captured_qimg.save(buffer, "JPEG", 90)
                img_bytes = buffer.getvalue()
            elif isinstance(self.captured_qimg, str) and Path(self.captured_qimg).exists():
                img_bytes = Path(self.captured_qimg).read_bytes()
            else:
                return

            try:
                ocr_res = cin_extractor.extract_cin_dual_faces(img_bytes)
                if ocr_res and ocr_res.get("success"):
                    extracted = ocr_res.get("extracted", {})
                    self.scanned_successfully.emit({"success": True, "extracted": extracted, "bytes": img_bytes, "file_path": getattr(self, "captured_filepath", None)})
                    QMessageBox.information(
                        self, "نجاح بطاقة التعريف",
                        f"تم قراءة بطاقة التعريف واستخراج المعطيات:\nالاسم: {extracted.get('full_name', '')}\nرقم ب.ت: {extracted.get('cin_number', '')}"
                        if not is_fr else f"CIN lue avec succès!\nNom: {extracted.get('full_name', '')}"
                    )
                    self.accept()
                else:
                    QMessageBox.warning(self, "تنبيه", "تعذر قراءة بيانات بطاقة التعريف تلقائياً، يمكنك إدخالها يدويًا.")
                    self.accept()
            except Exception as e:
                QMessageBox.warning(self, "خطأ", f"حدث خطأ أثناء قراءة بطاقة التعريف: {e}")

    def _init_fallback_camera(self):
        """Starts fallback camera capture loop if no global CameraService is passed."""
        try:
            import cv2
            from PySide6.QtCore import QTimer
            try:
                import camera as camera_core
            except ImportError:
                import core.camera as camera_core
            
            src = camera_core.get_saved_camera_source()
            if camera_core.check_ip_reachable(src, timeout=1.0):
                self.fallback_cap = cv2.VideoCapture(src)
                if self.fallback_cap and self.fallback_cap.isOpened():
                    self.fallback_timer = QTimer(self)
                    self.fallback_timer.timeout.connect(self._read_fallback_frame)
                    self.fallback_timer.start(33)
        except Exception as e:
            print("Fallback camera initialization info:", e)

    def _read_fallback_frame(self):
        if self.fallback_cap and self.fallback_cap.isOpened() and self.captured_qimg is None:
            import cv2
            ret, frame = self.fallback_cap.read()
            if ret and frame is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
                self.last_frame = qimg
                self.viewport.setPixmap(
                    QPixmap.fromImage(qimg).scaled(
                        640, 360, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                )

    def _stop_fallback_camera(self):
        if self.fallback_timer:
            try:
                self.fallback_timer.stop()
            except Exception:
                pass
            self.fallback_timer = None
        if self.fallback_cap:
            try:
                self.fallback_cap.release()
            except Exception:
                pass
            self.fallback_cap = None

    def closeEvent(self, event):
        self._stop_fallback_camera()
        if self.camera_service and hasattr(self.camera_service, "frame_ready"):
            try:
                self.camera_service.frame_ready.disconnect(self._on_frame_received)
            except Exception:
                pass
        super().closeEvent(event)
