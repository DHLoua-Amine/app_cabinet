import os
import sys
import sqlite3
import hashlib
import glob
import ast
import re
from pathlib import Path

# Force stdout to utf-8 if possible
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"C:\Users\amin\Desktop\zarai1_pyside")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))

def run_diagnostics():
    print("=================================================================")
    print("           APPLICATION FULL DIAGNOSTIC & AUDIT SUITE             ")
    print("=================================================================")

    # 1. DATABASE CHECKSUM & INTEGRITY
    db_path = BASE_DIR / "database.db"
    print("\n--- 1. DATABASE CHECKSUM & INTEGRITY ---")
    if db_path.exists():
        stat = db_path.stat()
        with open(db_path, "rb") as f:
            md5_val = hashlib.md5(f.read()).hexdigest()
        print(f"Path: {db_path}")
        print(f"Size: {stat.st_size} bytes")
        print(f"MD5 Checksum: {md5_val}")
        print(f"Last Modified: {stat.st_mtime}")

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"Total Tables: {len(tables)}")
        for t in sorted(tables):
            try:
                cnt = cur.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                print(f"  - Table {t}: {cnt} rows")
            except Exception as e:
                print(f"  - Table {t}: ERROR ({e})")
        conn.close()

    # 2. PYTHON AST & SYNTAX HEALTH
    print("\n--- 2. PYTHON CODEBASE AST & SYNTAX AUDIT ---")
    py_files = [p for p in glob.glob(str(BASE_DIR / "**" / "*.py"), recursive=True) if ".venv" not in p]
    syntax_errors = []
    for pf in py_files:
        try:
            with open(pf, "r", encoding="utf-8") as s:
                ast.parse(s.read())
        except Exception as e:
            syntax_errors.append((pf, str(e)))
    print(f"Total Python Files Audited: {len(py_files)}")
    print(f"Syntax Errors Found: {len(syntax_errors)}")
    for pf, err in syntax_errors:
        print(f"  - {pf}: {err}")

    # 3. EXCEPTION HANDLING CENSUS
    print("\n--- 3. EXCEPTION HANDLING CENSUS ---")
    bare_excepts = []
    broad_excepts = []
    silent_passes = []

    for pf in py_files:
        rel_p = os.path.relpath(pf, BASE_DIR)
        with open(pf, "r", encoding="utf-8", errors="ignore") as s:
            lines = s.readlines()

        for idx, line in enumerate(lines, 1):
            if re.search(r"^\s*except\s*:", line):
                bare_excepts.append((rel_p, idx, line.strip()))
            elif re.search(r"^\s*except\s+Exception\s*:", line):
                broad_excepts.append((rel_p, idx, line.strip()))
                if idx < len(lines) and re.search(r"^\s*pass\s*$", lines[idx]):
                    silent_passes.append((rel_p, idx + 1, "except Exception: pass"))

    print(f"Bare Excepts (`except:`): {len(bare_excepts)}")
    print(f"Broad Excepts (`except Exception:`): {len(broad_excepts)}")
    print(f"Silent Passes (`except Exception: pass`): {len(silent_passes)}")

    # 4. ALWAYS TRUE SUCCESS FUNCTIONS SCAN
    print("\n--- 4. ALWAYS-TRUE SUCCESS FUNCTIONS SCAN ---")
    always_true_candidates = []
    for pf in py_files:
        rel_p = os.path.relpath(pf, BASE_DIR)
        with open(pf, "r", encoding="utf-8", errors="ignore") as s:
            content = s.read()
            # Find def functions that return True unconditionally without checking cursor.rowcount or raises
            funcs = re.findall(r'def\s+([a-zA-Z0-9_]+)\s*\(.*?\)\s*->\s*bool:(.*?)(?=def|\Z)', content, re.DOTALL)
            for fname, fbody in funcs:
                if "return True" in fbody and "return False" not in fbody and "try:" not in fbody:
                    always_true_candidates.append((rel_p, fname))

    print(f"Always-True Function Candidates (Without Fallback False): {len(always_true_candidates)}")
    for p, fn in always_true_candidates:
        print(f"  - {p}: {fn}()")

    # 5. SQL INJECTION SURFACE SCAN
    print("\n--- 5. SQL INJECTION SURFACE CHECK ---")
    sqli_sites = []
    for pf in py_files:
        rel_p = os.path.relpath(pf, BASE_DIR)
        with open(pf, "r", encoding="utf-8", errors="ignore") as s:
            for line_no, line in enumerate(s.readlines(), 1):
                if re.search(r"cursor\.execute\s*\(\s*f[\"'].*(SELECT|INSERT|UPDATE|DELETE)", line, re.IGNORECASE):
                    sqli_sites.append((rel_p, line_no, line.strip()))

    print(f"Formatted f-string SQL Execution Sites: {len(sqli_sites)}")
    for p, l, text in sqli_sites:
        print(f"  - {p}:{l} -> {text}")

    # 6. ID GENERATION SCHEMES UNBOUNDED CHECK
    print("\n--- 6. ID GENERATION UNBOUNDED SCHEMES SCAN ---")
    id_gen_funcs = []
    for pf in py_files:
        rel_p = os.path.relpath(pf, BASE_DIR)
        with open(pf, "r", encoding="utf-8", errors="ignore") as s:
            for line_no, line in enumerate(s.readlines(), 1):
                if ("def generate_" in line or "generate_client_id" in line or "generate_case_id" in line):
                    id_gen_funcs.append((rel_p, line_no, line.strip()))

    print(f"ID Generation Functions Found: {len(id_gen_funcs)}")
    for p, l, text in id_gen_funcs:
        print(f"  - {p}:{l} -> {text}")

    # 7. UNTRANSLATED STRING CANDIDATES
    print("\n--- 7. UNTRANSLATED UI STRING SCAN ---")
    untranslated = []
    for pf in py_files:
        if "ui" in pf:
            rel_p = os.path.relpath(pf, BASE_DIR)
            with open(pf, "r", encoding="utf-8", errors="ignore") as s:
                for line_no, line in enumerate(s.readlines(), 1):
                    if "QPushButton(" in line and '"' in line and not "_tr" in line and not "self.tr(" in line:
                        untranslated.append((rel_p, line_no, line.strip()))

    print(f"Hardcoded Untranslated QPushButton Labels: {len(untranslated)}")
    for p, l, text in untranslated[:15]:
        print(f"  - {p}:{l} -> {text}")

    print("=================================================================")
    print("               DIAGNOSTIC SUITE RUN COMPLETE                    ")
    print("=================================================================")

if __name__ == "__main__":
    run_diagnostics()
