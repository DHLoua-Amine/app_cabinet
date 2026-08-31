import sys
import os
import time
import sqlite3
import threading
from pathlib import Path

# Force UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

import config
import reception
import permissions
import db_server
import db_client

permissions.session.sign_in("admin", permissions.ROLE_ADMIN, "Notaire (Admin)")

print("=== RECEPTION API MULTI-MACHINE REAL-TIME DB SHARING TEST ===")

# Create test DB
test_db_path = BASE_DIR / "scratch" / "test_reception_remote.db"
if test_db_path.exists():
    test_db_path.unlink()

reception.DB_PATH = test_db_path
reception.init_db()

# Start DatabaseServer
shared_token = "reception-office-token-999"
server_port = 9877

server = db_server.DatabaseServer(
    db_path=test_db_path,
    token=shared_token,
    host="127.0.0.1",
    port=server_port
)

server.start()
print(f"1. DatabaseServer running on 127.0.0.1:{server_port}")

# Save network configuration to pretend we are in Workstation mode
config.save_network_config({
    "mode": config.MODE_WORKSTATION,
    "host": "127.0.0.1",
    "port": server_port,
    "token": shared_token
})

# Verify reception.is_remote() is True
print("2. Checking reception.is_remote():", reception.is_remote())
assert reception.is_remote() is True, "reception.is_remote() must be True in Workstation mode"

# Call reception.register_client() on Workstation 1 (Notary)
print("\n3. Workstation 1 (Notary) registering client via reception.register_client()...")
new_cid = reception.register_client(nom="Ben Ahmed", prenom="Tarak Remote", phone="71999888")
print(f"   ✓ Registered client '{new_cid}' over network connection!")

# Call reception.get_all_clients() on Workstation 2 (Secretary)
print("\n4. Workstation 2 (Secretary) reading client list via reception.get_all_clients()...")
all_clients = reception.get_all_clients()
print(f"   ✓ Workstation 2 retrieved {len(all_clients)} clients:")
for c in all_clients:
    print(f"     - Client ID: {c['client_id']} | Name: {c['full_name']} | Phone: {c['phone']}")

# Verify the client is found
found = any(c['client_id'] == new_cid for c in all_clients)
assert found is True, "Workstation 2 MUST see the client registered by Workstation 1 over TCP!"
print("\n[PASS] Reception API Multi-Machine Real-Time Data Sharing Verified 100% Success!")

# Cleanup: reset network config to Standalone
config.save_network_config({"mode": config.MODE_STANDALONE, "host": "", "port": config.DEFAULT_DB_PORT, "token": ""})
server.stop()
print("=== RECEPTION REMOTE TEST COMPLETE ===")
