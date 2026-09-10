import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "core") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "core"))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv2
from camera import VideoCaptureThread, check_ip_reachable, probe_camera_stream

def test_camera_stream_logic():
    print("[TEST] Testing camera stream logic...")
    
    # Test check_ip_reachable with invalid IP
    assert check_ip_reachable("http://127.0.0.1:9999/video", timeout=0.2) == False
    print("[SUCCESS] check_ip_reachable correctly handles unreachable URL")

    # Test VideoCaptureThread instantiation with dummy URL
    vt = VideoCaptureThread("http://127.0.0.1:9999/video")
    vt.start()
    if vt.thread:
        vt.thread.join(timeout=3.0)
    assert vt.failed == True, "VideoCaptureThread should fail cleanly for unreachable IP"
    assert vt.running == False, "VideoCaptureThread should stop running on failure"
    print("[SUCCESS] VideoCaptureThread handles unreachable URL cleanly without crashing")

    print("[ALL CAMERA TESTS PASSED]")

if __name__ == "__main__":
    test_camera_stream_logic()
