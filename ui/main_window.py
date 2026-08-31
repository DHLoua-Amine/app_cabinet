import time

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QFrame, QLabel, QPushButton, QStackedWidget, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QThread
from PySide6.QtGui import QCursor


class _LibraryWarmupThread(QThread):
    """
    Imports the slow third-party libraries away from the UI thread.

    pandas alone is about four seconds. Importing it on the UI thread freezes the window
    for that whole time in one un-interruptible block; here the interpreter yields between
    bytecodes and during the import's file I/O, so the window keeps repainting.
    Failures are ignored on purpose: this only pre-warms a cache, and every caller still
    imports what it needs.
    """

    def run(self):
        for module in ("pandas",):
            if self.isInterruptionRequested():
                return
            try:
                __import__(module)
            except Exception as e:
                print(f"[warmup] could not preload {module}: {type(e).__name__}: {e}")

import auth
import permissions
from permissions import Cap
import camera as camera_core
from ui.services.camera_service import CameraService, CameraState
from ui.components.camera_status_bar import CameraStatusBar, DetectionToast

# The eight page modules are imported inside _create_page(), not here. Importing them all
# up front dragged in pandas, reportlab and openpyxl and cost several seconds before the
# window appeared, even though only the Accueil page is visible at launch.

class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resize(1350, 900)
        self.init_ui()

    def update_sidebar_brand(self):
        import office_profile
        prof = office_profile.load()
        name = (prof.get("notary_name") or "").strip()
        is_fr = getattr(self, "current_lang", "ar") == "fr"
        
        if name:
            if is_fr:
                brand_text = f"DATLY — Cabinet {name}"
                win_title = f"DATLY — Cabinet {name}"
            else:
                brand_text = f"DATLY — مكتب {name}"
                win_title = f"DATLY — مكتب {name}"
        else:
            brand_text = "DATLY"
            win_title = "DATLY — المنظومة العدلية الذكية" if not is_fr else "DATLY — Notarial Suite"
            
        if hasattr(self, "sidebar_title"):
            self.sidebar_title.setText(brand_text)
        self.setWindowTitle(win_title)

    def init_ui(self):
        self.current_lang = getattr(auth.session_state, "lang", "ar")
        self.update_sidebar_brand()

        # Central Widget
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        
        # Main Horizontal Layout
        main_layout = QHBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. SIDEBAR (Left Panel) ──────────────────────────────────────────
        self.sidebar = QFrame(self.central_widget)
        self.sidebar.setObjectName("Sidebar")
        
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(5)

        # Sidebar Title
        self.sidebar_title = QLabel("المكتب الذكي", self.sidebar)
        self.sidebar_title.setObjectName("SidebarTitle")
        self.sidebar_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(self.sidebar_title)

        # Sidebar Navigation Buttons
        self.nav_buttons = {}
        
        # Format: (Key, Label AR, Label FR, Active)
        self.nav_items = [
            ("home", "الرئيسية والكاميرا", "Accueil & Caméra", True),
            ("register", "سجل الملفات", "Registre des Dossiers", True),
            ("clients", "دليل الحرفاء", "Répertoire des Clients", True),
            ("fiche", "بطاقة حريف", "Fiche Client", False),
            ("presence", "سجل الحضور والزيارات", "Journal de Présence", True), # Enabled
            ("compta", "المحاسبة والمالية", "Comptabilité", True),
            ("scanner", "الماسح والتلخيص الذكي", "Scanner IA", True),
            ("settings", "الإعدادات", "Paramètres", True),
        ]

        for key, lbl_ar, lbl_fr, active in self.nav_items:
            btn = QPushButton(lbl_ar, self.sidebar)
            btn.setProperty("class", "SidebarButton")
            btn.setCheckable(True)
            btn.setEnabled(active)
            if not active:
                btn.setToolTip("Ouvrable depuis l'accueil/répertoire / مفتوح من الاستقبال")
            
            # Store labels inside custom properties for easy translation updates
            btn.setProperty("lbl_ar", lbl_ar)
            btn.setProperty("lbl_fr", lbl_fr)
            
            sidebar_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        # Spacer at the bottom of sidebar
        sidebar_layout.addStretch()

        # Camera status lives here so it is on screen no matter which page is open.
        self.camera_status_bar = CameraStatusBar(self.sidebar, lang=self.current_lang)
        sidebar_layout.addWidget(self.camera_status_bar)

        # Logout button
        self.btn_logout = QPushButton(self.sidebar)
        self.btn_logout.setMinimumHeight(36)
        self.btn_logout.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_logout.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: #ffffff;
                font-weight: 700;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                margin-top: 6px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
        """)
        self.btn_logout.clicked.connect(self.logout_user)
        sidebar_layout.addWidget(self.btn_logout)

        # Connect navigation buttons
        self.nav_buttons["settings"].clicked.connect(lambda: self.switch_page("settings"))
        self.nav_buttons["register"].clicked.connect(lambda: self.switch_page("register"))
        self.nav_buttons["clients"].clicked.connect(lambda: self.switch_page("clients"))
        self.nav_buttons["compta"].clicked.connect(lambda: self.switch_page("compta"))
        self.nav_buttons["home"].clicked.connect(lambda: self.switch_page("home"))
        self.nav_buttons["scanner"].clicked.connect(lambda: self.switch_page("scanner"))
        self.nav_buttons["presence"].clicked.connect(lambda: self.switch_page("presence"))

        # Hide what this role cannot reach, so the secretary is not shown a door
        # she will only be refused at.
        for key, btn in self.nav_buttons.items():
            cap = self.PAGE_CAPABILITY.get(key)
            if cap is not None and not permissions.has(cap):
                btn.setVisible(False)

        main_layout.addWidget(self.sidebar)

        # ── 2. CONTENT AREA (Right Panel) ────────────────────────────────────
        self.content_area = QStackedWidget(self.central_widget)
        self.content_area.setObjectName("ContentArea")

        # Pages are built on first navigation — see _get_page(). Only Accueil is created
        # now, because it is the only one the user can actually see at launch.
        self._pages = {}

        main_layout.addWidget(self.content_area)

        self.update_ui_language(self.current_lang)

        # Start default page (Home page)
        self.nav_buttons["home"].setChecked(True)
        self.switch_page("home")

        # ── Session-long camera ──────────────────────────────────────────────
        # The camera belongs to the window, not to the Accueil page, so a client
        # walking in is still detected while the receptionist is in another file.
        self.camera_service = CameraService(self)
        self.camera_service.status_changed.connect(self._on_camera_status)
        self.camera_service.client_detected.connect(self._on_client_detected)

        self.detection_toast = DetectionToast(self, lang=self.current_lang)
        self.detection_toast.clicked.connect(self.open_fiche_client)

        # Accueil is built above, before the service exists, so attach it now. Pages
        # created later pick the service up in _create_page().
        for page in self._pages.values():
            if page is not None and hasattr(page, "attach_camera_service"):
                page.attach_camera_service(self.camera_service)
        self._sync_camera_preview("home")

        # Deferred: opening a camera takes 3-5 s and startup was just cut from 23 s to
        # under 9 s. Auto-start also only happens when a camera was actually configured
        # here, so machines without one are not made to wait for a probe that fails.
        QTimer.singleShot(self.CAMERA_AUTOSTART_MS, self._autostart_camera)

        # Then build the remaining pages quietly in the background, one per tick, so the
        # first click on any of them is instant. Ordered after the camera so its
        # connection is already under way before the warm-up starts.
        QTimer.singleShot(self.WARMUP_START_MS, self._warm_next_page)

    # ── Lazy page construction ───────────────────────────────────────────────
    # (key -> module path, class name, constructor args)
    PAGE_SPECS = {
        "settings": ("ui.pages.settings_page", "SettingsPage", ()),
        "register": ("ui.pages.register_page", "RegisterPage", ()),
        "clients": ("ui.pages.clients_page", "ClientsPage", ()),
        "compta": ("ui.pages.accounting_page", "AccountingPage", ()),
        "fiche": ("ui.pages.fiche_client_page", "FicheClientPage", (None,)),
        "home": ("ui.pages.home_page", "HomePage", ()),
        "scanner": ("ui.pages.scanner_page", "ScannerPage", ()),
        "presence": ("ui.pages.presence_page", "PresencePage", ()),
    }

    # A page the signed-in role may not open is not merely hidden: switch_page
    # refuses it, the warm-up skips it, and its data functions refuse underneath
    # anyway. Hiding the button is the courtesy, not the control.
    PAGE_CAPABILITY = {
        "compta": Cap.VIEW_FINANCE,
        "scanner": Cap.USE_SCANNER,
    }

    def may_open(self, key) -> bool:
        cap = self.PAGE_CAPABILITY.get(key)
        return cap is None or permissions.has(cap)

    def _create_page(self, key):
        """Imports the module, builds the page, wires its signals, adds it to the stack."""
        import importlib
        mod_path, cls_name, args = self.PAGE_SPECS[key]
        cls = getattr(importlib.import_module(mod_path), cls_name)
        page = cls(*args, self.content_area)

        if key == "settings":
            page.language_changed.connect(self.restart_app_for_language)
        elif key == "fiche":
            page.back_to_list.connect(lambda: self.switch_page("clients"))
        if key in ("clients", "home", "scanner", "presence"):
            page.client_selected.connect(self.open_fiche_client)

        # Accueil renders the shared feed; it does not own a camera.
        if hasattr(page, "attach_camera_service") and getattr(self, "camera_service", None):
            page.attach_camera_service(self.camera_service)

        self.content_area.addWidget(page)
        # A page built after startup still has to match the current language.
        if hasattr(page, "update_language"):
            page.update_language(self.current_lang)
        self._pages[key] = page
        return page

    def _get_page(self, key):
        page = self._pages.get(key)
        return page if page is not None else self._create_page(key)

    # Kept so existing code (and closeEvent) can still say self.home_page etc. without
    # forcing a page that was never opened to be built.
    def __getattr__(self, name):
        if name.endswith("_page"):
            key = {"fiche_page": "fiche", "accounting_page": "compta"}.get(
                name, name[:-len("_page")])
            pages = self.__dict__.get("_pages")
            if pages is not None and key in self.PAGE_SPECS:
                return pages.get(key)
        raise AttributeError(name)

    # ── Background page warm-up ──────────────────────────────────────────────
    # Pages are built on first navigation, which made that first click cost between
    # 0.3 s and 3.9 s depending on the page. Building them here instead — one per timer
    # tick, after the window is up and the camera has been asked to start — moves that
    # cost into idle time the user is not waiting on.
    #
    # Cheapest first, so the common pages are ready soonest. Each page is built inside a
    # single tick and control returns to the event loop between ticks, so a click that
    # lands mid-warm-up is still handled promptly.
    CAMERA_AUTOSTART_MS = 1500
    WARMUP_START_MS = 3000
    WARMUP_INTERVAL_MS = 250
    WARMUP_ORDER = ["clients", "presence", "register", "settings", "fiche", "scanner", "compta"]

    def _warm_next_page(self):
        """
        Loads the heavy libraries off the UI thread first, then builds one page per tick.

        Building a page straight away does not work: constructing Comptabilite or Journal
        calls load_data(), which needs pandas, and importing pandas takes about four
        seconds. Done on the UI thread that is a single un-interruptible tick — measured
        at 4,885 ms of frozen window, worse than the delay it was meant to remove.
        The import runs in a worker thread instead, where it yields to the event loop;
        once it is done a page costs roughly 150 ms to build, which fits in one tick.
        """
        if getattr(self, "_warmup_done", False):
            return

        if not getattr(self, "_libs_ready", False):
            if getattr(self, "_lib_thread", None) is None:
                self._lib_thread = _LibraryWarmupThread(self)
                self._lib_thread.finished.connect(self._on_libs_warmed)
                self._lib_thread.start()
            return      # _on_libs_warmed restarts the page ticks

        for key in self.WARMUP_ORDER:
            if not self.may_open(key):
                continue        # building it would raise from its own load_data()
            if key not in self._pages:
                try:
                    self._get_page(key)
                except Exception as e:
                    # A page that cannot be built must not stop the others, and must not
                    # surface as a dialog the user did not ask for.
                    print(f"[warmup] could not pre-build {key}: {type(e).__name__}: {e}")
                    self._pages[key] = None
                QTimer.singleShot(self.WARMUP_INTERVAL_MS, self._warm_next_page)
                return
        self._warmup_done = True

    def _on_libs_warmed(self):
        self._libs_ready = True
        QTimer.singleShot(self.WARMUP_INTERVAL_MS, self._warm_next_page)

    # ── Camera service plumbing ──────────────────────────────────────────────
    def _autostart_camera(self):
        """Brings the camera up by itself, but only when it makes sense to try."""
        if not camera_core.has_saved_camera_source():
            self.camera_status_bar.set_status(
                CameraState.OFF,
                "Aucune caméra configurée — connectez-la depuis Accueil / "
                "لم يتم إعداد كاميرا — اربطها من صفحة الاستقبال")
            return
        if not camera_core.get_camera_autostart():
            self.camera_status_bar.set_status(
                CameraState.OFF,
                "Démarrage automatique désactivé / التشغيل التلقائي معطّل")
            return
        self.camera_service.start()

    def _on_camera_status(self, state, detail):
        self.camera_status_bar.set_status(state, detail)
        home = self._pages.get("home")
        if home is not None and hasattr(home, "on_service_status"):
            home.on_service_status(state, detail)

    def _on_client_detected(self, client_id, name, score):
        """A visit was just recorded — say so wherever the user happens to be."""
        self.detection_toast.show_detection(client_id, name)

    def _sync_camera_preview(self, key):
        """Live video is only produced while the page that shows it is on screen."""
        if getattr(self, "camera_service", None) is None:
            return
        self.camera_service.set_preview_enabled(key == "home")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        toast = getattr(self, "detection_toast", None)
        if toast is not None and toast.isVisible():
            toast._reposition()

    def switch_page(self, key):
        if not self.may_open(key):
            # Reached only if something bypasses the hidden button - a shortcut, a
            # signal, a future caller. The refusal lives here rather than on the
            # button so those routes are covered too.
            is_fr = self.current_lang == "fr"
            QMessageBox.warning(
                self,
                "Accès refusé" if is_fr else "الدخول مرفوض",
                ("Cette section est réservée au notaire."
                 if is_fr else "هذا القسم مخصص للأستاذ فقط."))
            for k, btn in self.nav_buttons.items():
                btn.setChecked(k == self.content_area.currentIndex())
            return

        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)

        page = self._get_page(key)
        self.content_area.setCurrentWidget(page)
        self._sync_camera_preview(key)

        if key == "register":
            page.load_data()
        elif key == "clients":
            page.load_data()
        elif key == "compta":
            page.load_data()
        elif key == "scanner":
            page.load_clients_list()
        elif key == "presence":
            page.load_data()

    def open_fiche_client(self, client_id):
        fiche = self._get_page("fiche")
        fiche.client_id = client_id
        fiche.is_new = (client_id is None or client_id == "" or client_id == "NEW")

        if fiche.is_new:
            fiche.init_empty_client()
        
        fiche.load_client_data()

        # Ensure correct sidebar selection matches the active view
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == "fiche")

        self.content_area.setCurrentWidget(fiche)
        self._sync_camera_preview("fiche")

    def update_ui_language(self, lang_code):
        is_fr = lang_code == "fr"
        self.current_lang = lang_code

        # 1. Update Sidebar Buttons Texts
        for key, btn in self.nav_buttons.items():
            lbl = btn.property("lbl_fr" if is_fr else "lbl_ar")
            btn.setText(lbl)
            
        # 2. Update Sidebar Title & Window Title Dynamically from Office Profile
        self.update_sidebar_brand()
        
        # 3. Handle Layout Direction
        if is_fr:
            self.sidebar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.central_widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.sidebar_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            self.sidebar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.central_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.sidebar_title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
        # 4. Notify the pages that exist. A page built later picks the language up in
        #    _create_page(), so nothing is missed by not forcing them all into being here.
        for page in list(getattr(self, "_pages", {}).values()):
            if page is not None and hasattr(page, "update_language"):
                page.update_language(lang_code)

    def restart_app_for_language(self, lang_code):
        import __main__
        if hasattr(self, "btn_logout"):
            self.btn_logout.setText("🚪 " + ("Déconnexion" if self.current_lang == "fr" else "تسجيل الخروج"))

        if hasattr(__main__, 'window'):
            old_window = __main__.window
            from ui.main_window import MainWindow
            __main__.window = MainWindow()
            __main__.window.show()
            old_window.close()
        else:
            self.hide()
            self.__class__.current_window = self.__class__()
            self.__class__.current_window.show()
            self.close()

    def logout_user(self):
        is_fr = self.current_lang == "fr"
        confirm = QMessageBox.question(
            self,
            "Déconnexion" if is_fr else "تسجيل الخروج",
            "Voulez-vous vraiment vous déconnecter ?" if is_fr else "هل تريد حقاً تسجيل الخروج من التطبيق؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._requested_logout = True
            self.close()

    # Longest the window will wait for background work before closing anyway.
    # quit() does nothing to these threads — they override run() and have no event
    # loop — so closing used to block for the full duration of the task (a backup, or
    # a scanner API call up to its 120 s timeout).
    SHUTDOWN_GRACE_MS = 3000

    def _shutdown_thread(self, thread, label, deadline_ms):
        """Asks a worker thread to stop and waits only up to the shared deadline."""
        if thread is None or not thread.isRunning():
            return 0
        started = time.perf_counter()
        try:
            thread.requestInterruption()   # cooperative: checked inside run()
            thread.quit()                  # harmless; only helps event-loop threads
        except Exception:
            # (c) Safe. The thread object may already be gone during teardown;
            # the bounded wait below is what actually guarantees shutdown.
            pass
        thread.wait(max(1, int(deadline_ms)))
        waited = (time.perf_counter() - started) * 1000
        if thread.isRunning():
            print(f"[closeEvent] {label} did not stop within its grace period; "
                  f"closing anyway after {waited:.0f} ms")
        return waited

    def closeEvent(self, event):
        t_start = time.perf_counter()

        # 1. Stop the session-long camera service first. Its stop() is bounded, so a
        #    camera that has wedged cannot hold the application open.
        svc = getattr(self, 'camera_service', None)
        if svc is not None:
            try:
                stopped = svc.stop(timeout_ms=self.SHUTDOWN_GRACE_MS)
                print(f"[closeEvent] camera service stopped cleanly: {stopped}")
            except Exception as e:
                print(f"[closeEvent] camera service stop failed: {e}")

        if getattr(self, 'home_page', None):
            try:
                self.home_page.stop_camera()
            except Exception as e:
                print(f"[closeEvent] stop_camera failed: {e}")

        # 2..4. Every worker thread shares one grace budget, so the total wait is
        # bounded no matter how many are running.
        workers = []
        if getattr(self, 'fiche_page', None):
            workers.append(("ocr_thread", getattr(self.fiche_page, 'ocr_thread', None)))
        # The library pre-warm thread shares the same bounded grace budget.
        workers.append(("lib_warmup", getattr(self, "_lib_thread", None)))
        if getattr(self, 'scanner_page', None):
            workers.append(("pipeline_thread", getattr(self.scanner_page, 'pipeline_thread', None)))
        if getattr(self, 'settings_page', None):
            for attr in ('cam_thread', 'backup_thread', 'update_thread', 'import_thread'):
                workers.append((attr, getattr(self.settings_page, attr, None)))

        for label, t in workers:
            elapsed_ms = (time.perf_counter() - t_start) * 1000
            remaining = self.SHUTDOWN_GRACE_MS - elapsed_ms
            if remaining <= 0:
                if t is not None and t.isRunning():
                    print(f"[closeEvent] grace budget spent; not waiting for {label}")
                continue
            self._shutdown_thread(t, label, remaining)

        total = (time.perf_counter() - t_start) * 1000
        print(f"[closeEvent] shutdown completed in {total:.0f} ms")
        super().closeEvent(event)

