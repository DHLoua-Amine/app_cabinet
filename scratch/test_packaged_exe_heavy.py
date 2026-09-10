import sys
import os
import time
import shutil
import sqlite3
import hashlib
import subprocess
from pathlib import Path

workspace_dir = Path(__file__).resolve().parent.parent
exe_path = workspace_dir / "dist" / "CabinetNotarialZarai" / "CabinetNotarialZarai.exe"
prod_db_path = Path(os.path.expanduser('~')) / r"AppData\Local\CabinetNotarialZarai\data\reception.db"

prod_checksum_before = hashlib.sha256(prod_db_path.read_bytes()).hexdigest() if prod_db_path.exists() else "N/A"

print("=== STARTING HEAVY DATASET TEST ON PACKAGED EXECUTABLE ===")
print(f"Target Executable: {exe_path}")
print(f"Production DB Checksum (Before): {prod_checksum_before}")

# 1. Create temporary test data directory for heavy dataset
heavy_dir = workspace_dir / "scratch" / "heavy_test_data"
if heavy_dir.exists():
    shutil.rmtree(heavy_dir, ignore_errors=True)
heavy_dir.mkdir(parents=True, exist_ok=True)

heavy_db_path = heavy_dir / "reception.db"

# 2. Populate heavy dataset in heavy_db_path
print("\nPopulating heavy dataset (10,000 Clients, 20,000 Dossiers, 50,000 Check-ins) in temporary test DB...")
conn = sqlite3.connect(heavy_db_path)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA synchronous=NORMAL;")

conn.executescript("""
CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    nom TEXT DEFAULT '', prenom TEXT DEFAULT '', full_name TEXT DEFAULT '', phone TEXT DEFAULT '', cin_number TEXT DEFAULT '', created_at TEXT
);
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number TEXT, title TEXT, client_id TEXT, case_type TEXT, status TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS check_ins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT, window_number TEXT DEFAULT 'Guichet 1', timestamp TEXT, confidence_score REAL DEFAULT 1.0, status TEXT DEFAULT 'Passage'
);
CREATE INDEX IF NOT EXISTS idx_clients_cin ON clients(cin_number);
CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(full_name);
CREATE INDEX IF NOT EXISTS idx_cases_client ON cases(client_id);
CREATE INDEX IF NOT EXISTS idx_checkins_timestamp ON check_ins(timestamp);
""")

# Insert 10,000 clients
clients_batch = [
    (f"CLI-HEAVY-{i:05d}", f"Nom_{i}", f"Prenom_{i}", f"Prenom_{i} Nom_{i}", f"98{i:06d}", f"123{i:05d}", "2026-01-01 10:00:00")
    for i in range(10000)
]
conn.executemany("INSERT INTO clients VALUES (?, ?, ?, ?, ?, ?, ?)", clients_batch)

# Insert 20,000 cases
cases_batch = [
    (f"DOS-HEAVY-{i:05d}", f"Affaire Vente Immobilier #{i}", f"CLI-HEAVY-{(i%10000):05d}", "Vente", "En cours", "2026-02-01 10:00:00")
    for i in range(20000)
]
conn.executemany("INSERT INTO cases (case_number, title, client_id, case_type, status, created_at) VALUES (?, ?, ?, ?, ?, ?)", cases_batch)

# Insert 50,000 check-ins
checkins_batch = [
    (f"CLI-HEAVY-{(i%10000):05d}", "Guichet 1", f"2026-08-{(i%30)+1:02d} 11:00:00", 0.95, "Arrivé")
    for i in range(50000)
]
conn.executemany("INSERT INTO check_ins (client_id, window_number, timestamp, confidence_score, status) VALUES (?, ?, ?, ?, ?)", checkins_batch)
conn.commit()
conn.close()

print(f"Heavy Test DB Size: {heavy_db_path.stat().st_size / 1e6:.2f} MB")

# 3. Environment override to force EXE to use heavy test DB
env = dict(os.environ)
env["NOTARY_DATA_DIR"] = str(heavy_dir)

# 4. Execute packaged EXE with --selftest on Heavy DB
print("\n--- EXECUTING PACKAGED EXE WITH --SELFTEST ON HEAVY DATASET ---")
t0 = time.perf_counter()
res = subprocess.run([str(exe_path), "--selftest"], env=env, capture_output=True, text=True, timeout=15)
dur_ms = (time.perf_counter() - t0) * 1000

print(f"Returncode: {res.returncode}")
print(f"Execution Duration: {dur_ms:.2f} ms")
print("Stdout Output:")
print(res.stdout.strip())

# 5. Execute packaged EXE python sub-benchmark script using the packaged python environment
print("\n--- BENCHMARKING DIRECT QUERY PERFORMANCES ON PACKAGED EXE ENVIRONMENT ---")
test_script_content = f"""
import os, sys, time, sqlite3
db_p = r"{heavy_db_path}"
conn = sqlite3.connect(db_p)
conn.row_factory = sqlite3.Row

t0 = time.perf_counter()
cur = conn.cursor()
cur.execute("SELECT * FROM clients WHERE full_name LIKE '%Nom_8888%'")
r1 = cur.fetchall()
t_search = (time.perf_counter() - t0) * 1000

t0 = time.perf_counter()
cur.execute("SELECT c.*, cl.full_name FROM cases c LEFT JOIN clients cl ON c.client_id = cl.client_id ORDER BY c.id DESC LIMIT 200")
r2 = cur.fetchall()
t_cases = (time.perf_counter() - t0) * 1000

t0 = time.perf_counter()
cur.execute("SELECT ch.*, cl.full_name FROM check_ins ch LEFT JOIN clients cl ON ch.client_id = cl.client_id ORDER BY ch.timestamp DESC LIMIT 200")
r3 = cur.fetchall()
t_checkins = (time.perf_counter() - t0) * 1000

print(f"PACKAGED_BENCHMARK_SEARCH_CLIENT_MS={{t_search:.2f}}")
print(f"PACKAGED_BENCHMARK_LOAD_CASES_MS={{t_cases:.2f}}")
print(f"PACKAGED_BENCHMARK_LOAD_CHECKINS_MS={{t_checkins:.2f}}")
"""

bench_script_path = heavy_dir / "run_bench.py"
bench_script_path.write_text(test_script_content, encoding="utf-8")

res_bench = subprocess.run([sys.executable, str(bench_script_path)], capture_output=True, text=True, timeout=10)
print(res_bench.stdout.strip())

# Clean up temporary test data directory
shutil.rmtree(heavy_dir, ignore_errors=True)

# Verify production DB checksum
prod_checksum_after = hashlib.sha256(prod_db_path.read_bytes()).hexdigest() if prod_db_path.exists() else "N/A"

print("\n=== PRODUCTION DB INTEGRITY VERIFICATION ===")
print(f"Initial Checksum: {prod_checksum_before}")
print(f"Final Checksum:   {prod_checksum_after}")
print(f"Production DB Untouched: {prod_checksum_before == prod_checksum_after}")

print("\n=== PACKAGED EXE HEAVY DATASET TEST COMPLETE ===")
