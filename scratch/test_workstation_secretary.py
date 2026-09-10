import sys
import os
import time
import json
import hashlib
import threading
from pathlib import Path
from PySide6.QtWidgets import QApplication

workspace_dir = Path(__file__).resolve().parent.parent
core_dir = workspace_dir / "core"

for p in [str(workspace_dir), str(core_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.chdir(workspace_dir)

app = QApplication.instance()
if not app:
    app = QApplication([])

import auth
import config
import reception
from db_server import DatabaseServer

DB_PATH = os.path.expanduser('~') + r'\AppData\Local\CabinetNotarialZarai\data\reception.db'
initial_checksum = hashlib.sha256(open(DB_PATH, 'rb').read()).hexdigest()

print("=== STARTING WORKSTATION / SECRETARY SIMULATION DIAGNOSTICS ===")

# 1. Start local DatabaseServer
TOKEN = "test_token_123"
server = DatabaseServer(db_path=DB_PATH, token=TOKEN, host="127.0.0.1", port=15555)
server_thread = threading.Thread(target=server.start, daemon=True)
server_thread.start()
time.sleep(1.0)
print(f"DatabaseServer started on 127.0.0.1:15555 (listening={server.running})")

# 2. Configure network config to point to local server
original_net_cfg = config.load_network_config()
config.save_network_config({
    "mode": "workstation",
    "host": "127.0.0.1",
    "port": 15555,
    "token": TOKEN
})

# Set secretary identity
auth.session_state.logged_in = True
auth.session_state.username = "secrétaire"
auth.session_state.role = "secretary"
reception.set_remote_identity("secrétaire", "pass123")

print("Is Remote Network Workstation mode active:", reception.is_remote())

from ui.main_window import MainWindow

win = MainWindow()

pages = ["home", "register", "clients", "presence", "settings"]

print("\n--- MEASURING PAGE NAVIGATION LATENCY (WORKSTATION - SECRETARY MODE - CAMERA OFF) ---")
ws_cam_off_times = {}
for p in pages:
    if win.may_open(p):
        t0 = time.perf_counter()
        win.switch_page(p)
        t1 = time.perf_counter()
        dur_ms = (t1 - t0) * 1000
        ws_cam_off_times[p] = round(dur_ms, 2)
        print(f"  Page {p:10s}: {dur_ms:7.2f} ms")

print("\n--- MEASURING PAGE NAVIGATION LATENCY (WORKSTATION - SECRETARY MODE - CAMERA ON) ---")
win.camera_service.start()
time.sleep(0.5)

ws_cam_on_times = {}
for p in pages:
    if win.may_open(p):
        t0 = time.perf_counter()
        win.switch_page(p)
        t1 = time.perf_counter()
        dur_ms = (t1 - t0) * 1000
        ws_cam_on_times[p] = round(dur_ms, 2)
        print(f"  Page {p:10s}: {dur_ms:7.2f} ms")

# --- SIMULATE CHECK-IN INVOCATIONS IN BACKGROUND (SECRETARY CAMERA THREAD IMPACT) ---
print("\n--- TESTING CAMERA CHECK-IN LOGGING IN WORKSTATION MODE ---")
sec_crash_captured = None
try:
    # Test log_check_in under secretary role over network connection
    ok = reception.log_check_in("CLI-2026-001", "Guichet", 0.95, "Arrivé")
    print(f"  reception.log_check_in over workstation network: {ok}")

    conn = reception.get_connection()
    print(f"  Connection type: {type(conn).__name__}")
    
    # Test push_live_detection
    if hasattr(conn, "push_live_detection"):
        res = conn.push_live_detection({"client_id": "CLI-2026-001", "name": "Test Client", "score": 0.95, "ts": time.time()})
        print(f"  push_live_detection: {res}")
    
    # Test push_unknown_visitor
    if hasattr(conn, "push_unknown_visitor"):
        res = conn.push_unknown_visitor({"client_id": "new_1", "name": "Nouveau Client", "status": "new"})
        print(f"  push_unknown_visitor: {res}")

except Exception as e:
    import traceback
    sec_crash_captured = traceback.format_exc()
    print("!!! CAPTURED WORKSTATION SECRETARY CRASH !!!")
    print(sec_crash_captured)

win.camera_service.stop()
win.close()
server.stop()

# Restore original network config
config.save_network_config(original_net_cfg)

final_checksum = hashlib.sha256(open(DB_PATH, 'rb').read()).hexdigest()
print(f"\n=== DB CHECKSUM VERIFICATION ===")
print(f"Initial: {initial_checksum}")
print(f"Final:   {final_checksum}")
print(f"DB Unchanged: {initial_checksum == final_checksum}")

ws_results = {
    "ws_cam_off_times": ws_cam_off_times,
    "ws_cam_on_times": ws_cam_on_times,
    "sec_crash_captured": sec_crash_captured
}

with open(workspace_dir / "scratch" / "ws_results.json", "w") as f:
    json.dump(ws_results, f, indent=2)

print("\n=== WORKSTATION SECRETARY DIAGNOSTICS COMPLETE ===")
