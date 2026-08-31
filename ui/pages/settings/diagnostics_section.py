"""
ui/pages/settings/diagnostics_section.py — Modular UI section for Diagnostic Logs & Maintenance.
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt


class DiagnosticsSection(QFrame):
    """Encapsulates Section 6: System errors diagnostic log viewer, export, and clear log actions."""

    def __init__(self, current_lang="ar", parent=None):
        super().__init__(parent)
        self.current_lang = current_lang
        self.setProperty("class", "Card")
        self.init_ui()

    def init_ui(self):
        diag_lay = QVBoxLayout(self)

        self.diag_title = QLabel("6. سجل الصيانة والأخطاء / Diagnostic Logs", self)
        self.diag_title.setProperty("class", "CardTitle")
        diag_lay.addWidget(self.diag_title)

        self.diag_hint_lbl = QLabel(
            "إذا حدث أي إشكال مستقبلي، يمكنك معاينة وتصدير سجل الصيانة والأخطاء لإرساله لخدمة الصيانة فورياً:", self
        )
        diag_lay.addWidget(self.diag_hint_lbl)

        self.log_viewer = QTextEdit(self)
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setMaximumHeight(150)
        self.log_viewer.setStyleSheet("""
            QTextEdit {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #334155;
                font-family: 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        diag_lay.addWidget(self.log_viewer)

        self.export_diag_btn = QPushButton("تنزيل تقرير الصيانة / Exporter le Diagnostic (.log)", self)
        self.export_diag_btn.setObjectName("PrimaryButton")

        self.clear_log_btn = QPushButton("🗑 Vider le journal / مسح السجل", self)
        self.clear_log_btn.setObjectName("DangerButton")
        self.clear_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #dc2626; }
            QPushButton:pressed { background-color: #b91c1c; }
        """)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.export_diag_btn)
        btn_row.addWidget(self.clear_log_btn)
        diag_lay.addLayout(btn_row)

        self.diag_status = QLabel("", self)
        diag_lay.addWidget(self.diag_status)

        self.clear_log_btn.clicked.connect(self.clear_log)
        self.load_logs()
        self.update_translations(self.current_lang)

    def load_logs(self):
        try:
            from system_guardian import ERROR_LOG_PATH
            if ERROR_LOG_PATH.exists() and ERROR_LOG_PATH.stat().st_size > 0:
                log_content = ERROR_LOG_PATH.read_text(encoding="utf-8")
                self.log_viewer.setPlainText(log_content[-3000:])
            else:
                self.log_viewer.setPlainText(
                    "Aucun log d'erreur enregistré. Le système est propre."
                    if self.current_lang == "fr"
                    else "سجل النظام نظيف 100%! لم يتم تسجيل أي أخطاء."
                )
        except Exception:
            self.log_viewer.setPlainText("Journal propre." if self.current_lang == "fr" else "السجل نظيف.")

    def clear_log(self):
        from system_guardian import ERROR_LOG_PATH
        is_fr = self.current_lang == "fr"
        title = "Vider le journal de diagnostic" if is_fr else "مسح سجل الأخطاء"
        msg = (
            "Voulez-vous effacer tout le journal d'erreurs ?\nCette action est irréversible."
            if is_fr
            else "هل تريد مسح سجل الأخطاء بالكامل؟\nلا يمكن التراجع عن هذا الإجراء."
        )
        reply = QMessageBox.question(
            self, title, msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if ERROR_LOG_PATH.exists():
                ERROR_LOG_PATH.write_text("", encoding="utf-8")
            ok_msg = "Journal vidé avec succès. Le système est propre." if is_fr else "تم مسح السجل بنجاح. المنظومة نظيفة الآن."
            self.log_viewer.setPlainText(ok_msg)
            self.diag_status.setText(ok_msg)
        except Exception as e:
            err_msg = f"Erreur lors de la suppression : {e}" if is_fr else f"خطأ أثناء المسح: {e}"
            QMessageBox.warning(self, "Erreur" if is_fr else "خطأ", err_msg)

    def update_translations(self, lang: str):
        self.current_lang = lang
        is_fr = lang == "fr"
        if is_fr:
            self.diag_title.setText("6. Journal de Diagnostic & Maintenance Future")
            self.diag_hint_lbl.setText("En cas d'incident, vous pouvez consulter le journal et exporter un rapport technique :")
            self.export_diag_btn.setText("Exporter le rapport de Diagnostic (.log)")
            self.clear_log_btn.setText("🗑 Vider le journal")
        else:
            self.diag_title.setText("6. سجل تشخيص الصيانة والأخطاء المستقبلية")
            self.diag_hint_lbl.setText("إذا حدث أي إشكال مستقبلي، يمكنك تنزيل تقرير التشخيص بنقرة واحدة وإرساله للصيانة:")
            self.export_diag_btn.setText("تنزيل تقرير تشخيص النظام (system_errors.log)")
            self.clear_log_btn.setText("🗑 مسح السجل")
