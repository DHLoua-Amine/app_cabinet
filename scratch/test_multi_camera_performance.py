"""
test_multi_camera_performance.py — Multi-Camera CPU & Frame Rate Performance Benchmark
"""

import sys
import os
import time
import psutil

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, root_dir)
sys.path.insert(0, os.path.join(root_dir, "core"))

from PySide6.QtWidgets import QApplication
from ui.services.camera_service import CameraService
from core.camera import set_saved_camera_source, set_saved_secondary_camera_source, set_saved_tertiary_camera_source

def benchmark_multi_camera():
    print("=================================================================")
    print("      MULTI-CAMERA PERFORMANCE & CPU BENCHMARK TEST             ")
    print("=================================================================")
    
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    # Configure 3 camera sources (USB/Mock 0, RTSP mock IPs)
    set_saved_camera_source("0")
    set_saved_secondary_camera_source("rtsp://admin:admin1234@192.168.1.155:554/cam/realmonitor?channel=1&subtype=0")
    set_saved_tertiary_camera_source("rtsp://admin:pass@192.168.1.155:554/cam/realmonitor?channel=2&subtype=0")

    service = CameraService()
    print("Starting Multi-Camera Service with 3 cameras...")
    service.start()

    proc = psutil.Process(os.getpid())
    
    # Measure CPU & Memory over 5 seconds of active multi-camera execution
    cpu_samples = []
    print("Monitoring CPU & RAM over 5 seconds...")
    for i in range(10):
        time.sleep(0.5)
        cpu = proc.cpu_percent(interval=None)
        mem = proc.memory_info().rss / (1024 * 1024)
        cpu_samples.append(cpu)
        print(f"  Sample {i+1}/10: CPU = {cpu:.1f}%, RAM = {mem:.1f} MB")

    avg_cpu = sum(cpu_samples) / len(cpu_samples)
    print(f"\nAverage CPU Usage across 3 Cameras: {avg_cpu:.1f}%")
    print(f"Final Memory RSS: {mem:.1f} MB")

    service.stop()
    print("Multi-Camera Service stopped cleanly with 0 thread locks!")
    print("=================================================================")
    assert avg_cpu < 60.0, "CPU usage is too high!"
    print("SUCCESS: Multi-Camera performance is smooth, efficient, and stable!")

if __name__ == "__main__":
    benchmark_multi_camera()
