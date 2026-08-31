"""
calendar_utils.py — Makes QDateEdit popup calendars render correctly.

A QCalendarWidget draws its month grid with an internal QTableView, so the global
stylesheet rule

    QTableView::item { padding: 8px 10px; border-bottom: 1px solid #f1f5f9; }

was applied to all 42 day cells. Seven columns each gained ~20px of horizontal
padding, the grid stopped fitting inside the popup, and the day numbers ended up
overlapping each other. assets/styles.qss now resets those metrics for
QCalendarWidget specifically; this module applies the matching widget-level settings.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor, QTextCharFormat, QBrush
from PySide6.QtWidgets import QCalendarWidget, QTableView, QHeaderView

# Applied directly to the calendar widget, not through the application stylesheet.
# The popup is a separate top-level window parented to a bare QWidget, and with
# app.setStyle("Fusion") its ground is painted from the *application* palette — which
# follows the system dark theme. Neither an app-level QSS rule nor setPalette() on the
# calendar reaches it, so the popup came out black with unreadable numbers. A
# widget-level stylesheet applies to this widget and its children regardless.
_CALENDAR_QSS = """
QCalendarWidget,
QCalendarWidget QWidget {
    background-color: #ffffff;
    color: #0f172a;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background-color: #1e3a8a;
    min-height: 36px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QCalendarWidget QToolButton {
    color: #ffffff;
    background-color: transparent;
    border: none;
    margin: 3px;
    padding: 4px 12px;
    font-size: 13px;
    font-weight: 600;
}
QCalendarWidget QToolButton:hover {
    background-color: #2547a5;
    border-radius: 4px;
}
QCalendarWidget QToolButton::menu-indicator { image: none; }
QCalendarWidget QSpinBox {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 1px 4px;
}
QCalendarWidget QMenu {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
}
QCalendarWidget QAbstractItemView {
    background-color: #ffffff;
    color: #0f172a;
    border: none;
    outline: none;
    gridline-color: transparent;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    font-size: 13px;
}
/* Reset the cell padding inherited from the global QTableView::item rule; seven
   padded columns no longer fit the popup and the numbers overlapped. */
QCalendarWidget QAbstractItemView::item {
    padding: 0px;
    margin: 0px;
    border: none;
}
QCalendarWidget QAbstractItemView::item:selected {
    background-color: #2563eb;
    color: #ffffff;
    border-radius: 4px;
}
QCalendarWidget QAbstractItemView:disabled { color: #cbd5e1; }
"""

# App palette (matches assets/styles.qss)
_INK = QColor("#0f172a")
_PAPER = QColor("#ffffff")
_MUTED = QColor("#64748b")
_ACCENT = QColor("#2563eb")
_WEEKEND = QColor("#dc2626")
_DISABLED = QColor("#cbd5e1")


def configure_calendar(date_edit, min_w: int = 340, min_h: int = 300):
    """
    Makes a QDateEdit's popup calendar readable and correctly laid out.

    Two separate problems are handled here:

    1. Colour. main.py calls app.setStyle("Fusion"), and Fusion paints the popup from
       the widget *palette*, not from the stylesheet — so on a machine with a dark
       system theme the calendar came out black with unreadable numbers no matter what
       the QSS said. An explicit light palette is set below so it always matches the
       rest of the app.

    2. Layout. A QCalendarWidget draws its month grid with an internal QTableView, so
       the global "QTableView::item { padding: 8px 10px }" rule was applied to all 42
       day cells; seven padded columns no longer fitted and the numbers overlapped.

    Safe to call more than once.
    """
    try:
        cal = date_edit.calendarWidget()
    except Exception:
        cal = None
    if cal is None:
        return

    cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    cal.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
    cal.setGridVisible(False)
    cal.setMinimumSize(min_w, min_h)
    cal.setFirstDayOfWeek(Qt.DayOfWeek.Monday)

    # The decisive part: a stylesheet on this widget, which the popup cannot bypass.
    cal.setStyleSheet(_CALENDAR_QSS)
    cal.setAutoFillBackground(True)

    # The popup that hosts the calendar is a plain QWidget parented to the QDateEdit;
    # paint it white too so no dark ground shows around the calendar's edges.
    holder = cal.parent()
    if holder is not None and holder is not date_edit:
        holder.setAutoFillBackground(True)
        hp = holder.palette()
        hp.setColor(QPalette.ColorRole.Window, _PAPER)
        hp.setColor(QPalette.ColorRole.Base, _PAPER)
        holder.setPalette(hp)
        holder.setStyleSheet("background-color: #ffffff;")

    # ── force a light palette regardless of Fusion / system dark mode ──
    pal = cal.palette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        pal.setColor(group, QPalette.ColorRole.Window, _PAPER)
        pal.setColor(group, QPalette.ColorRole.Base, _PAPER)
        pal.setColor(group, QPalette.ColorRole.AlternateBase, _PAPER)
        pal.setColor(group, QPalette.ColorRole.Button, _PAPER)
        pal.setColor(group, QPalette.ColorRole.Text, _INK)
        pal.setColor(group, QPalette.ColorRole.WindowText, _INK)
        pal.setColor(group, QPalette.ColorRole.ButtonText, _INK)
        pal.setColor(group, QPalette.ColorRole.Highlight, _ACCENT)
        pal.setColor(group, QPalette.ColorRole.HighlightedText, _PAPER)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, _DISABLED)
    cal.setPalette(pal)

    # Day-of-week header colours: weekends muted red, weekdays ink.
    weekday_fmt = QTextCharFormat()
    weekday_fmt.setForeground(QBrush(_INK))
    weekend_fmt = QTextCharFormat()
    weekend_fmt.setForeground(QBrush(_WEEKEND))
    for day in (Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday,
                Qt.DayOfWeek.Thursday, Qt.DayOfWeek.Friday):
        cal.setWeekdayTextFormat(day, weekday_fmt)
    for day in (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday):
        cal.setWeekdayTextFormat(day, weekend_fmt)

    # Days belonging to the previous/next month, greyed rather than invisible.
    outside = QTextCharFormat()
    outside.setForeground(QBrush(_MUTED))
    cal.setHeaderTextFormat(outside)

    view = cal.findChild(QTableView)
    if view is not None:
        view.setShowGrid(False)
        # Stretch both ways so the 7x6 grid always fills the popup exactly.
        view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        view.setWordWrap(False)
        vpal = view.palette()
        vpal.setColor(QPalette.ColorRole.Base, _PAPER)
        vpal.setColor(QPalette.ColorRole.Text, _INK)
        vpal.setColor(QPalette.ColorRole.Highlight, _ACCENT)
        vpal.setColor(QPalette.ColorRole.HighlightedText, _PAPER)
        view.setPalette(vpal)
