import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv2
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
    def __init__(self, score_threshold: float = 0.55, nms_threshold: float = 0.3, top_k: int = 5000):
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.top_k = top_k
        self.detector = None
        self.recognizer = None
        self._lock = threading.Lock()
        self._init_models()

    def _init_models(self):
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

    def detect_and_extract(self, frame_bgr: np.ndarray, non_blocking: bool = False, roi_box: Optional[Tuple[float, float, float, float]] = None) -> List[Dict]:
        if frame_bgr is None:
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

                # Fast Downscale to 640px max width for 5X faster YuNet inference
                max_dim = 640
                if max(orig_h, orig_w) > max_dim:
                    scale = max_dim / float(max(orig_h, orig_w))
                    target_w = int(orig_w * scale)
                    target_h = int(orig_h * scale)
                    resized_frame = cv2.resize(working_frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                else:
                    scale = 1.0
                    resized_frame = working_frame
                    target_w, target_h = orig_w, orig_h

                self.detector.setInputSize((target_w, target_h))
                _, faces = self.detector.detect(resized_frame)

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
                        
                        # Accept faces down to 30x30 pixels (for hallway/wall camera distances)
                        if x2 - x1 < 30 or y2 - y1 < 30:
                            continue

                        # Frontal/Angled Pose Filter: Permissive angle check (0.75) for walking clients
                        try:
                            re_x, le_x = scaled_face[4], scaled_face[6]
                            nose_x = scaled_face[8]
                            eye_dist = abs(le_x - re_x)
                            if eye_dist > 3:
                                dist_re_nose = abs(nose_x - re_x)
                                dist_le_nose = abs(le_x - nose_x)
                                asym_ratio = abs(dist_re_nose - dist_le_nose) / eye_dist
                                if asym_ratio > 0.75:
                                    continue  # Reject extreme 90-degree profile faces only
                        except Exception:
                            pass

                        crop = working_frame[y1:y2, x1:x2].copy()
                        if crop is None or crop.size == 0:
                            continue

                        # Anti-Blur Laplacian Filter: Relaxed threshold (10.0) for RTSP security video streams
                        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
                        blur_var = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())
                        if blur_var < 10.0:
                            continue

                        # Apply CLAHE contrast enhancement to handle backlit/shadowed faces
                        enhanced_frame = apply_clahe_contrast(working_frame)
                        enhanced_crop = apply_clahe_contrast(crop)

                        # Align & crop using full-resolution frame for maximum SFace feature accuracy
                        aligned = self.recognizer.alignCrop(enhanced_frame, scaled_face)
                        embedding = self.recognizer.feature(aligned).flatten()

                        actual_x1 = x1 + roi_offset_x
                        actual_y1 = y1 + roi_offset_y
                        actual_x2 = x2 + roi_offset_x
                        actual_y2 = y2 + roi_offset_y

                        results.append({
                            "bbox": (actual_x1, actual_y1, actual_x2, actual_y2),
                            "crop": enhanced_crop,
                            "raw_crop": crop,
                            "embedding": embedding,
                            "face_row": scaled_face,
                            "blur_var": blur_var
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
                cos_scores = np.dot(matrix_norm, q_norm)
                best_idx = np.argmax(cos_scores)
                best_score = float(cos_scores[best_idx])
                if best_score >= threshold:
                    return valid_ids[best_idx], best_score
                return None, best_score

            if not db_clients:
                return None, 0.0

            valid_ids = []
            valid_embs = []
            for client in db_clients:
                db_emb = client.get("embedding")
                if db_emb is not None and len(db_emb) == len(query_emb):
                    valid_ids.append(client["client_id"])
                    valid_embs.append(db_emb)

            if not valid_embs:
                return None, 0.0

            matrix = np.vstack(valid_embs).astype(np.float32)
            m_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            m_norms[m_norms == 0] = 1.0
            matrix_norm = matrix / m_norms

            cos_scores = np.dot(matrix_norm, q_norm)
            best_idx = np.argmax(cos_scores)
            best_score = float(cos_scores[best_idx])

            if best_score >= threshold:
                return valid_ids[best_idx], best_score
            return None, best_score
        except Exception:
            # Fallback to SFace C++ match
            best_id = None
            best_score = 0.0
            for client in db_clients:
                db_emb = client.get("embedding")
                if db_emb is None or self.recognizer is None:
                    continue
                try:
                    score_cos = self.recognizer.match(query_emb, db_emb, cv2.FaceRecognizerSF_FR_COSINE)
                    if score_cos > best_score:
                        best_score = score_cos
                        best_id = client["client_id"]
                except Exception as match_err:
                    # (b) One unusable stored embedding must not stop everyone else
                    # from being recognised - but a client who can never match is
                    # invisible to the camera forever, so it is counted and
                    # reported once per call rather than per client.
                    _match_failures.append(
                        f"{client.get('client_id')}: {match_err}")
            if best_score >= threshold:
                if _match_failures:
                    log_system_error(
                        f"face matching skipped {len(_match_failures)} stored "
                        f"embedding(s) - those clients cannot be recognised",
                        ValueError('; '.join(_match_failures[:10])))
                return best_id, best_score
            return None, best_score
