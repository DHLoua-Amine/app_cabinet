from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage

class FacePreviewDialog(QDialog):
    """
    Dialog modal d'agrandissement d'image de visage en haute résolution
    sans quitter l'application ni naviguer vers une autre page.
    """
    def __init__(self, qimg: QImage, name: str, status: str, client_id: str, lang: str = "ar", parent=None):
        super().__init__(parent)
        self.qimg = qimg
        self.name = name
        self.status = status
        self.client_id = client_id
        self.lang = lang
        
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.init_ui()

    def init_ui(self):
        is_fr = self.lang == "fr"
        is_known = self.status == "known"

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Card container
        card = QFrame(self)
        card.setObjectName("PreviewCard")
        border_color = "#10b981" if is_known else "#ef4444"
        card.setStyleSheet(f"""
            QFrame#PreviewCard {{
                background-color: #ffffff;
                border: 3px solid {border_color};
                border-radius: 16px;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(15)

        # Header Bar (Title + Close X Button)
        header_bar = QHBoxLayout()
        title_lbl = QLabel("معاينة الوجه المكبرة" if not is_fr else "Aperçu agrandi du visage", card)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #0f172a;")
        
        close_x_btn = QPushButton("✕", card)
        close_x_btn.setFixedSize(30, 30)
        close_x_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                border: none;
                border-radius: 15px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ef4444;
                color: #ffffff;
            }
        """)
        close_x_btn.clicked.connect(self.accept)

        header_bar.addWidget(title_lbl)
        header_bar.addStretch()
        header_bar.addWidget(close_x_btn)
        card_layout.addLayout(header_bar)

        # Large Image Display (Up to 450x450)
        img_lbl = QLabel(card)
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_lbl.setStyleSheet("background-color: #0f172a; border-radius: 12px;")

        if self.qimg and not self.qimg.isNull():
            pixmap = QPixmap.fromImage(self.qimg).scaled(
                450, 450,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            img_lbl.setPixmap(pixmap)
        else:
            img_lbl.setFixedSize(400, 400)
            img_lbl.setText("لا توجد صورة مكبرة" if not is_fr else "Aucune image agrandie")
            img_lbl.setStyleSheet("color: #94a3b8; font-size: 16px; font-weight: bold;")

        card_layout.addWidget(img_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        # Name and Status Label
        info_bar = QHBoxLayout()
        
        name_lbl = QLabel(self.name, card)
        name_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #0f172a;")
        
        status_lbl = QLabel("🟢 حريف مسجل" if is_known else "🔴 زائر جديد", card)
        status_color = "#047857" if is_known else "#b91c1c"
        status_bg = "#ecfdf5" if is_known else "#fef2f2"
        status_lbl.setStyleSheet(f"""
            padding: 6px 12px;
            background-color: {status_bg};
            color: {status_color};
            font-weight: bold;
            font-size: 13px;
            border-radius: 20px;
        """)

        info_bar.addWidget(name_lbl)
        info_bar.addStretch()
        info_bar.addWidget(status_lbl)
        card_layout.addLayout(info_bar)

        # Large Close Action Button
        close_btn = QPushButton("إغلاق المعاينة" if not is_fr else "Fermer l'aperçu", card)
        close_btn.setMinimumHeight(42)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f172a;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e293b;
            }
        """)
        close_btn.clicked.connect(self.accept)
        card_layout.addWidget(close_btn)

        main_layout.addWidget(card)
        self.setFixedSize(540, 620)
