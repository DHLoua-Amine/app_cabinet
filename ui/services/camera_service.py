"""
camera_service.py — one camera for the whole application session.

The camera used to be owned by the Accueil page: showEvent() started it, hideEvent()
stopped it. Walking to any other page tore the thread down and released the device, so a
client arriving while the receptionist was editing a file was never seen. This service
owns the camera instead, so detection runs for the entire session and page navigation
only decides whether a live picture is produced.
"""

import time

from PySide6.QtCore import QObject, Signal, QTimer

import camera as camera_core
from cooldown import CooldownManager
from ui.components.camera_thread import CameraThread


class CameraState:
    OFF = "off"                  # never started, or deliberately stopped
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"   # was working, then went away
    FAILED = "failed"            # could not be opened at all


class CameraService(QObject):
    """Owns the camera thread for the whole session. Created once by MainWindow."""

    frame_ready = Signal(object, list)          # QImage, detected faces (preview only)
    status_changed = Signal(str, str)           # CameraState, human-readable detail
    client_detected = Signal(str, str, float)   # client_id, name, score

    # A camera that disappears mid-session (unplugged, or grabbed by another program)
    # should be retried, but not in a tight loop that pins the CPU.
    RETRY_BACKOFF_S = [5, 15, 60]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._source = None
        self._state = CameraState.OFF
        self._detail = ""
        self._preview_enabled = False
        self._stopping = False
        self._retry_index = 0
        self._started_at = 0.0

        # ONE cooldown for the session. It used to live on the camera thread, which was
        # rebuilt on every visit to Accueil, so its memory of "already logged this
        # client" was wiped each time and the same visit was recorded again.
        self.cooldown = CooldownManager(cooldown_seconds=300)

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._retry)

    # ── state ────────────────────────────────────────────────────────────────
    @property
    def state(self):
        return self._state

    @property
    def detail(self):
        return self._detail

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.isRunning())

    def _set_state(self, state, detail=""):
        if state == self._state and detail == self._detail:
            return
        self._state = state
        self._detail = detail
        self.status_changed.emit(state, detail)

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self, source=None):
        """Starts the camera. Safe to call when already running (no-op)."""
        if self.is_running():
            return True

        if source is None:
            source = camera_core.get_saved_camera_source()
        if source is None or source == "":
            self._set_state(CameraState.OFF,
                            "Aucune caméra configurée / لم يتم إعداد أي كاميرا")
            return False

        self._source = source
        self._stopping = False
        self._started_at = time.time()

        self._thread = CameraThread(
            source=source,
            cooldown_mgr=self.cooldown,
            preview_enabled=self._preview_enabled,
        )
        self._thread.frame_ready.connect(self._on_frame)
        self._thread.connection_status.connect(self._on_connection_status)
        self._thread.client_detected.connect(self.client_detected)
        # Noticing the thread end on its own is how a mid-session unplug is detected.
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()
        self._set_state(CameraState.CONNECTING, str(source))
        return True

    def stop(self, timeout_ms: int = 3000) -> bool:
        """Stops the camera for good. Called on application close."""
        self._stopping = True
        self._retry_timer.stop()
        ok = True
        if self._thread:
            ok = self._thread.stop(timeout_ms=timeout_ms)
            self._thread = None
        self._set_state(CameraState.OFF, "")
        return ok

    def restart(self, source=None):
        self.stop()
        self._retry_index = 0
        return self.start(source)

    # ── preview ──────────────────────────────────────────────────────────────
    def set_preview_enabled(self, enabled: bool):
        """
        Turns the live picture on or off without touching detection.

        Detection is ~56 ms per call and dominates the loop; the preview pipeline is
        ~2 ms. Turning preview off also drops the detection cadence to a few per second,
        which is what actually saves the CPU while nobody is watching.
        """
        self._preview_enabled = bool(enabled)
        if self._thread:
            self._thread.set_preview_enabled(self._preview_enabled)

    def preview_enabled(self) -> bool:
        return self._preview_enabled

    # ── internal slots ───────────────────────────────────────────────────────
    def _on_frame(self, qimg, faces):
        self.frame_ready.emit(qimg, faces)

    def _on_connection_status(self, connected: bool):
        if connected:
            self._retry_index = 0
            self._set_state(CameraState.CONNECTED, f"source: {self._source}")
        else:
            self._set_state(
                CameraState.FAILED,
                "La caméra n'a envoyé aucune image / الكاميرا لم ترسل أي صورة")
            self._schedule_retry()

    def _on_thread_finished(self):
        """The loop ended. Deliberate stop, or the device went away mid-session."""
        if self._stopping:
            return
        if self._state == CameraState.CONNECTED:
            self._set_state(
                CameraState.DISCONNECTED,
                "Connexion perdue / انقطع الاتصال بالكاميرا")
        elif self._state != CameraState.FAILED:
            self._set_state(
                CameraState.FAILED,
                "La caméra n'a pas pu être ouverte / تعذّر فتح الكاميرا")
        self._schedule_retry()

    def _schedule_retry(self):
        if self._stopping:
            return
        delay = self.RETRY_BACKOFF_S[min(self._retry_index, len(self.RETRY_BACKOFF_S) - 1)]
        self._retry_index += 1
        self._retry_timer.start(int(delay * 1000))

    def _retry(self):
        if self._stopping:
            return
        self._thread = None
        self.start(self._source)
