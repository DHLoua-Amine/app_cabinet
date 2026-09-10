import sys
import os
import time
import hashlib
import threading
from pathlib import Path

workspace_dir = Path(__file__).resolve().parent.parent
core_dir = workspace_dir / "core"

for p in [str(workspace_dir), str(core_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.chdir(workspace_dir)

import auth
import config
import reception
from db_server import DatabaseServer

DB_PATH = os.path.expanduser('~') + r'\AppData\Local\CabinetNotarialZarai\data\reception.db'

# Start local DatabaseServer
TOKEN = "test_token_123"
server = DatabaseServer(db_path=DB_PATH, token=TOKEN, host="127.0.0.1", port=15556)
server_thread = threading.Thread(target=server.start, daemon=True)
server_thread.start()
time.sleep(1.0)

# Configure network config to point to local server
original_net_cfg = config.load_network_config()
config.save_network_config({
    "mode": "workstation",
    "host": "127.0.0.1",
    "port": 15556,
    "token": TOKEN
})

# Set secretary identity
auth.session_state.logged_in = True
auth.session_state.username = "secrétaire"
auth.session_state.role = "secretary"
reception.set_remote_identity("secrétaire", "pass123")

print("Is Remote:", reception.is_remote())

# Run log_check_in directly and print exception traceback
client_id = "CLI-9999-9999" # fresh client_id so 15s dedup doesn't trigger
now_str = "2026-09-06 14:00:00"
annee_mois = "2026-09"

try:
    with reception.get_db_cursor(commit=True) as cursor:
        print("Executing PRAGMA table_info(check_ins)...")
        cursor.execute("PRAGMA table_info(check_ins)")
        rows = cursor.fetchall()
        print(f"Columns fetched: {[r['name'] for r in rows]}")

        print("Executing INSERT INTO check_ins...")
        cursor.execute("""
            INSERT INTO check_ins (client_id, window_number, timestamp, confidence_score, status)
            VALUES (?, ?, ?, ?, ?)
        """, (client_id, "Guichet", now_str, 0.95, "Arrivé"))
        print("INSERT INTO check_ins SUCCESS")

        print("Executing INSERT INTO monthly_visit_stats...")
        cursor.execute("""
            INSERT INTO monthly_visit_stats (annee_mois, nombre_visites, montant_avances, montant_total)
            VALUES (?, 1, 0.0, 0.0)
            ON CONFLICT(annee_mois) DO UPDATE SET
                nombre_visites = nombre_visites + 1
        """, (annee_mois,))
        print("INSERT INTO monthly_visit_stats SUCCESS")

except Exception as e:
    import traceback
    print("!!! EXCEPTION RAISED IN SECRETARY LOG_CHECK_IN !!!")
    print(traceback.format_exc())

server.stop()
config.save_network_config(original_net_cfg)
