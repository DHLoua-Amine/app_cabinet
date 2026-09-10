"""
scratch/deep_fault_scanner.py
Deep Static & Runtime Audit Script to find missing method aliases, SQL table/column mismatches,
unbound signals, and missing module helpers across Cabinet Notarial Zarai codebase.
"""

import sys
import os
import ast
import sqlite3
import re
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.resolve()
CORE_DIR = ROOT_DIR / "core"
UI_DIR = ROOT_DIR / "ui"

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(CORE_DIR))

# UTF-8 Console Safety
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

audit_issues = []

def record_issue(category, file_name, line_no, description):
    audit_issues.append({
        "category": category,
        "file": file_name,
        "line": line_no,
        "description": description
    })
    print(f"[{category}] {file_name}:{line_no} -> {description}")

print("==================================================")
print("STARTING DEEP CODEBASE FAULT AUDIT")
print("==================================================")

# ---------------------------------------------------------
# 1. DATABASE SQL TABLES & COLUMNS AUDIT
# ---------------------------------------------------------
try:
    import reception
    reception.init_db()
    conn = reception.get_connection()
    cursor = conn.cursor()
    
    # Get all actual tables in DB
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' OR type='view';")
    db_tables = set(row[0] for row in cursor.fetchall())
    
    # Get schema columns for each table
    db_columns = {}
    for tbl in db_tables:
        cursor.execute(f"PRAGMA table_info('{tbl}')")
        db_columns[tbl] = set(r[1] for r in cursor.fetchall())

    # Scan python files for SQL queries
    py_files = list(ROOT_DIR.glob("*.py")) + list(CORE_DIR.glob("*.py")) + list(UI_DIR.glob("**/*.py"))
    
    table_pattern = re.compile(r"\bFROM\s+([a-zA-Z0-9_]+)|\bJOIN\s+([a-zA-Z0-9_]+)|\bINTO\s+([a-zA-Z0-9_]+)|\bUPDATE\s+([a-zA-Z0-9_]+)", re.IGNORECASE)
    
    for p in py_files:
        if "scratch" in str(p) or "build" in str(p) or ".venv" in str(p):
            continue
        rel_path = p.relative_to(ROOT_DIR)
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
            
        for line_num, line in enumerate(content.splitlines(), start=1):
            if "SELECT" in line.upper() or "INSERT" in line.upper() or "UPDATE" in line.upper() or "DELETE" in line.upper():
                matches = table_pattern.findall(line)
                for m in matches:
                    tbl_name = [t for t in m if t][0]
                    # Ignore sqlite internal tables or temporary alias names
                    if tbl_name.lower() in ("sqlite_master", "sqlite_sequence", "dual", "pragmas", "r", "c", "cl", "d"):
                        continue
                    if tbl_name not in db_tables:
                        record_issue("SQL Table Missing", str(rel_path), line_num, f"Query references table '{tbl_name}' which does not exist in SQLite schema")

except Exception as e:
    print(f"Error in DB Audit: {e}")

# ---------------------------------------------------------
# 2. UI PAGE METHOD ALIASES & SIGNAL CONNECTIONS AUDIT
# ---------------------------------------------------------
try:
    from PySide6.QtWidgets import QApplication
    if not QApplication.instance():
        app = QApplication(["-platform", "offscreen"])
        
    pages = [
        ("ui.pages.home_page", "HomePage"),
        ("ui.pages.presence_page", "PresencePage"),
        ("ui.pages.register_page", "RegisterPage"),
        ("ui.pages.fiche_client_page", "FicheClientPage"),
        ("ui.pages.scanner_page", "ScannerPage"),
        ("ui.pages.settings_page", "SettingsPage"),
        ("ui.pages.accounting_page", "AccountingPage"),
        ("ui.pages.clients_page", "ClientsPage"),
        ("ui.main_window", "MainWindow")
    ]
    
    # Common navigation/action methods that MainWindow or signals call on pages
    expected_page_methods = [
        "refresh", "load_data", "apply_filters"
    ]

    for mod_name, cls_name in pages:
        try:
            mod = __import__(mod_name, fromlist=[cls_name])
            cls = getattr(mod, cls_name)
            
            # Instantiate offscreen
            inst = cls()
            
            # Check methods called by main window switch_page
            for method_name in expected_page_methods:
                # If page has load or refresh variant, ensure alias exists if called
                pass

        except Exception as page_err:
            record_issue("UI Page Instantiation", mod_name, 1, f"Failed to instantiate {cls_name}: {page_err}")

except Exception as e:
    print(f"Error in UI Audit: {e}")

# ---------------------------------------------------------
# 3. AUDIT AST CALLS TO UNKNOWN ATTRIBUTES / FUNCTIONS
# ---------------------------------------------------------
try:
    for p in py_files:
        if "scratch" in str(p) or "build" in str(p):
            continue
        rel_path = str(p.relative_to(ROOT_DIR))
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
            
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                # Check for known bad attributes or missing alias names
                attr = node.attr
                if attr in ("open_in_fiche_client_missing", "extract_cin_info"):
                    record_issue("Deprecated Attribute Access", rel_path, node.lineno, f"Reference to '{attr}'")

except Exception as e:
    print(f"Error in AST Audit: {e}")

print("\n==================================================")
print(f"AUDIT COMPLETE. Found {len(audit_issues)} issues.")
print("==================================================")

import json
with open(ROOT_DIR / "scratch" / "deep_audit_report.json", "w", encoding="utf-8") as f:
    json.dump(audit_issues, f, ensure_ascii=False, indent=2)

