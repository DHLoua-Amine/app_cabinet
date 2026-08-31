"""
collapsible_box.py — a section that shows only its title until it is clicked.

This lived inside scanner_page.py, where the Scanner's three sections used it.
The Paramètres page needs the same behaviour — eight settings groups all open at
once is a wall of controls to scroll past when you came to change one thing — so
it moves here rather than being copied.

Kept deliberately plain: a header row that toggles, and a content frame that is
shown or hidden. No animation, because a settings panel that slides is a settings
panel you wait for.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel


class CollapsibleSection(QFrame):
    """A titled section, collapsed by default, that opens when its header is clicked."""

    toggled = Signal(bool)

    def __init__(self, title, expanded=False, parent=None):
        super().__init__(parent)
        self.setObjectName("CollapsibleSection")
        self.setStyleSheet("""
            QFrame#CollapsibleSection {
                background-color: #ffffff;
                border-radius: 12px;
                border: 1.5px solid #cbd5e1;
            }
        """)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # ── header ───────────────────────────────────────────────────────────
        self.header = QFrame(self)
        self.header.setObjectName("CollapsibleHeader")
        self._style_header(expanded)
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(14, 11, 14, 11)
        self.header_layout.setSpacing(10)

        self.arrow = QLabel("▼" if expanded else "▶", self.header)
        self.arrow.setStyleSheet(
            "font-weight: bold; color: #1e3a8a; border: none; background: transparent;")

        self.title_lbl = QLabel(title, self.header)
        self.title_lbl.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #0f172a; "
            "border: none; background: transparent;")

        self.header_layout.addWidget(self.arrow)
        self.header_layout.addWidget(self.title_lbl)
        self.header_layout.addStretch()

        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.mousePressEvent = self.toggle_expansion
        self.layout.addWidget(self.header)

        # ── content ──────────────────────────────────────────────────────────
        self.content = QFrame(self)
        self.content.setObjectName("CollapsibleContent")
        self.content.setStyleSheet("""
            QFrame#CollapsibleContent {
                border: none;
                background-color: #ffffff;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }
        """)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 12, 12, 12)
        self.content_layout.setSpacing(10)
        self.layout.addWidget(self.content)

        self.is_expanded = bool(expanded)
        self.content.setVisible(self.is_expanded)

    def _style_header(self, expanded: bool):
        # A closed section reads as a title bar; an open one loses its bottom
        # rounding so it joins visually to the content below it.
        self.header.setStyleSheet("""
            QFrame#CollapsibleHeader {
                background-color: %s;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom-left-radius: %s;
                border-bottom-right-radius: %s;
                border-bottom: %s;
            }
        """ % ("#e8eef6" if expanded else "#f1f5f9",
               "0px" if expanded else "10px",
               "0px" if expanded else "10px",
               "1.5px solid #cbd5e1" if expanded else "none"))

    def toggle_expansion(self, event=None):
        self.set_expanded(not self.is_expanded)

    def set_expanded(self, expanded: bool):
        """Opens or closes the section programmatically."""
        self.is_expanded = bool(expanded)
        self.content.setVisible(self.is_expanded)
        self.arrow.setText("▼" if self.is_expanded else "▶")
        self._style_header(self.is_expanded)
        self.toggled.emit(self.is_expanded)

    def set_title(self, title: str):
        self.title_lbl.setText(title)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)
