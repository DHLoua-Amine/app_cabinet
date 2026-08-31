import time
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

# Import business logic from core/
import auth
import reception
from camera import VideoCaptureThread
from face_engine import get_global_face_engine
from cooldown import CooldownManager
from config import PROFILES_DIR, STATUS_NEW_VISIT


class CameraThread(QThread):
    # Signals to send frames and detections to UI
    frame_ready = Signal(QImage, list)  # frame, list of detected faces
    connection_status = Signal(bool)    # True = connected, False = failed
    client_detected = Signal(str, str, float)   # client_id, display name, score

    # Opening a webcam measured 3.3-4.8 s on real hardware, so the old
    # 100 * 30 ms = 3 s budget expired before the first frame could arrive and the
    # camera "failed" every time from cold. Wall-clock, and generous.
    CONNECT_TIMEOUT_S = 20.0

    # Detection is 56 ms per call and dominates the loop (preview is ~2 ms). Running it
    # every 3rd frame costs over half a core continuously, which is wasteful when nobody
    # is looking at the preview. A walk-in stands at reception for seconds, so a few
    # detections per second is ample while backgrounded.
    DETECT_EVERY_N_FRAMES_PREVIEW = 3
    BACKGROUND_DETECT_INTERVAL_S = 0.33

    def __init__(self, source=0, cooldown_mgr=None, preview_enabled=True):
        super().__init__()
        self.source = source
        self.running = False
        self.cap_thread = None
        self.face_engine = get_global_face_engine()
        # One shared cooldown owned by the service, so it survives page navigation
        # instead of being reset every time the camera was rebuilt.
        self.cooldown_mgr = cooldown_mgr if cooldown_mgr is not None else CooldownManager()
        self.face_cache = None
        self._cache_gen = -1
        self._preview_enabled = bool(preview_enabled)

    def set_preview_enabled(self, enabled: bool):
        """Live video is only produced while a page is actually showing it."""
        self._preview_enabled = bool(enabled)

    def run(self):
        self.running = True
        try:
            # 1. Load embeddings matrix
            self.face_cache = reception.get_all_face_embeddings()
            self._cache_gen = reception.cache_generation()

            # 2. Names for on-screen labels.
            try:
                client_map = reception.get_client_name_map()
            except Exception:
                client_map = {}

            # 3. Start OpenCV video capture thread
            self.cap_thread = VideoCaptureThread(source=self.source)
            self.cap_thread.start()
            
            frame_counter = 0
            active_boxes = []
            detected_faces_summary = {}
            persistent_unknown_faces = {}

            connected_signal_sent = False
            opened_at = time.time()
            last_bg_detect = 0.0

            while self.running and self.cap_thread.running:
                if self.isInterruptionRequested():
                    break
                ret, frame = self.cap_thread.read_frame()
                if not ret or frame is None:
                    time.sleep(0.03)
                    if not connected_signal_sent and (time.time() - opened_at) > self.CONNECT_TIMEOUT_S:
                        self.connection_status.emit(False)
                        connected_signal_sent = True
                        break
                    continue

                if not connected_signal_sent:
                    self.connection_status.emit(True)
                    connected_signal_sent = True
                
                preview = self._preview_enabled
                display_frame = frame.copy() if preview else None
                frame_counter += 1
                now = time.time()

                if frame_counter % 60 == 0:
                    gen = reception.cache_generation()
                    if gen != self._cache_gen:
                        self.face_cache = reception.get_all_face_embeddings()
                        self._cache_gen = gen
                        try:
                            client_map = reception.get_client_name_map()
                        except Exception:
                            pass

                if preview:
                    should_detect = (frame_counter % self.DETECT_EVERY_N_FRAMES_PREVIEW == 0 or not active_boxes)
                else:
                    should_detect = (now - last_bg_detect) >= self.BACKGROUND_DETECT_INTERVAL_S

                if should_detect:
                    last_bg_detect = now
                    detections = self.face_engine.detect_and_extract(frame)
                    active_boxes = []
                    current_detected_summary = {}

                    for det in detections:
                        x1, y1, x2, y2 = det["bbox"]
                        crop = det["crop"]
                        embedding = det["embedding"]
                        
                        matched_id, score = self.face_engine.match_face(embedding, prebuilt_cache=self.face_cache)
                        
                        crop_qimg = None
                        if preview:
                            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                            ch, cw, cc = crop_rgb.shape
                            crop_qimg = QImage(crop_rgb.data, cw, ch, cc * cw, QImage.Format.Format_RGB888).copy()

                        if matched_id:
                            name_disp = client_map.get(matched_id, f"Client #{matched_id}")
                            color = (0, 180, 80)
                            label = f"OK {name_disp} ({score*100:.0f}%)"

                            # Auto-purge any transient unknown entries that match this recognized face!
                            to_purge = []
                            q_norm = embedding / np.linalg.norm(embedding) if np.linalg.norm(embedding) > 0 else embedding
                            for unk_k, unk_v in list(persistent_unknown_faces.items()):
                                u_emb = unk_v.get("embedding")
                                if u_emb is not None:
                                    u_norm = u_emb / np.linalg.norm(u_emb) if np.linalg.norm(u_emb) > 0 else u_emb
                                    if float(np.dot(u_norm, q_norm)) >= 0.50:
                                        to_purge.append(unk_k)
                            for pk in to_purge:
                                persistent_unknown_faces.pop(pk, None)

                            _, should_log = self.cooldown_mgr.process_detection(matched_id, "Guichet")
                            if should_log:
                                try:
                                    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
                                    cv2.imwrite(str(PROFILES_DIR / f"{matched_id}.jpg"), crop)
                                except Exception:
                                    pass
                                if reception.log_check_in(matched_id, "Guichet", score, STATUS_NEW_VISIT):
                                    self.client_detected.emit(matched_id, name_disp, float(score))

                            current_detected_summary[matched_id] = {
                                "client_id": matched_id,
                                "name": name_disp,
                                "status": "known",
                                "crop_qimg": crop_qimg,
                                "embedding": embedding
                            }
                            active_boxes.append((x1, y1, x2, y2, color, label))
                        else:
                            color = (220, 50, 50)
                            new_matched_key = None
                            q_norm = embedding / np.linalg.norm(embedding) if np.linalg.norm(embedding) > 0 else embedding

                            for fk, fd in list(persistent_unknown_faces.items()):
                                u_emb = fd.get("embedding")
                                if u_emb is not None:
                                    try:
                                        u_norm = u_emb / np.linalg.norm(u_emb) if np.linalg.norm(u_emb) > 0 else u_emb
                                        if float(np.dot(u_norm, q_norm)) >= 0.55:
                                            new_matched_key = fk
                                            break
                                    except Exception:
                                        pass
                                        
                            if not new_matched_key:
                                temp_key = f"new_{len(persistent_unknown_faces) + 1}_{int(now) % 10000}"
                                persistent_unknown_faces[temp_key] = {
                                    "client_id": temp_key,
                                    "name": "Nouveau Client" if auth.session_state.lang == "fr" else "زائر جديد",
                                    "status": "new",
                                    "crop_qimg": crop_qimg,
                                    "embedding": embedding
                                }
                                new_matched_key = temp_key
                            else:
                                if crop_qimg and not crop_qimg.isNull():
                                    persistent_unknown_faces[new_matched_key]["crop_qimg"] = crop_qimg
                                persistent_unknown_faces[new_matched_key]["embedding"] = embedding

                            current_detected_summary[new_matched_key] = persistent_unknown_faces[new_matched_key]
                            active_boxes.append((x1, y1, x2, y2, color, "Nouveau Client" if auth.session_state.lang == "fr" else "زائر جديد"))

                    detected_faces_summary = current_detected_summary

                if preview:
                    for x1, y1, x2, y2, color, label in active_boxes:
                        cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                        cv2.rectangle(display_frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
                        cv2.putText(display_frame, label, (x1 + 3, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

                    rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_frame.shape
                    q_img = QImage(rgb_frame.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()

                    self.frame_ready.emit(q_img, list(detected_faces_summary.values()))

                time.sleep(0.015)
        except Exception as e:
            try:
                from system_guardian import log_system_error
                log_system_error("CameraThread loop exception", e)
            except Exception:
                pass
        finally:
            if self.cap_thread:
                try:
                    self.cap_thread.stop()
                except Exception:
                    pass
                self.cap_thread = None

    def stop(self, timeout_ms: int = 3000) -> bool:
        """
        Asks the loop to finish and waits, but never forever.

        This used to call self.wait() with no timeout. That was survivable while the
        thread only lived as long as the Accueil page was open; as a session-long
        background service an unbounded wait would hang application close.
        Returns True if the thread actually finished within the timeout.
        """
        self.running = False
        self.requestInterruption()
        if self.cap_thread:
            try:
                self.cap_thread.stop()
            except Exception as stop_err:
                # (b) A capture thread that will not stop keeps the device open,
                # and the next connection then fails looking like "no camera".
                try:
                    from system_guardian import log_system_error
                    log_system_error("camera capture thread would not stop", stop_err)
                except Exception:
                    # (c) Safe. A guard around the logger during shutdown,
                    # when system_guardian may already be torn down.
                    pass
        if not self.isRunning():
            return True
        finished = self.wait(max(1, int(timeout_ms)))
        if not finished:
            print(f"[camera] thread did not stop within {timeout_ms} ms")
        return finished
