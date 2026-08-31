"""
Camera status strip and detection toast — visible on every page.

All camera feedback used to live inside the Accueil page (the connect button, the
viewport message, the face grid), so once the receptionist navigated away there was no
way to tell whether the camera was still working. These two widgets belong to the main
window instead of to a page.
"""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ui.services.camera_service import CameraState


_DOT = {
    CameraState.CONNECTED:    "#16a34a",
    CameraState.CONNECTING:   "#d97706",
    CameraState.DISCONNECTED: "#dc2626",
    CameraState.FAILED:       "#dc2626",
    CameraState.OFF:          "#94a3b8",
}

_TEXT_AR = {
    CameraState.CONNECTED:    "الكاميرا تعمل",
    CameraState.CONNECTING:   "جاري ربط الكاميرا",
    CameraState.DISCONNECTED: "انقطع الاتصال بالكاميرا",
    CameraState.FAILED:       "تعذّر تشغيل الكاميرا",
    CameraState.OFF:          "الكاميرا متوقفة",
}

_TEXT_FR = {
    CameraState.CONNECTED:    "Caméra active",
    CameraState.CONNECTING:   "Connexion caméra...",
    CameraState.DISCONNECTED: "Caméra déconnectée",
    CameraState.FAILED:       "Caméra indisponible",
    CameraState.OFF:          "Caméra arrêtée",
}


class CameraStatusBar(QFrame):
    """A dot and a short label, pinned to the bottom of the sidebar."""

    def __init__(self, parent=None, lang="ar"):
        super().__init__(parent)
        self.lang = lang
        self._state = CameraState.OFF
        self._detail = ""
        self.setObjectName("CameraStatusBar")
        self.setStyleSheet(
            "QFrame#CameraStatusBar { background: transparent; border: none;"
            " border-top: 1px solid rgba(255,255,255,0.12); }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 10)
        lay.setSpacing(8)

        self.dot = QLabel(self)
        self.dot.setFixedSize(10, 10)
        self.text = QLabel(self)
        self.text.setStyleSheet("color: #cbd5e1; font-size: 11px; border: none;")
        self.text.setWordWrap(True)

        lay.addWidget(self.dot)
        lay.addWidget(self.text, 1)
        self.set_status(CameraState.OFF, "")

    def set_status(self, state, detail=""):
        self._state, self._detail = state, detail
        colour = _DOT.get(state, "#94a3b8")
        self.dot.setStyleSheet(
            f"background-color: {colour}; border-radius: 5px; border: none;")
        table = _TEXT_FR if self.lang == "fr" else _TEXT_AR
        self.text.setText(table.get(state, state))
        self.setToolTip(detail or "")

    def set_language(self, lang):
        self.lang = lang
        self.set_status(self._state, self._detail)


class DetectionToast(QFrame):
    """
    A small dismissible card that appears over whatever page is open when a client is
    recognised and their visit is recorded. Clicking it opens that client's file.
    """

    clicked = Signal(str)   # client_id

    VISIBLE_MS = 5000

    def __init__(self, parent=None, lang="ar"):
        super().__init__(parent)
        self.lang = lang
        self._client_id = None
        self.setObjectName("DetectionToast")
        self.setStyleSheet("""
            QFrame#DetectionToast {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-left: 4px solid #16a34a;
                border-radius: 8px;
            }
            QLabel { color: #e2e8f0; border: none; background: transparent; }
        """)
        self.setFixedWidth(300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(3)

        self.title = QLabel(self)
        self.title.setStyleSheet("color:#4ade80; font-size:11px; font-weight:600; border:none;")
        self.name = QLabel(self)
        self.name.setStyleSheet("color:#f1f5f9; font-size:14px; font-weight:600; border:none;")
        self.name.setWordWrap(True)
        self.hint = QLabel(self)
        self.hint.setStyleSheet("color:#94a3b8; font-size:10px; border:none;")

        lay.addWidget(self.title)
        lay.addWidget(self.name)
        lay.addWidget(self.hint)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_detection(self, client_id, display_name):
        is_fr = self.lang == "fr"
        self._client_id = client_id
        self.title.setText("PRÉSENCE ENREGISTRÉE" if is_fr else "تم تسجيل الحضور")
        self.name.setText(display_name or (f"Client {client_id}" if is_fr else f"حريف {client_id}"))
        self.hint.setText("Cliquez pour ouvrir la fiche" if is_fr
                          else "اضغط لفتح بطاقة الحريف")
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(self.VISIBLE_MS)

    def _reposition(self):
        p = self.parentWidget()
        if not p:
            return
        margin = 24
        x = margin if self.lang != "fr" else p.width() - self.width() - margin
        # Arabic layout is right-to-left, so the toast sits on the opposite side.
        if self.lang != "fr":
            x = p.width() - self.width() - margin
        self.move(max(0, x), max(0, p.height() - self.height() - margin))

    def mousePressEvent(self, event):
        if self._client_id:
            self.clicked.emit(self._client_id)
        self.hide()
        super().mousePressEvent(event)

    def set_language(self, lang):
        self.lang = lang
