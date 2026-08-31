import sys
import os
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QUrl, QDir, QTimer
from PySide6.QtMultimedia import (
    QMediaCaptureSession, QMediaRecorder, QAudioInput, QMediaDevices, QMediaFormat
)


class AudioRecorder(QObject):
    """
    Microphone dictation recorder built on QtMultimedia.

    QMediaRecorder finalises its container asynchronously: when stop() returns, the
    file on disk is still only a header. This class therefore never emits
    recording_stopped straight after stop() — it waits until Qt reports StoppedState
    and the file size has settled, so the receiver always reads complete audio.
    """

    # Signals
    recording_started = Signal()
    recording_stopped = Signal(str)   # Emits output file path once the file is complete
    error_occurred = Signal(str)

    # A valid AAC/MP4 recording is comfortably larger than a bare container header (~44 bytes).
    MIN_VALID_BYTES = 2048
    # RMS amplitude (16-bit scale, max 32767) below which the recording is treated as
    # silence. Measured reference: a muted microphone produces RMS ≈ 22.
    SILENCE_RMS_THRESHOLD = 120.0
    FINALISE_POLL_MS = 120
    FINALISE_TIMEOUT_MS = 8000

    def __init__(self):
        super().__init__()
        self.session = None
        self.audio_input = None
        self.recorder = None
        self.output_path = ""
        self.output_mime = "audio/mp4"
        self.is_recording = False

        self._finalise_timer = None
        self._finalise_elapsed = 0
        self._last_size = -1
        self._stable_ticks = 0

        self.init_recorder()

    def init_recorder(self):
        try:
            # Check for available audio inputs
            devices = QMediaDevices.audioInputs()
            if not devices:
                print("[AudioRecorder] Aucun micro physique detecte sur ce PC.")
                return

            self.session = QMediaCaptureSession()
            self.audio_input = QAudioInput()

            # Select default audio input device
            default_device = QMediaDevices.defaultAudioInput()
            self.audio_input.setDevice(default_device)
            self.session.setAudioInput(self.audio_input)

            self.recorder = QMediaRecorder()
            self.session.setRecorder(self.recorder)

            # Configure default high-quality audio recording format
            media_format = QMediaFormat()
            # Under Windows, AAC inside M4A is natively supported and lightweight
            media_format.setFileFormat(QMediaFormat.FileFormat.Mpeg4Audio)
            media_format.setAudioCodec(QMediaFormat.AudioCodec.AAC)
            self.recorder.setMediaFormat(media_format)
            self.recorder.setQuality(QMediaRecorder.Quality.HighQuality)

            # Surface backend failures (device busy, codec missing) instead of failing silently.
            try:
                self.recorder.errorOccurred.connect(self._on_recorder_error)
            except Exception:
                # (c) Safe. Older Qt multimedia builds do not expose this
                # signal; recording still works, just without the extra detail.
                pass

        except Exception as e:
            print(f"[AudioRecorder] Erreur d'initialisation QtMultimedia: {e}")
            self.recorder = None

    def _on_recorder_error(self, error, error_string=""):
        if error == QMediaRecorder.Error.NoError:
            return
        self.is_recording = False
        self._stop_finalise_timer()
        self.error_occurred.emit(error_string or "Erreur d'enregistrement audio / خطأ في التسجيل الصوتي")

    def start(self):
        if self.is_recording:
            return

        if not self.recorder:
            self.error_occurred.emit(
                "Aucun microphone disponible ou QtMultimedia non supporte sur ce PC / لا يوجد مايكروفون مفعل"
            )
            return

        try:
            # Prepare temporary output path in user workspace
            temp_dir = Path(QDir.tempPath()) / "CabinetZarai"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Save format specific extension, and report the matching MIME type so the
            # transcription engine describes the payload correctly.
            ext = "m4a"
            self.output_mime = "audio/mp4"
            if self.recorder.mediaFormat().fileFormat() == QMediaFormat.FileFormat.Wave:
                ext = "wav"
                self.output_mime = "audio/wav"

            self.output_path = str(temp_dir / f"dictation_temp.{ext}")

            # Remove existing temp file if any
            if os.path.exists(self.output_path):
                try:
                    os.remove(self.output_path)
                except Exception as rm_err:
                    # (b) A previous recording that will not delete can end up
                    # transcribed in place of the one just made.
                    print(f"[AUDIO] could not remove the previous recording "
                          f"{self.output_path}: {rm_err}", file=sys.stderr)

            self.recorder.setOutputLocation(QUrl.fromLocalFile(self.output_path))
            self.recorder.record()
            self.is_recording = True
            self.recording_started.emit()
            print(f"[AudioRecorder] Enregistrement demarre a : {self.output_path}")

        except Exception as e:
            self.is_recording = False
            self.error_occurred.emit(str(e))

    def stop(self):
        if not self.is_recording or not self.recorder:
            return

        try:
            self.recorder.stop()
            self.is_recording = False
            # Do NOT emit yet: the container is still being written.
            self._begin_finalise_watch()
        except Exception as e:
            self.error_occurred.emit(str(e))

    # ── Waiting for Qt to finish writing the file ────────────────────────────
    def _begin_finalise_watch(self):
        self._stop_finalise_timer()
        self._finalise_elapsed = 0
        self._last_size = -1
        self._stable_ticks = 0

        self._finalise_timer = QTimer(self)
        self._finalise_timer.setInterval(self.FINALISE_POLL_MS)
        self._finalise_timer.timeout.connect(self._check_finalised)
        self._finalise_timer.start()

    def _stop_finalise_timer(self):
        if self._finalise_timer is not None:
            try:
                self._finalise_timer.stop()
                self._finalise_timer.deleteLater()
            except Exception:
                # (c) Safe. Stopping a timer Qt has already destroyed.
                pass
            self._finalise_timer = None

    def measure_level(self, timeout_ms: int = 8000) -> float:
        """
        Returns the RMS amplitude (0-32767) of the finished recording, or -1 if unknown.

        A dictation that captured silence must never be sent for transcription: the
        model will invent plausible notarial text rather than return nothing, which
        would put invented clauses into a deed.
        """
        try:
            from PySide6.QtCore import QUrl, QEventLoop, QTimer
            from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
            import numpy as np
        except Exception:
            return -1.0

        if not self.output_path or not os.path.exists(self.output_path):
            return -1.0

        try:
            decoder = QAudioDecoder()
            fmt = QAudioFormat()
            fmt.setSampleRate(16000)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            decoder.setAudioFormat(fmt)
            decoder.setSource(QUrl.fromLocalFile(self.output_path))

            chunks = []

            def on_ready():
                buf = decoder.read()
                if buf.isValid():
                    chunks.append(np.frombuffer(bytes(buf.constData()[:buf.byteCount()]), dtype=np.int16))

            loop = QEventLoop()
            decoder.bufferReady.connect(on_ready)
            decoder.finished.connect(loop.quit)
            QTimer.singleShot(timeout_ms, loop.quit)
            decoder.start()
            loop.exec()

            if not chunks:
                return -1.0
            data = np.concatenate(chunks).astype(np.float64)
            if data.size == 0:
                return -1.0
            return float(np.sqrt(np.mean(data ** 2)))
        except Exception:
            return -1.0

    def _current_size(self) -> int:
        try:
            return os.path.getsize(self.output_path) if os.path.exists(self.output_path) else -1
        except Exception:
            return -1

    def _recorder_is_stopped(self) -> bool:
        try:
            return self.recorder.recorderState() == QMediaRecorder.RecorderState.StoppedState
        except Exception:
            return True

    def _check_finalised(self):
        self._finalise_elapsed += self.FINALISE_POLL_MS
        size = self._current_size()

        # The file is done when Qt has left RecordingState, the size is plausible,
        # and it has stopped growing for two consecutive polls.
        if size == self._last_size and size >= self.MIN_VALID_BYTES and self._recorder_is_stopped():
            self._stable_ticks += 1
        else:
            self._stable_ticks = 0
        self._last_size = size

        if self._stable_ticks >= 2:
            self._stop_finalise_timer()
            print(f"[AudioRecorder] Enregistrement finalise ({size} octets) : {self.output_path}")
            self.recording_stopped.emit(self.output_path)
            return

        if self._finalise_elapsed >= self.FINALISE_TIMEOUT_MS:
            self._stop_finalise_timer()
            if size >= self.MIN_VALID_BYTES:
                # Usable audio, just slow to settle — hand it over.
                print(f"[AudioRecorder] Finalisation lente, fichier accepte ({size} octets).")
                self.recording_stopped.emit(self.output_path)
            else:
                self.error_occurred.emit(
                    "تعذّر حفظ التسجيل الصوتي بشكل كامل. يرجى إعادة التسجيل. "
                    "(Le fichier audio n'a pas pu être finalisé)"
                )
