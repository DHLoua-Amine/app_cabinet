import sys
import os
import time
import json
import hashlib
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
import reception
import config
from ui.main_window import MainWindow

DB_PATH = os.path.expanduser('~') + r'\AppData\Local\CabinetNotarialZarai\data\reception.db'
initial_checksum = hashlib.sha256(open(DB_PATH, 'rb').read()).hexdigest()

print("=== STARTING PERFORMANCE & CAMERA DIAGNOSTICS ===")

# --- 1. LOCAL ADMIN MODE BENCHMARK ---
auth.session_state.logged_in = True
auth.session_state.username = "admin"
auth.session_state.role = "admin"

win = MainWindow()

pages = ["home", "register", "clients", "presence", "compta", "scanner", "settings"]

print("\n--- MEASURING PAGE NAVIGATION LATENCY (CAMERA OFF - LOCAL ADMIN) ---")
cam_off_times = {}
for p in pages:
    if win.may_open(p):
        t0 = time.perf_counter()
        win.switch_page(p)
        t1 = time.perf_counter()
        dur_ms = (t1 - t0) * 1000
        cam_off_times[p] = round(dur_ms, 2)
        print(f"  Page {p:10s}: {dur_ms:7.2f} ms")

print("\n--- MEASURING PAGE NAVIGATION LATENCY (CAMERA ON - LOCAL ADMIN) ---")
# Start camera service (mock or test camera if available, or force camera loop)
win.camera_service.start()
time.sleep(0.5)

cam_on_times = {}
for p in pages:
    if win.may_open(p):
        t0 = time.perf_counter()
        win.switch_page(p)
        t1 = time.perf_counter()
        dur_ms = (t1 - t0) * 1000
        cam_on_times[p] = round(dur_ms, 2)
        print(f"  Page {p:10s}: {dur_ms:7.2f} ms")

win.camera_service.stop()

# --- 2. PRESENCE PAGE DEEP DIVE & CACHE INVESTIGATION ---
print("\n--- INVESTIGATING PRESENCE PAGE & CACHE INVALIDATION ---")
t0 = time.perf_counter()
df_recent = reception.get_recent_check_ins(limit=200)
t_recent = (time.perf_counter() - t0) * 1000

t0 = time.perf_counter()
n_total = reception.count_check_ins()
t_count = (time.perf_counter() - t0) * 1000

t0 = time.perf_counter()
n_today = reception.count_check_ins_today()
t_today = (time.perf_counter() - t0) * 1000

t0 = time.perf_counter()
ids, embs = reception.get_all_face_embeddings()
t_embs = (time.perf_counter() - t0) * 1000

print(f"  get_recent_check_ins(200): {t_recent:.2f} ms")
print(f"  count_check_ins:          {t_count:.2f} ms")
print(f"  count_check_ins_today:    {t_today:.2f} ms")
print(f"  get_all_face_embeddings:  {t_embs:.2f} ms ({len(ids)} faces loaded)")

# Test cache invalidation impact
print("  Simulating check-in log (which calls clear_db_caches())...")
reception.clear_db_caches()

t0 = time.perf_counter()
ids, embs = reception.get_all_face_embeddings()
t_embs_after_clear = (time.perf_counter() - t0) * 1000
print(f"  get_all_face_embeddings (POST CLEAR): {t_embs_after_clear:.2f} ms")

final_checksum = hashlib.sha256(open(DB_PATH, 'rb').read()).hexdigest()
print(f"\n=== DB CHECKSUM VERIFICATION ===")
print(f"Initial: {initial_checksum}")
print(f"Final:   {final_checksum}")
print(f"DB Unchanged: {initial_checksum == final_checksum}")

perf_results = {
    "cam_off_times": cam_off_times,
    "cam_on_times": cam_on_times,
    "presence_details": {
        "recent_ms": t_recent,
        "count_ms": t_count,
        "today_ms": t_today,
        "embs_cached_ms": t_embs,
        "embs_uncached_ms": t_embs_after_clear
    }
}

with open(workspace_dir / "scratch" / "perf_results.json", "w") as f:
    json.dump(perf_results, f, indent=2)

win.close()
