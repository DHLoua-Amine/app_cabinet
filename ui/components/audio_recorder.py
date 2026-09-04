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

            # Le peripherique est relache tant qu'on n'enregistre pas.
            # Auparavant la session gardait le micro ouvert du demarrage de
            # l'application a sa fermeture : une deuxieme instance - ou tout
            # autre logiciel - ne pouvait plus l'ouvrir, et l'enregistrement
            # produisait un conteneur vide sans la moindre erreur.
            self.session.setAudioInput(None)


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
        self._relacher_peripherique()

        # Qt rend des messages anglais que le notaire ne peut pas exploiter.
        # Le plus frequent, « No valid stream found for encoding », signifie que
        # le micro n'a fourni aucun flux : presque toujours une autre instance
        # de l'application, ou un autre logiciel, qui le tient deja.
        brut = (error_string or "").strip()
        if "no valid stream" in brut.lower() or "stream" in brut.lower():
            message = ("لم يوفّر المايكروفون أي تدفّق صوتي. غالبًا لأنّه مستعمل من طرف "
                       "برنامج آخر أو نسخة أخرى من التطبيق. أغلقها ثم أعد المحاولة. "
                       "(Micro occupe par une autre application)")
        else:
            message = ("تعذّر تسجيل الصوت. يرجى التأكّد من المايكروفون وإعادة المحاولة. "
                       f"(Erreur d'enregistrement : {brut or 'inconnue'})")
        self._journaliser("erreur QMediaRecorder", brut or str(error))
        self.error_occurred.emit(message)

    def _diagnostiquer_peripherique(self):
        """Rend (disponible, message) avant de lancer une dictee.

        Ne refuse que sur le cas certain - aucun micro branche. Tout autre
        signal (peripherique occupe, erreur d'ouverture) s'est revele peu
        fiable a la mesure et ferait perdre des dictees valides ; c'est le
        message de fin, base sur la duree capturee, qui nomme la cause."""
        try:
            dev = QMediaDevices.defaultAudioInput()
            if dev.isNull():
                return False, ("لا يوجد مايكروفون على هذا الحاسوب. "
                               "(Aucun microphone detecte sur ce PC)")
            # On NE sonde PAS le peripherique pour refuser la dictee : mesure
            # faite le 3 septembre 2026, QAudioSource rend OpenError alors que
            # le micro est disponible (partage WASAPI, sonde juste apres une
            # liberation). Bloquer la-dessus empeche des dictees valides.
            # Seule l'absence totale de micro est un refus sur.
            return True, ""
        except Exception:
            # La sonde ne doit jamais empecher d'essayer d'enregistrer.
            return True, ""

    def start(self):
        if self.is_recording:
            return

        if not self.recorder:
            self.error_occurred.emit(
                "Aucun microphone disponible ou QtMultimedia non supporte sur ce PC / لا يوجد مايكروفون مفعل"
            )
            return

        disponible, pourquoi = self._diagnostiquer_peripherique()
        if not disponible:
            self._journaliser("micro indisponible au demarrage de la dictee", pourquoi)
            self.error_occurred.emit(pourquoi)
            return

        try:
            # Le micro n'est pris QUE pendant l'enregistrement (voir init_recorder).
            self.session.setAudioInput(self.audio_input)

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

    def _relacher_peripherique(self):
        """Rend le micro au systeme des que la dictee est finie."""
        try:
            if self.session is not None:
                self.session.setAudioInput(None)
        except Exception:
            pass

    def _journaliser(self, titre, detail=""):
        """Ecrit dans system_errors.log. Sans ceci un echec de dictee ne laisse
        aucune trace : impossible ensuite de savoir si le micro etait absent,
        occupe, ou simplement muet."""
        try:
            from system_guardian import log_system_error
            log_system_error(f"Dictee : {titre}", RuntimeError(str(detail)[:500]))
        except Exception:
            pass

    def stop(self):
        if not self.is_recording or not self.recorder:
            return

        try:
            self.recorder.stop()
            self.is_recording = False
            self._duree_enregistree = self.recorder.duration()
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
            self._relacher_peripherique()
            self.recording_stopped.emit(self.output_path)
            return

        if self._finalise_elapsed >= self.FINALISE_TIMEOUT_MS:
            self._stop_finalise_timer()
            if size >= self.MIN_VALID_BYTES:
                # Usable audio, just slow to settle — hand it over.
                print(f"[AudioRecorder] Finalisation lente, fichier accepte ({size} octets).")
                self._relacher_peripherique()
                self.recording_stopped.emit(self.output_path)
            else:
                # Le message doit nommer la cause : « non finalise » ne dit au
                # notaire ni ce qui s'est passe ni quoi faire. Une duree restee
                # a zero signifie que le peripherique n'a livre aucun echantillon
                # - micro occupe ou muet - et non que l'ecriture a echoue.
                duree = getattr(self, "_duree_enregistree", 0)
                if duree <= 0:
                    message = ("لم يلتقط المايكروفون أي صوت. تأكّد من عدم استعماله "
                               "من طرف برنامج آخر أو نسخة أخرى من التطبيق، ثم أعد المحاولة. "
                               "(Aucun son capte - micro probablement occupe)")
                else:
                    message = ("التسجيل قصير جدًا. يرجى التحدّث لثانيتين على الأقل. "
                               "(Enregistrement trop court)")
                self._journaliser(
                    f"fichier inexploitable ({size} octets, duree {duree} ms)", message)
                self._relacher_peripherique()
                self.error_occurred.emit(message)
