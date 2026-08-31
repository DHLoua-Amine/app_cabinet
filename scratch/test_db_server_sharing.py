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

print("=== REAL BEHAVIORAL MULTI-MACHINE NETWORK DATABASE SHARING TEST ===")

# Create a test DB path
test_db_path = BASE_DIR / "scratch" / "test_shared_reception.db"
if test_db_path.exists():
    test_db_path.unlink()

# Set test DB in reception module
reception.DB_PATH = test_db_path
reception.init_db()

# Start DatabaseServer in background thread on 127.0.0.1:9876 with secret token
shared_token = "test-office-token-12345"
server_port = 9876

server = db_server.DatabaseServer(
    db_path=test_db_path,
    token=shared_token,
    host="127.0.0.1",
    port=server_port
)

ok = server.start()
print(f"1. Started DatabaseServer on 127.0.0.1:{server_port} serving '{test_db_path.name}' -> Started: {ok}")

# Create Client 1 (Simulating Notary Laptop)
print("\n2. Connecting Laptop 1 (Notary RemoteConnection) over TCP...")
conn1 = db_client.RemoteConnection("127.0.0.1", server_port, shared_token)
cur1 = conn1.cursor()
print("   ✓ Laptop 1 connected cleanly!")

# Create Client 2 (Simulating Secretary Laptop)
print("\n3. Connecting Laptop 2 (Secretary RemoteConnection) over TCP...")
conn2 = db_client.RemoteConnection("127.0.0.1", server_port, shared_token)
cur2 = conn2.cursor()
print("   ✓ Laptop 2 connected cleanly!")

# Have Laptop 1 (Notary) execute SQL to insert a new client record over TCP and commit
print("\n4. Laptop 1 (Notary) creating a new client over TCP network connection...")
test_cid = "NET-888999"
cur1.execute("""
    INSERT INTO clients (client_id, nom, prenom, full_name, phone, created_at)
    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
""", (test_cid, "Ben Hadj", "Amine Network", "Amine Network Ben Hadj", "98123456"))

conn1.commit()
print(f"   ✓ Laptop 1 inserted and committed client '{test_cid}' into shared DB!")

# Have Laptop 2 (Secretary) query clients over TCP network connection
print("\n5. Laptop 2 (Secretary) querying client list over TCP network connection...")
cur2.execute("SELECT client_id, full_name, phone FROM clients WHERE client_id=?", (test_cid,))
rows = [dict(r) for r in cur2.fetchall()]
print(f"   ✓ Laptop 2 returned {len(rows)} matching rows:")
for r in rows:
    print(f"     - Client ID: {r['client_id']} | Name: {r['full_name']} | Phone: {r['phone']}")

assert len(rows) == 1, "Laptop 2 MUST see the client inserted by Laptop 1!"
assert rows[0]['client_id'] == test_cid, "Client ID must match!"
print("\n[PASS] Real-time TCP Network Data Sharing Verified 100% Success!")

# Cleanup
conn1.close()
conn2.close()
server.stop()
print("=== MULTI-MACHINE REAL-TIME DB SHARING TEST COMPLETED SUCCESSFULLY ===")
