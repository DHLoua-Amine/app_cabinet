import sys
import os
BASE = os.path.abspath('.')
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'core'))

import numpy as np
import cv2
from ui.components.camera_thread import CameraThread

def test_camera_thread_quality():
    th = CameraThread(source=0)
    
    # 1. Create a dark / blurry crop
    blurry_crop = np.zeros((80, 80, 3), dtype=np.uint8)
    cv2.GaussianBlur(blurry_crop, (15, 15), 0, dst=blurry_crop)
    
    # 2. Create a sharp, well-lit crop
    sharp_crop = np.full((120, 120, 3), 130, dtype=np.uint8)
    # Add fake facial features (eyes, mouth edges)
    cv2.circle(sharp_crop, (30, 40), 10, (20, 20, 20), -1)
    cv2.circle(sharp_crop, (90, 40), 10, (20, 20, 20), -1)
    cv2.line(sharp_crop, (40, 90), (80, 90), (30, 30, 30), 4)
    
    score_blurry = th._evaluate_face_quality(blurry_crop)
    score_sharp = th._evaluate_face_quality(sharp_crop)
    
    print(f"Blurry crop face score: {score_blurry:.2f}")
    print(f"Sharp crop face score:  {score_sharp:.2f}")
    
    assert score_sharp > score_blurry, "Sharp, well-lit crop must score higher than blurry crop!"
    print("CameraThread Quality Ranking Test: PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_camera_thread_quality()
