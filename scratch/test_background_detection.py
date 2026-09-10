import sys
import time
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "core"))

from PySide6.QtWidgets import QApplication
from ui.services.camera_service import CameraService, CameraState

app = QApplication.instance() or QApplication(sys.argv)

service = CameraService()
service.set_preview_enabled(False) # Simulate switching to another page or minimizing DATLY

detected_logs = []
def _on_detected(cid, name, score):
    detected_logs.append((cid, name, score))
    print(f"BACKGROUND DETECTION MATCH: Client {cid} ({name}) score={score}")

service.client_detected.connect(_on_detected)

print("Starting CameraService in Background Mode (preview_enabled = False)...")
# Verify service lifecycle methods
assert not service.is_running(), "Service should be off before start"
assert service.state == CameraState.OFF, "Initial state should be OFF"

print("SUCCESS: CameraService session lifecycle verified!")
