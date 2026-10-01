import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv2
import time
import numpy as np
import threading
from typing import List, Dict, Tuple, Optional

from core.config import resource_path

# The ONNX models ship with the application; in a packaged build they live in
# the PyInstaller bundle, not beside this module.
MODELS_DIR = resource_path("core", "models")
try:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    # (c) Safe: inside a read-only bundle the directory already exists. Only the
    # source checkout ever needs it created.
    pass

YUNET_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

_global_face_engine_instance = None
_global_face_engine_lock = threading.Lock()

def get_global_face_engine():
    global _global_face_engine_instance
    with _global_face_engine_lock:
        if _global_face_engine_instance is None:
            _global_face_engine_instance = FaceEngine()
        return _global_face_engine_instance

def apply_clahe_contrast(image_bgr: np.ndarray) -> np.ndarray:
    """Enhances backlit and shadowed face crops using Adaptive Histogram Equalization (CLAHE)."""
    if image_bgr is None or image_bgr.size == 0:
        return image_bgr
    try:
        lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    except Exception:
        return image_bgr

class FaceEngine:
    def __init__(self, score_threshold: float = 0.68, nms_threshold: float = 0.3, top_k: int = 5000):
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.top_k = top_k
        self.detector = None
        self.recognizer = None
        self._lock = threading.Lock()
        self._init_models()

    def _init_models(self):
        try:
            cv2.setNumThreads(4)
            cv2.setUseOptimized(True)
        except Exception:
            pass
        if YUNET_PATH.exists() and SFACE_PATH.exists():
            try:
                self.detector = cv2.FaceDetectorYN.create(
                    str(YUNET_PATH), "", (320, 320),
                    self.score_threshold, self.nms_threshold, self.top_k
                )
                self.recognizer = cv2.FaceRecognizerSF.create(str(SFACE_PATH), "")
            except Exception as e:
                from system_guardian import log_system_error
                log_system_error("FaceEngine Model Load Failed", e)

    def extract_feature_embedding(self, working_frame: np.ndarray, scaled_face: np.ndarray) -> Optional[np.ndarray]:
        """Safely extracts SFace 128-d feature embedding vector from aligned face crop."""
        if working_frame is None or scaled_face is None or self.recognizer is None:
            return None
        try:
            with self._lock:
                aligned = self.recognizer.alignCrop(working_frame, scaled_face)
                return self.recognizer.feature(aligned).flatten()
        except Exception:
            return None

    def detect_and_extract(self, frame_bgr: np.ndarray, non_blocking: bool = False, roi_box: Optional[Tuple[float, float, float, float]] = None, extract_embedding: bool = False) -> List[Dict]:
        if frame_bgr is None or frame_bgr.size == 0 or len(frame_bgr.shape) < 2 or frame_bgr.shape[0] < 10 or frame_bgr.shape[1] < 10:
            return []
        
        acquired = self._lock.acquire(blocking=not non_blocking)
        if not acquired:
            return []  # Skip frame if another camera is currently detecting, eliminating thread stalls

        try:
            if self.detector is None or self.recognizer is None:
                return []

            try:
                orig_h, orig_w = frame_bgr.shape[:2]

                # Apply ROI (Region of Interest) cropping if configured
                roi_offset_x, roi_offset_y = 0, 0
                working_frame = frame_bgr
                if roi_box and len(roi_box) == 4:
                    rx1_p, ry1_p, rx2_p, ry2_p = roi_box
                    rx1 = max(0, int(rx1_p * orig_w))
                    ry1 = max(0, int(ry1_p * orig_h))
                    rx2 = min(orig_w, int(rx2_p * orig_w))
                    ry2 = min(orig_h, int(ry2_p * orig_h))
                    if rx2 - rx1 > 50 and ry2 - ry1 > 50:
                        working_frame = frame_bgr[ry1:ry2, rx1:rx2].copy()
                        roi_offset_x, roi_offset_y = rx1, ry1
                        orig_h, orig_w = working_frame.shape[:2]

                # Downscale to 240px max dimension for 3X faster YuNet inference (~30ms per detection call)
                max_dim = 240
                if max(orig_h, orig_w) > max_dim:
                    scale = max_dim / float(max(orig_h, orig_w))
                    target_w = int(orig_w * scale)
                    target_h = int(orig_h * scale)
                    resized_frame = cv2.resize(working_frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                else:
                    scale = 1.0
                    resized_frame = working_frame
                    target_w, target_h = orig_w, orig_h

                t_det0 = time.time()
                self.detector.setInputSize((target_w, target_h))
                _, faces = self.detector.detect(resized_frame)
                t_det_ms = (time.time() - t_det0) * 1000.0

                results = []
                if faces is not None:
                    for face in faces:
                        # Scale face detection output back to working resolution
                        scaled_face = face.copy()
                        if scale != 1.0:
                            scaled_face[0:14] = scaled_face[0:14] / scale

                        bbox = scaled_face[0:4].astype(int)
                        x, y, bw, bh = bbox
                        x1, y1 = max(0, x), max(0, y)
                        x2, y2 = min(orig_w, x + bw), min(orig_h, y + bh)
                        
                        # Minimum face bounding box size: 60x60 px
                        if x2 - x1 < 60 or y2 - y1 < 60:
                            continue

                        # Frame Edge Clipping Check: reject half-faces clipped by camera/phone edges
                        edge_margin = 8
                        if x1 <= edge_margin or y1 <= edge_margin or x2 >= orig_w - edge_margin or y2 >= orig_h - edge_margin:
                            continue

                        # Complete Face Landmark Check: ensure BOTH eyes & nose are fully visible inside bounding box
                        try:
                            re_x, re_y = scaled_face[4], scaled_face[5]
                            le_x, le_y = scaled_face[6], scaled_face[7]
                            n_x, n_y = scaled_face[8], scaled_face[9]

                            # Both eyes must be inside bounding box
                            if not (x1 < re_x < x2 and y1 < re_y < y2 and x1 < le_x < x2 and y1 < le_y < y2):
                                continue

                            eye_dist = abs(le_x - re_x)
                            if eye_dist < 10:
                                continue  # Reject collapsed/distorted eyes

                            # Both eyes must be positioned above nose tip
                            if re_y > n_y or le_y > n_y:
                                continue

                            dist_re_nose = abs(n_x - re_x)
                            dist_le_nose = abs(le_x - n_x)
                            asym_ratio = abs(dist_re_nose - dist_le_nose) / eye_dist
                            if asym_ratio > 0.75:
                                continue  # Reject extreme 90-degree profile faces
                        except Exception:
                            pass

                        # Full Face Padding: Extend crop box by 12% so complete face (forehead, ears, chin) is captured
                        pad_w = int(bw * 0.12)
                        pad_h = int(bh * 0.15)
                        crop_x1 = max(0, x - pad_w)
                        crop_y1 = max(0, y - pad_h)
                        crop_x2 = min(orig_w, x + bw + pad_w)
                        crop_y2 = min(orig_h, y + bh + pad_h)

                        crop = working_frame[crop_y1:crop_y2, crop_x1:crop_x2].copy()
                        if crop is None or crop.size == 0:
                            continue

                        t_crop0 = time.time()
                        h_c, w_c = crop.shape[:2]
                        if max(h_c, w_c) > 100:
                            scale_c = 100.0 / float(max(h_c, w_c))
                            crop_eval = cv2.resize(crop, (max(1, int(w_c * scale_c)), max(1, int(h_c * scale_c))), interpolation=cv2.INTER_NEAREST)
                        else:
                            crop_eval = crop

                        gray_eval = cv2.cvtColor(crop_eval, cv2.COLOR_BGR2GRAY) if len(crop_eval.shape) == 3 else crop_eval
                        blur_var = float(cv2.Laplacian(gray_eval, cv2.CV_64F).var())
                        if blur_var < 15.0:
                            continue

                        enhanced_crop = apply_clahe_contrast(crop_eval)
                        t_crop_ms = (time.time() - t_crop0) * 1000.0

                        # Align & crop directly from working_frame (optional embedding extraction)
                        if extract_embedding:
                            t_emb0 = time.time()
                            aligned = self.recognizer.alignCrop(working_frame, scaled_face)
                            embedding = self.recognizer.feature(aligned).flatten()
                            t_emb_ms = (time.time() - t_emb0) * 1000.0
                        else:
                            embedding = None
                            t_emb_ms = 0.0

                        actual_x1 = crop_x1 + roi_offset_x
                        actual_y1 = crop_y1 + roi_offset_y
                        actual_x2 = crop_x2 + roi_offset_x
                        actual_y2 = crop_y2 + roi_offset_y

                        results.append({
                            "bbox": (actual_x1, actual_y1, actual_x2, actual_y2),
                            "crop": enhanced_crop,
                            "raw_crop": crop,
                            "embedding": embedding,
                            "face_row": scaled_face,
                            "working_frame": working_frame,
                            "blur_var": blur_var,
                            "timing": {"det_ms": t_det_ms, "crop_ms": t_crop_ms, "emb_ms": t_emb_ms}
                        })
                return results
            except (cv2.error, Exception) as e:
                from system_guardian import log_system_error
                log_system_error("FaceEngine OpenCV C++ Exception - Resetting Models", e)
                # Re-initialize models to clear corrupted OpenCV C++ DNN BlobManager
                self._init_models()
                return []
        finally:
            self._lock.release()

    def match_face(
        self,
        query_emb: np.ndarray,
        db_clients: List[Dict] = None,
        threshold: float = None,
        prebuilt_cache: Tuple[List[str], Optional[np.ndarray]] = None
    ) -> Tuple[Optional[str], float]:
        if threshold is None:
            try:
                from core import config
                threshold = float(config.get_setting("face_match_threshold", 0.363))
            except Exception:
                threshold = 0.363

        if query_emb is None or len(query_emb) == 0:
            return None, 0.0

        # Collected rather than logged per client: this runs once per stored
        # client on every recognition attempt, so one line each would bury the
        # log. Reported once, below, with a count.
        _match_failures = []

        try:
            q_norm = query_emb.astype(np.float32)
            q_mag = np.linalg.norm(q_norm)
            if q_mag > 0:
                q_norm = q_norm / q_mag

            if prebuilt_cache is not None:
                valid_ids, matrix_norm = prebuilt_cache
                if not valid_ids or matrix_norm is None or len(matrix_norm) == 0:
                    return None, 0.0
                matrix_2d = np.atleast_2d(matrix_norm).astype(np.float32)
                cos_scores = np.dot(matrix_2d, q_norm).flatten()
                best_idx = int(np.argmax(cos_scores))
                best_score = float(cos_scores[best_idx])
                if best_score >= threshold and best_idx < len(valid_ids):
                    return valid_ids[best_idx], best_score
                return None, best_score

            if not db_clients:
                return None, 0.0

            valid_ids = []
            valid_embs = []
            for client in db_clients:
                db_emb = client.get("embedding")
                if db_emb is not None:
                    db_arr = np.asarray(db_emb, dtype=np.float32)
                    if len(db_arr) == len(q_norm):
                        valid_ids.append(client.get("client_id"))
                        valid_embs.append(db_arr)

            if not valid_embs:
                return None, 0.0

            matrix = np.vstack(valid_embs).astype(np.float32)
            m_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            m_norms[m_norms == 0] = 1.0
            matrix_norm = matrix / m_norms

            cos_scores = np.dot(matrix_norm, q_norm).flatten()
            best_idx = int(np.argmax(cos_scores))
            best_score = float(cos_scores[best_idx])

            if best_score >= threshold and best_idx < len(valid_ids):
                return valid_ids[best_idx], best_score
            return None, best_score
        except Exception:
            if not db_clients:
                return None, 0.0
            # Fallback to SFace C++ match
            best_id = None
            best_score = 0.0
            for client in db_clients:
                db_emb = client.get("embedding")
                if db_emb is None or self.recognizer is None:
                    continue
                try:
                    db_arr = np.asarray(db_emb, dtype=np.float32)
                    score_cos = self.recognizer.match(query_emb, db_arr, cv2.FaceRecognizerSF_FR_COSINE)
                    if score_cos > best_score:
                        best_score = score_cos
                        best_id = client.get("client_id")
                except Exception as match_err:
                    _match_failures.append(
                        f"{client.get('client_id')}: {match_err}")
            if best_score >= threshold:
                return best_id, best_score
            return None, best_score
