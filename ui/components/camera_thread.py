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
    # Les fiches « inconnu » que le fil retire parce que la personne vient d'etre
    # reconnue. Sans ce signal l'interface les gardait affichees pour toute la
    # session : c'est la cause principale des doublons observes le 4/09/2026.
    unknown_purged = Signal(list)               # cles a retirer de l'affichage


    # Opening a webcam measured 3.3-4.8 s on real hardware, so the old
    # 100 * 30 ms = 3 s budget expired before the first frame could arrive and the
    # camera "failed" every time from cold. Wall-clock, and generous.
    CONNECT_TIMEOUT_S = 20.0

    # Detection is 56 ms per call and dominates the loop (preview is ~2 ms). Running it
    # every 3rd frame costs over half a core continuously, which is wasteful when nobody
    # is looking at the preview. A walk-in stands at reception for seconds, so a few
    # detections per second is ample while backgrounded.
    # Delai minimal entre deux creations de fiche « nouveau visiteur ».
    DELAI_NOUVEAU_VISITEUR_S = 2.0

    DETECT_EVERY_N_FRAMES_PREVIEW = 2
    BACKGROUND_DETECT_INTERVAL_S = 1.0

    def __init__(self, source=0, cooldown_mgr=None, preview_enabled=True,
                 memoire_inconnus=None):
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
        # Relire le reglage a chaque visage compare coûterait un acces disque
        # plusieurs fois par seconde, pour une valeur qui ne bouge pas.
        self._seuil_cache = None
        # Memoire des visiteurs inconnus. Elle vivait DANS run(), donc elle
        # mourait a chaque reconnexion de la camera et tout le monde redevenait
        # nouveau. Elle appartient desormais au service, comme le cooldown des
        # clients reconnus, et pour la meme raison.
        self.memoire_inconnus = memoire_inconnus if memoire_inconnus is not None else {
            "fiches": {}, "compteur": 0, "dernier_ajout": 0.0, "pending": {}
        }


    def _seuil_similarite(self):
        if self._seuil_cache is not None:
            return self._seuil_cache
        try:
            from core import config
            self._seuil_cache = float(config.get_setting("face_match_threshold", 0.363))
        except Exception:
            self._seuil_cache = 0.363
        return self._seuil_cache

    def _calc_similarity(self, emb1, emb2) -> float:
        """Safely calculates cosine similarity between two embeddings without crashing."""
        if emb1 is None or emb2 is None:
            return 0.0
        try:
            a = np.asarray(emb1, dtype=np.float32).flatten()
            b = np.asarray(emb2, dtype=np.float32).flatten()
            if len(a) != len(b) or len(a) == 0:
                return 0.0
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(np.dot(a / norm_a, b / norm_b))
        except Exception:
            return 0.0

    def set_preview_enabled(self, enabled: bool):
        """Live video is only produced while a page is actually showing it."""
        self._preview_enabled = bool(enabled)

    def _evaluate_face_quality(self, crop) -> float:
        """Evaluates face crop clarity, pose symmetry, and brightness balance.
        Higher composite score means a sharper, clearer, and better lit face picture."""
        if crop is None or crop.size == 0:
            return 0.0
        try:
            h_orig, w_orig = crop.shape[:2]
            if h_orig < 50 or w_orig < 50:
                return 0.0

            # Downscale crop to max 100px for 100X faster quality evaluation (<0.8ms)
            if max(h_orig, w_orig) > 100:
                scale = 100.0 / float(max(h_orig, w_orig))
                small_crop = cv2.resize(crop, (max(1, int(w_orig * scale)), max(1, int(h_orig * scale))), interpolation=cv2.INTER_NEAREST)
            else:
                small_crop = crop

            crop_gray = cv2.cvtColor(small_crop, cv2.COLOR_BGR2GRAY) if len(small_crop.shape) == 3 else small_crop

            # 1. Sharpness (Laplacian variance - detail level)
            sharpness = float(cv2.Laplacian(crop_gray, cv2.CV_64F).var())

            # 2. Lighting & Brightness balance (ideal around 130)
            mean_b = float(np.mean(crop_gray))
            std_b = float(np.std(crop_gray))
            lighting_score = max(0.0, 100.0 - abs(mean_b - 130.0))

            # 3. Resolution factor
            resolution_score = min((w_orig * h_orig) / 1000.0, 50.0)

            # Composite total quality score
            return float((sharpness * 1.5) + (lighting_score * 0.5) + (std_b * 0.8) + resolution_score)
        except Exception:
            return 0.0

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
            # Reprise de la memoire du service, et non un dictionnaire neuf :
            # une reconnexion ne doit pas transformer les visiteurs deja vus
            # en nouvelles fiches.
            persistent_unknown_faces = self.memoire_inconnus["fiches"]
            pending_unknowns = self.memoire_inconnus.setdefault("pending", {})
            active_recognized_tracks = self.memoire_inconnus.setdefault("active_tracks", {})
            active_spatial_tracks = self.memoire_inconnus.setdefault("active_spatial_tracks", {})

            connected_signal_sent = False
            opened_at = time.time()
            last_bg_detect = 0.0
            last_valid_frame_time = time.time()

            while self.running and self.cap_thread and self.cap_thread.running:
                if self.isInterruptionRequested():
                    break
                ret, frame = self.cap_thread.read_frame()
                if not ret or frame is None:
                    time.sleep(0.03)
                    if not connected_signal_sent and (time.time() - opened_at) > self.CONNECT_TIMEOUT_S:
                        self.connection_status.emit(False)
                        connected_signal_sent = True
                        break
                    if connected_signal_sent and (time.time() - last_valid_frame_time) > 2.5:
                        self.connection_status.emit(False)
                        break
                    continue

                last_valid_frame_time = time.time()
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
                    if reception.is_remote():
                        try:
                            conn = reception.get_connection()
                            if hasattr(conn, "get_unknown_visitors"):
                                remote_unk = conn.get_unknown_visitors()
                                for rv in remote_unk:
                                    cid = rv.get("client_id")
                                    if cid and cid not in persistent_unknown_faces:
                                        persistent_unknown_faces[cid] = rv
                            if hasattr(conn, "get_live_detection"):
                                recent = conn.get_live_detection(getattr(self, "_last_live_ts", 0))
                                for det in recent:
                                    ts = det.get("ts", 0)
                                    if ts > getattr(self, "_last_live_ts", 0):
                                        self._last_live_ts = ts
                                        self.client_detected.emit(det.get("client_id", ""), det.get("name", ""), float(det.get("score", 0.9)))
                        except Exception:
                            pass

                if preview:
                    should_detect = (frame_counter % self.DETECT_EVERY_N_FRAMES_PREVIEW == 0)
                else:
                    should_detect = (now - last_bg_detect) >= self.BACKGROUND_DETECT_INTERVAL_S

                if should_detect:
                    last_bg_detect = now
                    try:
                        t0_det = time.time()
                        detections = self.face_engine.detect_and_extract(frame, non_blocking=True)
                        t_det_ms = (time.time() - t0_det) * 1000.0
                        active_boxes = []
                        current_detected_summary = {}

                        # Discard transient pending faces older than 0.6s (single-frame glitches & shadows)
                        for pk, pd in list(pending_unknowns.items()):
                            if now - pd.get("last_seen", now) > 0.6:
                                pending_unknowns.pop(pk, None)

                        # Discard stale recognized tracks older than 3.5s
                        for r_id, r_info in list(active_recognized_tracks.items()):
                            if now - r_info.get("last_seen", now) > 3.5:
                                active_recognized_tracks.pop(r_id, None)

                        # Discard stale spatial tracks older than 3.0s
                        for t_k, t_i in list(active_spatial_tracks.items()):
                            if now - t_i.get("last_seen", now) > 3.0:
                                active_spatial_tracks.pop(t_k, None)

                        for det in detections:
                            x1, y1, x2, y2 = det["bbox"]
                            crop = det["crop"]
                            embedding = det["embedding"]
                            scaled_face = det["face_row"]
                            working_frame = det.get("working_frame")
                            timing = det.get("timing", {})
                            yunet_ms = timing.get("det_ms", 0.0)
                            crop_prep_ms = timing.get("crop_ms", 0.0)
                            
                            bw, bh = x2 - x1, y2 - y1
                            t0_eval = time.time()
                            crop_quality = self._evaluate_face_quality(crop)
                            eval_ms = (time.time() - t0_eval) * 1000.0
                            quality_ms = crop_prep_ms + eval_ms

                            if crop_quality < 20.0:
                                continue  # Automatically discard very low quality frames

                            # Spatial-Temporal Track Fast-Path: match face box to active tracks (known client OR unknown visitor)
                            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                            matched_track_key = None
                            matched_track_info = None

                            if active_spatial_tracks:
                                for t_k, t_i in list(active_spatial_tracks.items()):
                                    if now - t_i.get("last_seen", 0.0) <= 2.5:
                                        rx1, ry1, rx2, ry2 = t_i["bbox"]
                                        rcx, rcy = (rx1 + rx2) / 2.0, (ry1 + ry2) / 2.0
                                        dist = np.hypot(cx - rcx, cy - rcy)
                                        if dist < 140:
                                            matched_track_key = t_k
                                            matched_track_info = t_i
                                            break

                            sface_ms = 0.0
                            t_match_ms = 0.0

                            if matched_track_info is not None:
                                matched_id = matched_track_info.get("matched_id")
                                score = matched_track_info.get("score", 0.0)
                                if embedding is None:
                                    embedding = matched_track_info.get("norm_emb")
                                sface_ms = 0.0
                                t_match_ms = 0.0
                            else:
                                if embedding is None and working_frame is not None and scaled_face is not None:
                                    t0_emb = time.time()
                                    embedding = self.face_engine.extract_feature_embedding(working_frame, scaled_face)
                                    sface_ms = (time.time() - t0_emb) * 1000.0
                                else:
                                    sface_ms = 0.0

                                t0_match = time.time()
                                matched_id, score = self.face_engine.match_face(embedding, prebuilt_cache=self.face_cache)
                                t_match_ms = (time.time() - t0_match) * 1000.0
                                matched_track_key = f"track_{now:.2f}_{int(cx)}_{int(cy)}"

                            net_delay_ms = 0.0
                            if hasattr(self.cap_thread, 'last_frame_time') and self.cap_thread.last_frame_time:
                                net_delay_ms = max(0.0, (now - self.cap_thread.last_frame_time) * 1000.0)

                            total_proc_ms = yunet_ms + quality_ms + sface_ms + t_match_ms
                            
                            net_flag = "🚨 (Wi-Fi TCP Socket Queue Delay)" if net_delay_ms > 150 else ""
                            yunet_flag = "🚨 (High Resolution Detector Load)" if yunet_ms > 50 else ""
                            quality_flag = "🚨 (Large Crop Laplacian/CLAHE Load)" if quality_ms > 40 else ""
                            sface_flag = "🚨 (CPU Neural Network Inference Bottleneck)" if sface_ms > 100 else ("⚡ (Track Cached - 0ms)" if sface_ms == 0 else "")

                            print(f"\n======================================================================"
                                  f"\n[⏱️ DEEP LATENCY DIAGNOSTICS] Frame #{frame_counter} | Face Box: {bw}x{bh} px"
                                  f"\n======================================================================"
                                  f"\n  ├─ 1. TCP Socket Queue Delay: {net_delay_ms:6.1f} ms  {net_flag}"
                                  f"\n  ├─ 2. YuNet Face Detection:   {yunet_ms:6.1f} ms  {yunet_flag}"
                                  f"\n  ├─ 3. Quality & CLAHE Crop:   {quality_ms:6.1f} ms  {quality_flag}"
                                  f"\n  ├─ 4. SFace NN Inference:     {sface_ms:6.1f} ms  {sface_flag}"
                                  f"\n  ├─ 5. DB Vector Matching:     {t_match_ms:6.1f} ms"
                                  f"\n  └─ TOTAL PROCESSING TIME:     {total_proc_ms:6.1f} ms  [Target: <50ms]"
                                  f"\n======================================================================", flush=True)

                            q_norm = embedding / np.linalg.norm(embedding) if embedding is not None and np.linalg.norm(embedding) > 0 else embedding

                            if matched_track_key:
                                active_spatial_tracks[matched_track_key] = {
                                    "last_seen": now,
                                    "bbox": (x1, y1, x2, y2),
                                    "norm_emb": q_norm,
                                    "matched_id": matched_id,
                                    "score": score
                                }

                            # Secondary Spatial-Temporal Track Continuity check for turning head
                            if not matched_id and active_recognized_tracks and embedding is not None:
                                for r_id, r_info in list(active_recognized_tracks.items()):
                                    if now - r_info.get("last_seen", 0.0) <= 3.5:
                                        rx1, ry1, rx2, ry2 = r_info["bbox"]
                                        rcx, rcy = (rx1 + rx2) / 2.0, (ry1 + ry2) / 2.0
                                        dist = np.hypot(cx - rcx, cy - rcy)
                                        sim = self._calc_similarity(r_info.get("norm_emb"), embedding)
                                        if dist < 160 and sim >= 0.28:
                                            matched_id = r_id
                                            score = max(score, sim, 0.40)
                                            break
                            
                            # Always generate crop_qimg for detected face so profile thumbnail is created regardless of preview state
                            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                            ch, cw, cc = crop_rgb.shape
                            crop_bytes = bytes(crop_rgb.data)
                            crop_qimg = QImage(crop_bytes, cw, ch, cc * cw, QImage.Format.Format_RGB888).copy()

                            if matched_id:
                                # Update active recognized track for turned head continuity
                                active_recognized_tracks[matched_id] = {
                                    "last_seen": now,
                                    "bbox": (x1, y1, x2, y2),
                                    "norm_emb": q_norm,
                                    "score": score
                                }

                                name_disp = client_map.get(matched_id, f"Client #{matched_id}")
                                color = (0, 180, 80)
                                label = f"OK {name_disp} ({score*100:.0f}%)"

                                print(f"[🎯 MATCHED FACE] {name_disp} (ID #{matched_id}) | Similarity Score: {score*100:.1f}%", flush=True)

                                # Auto-purge any transient or persistent unknown entries matching this recognized client!
                                to_purge = []
                                for unk_k, unk_v in list(persistent_unknown_faces.items()):
                                    if self._calc_similarity(unk_v.get("embedding"), embedding) >= 0.28:
                                        to_purge.append(unk_k)
                                for pk in to_purge:
                                    persistent_unknown_faces.pop(pk, None)
                                if to_purge:
                                    self.unknown_purged.emit(list(to_purge))

                                # Also purge matching pending transients
                                to_purge_pending = []
                                for pk, pd in list(pending_unknowns.items()):
                                    if self._calc_similarity(pd.get("embedding"), embedding) >= 0.28:
                                        to_purge_pending.append(pk)
                                for pk in to_purge_pending:
                                    pending_unknowns.pop(pk, None)

                                _, should_log = self.cooldown_mgr.process_detection(matched_id, "Guichet")
                                if should_log:
                                    try:
                                        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
                                        prof_path = PROFILES_DIR / f"{matched_id}.jpg"
                                        should_write = not prof_path.exists()
                                        if should_write:
                                            cv2.imwrite(str(prof_path), crop)
                                    except Exception:
                                        pass
                                    try:
                                        if reception.log_check_in(matched_id, "Guichet", score, STATUS_NEW_VISIT):
                                            self.client_detected.emit(matched_id, name_disp, float(score))
                                            if reception.is_remote():
                                                try:
                                                    conn = reception.get_connection()
                                                    if hasattr(conn, "push_live_detection"):
                                                        conn.push_live_detection({"client_id": matched_id, "name": name_disp, "score": float(score), "ts": time.time()})
                                                except Exception:
                                                    pass
                                    except Exception as e_checkin:
                                        try:
                                            reception.log_system_error("camera_thread log_check_in error", e_checkin)
                                        except Exception:
                                            pass

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

                                # 1. Match against existing persistent unknown faces
                                for fk, fd in list(persistent_unknown_faces.items()):
                                    if self._calc_similarity(fd.get("embedding"), embedding) >= self._seuil_similarite():
                                        new_matched_key = fk
                                        break
                                            
                                if new_matched_key:
                                    # Burst quality ranking: upgrade thumbnail if clearer frame detected
                                    existing_q = persistent_unknown_faces[new_matched_key].get("quality_score", 0.0)
                                    if crop_quality >= existing_q or "crop_qimg" not in persistent_unknown_faces[new_matched_key]:
                                        if crop_qimg and not crop_qimg.isNull():
                                            persistent_unknown_faces[new_matched_key]["crop_qimg"] = crop_qimg
                                        persistent_unknown_faces[new_matched_key]["embedding"] = embedding
                                        persistent_unknown_faces[new_matched_key]["quality_score"] = crop_quality

                                    current_detected_summary[new_matched_key] = persistent_unknown_faces[new_matched_key]
                                    active_boxes.append((x1, y1, x2, y2, color, persistent_unknown_faces[new_matched_key].get("name", "Nouveau Client")))
                                else:
                                    # 2. Check 0.3s (2-3 frame) transient verification buffer for unknown visitors
                                    pending_matched_id = None
                                    for pk, pd in list(pending_unknowns.items()):
                                        if self._calc_similarity(pd.get("embedding"), embedding) >= self._seuil_similarite():
                                            pending_matched_id = pk
                                            break

                                    if pending_matched_id:
                                        p_entry = pending_unknowns[pending_matched_id]
                                        p_entry["hits"] += 1
                                        p_entry["last_seen"] = now
                                        if crop_quality > p_entry.get("quality_score", 0.0):
                                            p_entry["quality_score"] = crop_quality
                                            p_entry["crop_qimg"] = crop_qimg
                                            p_entry["embedding"] = embedding

                                        elapsed = now - p_entry["first_seen"]
                                        # Verification condition: 2 to 3 consecutive detections within 0.2-0.35s
                                        if p_entry["hits"] >= 3 or (p_entry["hits"] >= 2 and elapsed >= 0.20):
                                            self.memoire_inconnus["compteur"] += 1
                                            self.memoire_inconnus["dernier_ajout"] = now
                                            temp_key = f"new_{self.memoire_inconnus['compteur']}"
                                            persistent_unknown_faces[temp_key] = {
                                                "client_id": temp_key,
                                                "name": "Nouveau Client" if auth.session_state.lang == "fr" else "زائر جديد",
                                                "status": "new",
                                                "crop_qimg": p_entry.get("crop_qimg", crop_qimg),
                                                "embedding": p_entry.get("embedding", embedding),
                                                "quality_score": p_entry.get("quality_score", crop_quality)
                                            }
                                            pending_unknowns.pop(pending_matched_id, None)
                                            print(f"[❓ NEW VISITOR] Registered unknown visitor entry #{self.memoire_inconnus['compteur']} (Key: {temp_key})", flush=True)

                                            if reception.is_remote():
                                                try:
                                                    conn = reception.get_connection()
                                                    if hasattr(conn, "push_unknown_visitor"):
                                                        conn.push_unknown_visitor({
                                                            "client_id": temp_key,
                                                            "name": persistent_unknown_faces[temp_key]["name"],
                                                            "status": "new"
                                                        })
                                                except Exception:
                                                    pass

                                            current_detected_summary[temp_key] = persistent_unknown_faces[temp_key]
                                            active_boxes.append((x1, y1, x2, y2, color, persistent_unknown_faces[temp_key]["name"]))
                                    else:
                                        # Register transient candidate frame (discarded if single glitch frame)
                                        import random
                                        p_id = f"pending_{now:.3f}_{random.randint(1000, 9999)}"
                                        pending_unknowns[p_id] = {
                                            "hits": 1,
                                            "first_seen": now,
                                            "last_seen": now,
                                            "crop_qimg": crop_qimg,
                                            "embedding": embedding,
                                            "quality_score": crop_quality
                                        }

                        detected_faces_summary = current_detected_summary
                    except Exception as e_det:
                        try:
                            from system_guardian import log_system_error
                            log_system_error("CameraThread detection step error", e_det)
                        except Exception:
                            pass

                if preview and display_frame is not None:
                    for x1, y1, x2, y2, color, label in active_boxes:
                        cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                        cv2.rectangle(display_frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
                        cv2.putText(display_frame, label, (x1 + 3, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

                    rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_frame.shape
                    img_bytes = bytes(rgb_frame.data)
                    q_img = QImage(img_bytes, w, h, ch * w, QImage.Format.Format_RGB888).copy()

                    self.frame_ready.emit(q_img, list(detected_faces_summary.values()))
                elif not preview and should_detect:
                    # Background mode: GUI video rendering is paused, but emit detected faces to UI list & toast!
                    self.frame_ready.emit(QImage(), list(detected_faces_summary.values()))

                time.sleep(0.002)
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
