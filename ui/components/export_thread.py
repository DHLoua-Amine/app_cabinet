"""
export_thread.py — Runs long exports off the UI thread.

Excel and PDF exports were built and written synchronously inside the button handler,
so the window stopped repainting for the whole operation (measured: 12.6 s for 20,000
dossiers, 21.9 s for 50,000 presence rows). Users read a frozen window as a crash and
force-quit it, which is exactly the moment a half-written file is worst.
"""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QProgressDialog
from PySide6.QtCore import Qt


class ExportThread(QThread):
    """
    Calls `build(progress_cb)` in the background and writes the returned bytes to disk.

    `build` receives a callback it may invoke with (done, total) to drive a real
    progress bar; if it never calls it, the dialog stays indeterminate.
    """

    progress = Signal(int, int)     # done, total
    finished_ok = Signal(str)       # output path
    failed = Signal(str)            # error message

    def __init__(self, build, out_path, parent=None):
        super().__init__(parent)
        self._build = build
        self._out_path = out_path

    def run(self):
        try:
            def report(done, total):
                self.progress.emit(int(done), int(total))
                return not self.isInterruptionRequested()

            data = self._build(report)
            if self.isInterruptionRequested():
                return
            if data is None:
                self.failed.emit("Aucune donnée produite / لم يتم إنتاج أي بيانات")
                return
            mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
            with open(self._out_path, mode) as f:
                f.write(data)
            self.finished_ok.emit(str(self._out_path))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


def run_export_with_progress(parent, build, out_path, title, label):
    """
    Starts an ExportThread and shows a cancellable progress dialog over it.

    Returns the thread so the caller can keep a reference (and so closeEvent can
    interrupt it). The dialog stays responsive because the work is on the thread.
    """
    dlg = QProgressDialog(label, "Annuler / إلغاء", 0, 0, parent)
    dlg.setWindowTitle(title)
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.setMinimumDuration(0)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.setValue(0)

    thread = ExportThread(build, out_path, parent)

    def on_progress(done, total):
        if total > 0:
            if dlg.maximum() != total:
                dlg.setRange(0, total)
            dlg.setValue(done)

    def cleanup():
        dlg.close()

    thread.progress.connect(on_progress)
    thread.finished_ok.connect(lambda _p: cleanup())
    thread.failed.connect(lambda _m: cleanup())
    dlg.canceled.connect(thread.requestInterruption)

    thread.start()
    dlg.show()
    return thread
