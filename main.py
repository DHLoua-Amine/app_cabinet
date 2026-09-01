import sys
import os
import traceback
from pathlib import Path

# Add core and root directories to path for imports (supports PyInstaller frozen mode)
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
    MEI_DIR = Path(getattr(sys, '_MEIPASS', BASE_DIR))
    sys.path.insert(0, str(MEI_DIR))
    sys.path.insert(0, str(MEI_DIR / "core"))
else:
    BASE_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(BASE_DIR))
    sys.path.insert(0, str(BASE_DIR / "core"))



# ── Nothing below this line may fail silently ────────────────────────────────
# The packaged build is produced with --noconsole. Anything that raised while
# the module-level imports ran therefore killed the process with no window, no
# message and no log: the office double-clicked the icon and nothing happened.
# `from ui.main_window import MainWindow` at module scope pulled in every page,
# OpenCV and the face engine before a single line of error handling existed.
# Every import that can fail now happens inside _run(), underneath a handler
# that does not itself depend on Qt having loaded.

def _crash_log_path() -> Path:
    """Somewhere writable, whatever went wrong. Never raises."""
    for candidate in (os.environ.get("LOCALAPPDATA"), os.environ.get("TEMP"),
                      os.environ.get("TMP"), str(Path.home())):
        if not candidate:
            continue
        try:
            d = Path(candidate) / "CabinetNotarialZarai"
            d.mkdir(parents=True, exist_ok=True)
            return d / "startup_error.log"
        except Exception:
            continue
    return Path("CabinetNotarialZarai_startup_error.log")


def _show_fatal(title: str, body: str, detail: str = "") -> None:
    """
    Reports a startup failure to the person in front of the machine.

    Tries a native Win32 message box FIRST: it needs no Qt, no stylesheet and no
    event loop, so it still works when the failure IS that Qt could not load —
    which is exactly the case the old code could not report, because it tried to
    report it with a Qt dialog.
    """
    full = body if not detail else f"{body}\n\n{detail}"
    path = _crash_log_path()
    try:
        import datetime
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
            f.write(full + "\n")
        full += f"\n\nDétails enregistrés dans :\n{path}"
    except Exception:
        # (c) Safe: we are already in the failure path. Losing the log must not
        # stop the message from reaching the user.
        pass

    shown = False
    try:
        if sys.platform == "win32":
            import ctypes
            MB_ICONERROR = 0x10
            ctypes.windll.user32.MessageBoxW(None, full, title, MB_ICONERROR)
            shown = True
    except Exception:
        shown = False
    if not shown:
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is None:
                QApplication(sys.argv[:1])
            QMessageBox.critical(None, title, full)
            shown = True
        except Exception:
            # (c) Safe: the stderr fallback below is the last resort.
            pass
    if not shown:
        print(f"{title}\n{full}", file=sys.stderr)


FATAL_TITLE = "Cabinet Notarial — Erreur de démarrage / خطأ في بدء التشغيل"


def load_stylesheet(app, qss_path):
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
        print(f"[OK] Feuille de style QSS chargee : {qss_path}")
        return True
    print(f"[AVERTISSEMENT] Feuille de style QSS introuvable a : {qss_path}")
    return False


def _build_wheel_filter():
    """Built lazily so importing PySide6 stays inside the guarded section."""
    from PySide6.QtWidgets import QApplication, QComboBox
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import QObject, QEvent

    class ComboBoxWheelFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Wheel and isinstance(obj, QComboBox):
                if not obj.view().isVisible():
                    # Ignore the wheel event for combobox so it doesn't change selection
                    # Pass it directly to the parent so the scroll area scrolls instead
                    event.ignore()
                    parent = obj.parent()
                    if parent:
                        QApplication.postEvent(parent, QWheelEvent(
                            event.position(), event.globalPosition(), event.pixelDelta(),
                            event.angleDelta(), event.buttons(), event.modifiers(),
                            event.phase(), event.inverted()
                        ))
                    return True
            return False

    return ComboBoxWheelFilter()


def _selftest() -> int:
    """
    `CabinetNotarialZarai.exe --selftest` — verifies an installation.

    Packaging failures are silent by nature: the stylesheet and the face models
    were absent from a build for weeks and the only symptom was an ugly window
    and recognition that never matched anyone. This checks, on the client's own
    machine, that every file the application opens at runtime is really there.
    Writes its result to the console AND to the startup log, so it works whether
    or not the build has a console.
    """
    lines = []
    ok = True

    def check(label, passed, detail=""):
        nonlocal ok
        ok = ok and passed
        lines.append(f"[{'OK' if passed else '!!'}] {label}{('  ' + detail) if detail else ''}")

    lines.append(f"frozen={getattr(sys, 'frozen', False)}  exe={sys.executable}")
    try:
        import config
        check("config imported", True)
        lines.append(f"     RESOURCE_ROOT = {config.RESOURCE_ROOT}")
        lines.append(f"     DATA_DIR      = {config.DATA_DIR}")
        qss = config.resource_path("assets", "styles.qss")
        check("stylesheet present", qss.exists(), str(qss))
        check("data directory writable", os.access(str(config.DATA_DIR), os.W_OK))
        check("API keys sealed at rest (DPAPI)", config.keystore_is_encrypted())
    except Exception as e:
        check("config imported", False, f"{type(e).__name__}: {e}")

    try:
        import face_engine
        check("face model: detector", face_engine.YUNET_PATH.exists(),
              str(face_engine.YUNET_PATH))
        check("face model: recogniser", face_engine.SFACE_PATH.exists(),
              str(face_engine.SFACE_PATH))
        eng = face_engine.get_global_face_engine()
        check("face engine loads the models", eng is not None)
    except Exception as e:
        check("face engine", False, f"{type(e).__name__}: {e}")

    try:
        import reception
        reception.startup_initialise()
        check("database initialised", True)
    except Exception as e:
        check("database initialised", False, f"{type(e).__name__}: {e}")

    # The machine id and licence state, so a support call can start with facts
    # instead of asking the notary to navigate to a settings page.
    try:
        import licensing
        st = licensing.status()
        lines.append(f"     MACHINE ID    = {st.get('machine','')}")
        lines.append(f"     LICENCE       = {st.get('status')} — {st.get('detail','')}")
        check("licence subsystem responds", bool(st.get("status")))
    except Exception as e:
        check("licence subsystem responds", False, f"{type(e).__name__}: {e}")

    try:
        import config as _c
        net = _c.load_network_config()
        lines.append(f"     NETWORK MODE  = {net.get('mode')}"
                     + (f"  -> {net.get('host')}:{net.get('port')}"
                        if net.get('mode') == 'workstation' else ""))
    except Exception:
        pass

    report = "SELFTEST " + ("PASSED" if ok else "FAILED") + "\n" + "\n".join(lines)
    print(report)
    try:
        with open(_crash_log_path().with_name("selftest.log"), "w", encoding="utf-8") as f:
            f.write(report + "\n")
    except Exception:
        # (c) Safe: the console output above is the primary channel.
        pass
    if not ok and sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, report, "Selftest", 0x10)
        except Exception:
            pass
    return 0 if ok else 1


def _run() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    # 0. Qt itself.
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont
    except Exception as e:
        _show_fatal(
            FATAL_TITLE,
            "L'interface graphique n'a pas pu être chargée. L'application va se fermer.\n"
            "تعذّر تحميل الواجهة الرسومية. سيتم إغلاق التطبيق.",
            f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")
        return 1

    # 1. Initialize QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("DATLY")
    app.setOrganizationName("DATLY")

    from PySide6.QtGui import QIcon
    icon_path = BASE_DIR / "assets" / "app_icon.ico"
    if not icon_path.exists():
        icon_path = BASE_DIR / "assets" / "datly_logo.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # 1a. Prevent mouse wheel scrolling from accidentally changing numbers inside SpinBoxes app-wide
    from PySide6.QtCore import QObject, QEvent
    from PySide6.QtWidgets import QAbstractSpinBox

    class NoSpinBoxWheelFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Wheel and isinstance(obj, QAbstractSpinBox):
                event.ignore()
                return True
            return super().eventFilter(obj, event)

    spin_filter = NoSpinBoxWheelFilter(app)
    app.installEventFilter(spin_filter)

    # 1b. Single Instance Lock: Prevent launching multiple instances concurrently
    from PySide6.QtCore import QSharedMemory
    shared_mem = QSharedMemory("DATLY_SingleInstanceKey")
    if not shared_mem.create(1):
        _show_fatal(
            FATAL_TITLE,
            "L'application DATLY est déjà en cours d'exécution sur ce poste.\n"
            "منظومة DATLY قيد التشغيل بالفعل على هذا الجهاز."
        )
        return 0
    app._single_instance_lock = shared_mem

    # 2. Configure style and font
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    # 3. Prepare the database before any page is built.
    # This used to happen as a side effect of `import reception`, swallowed by a bare
    # `except Exception: pass`. A locked file or a full disk then produced an app with no
    # tables and no indexes, and the user chased a cascade of unrelated errors. Now it
    # fails once, clearly, and stops.
    try:
        import config
        import reception
        reception.startup_initialise()
    except Exception as e:
        _show_fatal(
            FATAL_TITLE,
            "La base de données n'a pas pu être initialisée. "
            "L'application va se fermer.\n\n"
            "تعذّر تجهيز قاعدة البيانات. سيتم إغلاق التطبيق.\n\n"
            "Causes fréquentes : disque plein, fichier verrouillé par une autre "
            "instance, dossier de données inaccessible, ou — si ce poste est "
            "configuré en mode « poste de travail » — serveur du cabinet "
            "injoignable.\n"
            "الأسباب الشائعة: القرص ممتلئ، أو الملف مستعمل من نسخة أخرى من البرنامج، "
            "أو تعذّر الوصول إلى مجلد البيانات.",
            f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")
        return 1

    # 3b. If this machine is the office server, start serving before any window
    # exists, so a workstation switched on at the same moment finds it ready.
    try:
        import db_service
        started, note = db_service.start_if_server()
        if note:
            print(f"[office server] {note}")
        if started is False and note:
            # Failing to bind is not fatal for THIS machine — it still has the
            # database locally — but every other machine in the office is about
            # to fail, so it must be said out loud rather than logged quietly.
            from PySide6.QtWidgets import QMessageBox as _QMB
            _QMB.warning(
                None, "Serveur du cabinet / خادم المكتب",
                "Cette machine est configurée comme serveur du cabinet, mais le "
                "service n'a pas pu démarrer.\n\n"
                f"{note}\n\n"
                "Les autres postes ne pourront pas se connecter.\n"
                "هذا الجهاز مضبوط كخادم للمكتب لكن تعذّر تشغيل الخدمة. "
                "لن تتمكّن بقية الأجهزة من الاتصال.")
    except Exception as e:
        print(f"[office server] not started: {type(e).__name__}: {e}")

    # The stylesheet SHIPS WITH the application, so it is resolved through
    # resource_path() rather than from __file__: inside a packaged build those
    # are different directories, and the window used to open unstyled.
    if not load_stylesheet(app, str(config.resource_path("assets", "styles.qss"))):
        load_stylesheet(app, str(BASE_DIR / "assets" / "styles.qss"))

    # 4. Sign in BEFORE the window exists.
    # Previously the application opened straight onto Accueil with every page one
    # click away and no notion of who was using it: `auth_logged_in` was False and
    # nothing in the app ever read it. The window is now built only after a role
    # has been established, so there is no window-shaped hole to reach through.
    try:
        import auth
        import permissions
        from ui.dialogs.login_dialog import LoginDialog
        auth.init_user_store()
        auth.migrate_legacy_passwords()
    except Exception as e:
        _show_fatal(
            FATAL_TITLE,
            "Comptes utilisateurs inaccessibles. L'application va se fermer.\n"
            "تعذّر الوصول إلى حسابات المستعملين. سيتم إغلاق التطبيق.",
            f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")
        return 1

    # 3c. Remote License & Revocation check via GitHub
    try:
        from remote_license import check_remote_license, set_client_features
        is_active, msg, client_info = check_remote_license()
        if not is_active:
            _show_fatal(
                "Cabinet Notarial — Licence Suspendue / تم إيقاف الترخيص",
                "Votre accès à l'application a été suspendu ou révoqué à distance.\n"
                "تم تعليق أو إلغاء ترخيص استخدام التطبيق عن بُعد.",
                msg.replace("<b>", "").replace("</b>", "").replace("<br>", "\n")
            )
            return 1
        # Enregistrer les fonctionnalités personnalisées du client actuel
        set_client_features(client_info.get("features", {}))
    except Exception as lic_err:
        print(f"[license check] skipped: {lic_err}")

    # Install global filter for QComboBox scrolling fix
    wheel_filter = _build_wheel_filter()
    app.installEventFilter(wheel_filter)
    app._wheel_filter = wheel_filter

    while True:
        login = LoginDialog(None, lang=auth.session_state.lang)
        if login.exec() != LoginDialog.DialogCode.Accepted or not permissions.session.logged_in:
            return 0

        try:
            from ui.main_window import MainWindow
            window = MainWindow()
        except Exception as e:
            _show_fatal(
                FATAL_TITLE,
                "La fenêtre principale n'a pas pu être construite. "
                "L'application va se fermer.\n"
                "تعذّر إنشاء النافذة الرئيسية. سيتم إغلاق التطبيق.",
                f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")
            return 1

        window.show()
        ret = app.exec()
        if getattr(window, "_requested_logout", False):
            permissions.session.sign_out()
            continue
        else:
            return ret


def main():
    try:
        sys.exit(_run())
    except SystemExit:
        raise
    except BaseException as e:
        _show_fatal(
            FATAL_TITLE,
            "Une erreur inattendue a empêché le démarrage.\n"
            "حدث خطأ غير متوقّع منع بدء التشغيل.",
            f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
