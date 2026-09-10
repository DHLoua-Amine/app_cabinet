"""
scratch/deep_fault_scanner_v2.py
AST-based SQL & UI call audit for Cabinet Notarial Zarai.
Parses exact Python code ASTs to inspect real SQL string literals and UI method bindings.
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
print("STARTING AST PRECISE FAULT AUDIT")
print("==================================================")

# 1. Initialize DB to get actual schema tables & columns
try:
    import reception
    reception.init_db()
    conn = reception.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' OR type='view';")
    db_tables = set(row[0].lower() for row in cursor.fetchall())
    
    db_columns = {}
    for tbl in db_tables:
        try:
            cursor.execute(f"PRAGMA table_info('{tbl}')")
            db_columns[tbl] = set(r[1].lower() for r in cursor.fetchall())
        except Exception:
            pass

except Exception as e:
    print(f"DB Init Error: {e}")
    db_tables = set()
    db_columns = {}

# SQL FROM/JOIN/INTO/UPDATE regex for real SQL strings
table_regex = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z0-9_]+)", re.IGNORECASE)

py_files = list(ROOT_DIR.glob("*.py")) + list(CORE_DIR.glob("*.py")) + list(UI_DIR.glob("**/*.py"))

for p in py_files:
    if "scratch" in str(p) or "build" in str(p) or ".venv" in str(p):
        continue
    rel_path = str(p.relative_to(ROOT_DIR))
    
    try:
        source = p.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(p))
    except Exception:
        continue

    # Inspect AST Nodes
    for node in ast.walk(tree):
        # Look for cursor.execute("SQL...") or query strings
        if isinstance(node, ast.Call):
            # Check if function call is execute / executemany
            func_name = ""
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id
                
            if func_name in ("execute", "executemany") and node.args:
                arg0 = node.args[0]
                sql_str = ""
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    sql_str = arg0.value
                elif isinstance(arg0, ast.JoinedStr): # f-strings
                    for val in arg0.values:
                        if isinstance(val, ast.Constant) and isinstance(val.value, str):
                            sql_str += val.value

                if sql_str:
                    matches = table_regex.findall(sql_str)
                    for tbl in matches:
                        tbl_l = tbl.lower()
                        if tbl_l in ("sqlite_master", "sqlite_sequence", "dual", "pragmas", "r", "c", "cl", "d"):
                            continue
                        if db_tables and tbl_l not in db_tables:
                            record_issue("SQL Table Missing", rel_path, node.lineno, f"Query '{sql_str[:40]}...' targets table '{tbl}' not in DB schema")

print("\n==================================================")
print(f"AST AUDIT COMPLETE. Found {len(audit_issues)} real issues.")
print("==================================================")
