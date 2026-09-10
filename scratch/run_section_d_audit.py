import sys
import os
import time
import ast
import json
import sqlite3
import hashlib
from pathlib import Path
from PySide6.QtWidgets import QApplication

workspace_dir = Path(__file__).resolve().parent.parent
core_dir = workspace_dir / "core"

for p in [str(workspace_dir), str(core_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.chdir(workspace_dir)

DB_PATH = os.path.expanduser('~') + r'\AppData\Local\CabinetNotarialZarai\data\reception.db'
initial_checksum = hashlib.sha256(open(DB_PATH, 'rb').read()).hexdigest()

print("=== STARTING SECTION D: CODE STRUCTURE, QUALITY & PERFORMANCE AUDIT ===")

# --- 1. STARTUP TIMING BENCHMARK (COLD vs WARM) ---
t0 = time.perf_counter()
import auth
import config
import reception
import permissions
t_imports = (time.perf_counter() - t0) * 1000

t0 = time.perf_counter()
reception.init_db()
t_init_db = (time.perf_counter() - t0) * 1000

app = QApplication.instance()
if not app:
    app = QApplication([])

t0 = time.perf_counter()
from ui.main_window import MainWindow
win = MainWindow()
t_win_build = (time.perf_counter() - t0) * 1000

total_startup_ms = t_imports + t_init_db + t_win_build
print(f"Startup Breakdown:")
print(f"  Imports (core modules): {t_imports:.2f} ms")
print(f"  DB Init:                {t_init_db:.2f} ms")
print(f"  MainWindow Construction:{t_win_build:.2f} ms")
print(f"  Total Startup Time:     {total_startup_ms:.2f} ms ({total_startup_ms/1000:.2f} s)")

win.close()

# --- 2. AST DEAD CODE AUDIT ---
py_files = list(workspace_dir.glob("core/**/*.py")) + list(workspace_dir.glob("ui/**/*.py"))

defined_funcs = {}
defined_classes = {}
func_calls = set()
class_uses = set()

for py_file in py_files:
    rel_path = str(py_file.relative_to(workspace_dir))
    try:
        tree = ast.parse(py_file.read_text(encoding='utf-8'), filename=rel_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not node.name.startswith("_"):
                    defined_funcs[node.name] = f"{rel_path}:{node.lineno}"
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    defined_classes[node.name] = f"{rel_path}:{node.lineno}"
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    func_calls.add(node.func.attr)
            elif isinstance(node, ast.Name):
                class_uses.add(node.id)
    except Exception as e:
        print(f"Error reading {rel_path}: {e}")

uncalled_funcs = {k: v for k, v in defined_funcs.items() if k not in func_calls and k not in ["run", "run_app", "main", "init_ui", "load_data", "update_language", "eventFilter", "closeEvent", "showEvent", "hideEvent"]}
unused_classes = {k: v for k, v in defined_classes.items() if k not in class_uses}

print(f"\nPotential Unreferenced Functions: {len(uncalled_funcs)}")
for k, v in list(uncalled_funcs.items())[:15]:
    print(f"  {k:30s} -> {v}")

print(f"\nPotential Unused Classes: {len(unused_classes)}")
for k, v in list(unused_classes.items())[:10]:
    print(f"  {k:30s} -> {v}")

# --- 3. SYNTHETIC LOAD TEST ON TEMPORARY IN-MEMORY / SCRATCH DB ---
print("\n--- RUNNING SYNTHETIC LOAD TEST (10,000 Clients, 20,000 Dossiers, 50,000 Check-ins) ---")

# Create temporary benchmark DB in memory so production DB is untouched
test_conn = sqlite3.connect(":memory:")
test_conn.row_factory = sqlite3.Row

# Build schema
test_conn.executescript("""
CREATE TABLE clients (
    client_id TEXT PRIMARY KEY,
    nom TEXT, prenom TEXT, full_name TEXT, phone TEXT, cin_number TEXT, created_at TEXT
);
CREATE TABLE cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number TEXT, title TEXT, client_id TEXT, case_type TEXT, status TEXT, created_at TEXT
);
CREATE TABLE check_ins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT, window_number TEXT, timestamp TEXT, confidence_score REAL, status TEXT
);
CREATE INDEX idx_clients_cin ON clients(cin_number);
CREATE INDEX idx_clients_name ON clients(full_name);
CREATE INDEX idx_cases_client ON cases(client_id);
CREATE INDEX idx_checkins_timestamp ON check_ins(timestamp);
""")

print("Inserting 10,000 synthetic clients...")
clients_data = [(f"CLI-LOAD-{i:05d}", f"Nom_{i}", f"Prenom_{i}", f"Prenom_{i} Nom_{i}", f"98{i:06d}", f"123{i:05d}", "2026-01-01 10:00:00") for i in range(10000)]
test_conn.executemany("INSERT INTO clients VALUES (?, ?, ?, ?, ?, ?, ?)", clients_data)

print("Inserting 20,000 synthetic dossiers...")
cases_data = [(f"DOS-LOAD-{i:05d}", f"Affaire #{i}", f"CLI-LOAD-{(i%10000):05d}", "Vente", "En cours", "2026-02-01 10:00:00") for i in range(20000)]
test_conn.executemany("INSERT INTO cases (case_number, title, client_id, case_type, status, created_at) VALUES (?, ?, ?, ?, ?, ?)", cases_data)

print("Inserting 50,000 synthetic check-ins...")
checkins_data = [(f"CLI-LOAD-{(i%10000):05d}", "Guichet 1", "2026-08-01 11:00:00", 0.95, "Arrivé") for i in range(50000)]
test_conn.executemany("INSERT INTO check_ins (client_id, window_number, timestamp, confidence_score, status) VALUES (?, ?, ?, ?, ?)", checkins_data)
test_conn.commit()

# Measure queries on 10k/20k/50k dataset
t0 = time.perf_counter()
cur = test_conn.cursor()
cur.execute("SELECT * FROM clients WHERE full_name LIKE '%Nom_5000%'")
r_clients = cur.fetchall()
t_search_client = (time.perf_counter() - t0) * 1000

t0 = time.perf_counter()
cur.execute("SELECT c.*, cl.full_name FROM cases c LEFT JOIN clients cl ON c.client_id = cl.client_id ORDER BY c.id DESC LIMIT 200")
r_cases = cur.fetchall()
t_search_cases = (time.perf_counter() - t0) * 1000

t0 = time.perf_counter()
cur.execute("SELECT ch.*, cl.full_name FROM check_ins ch LEFT JOIN clients cl ON ch.client_id = cl.client_id ORDER BY ch.timestamp DESC LIMIT 200")
r_checkins = cur.fetchall()
t_search_checkins = (time.perf_counter() - t0) * 1000

print(f"Query Results on Heavy Dataset:")
print(f"  Search client by name (10k rows):       {t_search_client:.2f} ms ({len(r_clients)} matches)")
print(f"  Load recent dossiers (20k rows + JOIN): {t_search_cases:.2f} ms ({len(r_cases)} rows returned)")
print(f"  Load recent check-ins (50k rows + JOIN):{t_search_checkins:.2f} ms ({len(r_checkins)} rows returned)")

test_conn.close()

final_checksum = hashlib.sha256(open(DB_PATH, 'rb').read()).hexdigest()
print(f"\n=== DB CHECKSUM VERIFICATION ===")
print(f"Initial: {initial_checksum}")
print(f"Final:   {final_checksum}")
print(f"DB Unchanged: {initial_checksum == final_checksum}")

section_d_results = {
    "startup": {
        "imports_ms": t_imports,
        "init_db_ms": t_init_db,
        "win_build_ms": t_win_build,
        "total_ms": total_startup_ms
    },
    "uncalled_funcs": uncalled_funcs,
    "unused_classes": unused_classes,
    "load_test": {
        "search_client_ms": t_search_client,
        "search_cases_ms": t_search_cases,
        "search_checkins_ms": t_search_checkins
    }
}

with open(workspace_dir / "scratch" / "section_d_results.json", "w") as f:
    json.dump(section_d_results, f, indent=2)

print("\n=== SECTION D AUDIT COMPLETE ===")
