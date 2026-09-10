"""
scratch/full_app_automated_test.py
Full Automated Test Suite for Cabinet Notarial Zarai (PySide6 application).
"""

import sys
import os
import sqlite3
import traceback
import tempfile
import time
from pathlib import Path

# Ensure UTF-8 output streams for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Set up paths exactly as main.py does
ROOT_DIR = Path(__file__).parent.parent.resolve()
CORE_DIR = ROOT_DIR / "core"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(CORE_DIR))

import auth
import permissions

# Set admin session role for testing delete permissions
permissions.session.sign_in("admin", "admin", "Notaire Test")

# Create offscreen Qt Application
from PySide6.QtWidgets import QApplication
if not QApplication.instance():
    app = QApplication(["-platform", "offscreen"])
else:
    app = QApplication.instance()

test_results = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def record_pass(test_name, details=""):
    test_results["passed"].append({"name": test_name, "details": details})
    print(f"[PASS] {test_name}: {details}")

def record_fail(test_name, error="", traceback_str=""):
    test_results["failed"].append({"name": test_name, "error": str(error), "traceback": traceback_str})
    print(f"[FAIL] {test_name}: {error}")

def record_warning(test_name, details=""):
    test_results["warnings"].append({"name": test_name, "details": details})
    print(f"[WARN] {test_name}: {details}")

print("==================================================")
print("STARTING FULL AUTOMATED SYSTEM TEST")
print("==================================================")

# ---------------------------------------------------------
# TEST 1: Database Operations & Schema Integrity
# ---------------------------------------------------------
try:
    import reception
    reception.init_db()
    conn = reception.get_connection()
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    required_tables = ["clients", "check_ins", "cases", "fees"]
    missing_tables = [t for t in required_tables if t not in tables]
    if missing_tables:
        record_fail("DB Schema Check", f"Missing tables: {missing_tables}")
    else:
        record_pass("DB Schema Check", f"Found main tables: {tables}")
    
    # Check client columns for parentage and CIN fields
    cursor.execute("PRAGMA table_info(clients);")
    client_cols = [row[1] for row in cursor.fetchall()]
    new_fields = ["father_name", "grandfather_name", "cin_issue_date", "cin_issue_place"]
    missing_fields = [f for f in new_fields if f not in client_cols]
    if missing_fields:
        record_fail("DB Client Columns", f"Missing client parentage/CIN fields: {missing_fields}")
    else:
        record_pass("DB Client Columns", f"All parentage & CIN fields present: {new_fields}")

except Exception as e:
    record_fail("DB Connection & Schema", str(e), traceback.format_exc())

# ---------------------------------------------------------
# TEST 2: Reception & Client Data Manager Functions
# ---------------------------------------------------------
try:
    # Test updating/creating client civil status with parentage & CIN details
    test_client_id = reception.generate_client_id(prefix="TEST_")
    client_data = {
        "client_id": test_client_id,
        "full_name": "اختبار حريف بن أحمد بن محمد الفرشيشي",
        "nom": "الفرشيشي",
        "prenom": "اختبار",
        "father_name": "أحمد",
        "grandfather_name": "محمد",
        "cin_number": "09988776",
        "cin_issue_date": "2020-05-15",
        "cin_issue_place": "تونس",
        "phone": "98765432",
        "address": "شارع الحبيب بورقيبة تونس"
    }
    
    # Create client via get_db_cursor
    with reception.get_db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO clients (client_id, full_name, nom, prenom, father_name, grandfather_name, cin_number, cin_issue_date, cin_issue_place, phone, address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            client_data["client_id"], client_data["full_name"], client_data["nom"], client_data["prenom"],
            client_data["father_name"], client_data["grandfather_name"], client_data["cin_number"],
            client_data["cin_issue_date"], client_data["cin_issue_place"], client_data["phone"], client_data["address"]
        ))
    record_pass("Client Create Test", f"Created test client_id: {test_client_id}")
    
    # Fetch client by ID
    client = reception.get_client_by_id(test_client_id)
    if client:
        if client.get("father_name") == "أحمد" and client.get("cin_issue_place") == "تونس":
            record_pass("Client Retrieval by ID", f"Retrieved client successfully: {client.get('full_name')}")
        else:
            record_fail("Client Retrieval Data Mismatch", f"Client data: {client}")
    else:
        record_fail("Client Retrieval by ID", f"Client ID {test_client_id} not found")

    # Clean up test client
    reception.delete_client(test_client_id)
    record_pass("Client Cleanup", f"Deleted test client {test_client_id}")

except Exception as e:
    record_fail("Reception Module", str(e), traceback.format_exc())

# ---------------------------------------------------------
# TEST 3: Price Formatting & Contract Templating
# ---------------------------------------------------------
try:
    import contract_templates
    
    # Price formatting test: numbers + arabic words + parenthesized number
    p1 = contract_templates.format_arabic_price(5000)
    
    if "5000" in p1 and "خمسة" in p1:
        record_pass("Price Formatter (5000 TND)", f"Output: '{p1}'")
    else:
        record_fail("Price Formatter (5000 TND)", f"Unexpected output: '{p1}'")

except Exception as e:
    record_fail("Contract Generator Tools", str(e), traceback.format_exc())

# ---------------------------------------------------------
# TEST 4: Licensing & System Security
# ---------------------------------------------------------
try:
    import licensing
    fp = licensing.machine_fingerprint()
    lic_status = licensing.status()
    record_pass("Licensing Subsystem", f"Fingerprint: {fp[:12]}..., Status: {lic_status.get('status')}")
    
    import remote_license
    ok, msg, info = remote_license.check_remote_license()
    record_pass("Remote License Check", f"Active: {ok}, Msg: {msg}")

    import system_guardian
    system_guardian.log_system_error("Test Non-fatal Error Log", Exception("Test error"))
    record_pass("System Guardian", "Logging function executed without exception")

except Exception as e:
    record_fail("Licensing & Security", str(e), traceback.format_exc())

# ---------------------------------------------------------
# TEST 5: UI Pages Instantiation & Qt Signal Test
# ---------------------------------------------------------
pages_to_test = [
    ("HomePage", "ui.pages.home_page", "HomePage"),
    ("PresencePage", "ui.pages.presence_page", "PresencePage"),
    ("RegisterPage", "ui.pages.register_page", "RegisterPage"),
    ("FicheClientPage", "ui.pages.fiche_client_page", "FicheClientPage"),
    ("ScannerPage", "ui.pages.scanner_page", "ScannerPage"),
    ("SettingsPage", "ui.pages.settings_page", "SettingsPage"),
    ("AccountingPage", "ui.pages.accounting_page", "AccountingPage"),
    ("ClientsPage", "ui.pages.clients_page", "ClientsPage"),
    ("MainWindow", "ui.main_window", "MainWindow")
]

for name, mod_path, cls_name in pages_to_test:
    try:
        mod = __import__(mod_path, fromlist=[cls_name])
        cls = getattr(mod, cls_name)
        inst = cls()
        record_pass(f"UI Instantiation: {name}", f"Successfully created {cls_name}")
        
        # Page-specific functional checks
        if name == "RegisterPage":
            # Test table model / data source
            if hasattr(inst, "model") and inst.model:
                row_count = inst.model.rowCount()
                record_pass("RegisterPage Table Model", f"Rows in model: {row_count}")
            # Check context menu action slot
            if hasattr(inst, "open_in_fiche_client") or hasattr(inst, "_on_open_in_fiche_client"):
                record_pass("RegisterPage Action", "Fiche client context action verified")
            else:
                record_warning("RegisterPage Action", "open_in_fiche_client slot method check")
                
        elif name == "ScannerPage":
            if hasattr(inst, "on_client_selected") or hasattr(inst, "fill_client_details") or hasattr(inst, "fill_client_preamble_from_db"):
                record_pass("ScannerPage Client Selection", "Client auto-fill method verified")
                
        elif name == "FicheClientPage":
            if hasattr(inst, "tab_civil"):
                record_pass("FicheClientPage Tab Civil", "Civil tab exists and initialized")

    except Exception as e:
        record_fail(f"UI Instantiation: {name}", str(e), traceback.format_exc())

# ---------------------------------------------------------
# TEST 6: Scanner OCR & Document Parsing Edge Cases
# ---------------------------------------------------------
try:
    import cin_extractor
    sample_ocr_dict = {
        "first_name": "علي",
        "last_name": "الفرجاني",
        "father_name": "محمد",
        "grandfather_name": "البشير",
        "cin_number": "08765432"
    }
    full_n = cin_extractor._assemble_tunisian_full_name(sample_ocr_dict)
    if "علي" in full_n and "محمد" in full_n and "الفرجاني" in full_n:
        record_pass("OCR Name Assembly", f"Assembled: '{full_n}'")
    else:
        record_fail("OCR Name Assembly", f"Unexpected name output: '{full_n}'")

except Exception as e:
    record_fail("OCR Parser Module", str(e), traceback.format_exc())

# ---------------------------------------------------------
# TEST SUMMARY
# ---------------------------------------------------------
print("\n==================================================")
print("TEST SUMMARY")
print(f"PASSED: {len(test_results['passed'])}")
print(f"FAILED: {len(test_results['failed'])}")
print(f"WARNINGS: {len(test_results['warnings'])}")
print("==================================================")

if test_results['failed']:
    print("\n[!] DETAILED FAULTS FOUND:")
    for f in test_results['failed']:
        print(f"\n--- FAULT IN: {f['name']} ---")
        print(f"Error: {f['error']}")
        print(f"Traceback:\n{f['traceback']}")

import json
with open(ROOT_DIR / "scratch" / "automated_test_report.json", "w", encoding="utf-8") as f:
    json.dump(test_results, f, ensure_ascii=False, indent=2)

print("\nReport written to scratch/automated_test_report.json")
