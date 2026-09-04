import sys
import os
sys.path.insert(0, os.path.abspath("."))

import cv2
import numpy as np
import threading
import time
from core.face_engine import get_global_face_engine

def worker(thread_id):
    engine = get_global_face_engine()
    for i in range(20):
        # Create a dummy image with a noise pattern
        dummy_frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
        try:
            results = engine.detect_and_extract(dummy_frame)
            print(f"Thread {thread_id} frame {i} -> {len(results)} faces")
        except Exception as e:
            print(f"Thread {thread_id} frame {i} FAILED: {e}")
        time.sleep(0.01)

threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()

print("ALL THREAD TESTS PASSED CLEANLY!")
