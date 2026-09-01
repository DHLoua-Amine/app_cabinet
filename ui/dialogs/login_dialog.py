"""
login_dialog.py — the gate that actually stands in front of the application.

Before this existed the app opened straight onto the Accueil page with every
other page one click away, `auth_logged_in` permanently False and nothing reading
it. This dialog is modal and the window behind it is only built once it returns
Accepted, so there is no moment at which the application is on screen without a
signed-in role.

It carries three flows:
  * sign in
  * first-run setup, when the database has no accounts yet
  * forgotten password — the notary's recovery code, and a pointer to the notary
    for the secretary
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFrame, QMessageBox, QTextEdit,
)

import auth
import office_profile
import permissions


class LoginDialog(QDialog):
    MIN_PASSWORD_LEN = 8

    def __init__(self, parent=None, lang: str = "ar"):
        super().__init__(parent)
        self.lang = lang
        self.setModal(True)
        self.setMinimumWidth(460)
        self._build()
        self._apply_direction()

    # ── helpers ──────────────────────────────────────────────────────────────
    @property
    def is_fr(self) -> bool:
        return self.lang == "fr"

    def tr(self, fr: str, ar: str) -> str:
        return fr if self.is_fr else ar

    def _apply_direction(self):
        self.setLayoutDirection(
            Qt.LayoutDirection.LeftToRight if self.is_fr
            else Qt.LayoutDirection.RightToLeft)

    def _status(self, msg: str, ok: bool = False):
        self.status.setText(msg)
        self.status.setStyleSheet(
            f"color: {'#059669' if ok else '#dc2626'}; font-weight: bold;")

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build(self):
        self.setWindowTitle(self.tr("DATLY — Connexion", "DATLY — تسجيل الدخول"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)

        import config
        from PySide6.QtGui import QPixmap
        logo_path = config.resource_path("assets", "datly_logo.png")
        if not logo_path.exists():
            from pathlib import Path
            logo_path = Path(__file__).resolve().parent.parent.parent / "assets" / "datly_logo.png"

        if logo_path.exists():
            logo_lbl = QLabel(self)
            pix = QPixmap(str(logo_path))
            if not pix.isNull():
                scaled_pix = pix.scaledToWidth(220, Qt.TransformationMode.SmoothTransformation)
                logo_lbl.setPixmap(scaled_pix)
                logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lay.addWidget(logo_lbl)

        title = QLabel(self.tr("DATLY", "DATLY"), self)
        title.setStyleSheet("font-size: 24px; font-weight: 900; color: #1e3a8a; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        self.subtitle = QLabel("", self)
        self.subtitle.setWordWrap(True)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setStyleSheet("color: #475569; font-size: 12px;")
        lay.addWidget(self.subtitle)

        line = QFrame(self); line.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(line)

        # account picker — a short fixed list beats free typing for two accounts
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Compte :", "الحساب :"), self))
        self.user_combo = QComboBox(self)
        self._reload_accounts()
        row.addWidget(self.user_combo, 1)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(self.tr("Mot de passe :", "كلمة المرور :"), self))
        self.pw_input = QLineEdit(self)
        self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_input.returnPressed.connect(self.attempt_login)
        row2.addWidget(self.pw_input, 1)
        lay.addLayout(row2)

        self.status = QLabel("", self)
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        self.login_btn = QPushButton(self.tr("Se connecter", "دخول"), self)
        self.login_btn.setProperty("class", "PrimaryButton")
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self.attempt_login)

        self.forgot_btn = QPushButton(
            self.tr("Mot de passe oublié ?", "نسيت كلمة المرور؟"), self)
        self.forgot_btn.setProperty("class", "SecondaryButton")
        self.forgot_btn.clicked.connect(self.forgot_password)

        self.net_btn = QPushButton(
            self.tr("🌐 Réseau", "🌐 شبكة المكتب"), self)
        self.net_btn.setProperty("class", "SecondaryButton")
        self.net_btn.setToolTip(self.tr("Lier cet ordinateur au serveur du cabinet", "ربط هذا الجهاز بشبكة المكتب"))
        self.net_btn.clicked.connect(self.open_network_dialog)

        self.quit_btn = QPushButton(self.tr("Quitter", "خروج"), self)
        self.quit_btn.clicked.connect(self.reject)

        btns.addWidget(self.login_btn, 2)
        btns.addWidget(self.forgot_btn, 2)
        btns.addWidget(self.net_btn, 2)
        btns.addWidget(self.quit_btn, 1)
        lay.addLayout(btns)

        self._maybe_first_run()

    def open_network_dialog(self):
        import config
        from PySide6.QtWidgets import QApplication
        cfg = config.load_network_config()
        
        box = QDialog(self)
        box.setModal(True)
        box.setWindowTitle(self.tr("Réseau du Cabinet (Lier au Serveur)", "إعدادات شبكة المكتب"))
        box.setMinimumWidth(440)
        v = QVBoxLayout(box)
        v.setSpacing(12)

        hint = QLabel(self.tr(
            "Configurez la connexion au PC serveur du Notaire pour partager la base de données :",
            "قم بربط هذا الجهاز بجهاز الأستاذ (الخادم) لمشاركة قاعدة البيانات :"), box)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#475569; font-size:12px;")
        v.addWidget(hint)

        # Mode
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(self.tr("Mode :", "الوضع :"), box))
        mode_combo = QComboBox(box)
        mode_combo.addItems([
            self.tr("Autonome (Un seul poste)", "مستقل — جهاز واحد"),
            self.tr("Poste de travail (Connecté au serveur)", "جهاز عمل — متصل بالخادم")
        ])
        if cfg.get("mode") == config.MODE_WORKSTATION:
            mode_combo.setCurrentIndex(1)
        else:
            mode_combo.setCurrentIndex(0)
        mode_row.addWidget(mode_combo, 1)
        v.addLayout(mode_row)

        # Host
        host_row = QHBoxLayout()
        host_row.addWidget(QLabel(self.tr("Adresse IP du serveur :", "عنوان الخادم IP :"), box))
        host_input = QLineEdit(box)
        host_input.setText(cfg.get("host") or "")
        host_input.setPlaceholderText("ex: 192.168.1.15")
        host_row.addWidget(host_input, 1)
        v.addLayout(host_row)

        # Token
        token_row = QHBoxLayout()
        token_row.addWidget(QLabel(self.tr("Clé d'accès / Token :", "مفتاح الدخول :"), box))
        token_input = QLineEdit(box)
        token_input.setText(cfg.get("token") or "")
        token_row.addWidget(token_input, 1)
        v.addLayout(token_row)

        status_lbl = QLabel("", box)
        status_lbl.setWordWrap(True)
        v.addWidget(status_lbl)

        btn_row = QHBoxLayout()
        save_btn = QPushButton(self.tr("Tester & Enregistrer", "اختبار الاتصال والحفظ"), box)
        save_btn.setProperty("class", "PrimaryButton")
        cancel_btn = QPushButton(self.tr("Annuler", "إلغاء"), box)
        cancel_btn.clicked.connect(box.reject)

        def do_save():
            is_workstation = (mode_combo.currentIndex() == 1)
            target_mode = config.MODE_WORKSTATION if is_workstation else config.MODE_STANDALONE
            host = host_input.text().strip()
            token = token_input.text().strip()
            port = config.DEFAULT_DB_PORT

            if is_workstation:
                if not host or not token:
                    status_lbl.setText(self.tr("L'adresse IP et la clé sont obligatoires !", "العنوان والمفتاح ضروريان !"))
                    status_lbl.setStyleSheet("color:#dc2626; font-weight:bold;")
                    return
                status_lbl.setText(self.tr("Vérification de la connexion au serveur...", "جاري فحص الاتصال بالخادم..."))
                status_lbl.setStyleSheet("color:#2563eb; font-weight:bold;")
                QApplication.processEvents()

                from db_client import probe
                ok, msg = probe(host, port, token)
                if not ok:
                    status_lbl.setText(self.tr(f"Impossible de joindre le serveur : {msg}", f"لم يستجب الخادم : {msg}"))
                    status_lbl.setStyleSheet("color:#dc2626; font-weight:bold;")
                    return

            config.save_network_config({
                "mode": target_mode,
                "host": host,
                "port": port,
                "token": token
            })
            QMessageBox.information(
                box, self.tr("Réseau du cabinet", "شبكة المكتب"),
                self.tr("Configuration enregistrée avec succès !", "تم حفظ الإعدادات بنجاح!"))
            box.accept()
            self.status.setText("")
            self._reload_accounts()
            self._maybe_first_run()

        save_btn.clicked.connect(do_save)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        v.addLayout(btn_row)

        box.exec()

    def _reload_accounts(self):
        self.user_combo.clear()
        try:
            users = auth.list_users()
        except Exception:
            users = []
        import office_profile
        prof = office_profile.load()
        notary_disp = office_profile.display_name(prof) or "عدل الإشهاد"

        for u in users:
            fr, ar = permissions.ROLE_LABELS.get(u["role"], (u["role"], u["role"]))
            if u["role"] == permissions.ROLE_ADMIN:
                disp = notary_disp
            else:
                disp = u.get("display_name") or u["username"]
            self.user_combo.addItem(
                f"{disp} — {self.tr(fr, ar)}",
                u["username"])
        if not users:
            self.user_combo.addItem(auth.DEFAULT_ADMIN, auth.DEFAULT_ADMIN)

    # ── first run ────────────────────────────────────────────────────────────
    def _maybe_first_run(self):
        """On a database with no accounts, create them and show the credentials once."""
        try:
            if auth.user_count() > 0:
                self.subtitle.setText(self.tr(
                    "Identifiez-vous pour ouvrir le cabinet.",
                    "سجّل دخولك لفتح المكتب."))
                return
        except Exception as e:
            self._status(self.tr(f"Base de données inaccessible : {e}",
                                 f"تعذّر الوصول إلى قاعدة البيانات : {e}"))
            return

        creds = auth.bootstrap()
        if not creds:
            return
        self._reload_accounts()
        self.subtitle.setText(self.tr(
            "Première utilisation : deux comptes viennent d'être créés.",
            "أول استعمال : تم إنشاء حسابين الآن."))
        self._show_credentials(creds)

    def _show_credentials(self, creds: dict):
        box = QDialog(self)
        box.setModal(True)
        box.setWindowTitle(self.tr("À noter maintenant", "دوّنها الآن"))
        box.setMinimumWidth(520)
        v = QVBoxLayout(box)
        warn = QLabel(self.tr(
            "Ces informations ne seront plus jamais affichées. "
            "Notez-les et rangez le code de récupération en lieu sûr : "
            "c'est le seul moyen de rouvrir le compte du notaire si le mot de "
            "passe est perdu.",
            "لن تُعرض هذه المعلومات مرة أخرى أبداً. دوّنها واحتفظ برمز الاسترجاع "
            "في مكان آمن : هو الوسيلة الوحيدة لاسترجاع حساب الأستاذ إذا ضاعت "
            "كلمة المرور."), box)
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #b45309; font-weight: bold;")
        v.addWidget(warn)

        text = QTextEdit(box)
        text.setReadOnly(True)
        text.setPlainText(
            f"{self.tr('Notaire (administrateur)', 'الأستاذ (المدير)')}\n"
            f"  {self.tr('utilisateur', 'المستخدم')} : {creds['admin_username']}\n"
            f"  {self.tr('mot de passe', 'كلمة المرور')} : {creds['admin_password']}\n\n"
            f"{self.tr('Secrétaire', 'الكاتبة')}\n"
            f"  {self.tr('utilisateur', 'المستخدم')} : {creds['secretary_username']}\n"
            f"  {self.tr('mot de passe', 'كلمة المرور')} : {creds['secretary_password']}\n\n"
            f"{self.tr('CODE DE RÉCUPÉRATION', 'رمز الاسترجاع')} : {creds['recovery_code']}\n"
        )
        text.setMinimumHeight(200)
        v.addWidget(text)

        ok = QPushButton(self.tr("J'ai noté ces informations", "دوّنتُ هذه المعلومات"), box)
        ok.clicked.connect(box.accept)
        v.addWidget(ok)
        box.exec()

    # ── login ────────────────────────────────────────────────────────────────
    def attempt_login(self):
        username = self.user_combo.currentData() or self.user_combo.currentText()
        password = self.pw_input.text()
        if not password:
            self._status(self.tr("Entrez votre mot de passe.", "أدخل كلمة المرور."))
            return
        self.login_btn.setEnabled(False)
        try:
            ok = auth.login(username, password)
        except Exception as e:
            self._status(self.tr(f"Erreur de connexion : {e}",
                                 f"خطأ في الدخول : {e}"))
            self.login_btn.setEnabled(True)
            return
        self.login_btn.setEnabled(True)

        if not ok:
            self.pw_input.clear()
            self._status(self.tr("Mot de passe incorrect.", "كلمة المرور غير صحيحة."))
            return

        user = auth.get_user(username) or {}
        if user.get("must_change"):
            if not self._force_password_change(username):
                auth.logout()
                self._status(self.tr("Changement de mot de passe requis.",
                                     "يجب تغيير كلمة المرور."))
                return
        self.accept()

    def _force_password_change(self, username: str) -> bool:
        """A generated first-run password must be replaced before work begins."""
        for _ in range(3):
            new, ok = self._ask_new_password(
                self.tr("Choisissez votre mot de passe", "اختر كلمة المرور الخاصة بك"))
            if not ok:
                return False
            problem = self.password_problem(new)
            if problem:
                QMessageBox.warning(self, self.tr("Mot de passe faible",
                                                  "كلمة مرور ضعيفة"), problem)
                continue
            auth.set_password(username, new)
            return True
        return False

    def _ask_new_password(self, title: str):
        dlg = QDialog(self)
        dlg.setModal(True)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(420)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(self.tr("Nouveau mot de passe :", "كلمة المرور الجديدة :"), dlg))
        a = QLineEdit(dlg); a.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(a)
        v.addWidget(QLabel(self.tr("Confirmez :", "أعد الإدخال :"), dlg))
        b = QLineEdit(dlg); b.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(b)
        msg = QLabel("", dlg); msg.setStyleSheet("color:#dc2626;"); msg.setWordWrap(True)
        v.addWidget(msg)
        row = QHBoxLayout()
        okb = QPushButton(self.tr("Valider", "تأكيد"), dlg)
        cab = QPushButton(self.tr("Annuler", "إلغاء"), dlg)
        row.addWidget(okb); row.addWidget(cab)
        v.addLayout(row)

        state = {"ok": False}

        def confirm():
            if a.text() != b.text():
                msg.setText(self.tr("Les deux saisies diffèrent.",
                                    "الإدخالان غير متطابقين."))
                return
            state["ok"] = True
            dlg.accept()

        okb.clicked.connect(confirm)
        cab.clicked.connect(dlg.reject)
        dlg.exec()
        return a.text(), state["ok"]

    def password_problem(self, pw: str):
        """Same rule the Paramètres page applies, kept in one place."""
        if len(pw) < self.MIN_PASSWORD_LEN:
            return self.tr(
                f"Au moins {self.MIN_PASSWORD_LEN} caractères.",
                f"على الأقل {self.MIN_PASSWORD_LEN} خانات.")
        if pw.isdigit() or pw.isalpha():
            return self.tr("Mélangez lettres et chiffres.",
                           "اخلط بين الحروف والأرقام.")
        if pw.lower() in ("zarai2024", "password", "motdepasse", "12345678"):
            return self.tr("Ce mot de passe est trop courant.",
                           "كلمة المرور هذه شائعة جداً.")
        return None

    # ── recovery ─────────────────────────────────────────────────────────────
    def forgot_password(self):
        username = self.user_combo.currentData() or self.user_combo.currentText()
        user = auth.get_user(username)
        if user is None:
            self._status(self.tr("Compte introuvable.", "الحساب غير موجود."))
            return

        if user["role"] != permissions.ROLE_ADMIN:
            # The secretary does not hold a recovery code by design: giving every
            # account its own code turns a lost slip of paper into a second way
            # into the office. Her route back in is the notary.
            QMessageBox.information(
                self, self.tr("Réinitialisation", "إعادة التعيين"),
                self.tr(
                    "Le mot de passe de la secrétaire est réinitialisé par le "
                    "notaire, depuis Paramètres → Comptes et sécurité.",
                    "يقوم الأستاذ بإعادة تعيين كلمة مرور الكاتبة من "
                    "الإعدادات ← الحسابات والأمان."))
            return

        self._recovery_flow(username)

    def _recovery_flow(self, username: str):
        dlg = QDialog(self)
        dlg.setModal(True)
        dlg.setWindowTitle(self.tr("Récupération du compte notaire",
                                   "استرجاع حساب الأستاذ"))
        dlg.setMinimumWidth(480)
        v = QVBoxLayout(dlg)
        info = QLabel(self.tr(
            "Entrez le code de récupération remis lors de l'installation, "
            "puis choisissez un nouveau mot de passe.",
            "أدخل رمز الاسترجاع الذي سُلّم لك عند التركيب، ثم اختر كلمة مرور جديدة."), dlg)
        info.setWordWrap(True)
        v.addWidget(info)

        v.addWidget(QLabel(self.tr("Code de récupération :", "رمز الاسترجاع :"), dlg))
        code = QLineEdit(dlg)
        code.setPlaceholderText("XXXXX-XXXXX-XXXXX-XXXXX")
        v.addWidget(code)

        v.addWidget(QLabel(self.tr("Nouveau mot de passe :", "كلمة المرور الجديدة :"), dlg))
        pw1 = QLineEdit(dlg); pw1.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(pw1)
        v.addWidget(QLabel(self.tr("Confirmez :", "أعد الإدخال :"), dlg))
        pw2 = QLineEdit(dlg); pw2.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(pw2)

        msg = QLabel("", dlg); msg.setWordWrap(True)
        msg.setStyleSheet("color:#dc2626; font-weight: bold;")
        v.addWidget(msg)

        row = QHBoxLayout()
        okb = QPushButton(self.tr("Réinitialiser", "إعادة التعيين"), dlg)
        cab = QPushButton(self.tr("Annuler", "إلغاء"), dlg)
        row.addWidget(okb); row.addWidget(cab)
        v.addLayout(row)

        def do_reset():
            if pw1.text() != pw2.text():
                msg.setText(self.tr("Les deux saisies diffèrent.",
                                    "الإدخالان غير متطابقين."))
                return
            problem = self.password_problem(pw1.text())
            if problem:
                msg.setText(problem)
                return
            ok, fresh = auth.reset_password_with_recovery_code(
                username, code.text(), pw1.text())
            if not ok:
                msg.setText(self.tr("Code de récupération invalide.",
                                    "رمز الاسترجاع غير صحيح."))
                return
            QMessageBox.information(
                self, self.tr("Nouveau code", "رمز جديد"),
                self.tr(
                    "Mot de passe réinitialisé.\n\n"
                    "L'ancien code est désormais inutilisable. Votre nouveau "
                    f"code de récupération est :\n\n{fresh}\n\n"
                    "Notez-le et rangez-le en lieu sûr.",
                    "تمت إعادة تعيين كلمة المرور.\n\n"
                    "الرمز القديم لم يعد صالحاً. رمز الاسترجاع الجديد هو :\n\n"
                    f"{fresh}\n\nدوّنه واحتفظ به في مكان آمن."))
            dlg.accept()

        okb.clicked.connect(do_reset)
        cab.clicked.connect(dlg.reject)
        dlg.exec()
