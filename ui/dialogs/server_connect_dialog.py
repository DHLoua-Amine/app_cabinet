import sys
import socket
import concurrent.futures
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal

def get_local_ip_prefixes():
    prefixes = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                prefixes.add(".".join(ip.split(".")[:3]))
        finally:
            s.close()
    except Exception:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                prefixes.add(".".join(ip.split(".")[:3]))
    except Exception:
        pass

    if not prefixes:
        prefixes = {"192.168.1", "192.168.0", "10.0.0", "10.46.129", "172.20.10"}
    return list(prefixes)


def scan_server_port(port=8765, timeout=0.2):
    """
    Scans local subnet(s) for the notary office server on port 8765.
    Returns the server IP string or None if not found.
    """
    prefixes = get_local_ip_prefixes()
    ip_candidates = []
    for prefix in prefixes:
        ip_candidates.extend([f"{prefix}.{i}" for i in range(1, 255)])

    def probe(ip):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            res = sock.connect_ex((ip, port))
            sock.close()
            if res == 0:
                return ip
        except Exception:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(probe, ip) for ip in ip_candidates]
        for f in concurrent.futures.as_completed(futures):
            found = f.result()
            if found:
                return found
    return None


class ScanThread(QThread):
    found_ip = Signal(str)

    def run(self):
        ip = scan_server_port()
        self.found_ip.emit(ip or "")


class ServerConnectDialog(QDialog):
    """
    Professional GUI Dialog shown when remote workstation mode cannot reach the server.
    Allows auto-detecting the server IP, setting Port/Token, and testing connection directly.
    """

    def __init__(self, current_ip="127.0.0.1", current_port=8765, current_token="", parent=None, lang="ar"):
        super().__init__(parent)
        self.lang = lang
        self.selected_ip = current_ip
        self.selected_port = current_port
        self.selected_token = current_token
        self.action_mode = "connect"  # "connect" or "standalone"
        self.init_ui(current_ip, current_port, current_token)

    def init_ui(self, current_ip, current_port, current_token):
        is_fr = self.lang == "fr"
        title_txt = "DATLY — Connexion au serveur du cabinet / الاتصال بسيرفر المكتب"
        self.setWindowTitle(title_txt)
        self.setMinimumWidth(520)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            QLabel {
                font-size: 13px;
                color: #1e293b;
            }
            QLineEdit {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton {
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton#PrimaryButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
            }
            QPushButton#PrimaryButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton#SecondaryButton {
                background-color: #f1f5f9;
                color: #334155;
                border: 1px solid #cbd5e1;
            }
            QPushButton#SecondaryButton:hover {
                background-color: #e2e8f0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header Banner
        header = QLabel(
            "Connexion au serveur du cabinet" if is_fr else "الاتصال بسيرفر المكتب", self)
        header.setStyleSheet("font-size: 16px; font-weight: 800; color: #0f172a;")
        layout.addWidget(header)

        subtext = QLabel(
            "Le serveur du notaire est introuvable à l'adresse actuelle.\n"
            "Veuillez vérifier que le PC notaire est allumé et connecté au même réseau Wi-Fi." if is_fr else
            "تعذّر الاتصال بسيرفر المكتب على العنوان الحالي.\n"
            "يرجى التأكد من تشغيل حاسوب النوتار واتصاله بنفس شبكة الـ Wi-Fi.", self)
        subtext.setWordWrap(True)
        subtext.setStyleSheet("color: #475569; font-size: 12px;")
        layout.addWidget(subtext)

        # IP Field + Auto Detect
        ip_lay = QHBoxLayout()
        ip_label = QLabel("Adresse IP :" if is_fr else "عنوان الـ IP:", self)
        self.ip_input = QLineEdit(str(current_ip or "127.0.0.1"), self)
        self.auto_btn = QPushButton("🔍 Auto-détection" if is_fr else "🔍 كشف تلقائي", self)
        self.auto_btn.setObjectName("SecondaryButton")
        self.auto_btn.clicked.connect(self.start_auto_scan)

        ip_lay.addWidget(ip_label)
        ip_lay.addWidget(self.ip_input, 1)
        ip_lay.addWidget(self.auto_btn)
        layout.addLayout(ip_lay)

        # Port Field
        port_lay = QHBoxLayout()
        port_label = QLabel("Port du serveur :" if is_fr else "منفذ السيرفر (Port):", self)
        self.port_input = QLineEdit(str(current_port or 8765), self)
        self.port_input.setFixedWidth(100)
        port_lay.addWidget(port_label)
        port_lay.addWidget(self.port_input)
        port_lay.addStretch()
        layout.addLayout(port_lay)

        # Token Field
        token_lay = QHBoxLayout()
        token_label = QLabel("Clé de sécurité (Token) :" if is_fr else "رمز الأمان (Token):", self)
        self.token_input = QLineEdit(str(current_token or ""), self)
        self.token_input.setPlaceholderText("Clé optionnelle / اختيارية")
        token_lay.addWidget(token_label)
        token_lay.addWidget(self.token_input, 1)
        layout.addLayout(token_lay)

        # Spinner Progress
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(6)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Action Buttons
        btn_lay = QHBoxLayout()
        self.test_btn = QPushButton("⚡ Tester la connexion" if is_fr else "⚡ اختبار الاتصال", self)
        self.test_btn.setObjectName("SecondaryButton")
        self.test_btn.clicked.connect(self.on_test_clicked)

        self.connect_btn = QPushButton("Se connecter" if is_fr else "حفظ والاتصال للسيرفر", self)
        self.connect_btn.setObjectName("PrimaryButton")
        self.connect_btn.clicked.connect(self.on_connect_clicked)

        self.standalone_btn = QPushButton("Mode Autonome (Poste seul)" if is_fr else "العمل بوضع مستقل (مكتب منفصل)", self)
        self.standalone_btn.setObjectName("SecondaryButton")
        self.standalone_btn.clicked.connect(self.on_standalone_clicked)

        btn_lay.addWidget(self.standalone_btn)
        btn_lay.addWidget(self.test_btn)
        btn_lay.addStretch()
        btn_lay.addWidget(self.connect_btn)
        layout.addLayout(btn_lay)

        if self.lang == "ar":
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    def start_auto_scan(self):
        self.auto_btn.setEnabled(False)
        self.progress.setVisible(True)
        try:
            port = int(self.port_input.text().strip() or 8765)
        except Exception:
            port = 8765
        self.scan_thread = ScanThread()
        self.scan_thread.found_ip.connect(self.on_scan_finished)
        self.scan_thread.start()

    def on_scan_finished(self, found_ip):
        self.auto_btn.setEnabled(True)
        self.progress.setVisible(False)
        is_fr = self.lang == "fr"
        if found_ip:
            self.ip_input.setText(found_ip)
            QMessageBox.information(
                self, "Serveur trouvé !" if is_fr else "تم العثور على السيرفر",
                f"Serveur détecté à l'adresse : {found_ip}" if is_fr else
                f"تم العثور على سيرفر المكتب على العنوان: {found_ip}")
        else:
            QMessageBox.warning(
                self, "Non trouvé" if is_fr else "لم يتم العثور عليه",
                "Aucun serveur détecté sur le réseau local.\n"
                "Assurez-vous que l'application est ouverte sur le PC Notaire." if is_fr else
                "لم يتم العثور على أي سيرفر على الشبكة المحلية.\n"
                "تأكد من فتح التطبيق أولاً على حاسوب النوتار.")

    def on_test_clicked(self):
        ip = self.ip_input.text().strip()
        try:
            port = int(self.port_input.text().strip() or 8765)
        except Exception:
            port = 8765
        is_fr = self.lang == "fr"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            res = s.connect_ex((ip, port))
            s.close()
            if res == 0:
                QMessageBox.information(
                    self, "Succès" if is_fr else "نجاح الاتصال",
                    f"Connexion réussie avec le serveur ({ip}:{port}) !" if is_fr else
                    f"تم الاتصال بنجاح مع السيرفر ({ip}:{port})!")
            else:
                QMessageBox.warning(
                    self, "Échec" if is_fr else "فشل الاتصال",
                    f"Impossible d'atteindre le serveur {ip}:{port}.\nVérifiez l'adresse et le pare-feu." if is_fr else
                    f"تعذّر الاتصال بالسيرفر على العنوان {ip}:{port}.\nتأكد من العنوان وتأكد من سماح الجدار الناري (Firewall).")
        except Exception as e:
            QMessageBox.warning(self, "Erreur" if is_fr else "خطأ", f"Erreur de test: {e}")

    def on_connect_clicked(self):
        ip = self.ip_input.text().strip()
        if not ip:
            return
        try:
            port = int(self.port_input.text().strip() or 8765)
        except Exception:
            port = 8765
        token = self.token_input.text().strip()
        self.selected_ip = ip
        self.selected_port = port
        self.selected_token = token
        self.action_mode = "connect"
        self.accept()

    def on_standalone_clicked(self):
        self.action_mode = "standalone"
        self.accept()
